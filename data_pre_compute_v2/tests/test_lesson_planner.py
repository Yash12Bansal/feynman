"""LessonPlanner tests — doc 19 Phase C.

Strategy: monkeypatch `anthropic.AsyncAnthropic` with a fake whose
`messages.create()` returns canned responses (tool_use blocks containing
LessonPlan-shaped payloads). Cover the happy path, the validation-error
retry path, the no-tool-use-block path, and the final-failure path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_planner import (
    LessonPlanner,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_prompts import (
    LESSON_PLANNING_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Chapter, Topic


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _config() -> PipelineConfig:
    return PipelineConfig(
        llm=LLMConfig(api_key="test-key", model="claude-sonnet-4-test")
    )


def _chapter() -> Chapter:
    return Chapter(
        chapter_id="ch1",
        chapter_index=1,
        title="Chapter X",
        summary="s",
        page_start=1,
        page_end=10,
        topic_ids=["t1"],
    )


def _topic(topic_id: str, name: str) -> Topic:
    return Topic(
        topic_id=topic_id,
        chapter_id="ch1",
        section_number="1.1",
        within_chapter_order=1,
        topic_name=name,
        orig_book_content="raw text",
        our_understanding="understanding",
    )


def _lecture_plan(seq: list[str]) -> ChapterLecturePlan:
    return ChapterLecturePlan(
        chapter_id="ch1",
        chapter_title="Chapter X",
        chapter_arc="arc",
        opening_hook="hook",
        concept_sequence=seq,
        length_budget_seconds=600,
        closing_summary="close",
    )


# A valid LessonPlan payload — covers all required fields and validators.
# Mirrors `test_lesson_plan_models.py::test_lesson_plan_section_7_worked_example_validates`
# in shape (ball-in-moving-train, doc 19 §7).
_VALID_LESSON_PLAN_PAYLOAD = {
    "topic_id": "t1",
    "title": "Ball thrown in a moving train",
    "hook": {
        "type": "paradox",
        "text": (
            "Throw a ball straight up on a moving train and it lands right "
            "back in your hand — as if the train weren't moving. Someone on "
            "the platform swears the ball flew in a curve. Both are right."
        ),
    },
    "crucial_facts": ["horizontal velocity is conserved across the throw"],
    "diagrams": [
        {
            "diagram_id": "train-frame",
            "purpose": "Show the throw from two reference frames.",
            "presentation_mode": "build_up",
            "required_elements": [
                {
                    "element_id": "vertical-drop",
                    "role": "trajectory",
                    "description": "vertical drop in train frame",
                },
                {
                    "element_id": "parabola",
                    "role": "curve",
                    "description": "parabola in ground frame",
                },
            ],
        }
    ],
    "choreography": [
        {
            "narration": "Throw a ball straight up on a moving train.",
            "actions": ["focus", "trace"],
            "target_element_id": "vertical-drop",
            "target_diagram_id": "train-frame",
            "is_question": False,
            "is_payoff": False,
            "presses_crucial_fact": False,
        },
        {
            "narration": "If the ball isn't pushed forward, how does it keep up?",
            "actions": [],
            "target_element_id": None,
            "target_diagram_id": None,
            "is_question": True,
            "is_payoff": False,
            "presses_crucial_fact": False,
        },
        {
            "narration": "Because nothing took its forward speed away.",
            "actions": ["trace"],
            "target_element_id": "parabola",
            "target_diagram_id": "train-frame",
            "is_question": False,
            "is_payoff": True,
            "presses_crucial_fact": True,
        },
        {
            "narration": "Horizontal velocity stays with the ball through the throw.",
            "actions": [],
            "target_element_id": None,
            "target_diagram_id": None,
            "is_question": False,
            "is_payoff": False,
            "presses_crucial_fact": True,
        },
    ],
    "equations": [],
}


# A LessonPlan payload that will FAIL Pydantic validation — the hook text
# starts with "In this lecture", which is on the forbidden-openers list. The
# planner should catch the ValidationError and retry.
_INVALID_HOOK_PAYLOAD = {
    **_VALID_LESSON_PLAN_PAYLOAD,
    "hook": {
        "type": "fact",
        "text": "In this lecture we will study relative motion.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Fake Anthropic client harness
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _FakeBlock:
    """Mimics anthropic.types.ToolUseBlock shape."""

    type: str
    name: str
    input: Any


@dataclass
class _FakeResponse:
    content: list[_FakeBlock]


class _FakeMessages:
    def __init__(self, queue: list[_FakeResponse]) -> None:
        self._queue = queue
        self.create_call_count = 0

    async def create(self, **kwargs: Any) -> _FakeResponse:
        # Assertions: system prompt + tool wiring are what we expect.
        assert kwargs.get("system") == LESSON_PLANNING_SYSTEM_PROMPT
        tools = kwargs.get("tools", [])
        assert tools and tools[0]["name"] == "emit_lesson_plan"
        self.create_call_count += 1
        if not self._queue:
            raise RuntimeError("test ran out of canned Anthropic responses")
        return self._queue.pop(0)


class _FakeAnthropicClient:
    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key
        # `messages` is bound at class level by the test setup.
        self.messages = _CURRENT_FAKE_MESSAGES


# Module-level pointer so each `LessonPlanner._call_anthropic` invocation
# (which constructs a fresh AsyncAnthropic) shares the SAME response queue.
_CURRENT_FAKE_MESSAGES: _FakeMessages | None = None


def _install_fake(
    monkeypatch: pytest.MonkeyPatch, responses: list[_FakeResponse]
) -> _FakeMessages:
    global _CURRENT_FAKE_MESSAGES
    _CURRENT_FAKE_MESSAGES = _FakeMessages(responses)
    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.lesson_planner.anthropic.AsyncAnthropic",
        _FakeAnthropicClient,
    )
    return _CURRENT_FAKE_MESSAGES


def _tool_use_response(payload: dict) -> _FakeResponse:
    return _FakeResponse(
        content=[_FakeBlock(type="tool_use", name="emit_lesson_plan", input=payload)]
    )


def _empty_response() -> _FakeResponse:
    return _FakeResponse(content=[])


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lesson_planner_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """One valid LessonPlan returned for one topic — single Anthropic call."""
    messages = _install_fake(
        monkeypatch, [_tool_use_response(_VALID_LESSON_PLAN_PAYLOAD)]
    )

    planner = LessonPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    plans = result["ch1"]
    assert len(plans) == 1
    assert plans[0].topic_id == "t1"
    assert plans[0].title == "Ball thrown in a moving train"
    assert plans[0].hook.type.value == "paradox"
    assert messages.create_call_count == 1


@pytest.mark.asyncio
async def test_lesson_planner_retries_on_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call returns a plan with a forbidden hook; second call succeeds."""
    messages = _install_fake(
        monkeypatch,
        [
            _tool_use_response(_INVALID_HOOK_PAYLOAD),
            _tool_use_response(_VALID_LESSON_PLAN_PAYLOAD),
        ],
    )

    planner = LessonPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    plans = result["ch1"]
    assert len(plans) == 1
    assert plans[0].topic_id == "t1"
    assert messages.create_call_count == 2


@pytest.mark.asyncio
async def test_lesson_planner_gives_up_after_two_validation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two consecutive validation failures → no plan emitted for the topic."""
    messages = _install_fake(
        monkeypatch,
        [
            _tool_use_response(_INVALID_HOOK_PAYLOAD),
            _tool_use_response(_INVALID_HOOK_PAYLOAD),
        ],
    )

    planner = LessonPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    # No plan made it into the result.
    assert result["ch1"] == []
    # Both attempts were tried.
    assert messages.create_call_count == 2


@pytest.mark.asyncio
async def test_lesson_planner_handles_missing_tool_use_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response with no tool_use block triggers retry; second call succeeds."""
    messages = _install_fake(
        monkeypatch,
        [_empty_response(), _tool_use_response(_VALID_LESSON_PLAN_PAYLOAD)],
    )

    planner = LessonPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    assert len(result["ch1"]) == 1
    assert messages.create_call_count == 2


@pytest.mark.asyncio
async def test_lesson_planner_catches_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic API exception → fallback retry path; both fail → empty."""

    class _ExplodingMessages:
        def __init__(self) -> None:
            self.create_call_count = 0

        async def create(self, **kwargs: Any) -> Any:
            self.create_call_count += 1
            raise RuntimeError("simulated API failure")

    global _CURRENT_FAKE_MESSAGES
    exploding = _ExplodingMessages()
    _CURRENT_FAKE_MESSAGES = exploding  # type: ignore[assignment]
    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.lesson_planner.anthropic.AsyncAnthropic",
        _FakeAnthropicClient,
    )

    planner = LessonPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    assert result["ch1"] == []
    assert exploding.create_call_count == 2  # both attempts hit, both failed


@pytest.mark.asyncio
async def test_lesson_planner_pins_topic_id_against_llm_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LLM could emit a renamed topic_id; the planner pins the real one."""
    renamed = {**_VALID_LESSON_PLAN_PAYLOAD, "topic_id": "wrong-llm-id"}
    _install_fake(monkeypatch, [_tool_use_response(renamed)])

    planner = LessonPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    plans = result["ch1"]
    assert len(plans) == 1
    # The pipeline pinned the curriculum's topic_id, not whatever the LLM said.
    assert plans[0].topic_id == "t1"


@pytest.mark.asyncio
async def test_lesson_planner_skips_chapter_without_lecture_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chapters with no ChapterLecturePlan are skipped without Anthropic calls."""
    messages = _install_fake(monkeypatch, [])

    planner = LessonPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {},  # no lecture plans
        {},
    )

    assert result == {}
    assert messages.create_call_count == 0
