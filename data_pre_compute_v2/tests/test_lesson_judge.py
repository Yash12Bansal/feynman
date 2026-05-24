"""PlanJudge tests — doc 19 Phase F.

Strategy: monkeypatch `anthropic.AsyncAnthropic` in the lesson_judge module
with a fake whose `messages.create` returns canned `tool_use` responses
containing PlanJudgement payloads. Same shape as test_lesson_planner.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge import (
    PlanJudge,
    PlanJudgement,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge_prompts import (
    LESSON_JUDGE_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    ChoreographyAction,
    ChoreographyStep,
    DiagramRequirement,
    ElementRequirement,
    Hook,
    HookType,
    LessonPlan,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _config() -> PipelineConfig:
    return PipelineConfig(llm=LLMConfig(api_key="test", model="claude-sonnet-4-test"))


def _make_plan() -> LessonPlan:
    """A minimal-valid LessonPlan: Q + P + 2 presses on the one crucial fact."""
    return LessonPlan(
        topic_id="topic-1",
        title="Test lesson",
        hook=Hook(type=HookType.paradox, text="A surprising-feeling hook."),
        crucial_facts=["the test crucial fact"],
        diagrams=[
            DiagramRequirement(
                diagram_id="d1",
                purpose="A test diagram.",
                required_elements=[
                    ElementRequirement(
                        element_id="elem-1", role="role-1", description="desc-1"
                    )
                ],
            )
        ],
        choreography=[
            ChoreographyStep(
                narration="A focus step.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="An honest question?",
                actions=[],
                is_question=True,
            ),
            ChoreographyStep(
                narration="The clean payoff.",
                actions=[],
                is_payoff=True,
                presses_crucial_fact=True,
            ),
        ],
    )


# Canned PlanJudgement payloads.
_PASSING_JUDGEMENT = {
    "passed": True,
    "score": 5,
    "issue": "Hook lands hard.",
    "suggestion": "Keep doing exactly this.",
}

_FAILING_JUDGEMENT = {
    "passed": False,
    "score": 2,
    "issue": "Hook reads like a textbook opener.",
    "suggestion": "Rewrite the first step as a real paradox or surprising fact.",
}

_BORDERLINE_JUDGEMENT_3 = {
    "passed": True,
    "score": 3,
    "issue": "Acceptable but bland.",
    "suggestion": "Sharpen the payoff sentence.",
}

_BORDERLINE_JUDGEMENT_2 = {
    "passed": False,
    "score": 2,
    "issue": "Hook is too academic.",
    "suggestion": "Open with a question, not a fact.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Fake Anthropic client harness
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _FakeBlock:
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
        self.last_user_message: str = ""

    async def create(self, **kwargs: Any) -> _FakeResponse:
        assert kwargs.get("system") == LESSON_JUDGE_SYSTEM_PROMPT
        messages = kwargs.get("messages") or []
        if messages:
            self.last_user_message = messages[0].get("content", "")
        self.create_call_count += 1
        if not self._queue:
            raise RuntimeError("test ran out of canned judge responses")
        return self._queue.pop(0)


class _FakeAnthropicClient:
    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.messages = _CURRENT_FAKE_MESSAGES


_CURRENT_FAKE_MESSAGES: _FakeMessages | None = None


def _install_fake(
    monkeypatch: pytest.MonkeyPatch, responses: list[_FakeResponse]
) -> _FakeMessages:
    global _CURRENT_FAKE_MESSAGES
    _CURRENT_FAKE_MESSAGES = _FakeMessages(responses)
    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge.anthropic.AsyncAnthropic",
        _FakeAnthropicClient,
    )
    return _CURRENT_FAKE_MESSAGES


def _tool_response(payload: dict[str, Any]) -> _FakeResponse:
    return _FakeResponse(
        content=[_FakeBlock(type="tool_use", name="emit_plan_judgement", input=payload)]
    )


def _empty_response() -> _FakeResponse:
    return _FakeResponse(content=[])


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_judge_emits_score_for_valid_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = _install_fake(monkeypatch, [_tool_response(_PASSING_JUDGEMENT)])
    judge = PlanJudge(_config())
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 5
    assert "lands" in result.issue.lower()
    assert messages.create_call_count == 1


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodingMessages:
        async def create(self, **kwargs: Any) -> Any:
            raise RuntimeError("simulated API failure")

    global _CURRENT_FAKE_MESSAGES
    _CURRENT_FAKE_MESSAGES = _ExplodingMessages()  # type: ignore[assignment]
    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge.anthropic.AsyncAnthropic",
        _FakeAnthropicClient,
    )

    judge = PlanJudge(_config())
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True  # skipped passes through
    assert result.score == 3
    assert "api_error" in result.issue


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_missing_tool_use_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, [_empty_response()])
    judge = PlanJudge(_config())
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 3
    assert "no_tool_use_block" in result.issue


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_invalid_tool_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool block with non-dict input → skipped."""
    bad_response = _FakeResponse(
        content=[
            _FakeBlock(type="tool_use", name="emit_plan_judgement", input="not a dict")
        ]
    )
    _install_fake(monkeypatch, [bad_response])
    judge = PlanJudge(_config())
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 3
    assert "tool_input_not_dict" in result.issue


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_pydantic_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool block with payload that fails PlanJudgement validation → skipped."""
    bad_payload = {"passed": True, "score": 99, "issue": "x", "suggestion": "y"}
    _install_fake(monkeypatch, [_tool_response(bad_payload)])
    judge = PlanJudge(_config())
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 3
    assert "pydantic_error" in result.issue


@pytest.mark.asyncio
async def test_judge_passes_threshold_at_min_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """score=3, min_score=3 → passed=True. score=2 → passed=False."""
    _install_fake(
        monkeypatch,
        [
            _tool_response(_BORDERLINE_JUDGEMENT_3),
            _tool_response(_BORDERLINE_JUDGEMENT_2),
        ],
    )
    judge = PlanJudge(_config(), min_score=3)
    r3 = await judge.judge(_make_plan(), topic_name="Test")
    r2 = await judge.judge(_make_plan(), topic_name="Test")
    assert r3.passed is True
    assert r3.score == 3
    assert r2.passed is False
    assert r2.score == 2


@pytest.mark.asyncio
async def test_judge_overrides_llm_passed_to_match_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM emits passed=True with score=2 (disagrees with threshold=3) →
    our `passed` overrides to False."""
    payload = {
        "passed": True,  # LLM is wrong / inconsistent
        "score": 2,
        "issue": "x",
        "suggestion": "y",
    }
    _install_fake(monkeypatch, [_tool_response(payload)])
    judge = PlanJudge(_config(), min_score=3)
    result = await judge.judge(_make_plan(), topic_name="Test")
    assert result.passed is False  # we override based on our threshold
    assert result.score == 2


@pytest.mark.asyncio
async def test_judge_user_message_includes_full_plan_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User message must contain hook text, crucial_facts, all step narrations,
    diagram requirements — so the LLM has full context to judge."""
    messages = _install_fake(monkeypatch, [_tool_response(_PASSING_JUDGEMENT)])
    judge = PlanJudge(_config())
    await judge.judge(_make_plan(), topic_name="The Test Lesson Name")

    msg = messages.last_user_message
    assert "The Test Lesson Name" in msg
    assert "A surprising-feeling hook." in msg
    assert "the test crucial fact" in msg
    assert "A focus step." in msg
    assert "An honest question?" in msg
    assert "The clean payoff." in msg
    assert "elem-1" in msg
    assert "d1" in msg


@pytest.mark.asyncio
async def test_judge_user_message_marks_question_and_payoff_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The serialization must surface the is_question / is_payoff /
    presses_crucial_fact flags so the LLM can grade Q→P rhythm."""
    messages = _install_fake(monkeypatch, [_tool_response(_PASSING_JUDGEMENT)])
    judge = PlanJudge(_config())
    await judge.judge(_make_plan(), topic_name="Test")

    msg = messages.last_user_message
    assert "QUESTION" in msg
    assert "PAYOFF" in msg
    assert "PRESSES_CRUCIAL_FACT" in msg


@pytest.mark.asyncio
async def test_judge_emits_concrete_issue_and_suggestion_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the LLM returns issue + suggestion strings, they pass through verbatim."""
    _install_fake(monkeypatch, [_tool_response(_FAILING_JUDGEMENT)])
    judge = PlanJudge(_config())
    result = await judge.judge(_make_plan(), topic_name="Test")
    assert result.issue == "Hook reads like a textbook opener."
    assert (
        result.suggestion
        == "Rewrite the first step as a real paradox or surprising fact."
    )


def test_planjudgement_skipped_factory() -> None:
    """`PlanJudgement.skipped(reason)` returns a pass-through judgement."""
    skipped = PlanJudgement.skipped("test-reason")
    assert skipped.passed is True
    assert skipped.score == 3
    assert skipped.issue == "test-reason"
    assert skipped.suggestion == ""
