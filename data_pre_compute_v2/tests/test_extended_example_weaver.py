"""ExtendedExampleWeaver tests.

Strategy mirrors test_lesson_judge.py / test_lesson_planner.py: inject a fake
LLM provider at the `provider=` seam whose `agenerate_tool_use` returns canned
payloads from a queue. No network, provider-agnostic.

Covers: generation + tagging + metadata persistence, idempotent re-run,
diagram-field sanitization, skip-when-zero-extras, retry-with-feedback.
"""

from __future__ import annotations

from typing import Any

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.extended_example_prompts import (
    EXTENDED_EXAMPLE_WEAVER_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.extended_example_weaver import (
    ExtendedExampleWeaver,
    ExtendedWeaverReport,
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
from lecture_pipeline_v2.curriculum.models import BookExample, Topic


# ── Fixtures ───────────────────────────────────────────────────────────────


def _config() -> PipelineConfig:
    return PipelineConfig(llm=LLMConfig(api_key="test", model="claude-sonnet-4-test"))


def _topic(*, prereqs: int = 1, with_book_example: bool = True) -> Topic:
    """A topic whose n_extended_examples() is controllable via prereq count.

    Rule: has_book_examples + 1-2 prereqs → 2 extras (default here).
    """
    return Topic(
        topic_id="topic-1",
        chapter_id="chap-1",
        section_number="1.1",
        within_chapter_order=0,
        topic_name="Newton's First Law",
        orig_book_content="An object in motion stays in motion...",
        our_understanding="A body keeps doing what it's doing unless a force acts on it.",
        prereq_topic_ids=[f"p{i}" for i in range(prereqs)],
        book_examples=(
            [
                BookExample(
                    verbatim_text="A 2 kg block...",
                    kind="worked_out",
                    lesson_focus="Apply the first law.",
                )
            ]
            if with_book_example
            else []
        ),
    )


def _plan() -> LessonPlan:
    """Minimal-valid concept-only plan with a clear summary tail so the
    weaver's insertion point lands before it."""
    return LessonPlan(
        topic_id="topic-1",
        title="Newton's First Law",
        hook=Hook(type=HookType.paradox, text="A surprising-feeling hook."),
        crucial_facts=["inertia keeps motion going"],
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
                narration="An honest question?", actions=[], is_question=True
            ),
            ChoreographyStep(
                narration="The clean payoff.",
                actions=[],
                is_payoff=True,
                presses_crucial_fact=True,
            ),
            ChoreographyStep(narration="To summarise, inertia rules."),
        ],
    )


def _payload(examples: list[dict[str, Any]]) -> dict[str, Any]:
    return {"examples": examples}


def _ex(kind: str, n_steps: int = 1, *, dirty: bool = False) -> dict[str, Any]:
    """A canned woven-example dict. `dirty=True` sets diagram-side fields the
    weaver must sanitize away."""
    step: dict[str, Any] = {"narration": f"A vivid {kind} anchor you've felt."}
    if dirty:
        step["actions"] = ["focus"]
        step["target_element_id"] = "invented-elem"
        step["target_diagram_id"] = "invented-diagram"
        step["is_question"] = True
    return {
        "kind": kind,
        "hook_text": f"{kind} hook text",
        "concept_tie": "ties back to inertia",
        "steps": [dict(step) for _ in range(n_steps)],
    }


# ── Fake provider ──────────────────────────────────────────────────────────


class _FakeProvider:
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
        assert system_prompt == EXTENDED_EXAMPLE_WEAVER_SYSTEM_PROMPT
        assert tool_name == "emit_extended_examples"
        self.last_user_message = user_prompt
        self.calls.append({"tool_name": tool_name})
        if not self._queue:
            raise RuntimeError("test ran out of canned responses")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def call_count(self) -> int:
        return len(self.calls)


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weaves_tags_steps_and_persists_metadata() -> None:
    topic = _topic()  # 2 extras
    assert topic.n_extended_examples() == 2
    provider = _FakeProvider([_payload([_ex("real_world"), _ex("fun_fact")])])
    weaver = ExtendedExampleWeaver(_config(), provider=provider)

    report = ExtendedWeaverReport()
    new_plan = await weaver.weave_for_topic(
        lesson_plan=_plan(), topic=topic, n_examples=2, report=report
    )

    tagged = [s for s in new_plan.choreography if s.is_extended_example]
    assert len(tagged) == 2
    assert {s.extended_example_ref for s in tagged} == {0, 1}
    # Metadata persisted on the topic for inspectability.
    assert [e.kind for e in topic.extended_examples] == ["real_world", "fun_fact"]
    assert report.examples_generated == 2
    assert report.topics_woven == 1
    # Inserted before the summary, not after it.
    summary_idx = next(
        i for i, s in enumerate(new_plan.choreography) if "summarise" in s.narration
    )
    assert all(new_plan.choreography.index(s) < summary_idx for s in tagged)


@pytest.mark.asyncio
async def test_sanitizes_diagram_side_fields() -> None:
    """LLM may emit actions / element ids despite the prompt — weaver must
    strip them so the post-merge LessonPlan validator never rejects."""
    topic = _topic()
    provider = _FakeProvider(
        [_payload([_ex("real_world", dirty=True), _ex("fun_fact", dirty=True)])]
    )
    weaver = ExtendedExampleWeaver(_config(), provider=provider)

    new_plan = await weaver.weave_for_topic(
        lesson_plan=_plan(), topic=topic, n_examples=2, report=ExtendedWeaverReport()
    )

    for s in new_plan.choreography:
        if s.is_extended_example:
            assert s.actions == []
            assert s.target_element_id is None
            assert s.target_diagram_id is None
            assert s.is_question is False
            assert s.is_payoff is False
            assert s.presses_crucial_fact is False


@pytest.mark.asyncio
async def test_idempotent_rerun_does_not_duplicate() -> None:
    topic = _topic()
    provider = _FakeProvider(
        [
            _payload([_ex("real_world"), _ex("fun_fact")]),
            _payload([_ex("real_world"), _ex("fun_fact")]),
        ]
    )
    weaver = ExtendedExampleWeaver(_config(), provider=provider)

    plan1 = await weaver.weave_for_topic(
        lesson_plan=_plan(), topic=topic, n_examples=2, report=ExtendedWeaverReport()
    )
    n_after_first = sum(1 for s in plan1.choreography if s.is_extended_example)

    plan2 = await weaver.weave_for_topic(
        lesson_plan=plan1, topic=topic, n_examples=2, report=ExtendedWeaverReport()
    )
    n_after_second = sum(1 for s in plan2.choreography if s.is_extended_example)

    assert n_after_first == 2
    assert n_after_second == 2  # not 4 — prior tagged steps stripped first
    assert len(topic.extended_examples) == 2


@pytest.mark.asyncio
async def test_skips_topics_with_zero_extras() -> None:
    """Empty book examples + <3 prereqs → 0 extras → no LLM call at all."""
    topic = _topic(prereqs=1, with_book_example=False)
    assert topic.n_extended_examples() == 0
    provider = _FakeProvider([])  # would raise if called
    weaver = ExtendedExampleWeaver(_config(), provider=provider)

    report = await weaver.weave_for_chapter(
        chapter_lesson_plans={"topic-1": _plan()},
        topics_by_id={"topic-1": topic},
    )

    assert provider.call_count == 0
    assert report.topics_eligible == 0
    assert report.examples_generated == 0


@pytest.mark.asyncio
async def test_retries_with_feedback_then_succeeds() -> None:
    topic = _topic()
    # First response is malformed (missing required fields → ValidationError),
    # second is good.
    bad = _payload([{"kind": "real_world"}])  # missing hook_text/concept_tie/steps
    good = _payload([_ex("real_world"), _ex("fun_fact")])
    provider = _FakeProvider([bad, good])
    weaver = ExtendedExampleWeaver(_config(), provider=provider)

    report = ExtendedWeaverReport()
    new_plan = await weaver.weave_for_topic(
        lesson_plan=_plan(), topic=topic, n_examples=2, report=report
    )

    assert provider.call_count == 2
    assert report.retries_used == 1
    assert sum(1 for s in new_plan.choreography if s.is_extended_example) == 2
    # The retry prompt carried feedback.
    assert "RETRY" in provider.last_user_message
