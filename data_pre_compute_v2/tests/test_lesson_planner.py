"""LessonPlanner tests — doc 19 Phase C.

Strategy: inject a fake LLM provider at the `provider=` seam whose
`agenerate_tool_use()` returns canned payloads from a queue. Cover the happy
path, the validation-error retry path, the no-tool-use-block path, and the
final-failure path. Provider-agnostic — exercises the same boundary regardless
of which real provider (claude / openai / gemini) the pipeline is configured for.
"""

from __future__ import annotations

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
# Fake provider (injected at the `provider=` seam)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeProvider:
    """LLM provider double. `agenerate_tool_use` pops the next item off a queue:
    a dict is returned as the tool payload, an Exception is raised, and None
    models 'the model emitted no tool call'.
    """

    def __init__(self, queue: list[Any]) -> None:
        self._queue = list(queue)
        self.calls: list[dict] = []

    async def agenerate_tool_use(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict | None:
        # The stage must wire the real prompt, tool name, and JSON schema.
        assert system_prompt == LESSON_PLANNING_SYSTEM_PROMPT
        assert tool_name == "emit_lesson_plan"
        assert "properties" in input_schema
        self.calls.append({"tool_name": tool_name, "max_tokens": max_tokens})
        if not self._queue:
            raise RuntimeError("test ran out of canned provider responses")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def create_call_count(self) -> int:
        return len(self.calls)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lesson_planner_happy_path() -> None:
    """One valid LessonPlan returned for one topic — single LLM call."""
    provider = _FakeProvider([_VALID_LESSON_PLAN_PAYLOAD])

    planner = LessonPlanner(_config(), provider=provider)
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
    assert provider.create_call_count == 1


@pytest.mark.asyncio
async def test_lesson_planner_retries_on_validation_error() -> None:
    """First call returns a plan with a forbidden hook; second call succeeds."""
    provider = _FakeProvider([_INVALID_HOOK_PAYLOAD, _VALID_LESSON_PLAN_PAYLOAD])

    planner = LessonPlanner(_config(), provider=provider)
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    plans = result["ch1"]
    assert len(plans) == 1
    assert plans[0].topic_id == "t1"
    assert provider.create_call_count == 2


@pytest.mark.asyncio
async def test_lesson_planner_gives_up_after_two_validation_failures() -> None:
    """Two consecutive validation failures → no plan emitted for the topic."""
    provider = _FakeProvider([_INVALID_HOOK_PAYLOAD, _INVALID_HOOK_PAYLOAD])

    planner = LessonPlanner(_config(), provider=provider)
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    # No plan made it into the result.
    assert result["ch1"] == []
    # Both attempts were tried.
    assert provider.create_call_count == 2


@pytest.mark.asyncio
async def test_lesson_planner_handles_missing_tool_use_block() -> None:
    """A response with no tool call (None) triggers retry; second call succeeds."""
    provider = _FakeProvider([None, _VALID_LESSON_PLAN_PAYLOAD])

    planner = LessonPlanner(_config(), provider=provider)
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    assert len(result["ch1"]) == 1
    assert provider.create_call_count == 2


@pytest.mark.asyncio
async def test_lesson_planner_catches_unexpected_exception() -> None:
    """Provider exception → fallback retry path; both fail → empty."""
    provider = _FakeProvider(
        [RuntimeError("simulated API failure"), RuntimeError("again")]
    )

    planner = LessonPlanner(_config(), provider=provider)
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    assert result["ch1"] == []
    assert provider.create_call_count == 2  # both attempts hit, both failed


@pytest.mark.asyncio
async def test_lesson_planner_pins_topic_id_against_llm_rename() -> None:
    """The LLM could emit a renamed topic_id; the planner pins the real one."""
    renamed = {**_VALID_LESSON_PLAN_PAYLOAD, "topic_id": "wrong-llm-id"}
    provider = _FakeProvider([renamed])

    planner = LessonPlanner(_config(), provider=provider)
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
async def test_lesson_planner_skips_chapter_without_lecture_plan() -> None:
    """Chapters with no ChapterLecturePlan are skipped without LLM calls."""
    provider = _FakeProvider([])

    planner = LessonPlanner(_config(), provider=provider)
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {},  # no lecture plans
        {},
    )

    assert result == {}
    assert provider.create_call_count == 0
