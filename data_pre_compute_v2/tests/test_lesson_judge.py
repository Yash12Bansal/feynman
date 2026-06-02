"""PlanJudge tests — doc 19 Phase F.

Strategy: inject a fake LLM provider at the `provider=` seam whose
`agenerate_tool_use` returns canned PlanJudgement payloads from a queue.
Provider-agnostic. Same shape as test_lesson_planner.py.
"""

from __future__ import annotations

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
# Fake provider (injected at the `provider=` seam)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeProvider:
    """LLM provider double. `agenerate_tool_use` pops the next queued item: a
    dict is the tool payload, an Exception is raised, None (or any non-dict)
    models 'no usable tool call'.
    """

    def __init__(self, queue: list[Any]) -> None:
        self._queue = list(queue)
        self.calls: list[dict] = []
        self.last_user_message: str = ""

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
    ) -> Any:
        assert system_prompt == LESSON_JUDGE_SYSTEM_PROMPT
        assert tool_name == "emit_plan_judgement"
        self.last_user_message = user_prompt
        self.calls.append({"tool_name": tool_name})
        if not self._queue:
            raise RuntimeError("test ran out of canned judge responses")
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
async def test_judge_emits_score_for_valid_plan() -> None:
    provider = _FakeProvider([_PASSING_JUDGEMENT])
    judge = PlanJudge(_config(), provider=provider)
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 5
    assert "lands" in result.issue.lower()
    assert provider.create_call_count == 1


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_api_error() -> None:
    provider = _FakeProvider([RuntimeError("simulated API failure")])
    judge = PlanJudge(_config(), provider=provider)
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True  # skipped passes through
    assert result.score == 3
    assert "api_error" in result.issue


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_missing_tool_use_block() -> None:
    provider = _FakeProvider([None])
    judge = PlanJudge(_config(), provider=provider)
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 3
    assert "no_tool_use_block" in result.issue


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_non_dict_payload() -> None:
    """A provider that returns a non-dict payload → skipped (no_tool_use_block)."""
    provider = _FakeProvider(["not a dict"])
    judge = PlanJudge(_config(), provider=provider)
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 3
    assert "no_tool_use_block" in result.issue


@pytest.mark.asyncio
async def test_judge_returns_skipped_on_pydantic_failure() -> None:
    """A payload that fails PlanJudgement validation → skipped."""
    bad_payload = {"passed": True, "score": 99, "issue": "x", "suggestion": "y"}
    provider = _FakeProvider([bad_payload])
    judge = PlanJudge(_config(), provider=provider)
    result = await judge.judge(_make_plan(), topic_name="Test lesson")
    assert result.passed is True
    assert result.score == 3
    assert "pydantic_error" in result.issue


@pytest.mark.asyncio
async def test_judge_passes_threshold_at_min_score() -> None:
    """score=3, min_score=3 → passed=True. score=2 → passed=False."""
    provider = _FakeProvider([_BORDERLINE_JUDGEMENT_3, _BORDERLINE_JUDGEMENT_2])
    judge = PlanJudge(_config(), provider=provider, min_score=3)
    r3 = await judge.judge(_make_plan(), topic_name="Test")
    r2 = await judge.judge(_make_plan(), topic_name="Test")
    assert r3.passed is True
    assert r3.score == 3
    assert r2.passed is False
    assert r2.score == 2


@pytest.mark.asyncio
async def test_judge_overrides_llm_passed_to_match_threshold() -> None:
    """LLM emits passed=True with score=2 (disagrees with threshold=3) →
    our `passed` overrides to False."""
    payload = {
        "passed": True,  # LLM is wrong / inconsistent
        "score": 2,
        "issue": "x",
        "suggestion": "y",
    }
    provider = _FakeProvider([payload])
    judge = PlanJudge(_config(), provider=provider, min_score=3)
    result = await judge.judge(_make_plan(), topic_name="Test")
    assert result.passed is False  # we override based on our threshold
    assert result.score == 2


@pytest.mark.asyncio
async def test_judge_user_message_includes_full_plan_serialization() -> None:
    """User message must contain hook text, crucial_facts, all step narrations,
    diagram requirements — so the LLM has full context to judge."""
    provider = _FakeProvider([_PASSING_JUDGEMENT])
    judge = PlanJudge(_config(), provider=provider)
    await judge.judge(_make_plan(), topic_name="The Test Lesson Name")

    msg = provider.last_user_message
    assert "The Test Lesson Name" in msg
    assert "A surprising-feeling hook." in msg
    assert "the test crucial fact" in msg
    assert "A focus step." in msg
    assert "An honest question?" in msg
    assert "The clean payoff." in msg
    assert "elem-1" in msg
    assert "d1" in msg


@pytest.mark.asyncio
async def test_judge_user_message_marks_question_and_payoff_flags() -> None:
    """The serialization must surface the is_question / is_payoff /
    presses_crucial_fact flags so the LLM can grade Q→P rhythm."""
    provider = _FakeProvider([_PASSING_JUDGEMENT])
    judge = PlanJudge(_config(), provider=provider)
    await judge.judge(_make_plan(), topic_name="Test")

    msg = provider.last_user_message
    assert "QUESTION" in msg
    assert "PAYOFF" in msg
    assert "PRESSES_CRUCIAL_FACT" in msg


@pytest.mark.asyncio
async def test_judge_emits_concrete_issue_and_suggestion_strings() -> None:
    """When the LLM returns issue + suggestion strings, they pass through verbatim."""
    provider = _FakeProvider([_FAILING_JUDGEMENT])
    judge = PlanJudge(_config(), provider=provider)
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
