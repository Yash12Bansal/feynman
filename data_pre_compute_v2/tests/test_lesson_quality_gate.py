"""LessonQualityGate tests — doc 19 Phase F orchestrator.

Strategy: stub the dependency objects (LessonPlanner, LessonDiagramGenerator,
DiagramQA, PlanJudge) with classes that record call args and return canned
results. The orchestrator only composes these; testing the composition logic
is easier than threading fake Anthropic messages through the deep stack.

LessonNarrator stays REAL — it's deterministic and we want to exercise its
real output in the gate's return value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.enrichment.diagram_qa import QAResult
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge import PlanJudgement
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import LessonNarrator
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    ChoreographyAction,
    ChoreographyStep,
    DiagramRequirement,
    ElementRequirement,
    Hook,
    HookType,
    LessonPlan,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_quality_gate import (
    GateReport,
    LessonQualityGate,
    _build_diagram_claim,
)
from lecture_pipeline_v2.curriculum.models import Diagram, DiagramRenderer


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _config() -> PipelineConfig:
    return PipelineConfig(llm=LLMConfig(api_key="test", model="claude-sonnet-4-test"))


def _make_plan(*, diagram_id: str = "d1", element_id: str = "elem-1") -> LessonPlan:
    return LessonPlan(
        topic_id="topic-1",
        title="Test lesson",
        hook=Hook(type=HookType.paradox, text="A real-feeling hook line."),
        crucial_facts=["the test crucial fact"],
        diagrams=[
            DiagramRequirement(
                diagram_id=diagram_id,
                purpose=f"Purpose for {diagram_id}",
                required_elements=[
                    ElementRequirement(
                        element_id=element_id,
                        role="role-1",
                        description=f"desc {element_id}",
                    )
                ],
            )
        ],
        choreography=[
            ChoreographyStep(
                narration="Step 1.",
                actions=[ChoreographyAction.focus],
                target_element_id=element_id,
                target_diagram_id=diagram_id,
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="Step 2 question?",
                actions=[],
                is_question=True,
            ),
            ChoreographyStep(
                narration="Step 3 payoff.",
                actions=[],
                is_payoff=True,
                presses_crucial_fact=True,
            ),
        ],
    )


def _make_plan_with_two_diagrams() -> LessonPlan:
    return LessonPlan(
        topic_id="topic-1",
        title="Test lesson",
        hook=Hook(type=HookType.paradox, text="A real-feeling hook line."),
        crucial_facts=["the test crucial fact"],
        diagrams=[
            DiagramRequirement(
                diagram_id="d1",
                purpose="Purpose for d1",
                required_elements=[
                    ElementRequirement(
                        element_id="elem-1", role="role-1", description="desc elem-1"
                    )
                ],
            ),
            DiagramRequirement(
                diagram_id="d2",
                purpose="Purpose for d2",
                required_elements=[
                    ElementRequirement(
                        element_id="elem-2", role="role-2", description="desc elem-2"
                    )
                ],
            ),
        ],
        choreography=[
            ChoreographyStep(
                narration="Step 1.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="Step 2 question?",
                actions=[],
                is_question=True,
            ),
            ChoreographyStep(
                narration="Step 3 payoff.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-2",
                target_diagram_id="d2",
                is_payoff=True,
                presses_crucial_fact=True,
            ),
        ],
    )


def _make_diagram(
    *, diagram_id: str = "diagram:topic-1:d1", description: str = "Purpose for d1"
) -> Diagram:
    return Diagram(
        diagram_id=diagram_id,
        renderer=DiagramRenderer.SVG,
        render_data={"title": diagram_id, "elements": [], "dictionary": {}},
        description=description,
        linked_topic_ids=["topic-1"],
        linked_beat_id="",
        presentation_mode="build_up",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stub classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _PlanCall:
    topic_id: str
    chapter_id: str
    concept_index: int
    prior_quality_feedback: str | None


class _StubPlanner:
    """Returns canned plans per call. Records `prior_quality_feedback` so
    tests can assert the gate threaded the judge's feedback through."""

    def __init__(self, plans: list[LessonPlan | None]) -> None:
        self._queue = list(plans)
        self.calls: list[_PlanCall] = []

    async def plan_one_topic(
        self,
        *,
        concept_index: int,
        curriculum: Any,
        topic_id: str,
        chapter_id: str,
        prior_quality_feedback: str | None = None,
    ) -> LessonPlan | None:
        self.calls.append(
            _PlanCall(
                topic_id=topic_id,
                chapter_id=chapter_id,
                concept_index=concept_index,
                prior_quality_feedback=prior_quality_feedback,
            )
        )
        if not self._queue:
            raise RuntimeError("test ran out of canned plans")
        return self._queue.pop(0)


class _StubJudge:
    """Returns canned judgements per call."""

    def __init__(self, judgements: list[PlanJudgement]) -> None:
        self._queue = list(judgements)
        self.call_count = 0

    async def judge(self, plan: LessonPlan, *, topic_name: str) -> PlanJudgement:
        self.call_count += 1
        if not self._queue:
            raise RuntimeError("test ran out of canned judgements")
        return self._queue.pop(0)


@dataclass
class _DiagCall:
    requirement_id: str
    prior_quality_feedback: str | None


class _StubDiagramGen:
    """Returns canned diagrams. Mirrors `generate_for_requirements` +
    `generate_one_requirement` signatures."""

    def __init__(
        self,
        initial_diagrams: list[Diagram],
        regen_diagrams: dict[str, Diagram] | None = None,
    ) -> None:
        self.initial_diagrams = initial_diagrams
        self.regen_diagrams = regen_diagrams or {}
        self.calls: list[_DiagCall] = []
        self.regen_call_count = 0

    async def generate_for_requirements(
        self,
        requirements: list[tuple[str, str, DiagramRequirement]],
    ) -> tuple[list[Diagram], Any]:
        return list(self.initial_diagrams), None

    async def generate_one_requirement(
        self,
        *,
        chapter_id: str,
        topic_id: str,
        requirement: DiagramRequirement,
        prior_quality_feedback: str | None = None,
        report: Any = None,
    ) -> Diagram | None:
        self.regen_call_count += 1
        self.calls.append(
            _DiagCall(
                requirement_id=requirement.diagram_id,
                prior_quality_feedback=prior_quality_feedback,
            )
        )
        return self.regen_diagrams.get(requirement.diagram_id)


class _StubQA:
    """Returns canned QAResults by diagram_id (lookup by id, fallthrough to default)."""

    def __init__(
        self,
        results_by_id: dict[str, QAResult] | None = None,
        default: QAResult | None = None,
    ) -> None:
        self.results_by_id = results_by_id or {}
        self.default = default or QAResult(
            passed=True, score=5, issue="", suggestion=""
        )
        self.call_count = 0
        self.calls: list[tuple[str, str]] = []  # (diagram_id, claim)

    async def verify(self, diagram: Diagram, claim: str) -> QAResult:
        self.call_count += 1
        self.calls.append((diagram.diagram_id, claim))
        return self.results_by_id.get(diagram.diagram_id, self.default)


def _build_gate(
    *,
    planner: _StubPlanner,
    diagram_generator: _StubDiagramGen,
    judge: _StubJudge,
    qa: _StubQA | None,
    max_quality_retries: int = 1,
) -> LessonQualityGate:
    return LessonQualityGate(
        _config(),
        planner=planner,  # type: ignore[arg-type]
        diagram_generator=diagram_generator,  # type: ignore[arg-type]
        narrator=LessonNarrator(_config()),
        plan_judge=judge,  # type: ignore[arg-type]
        diagram_qa=qa,  # type: ignore[arg-type]
        max_quality_retries=max_quality_retries,
    )


def _passing_judgement(score: int = 5) -> PlanJudgement:
    return PlanJudgement(
        passed=True, score=score, issue="fine", suggestion="keep going"
    )


def _failing_judgement(score: int = 2) -> PlanJudgement:
    return PlanJudgement(
        passed=False,
        score=score,
        issue="Hook is too academic.",
        suggestion="Open with a paradox instead of a definition.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gate_happy_path_no_regen() -> None:
    """Plan passes + diagram passes → no regen."""
    plan = _make_plan()
    diag = _make_diagram(description="Purpose for d1")
    planner = _StubPlanner([plan])
    judge = _StubJudge([_passing_judgement(score=5)])
    diag_gen = _StubDiagramGen(initial_diagrams=[diag])
    qa = _StubQA(default=QAResult(passed=True, score=5, issue="", suggestion=""))
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test lesson",
        concept_index=0,
        curriculum=object(),
    )

    assert result.plan is plan
    assert result.diagrams == [diag]
    assert result.narration is not None
    assert result.needs_review is False
    assert result.plan_regen_attempts == 0
    assert result.diagram_regen_attempts == 0
    assert len(planner.calls) == 1
    assert judge.call_count == 1


@pytest.mark.asyncio
async def test_gate_regens_plan_once_on_low_score() -> None:
    """Judge fails first plan; second attempt passes → 1 regen."""
    plan_v1 = _make_plan()
    plan_v2 = _make_plan()
    planner = _StubPlanner([plan_v1, plan_v2])
    judge = _StubJudge([_failing_judgement(score=2), _passing_judgement(score=5)])
    diag = _make_diagram()
    diag_gen = _StubDiagramGen(initial_diagrams=[diag])
    qa = _StubQA(default=QAResult(passed=True, score=5, issue="", suggestion=""))
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test lesson",
        concept_index=0,
        curriculum=object(),
    )

    # Best plan is the v2 retry (score 5 > score 2).
    assert result.plan is plan_v2
    assert result.plan_regen_attempts == 1
    assert result.plan_judgement is not None and result.plan_judgement.score == 5
    assert result.needs_review is False
    assert len(planner.calls) == 2


@pytest.mark.asyncio
async def test_gate_gives_up_after_max_quality_retries() -> None:
    """Judge fails twice in a row (with retries=1) → keeps best, needs_review=True."""
    plan_v1 = _make_plan()
    plan_v2 = _make_plan()
    planner = _StubPlanner([plan_v1, plan_v2])
    judge = _StubJudge([_failing_judgement(score=2), _failing_judgement(score=1)])
    diag = _make_diagram()
    diag_gen = _StubDiagramGen(initial_diagrams=[diag])
    qa = _StubQA(default=QAResult(passed=True, score=5, issue="", suggestion=""))
    gate = _build_gate(
        planner=planner,
        diagram_generator=diag_gen,
        judge=judge,
        qa=qa,
        max_quality_retries=1,
    )

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test lesson",
        concept_index=0,
        curriculum=object(),
    )

    # v1 had score 2 (higher than v2's 1), so v1 wins.
    assert result.plan is plan_v1
    assert result.plan_regen_attempts == 1
    assert result.needs_review is True
    assert result.plan_judgement is not None and result.plan_judgement.score == 2


@pytest.mark.asyncio
async def test_gate_passes_judge_suggestion_to_planner() -> None:
    """Second planner call sees judge's suggestion in prior_quality_feedback."""
    plan_v1 = _make_plan()
    plan_v2 = _make_plan()
    planner = _StubPlanner([plan_v1, plan_v2])
    failing = _failing_judgement(score=2)
    judge = _StubJudge([failing, _passing_judgement(score=5)])
    diag_gen = _StubDiagramGen(initial_diagrams=[_make_diagram()])
    qa = _StubQA()
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test",
        concept_index=0,
        curriculum=object(),
    )

    # First call: no prior feedback. Second call: includes judge suggestion verbatim.
    assert planner.calls[0].prior_quality_feedback is None
    second_feedback = planner.calls[1].prior_quality_feedback
    assert second_feedback is not None
    assert failing.suggestion in second_feedback
    assert failing.issue in second_feedback


@pytest.mark.asyncio
async def test_gate_regens_only_offending_diagrams() -> None:
    """Two diagrams, one passes, one fails QA → only the failing one regens."""
    plan = _make_plan_with_two_diagrams()
    diag1 = _make_diagram(diagram_id="diagram:topic-1:d1", description="Purpose for d1")
    diag2_v1 = _make_diagram(
        diagram_id="diagram:topic-1:d2", description="Purpose for d2"
    )
    # Real generator pins diagram_id deterministically from requirement.diagram_id,
    # so a regen produces the SAME id. We differentiate by render_data content.
    diag2_v2 = Diagram(
        diagram_id="diagram:topic-1:d2",
        renderer=DiagramRenderer.SVG,
        render_data={"title": "v2", "elements": [], "dictionary": {}},
        description="Purpose for d2",
        linked_topic_ids=["topic-1"],
        linked_beat_id="",
        presentation_mode="build_up",
    )

    planner = _StubPlanner([plan])
    judge = _StubJudge([_passing_judgement(score=5)])
    diag_gen = _StubDiagramGen(
        initial_diagrams=[diag1, diag2_v1],
        regen_diagrams={"d2": diag2_v2},
    )

    # QA verdicts: d1 passes, d2 (v1) fails → regen → d2 (v2) passes.
    # Because both d2 versions share the same diagram_id, we model this with
    # a queued-verdict QA that returns per call rather than by id.
    class _SequencedQA:
        def __init__(self, verdicts: list[QAResult]) -> None:
            self._queue = list(verdicts)
            self.call_count = 0

        async def verify(self, diagram: Diagram, claim: str) -> QAResult:
            self.call_count += 1
            return self._queue.pop(0)

    qa = _SequencedQA(
        [
            QAResult(passed=True, score=5, issue="", suggestion=""),  # d1
            QAResult(
                passed=False, score=2, issue="muddled", suggestion="redraw"
            ),  # d2_v1
            QAResult(passed=True, score=5, issue="", suggestion=""),  # d2_v2
        ]
    )
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test",
        concept_index=0,
        curriculum=object(),
    )

    assert diag_gen.regen_call_count == 1
    assert diag_gen.calls[0].requirement_id == "d2"
    assert result.diagram_regen_attempts == 1
    # Final diagram set: original d1 + regenerated d2 (replaced in-place).
    final_ids = {d.diagram_id for d in result.diagrams}
    assert final_ids == {"diagram:topic-1:d1", "diagram:topic-1:d2"}
    # The d2 entry must be the v2 render_data.
    d2_final = next(d for d in result.diagrams if d.diagram_id == "diagram:topic-1:d2")
    assert d2_final.render_data["title"] == "v2"
    assert result.needs_review is False


@pytest.mark.asyncio
async def test_gate_works_without_diagram_qa() -> None:
    """qa=None disables visual QA; diagrams pass through unjudged."""
    plan = _make_plan()
    diag = _make_diagram()
    planner = _StubPlanner([plan])
    judge = _StubJudge([_passing_judgement(score=5)])
    diag_gen = _StubDiagramGen(initial_diagrams=[diag])
    gate = _build_gate(
        planner=planner, diagram_generator=diag_gen, judge=judge, qa=None
    )

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test",
        concept_index=0,
        curriculum=object(),
    )

    assert result.diagrams == [diag]
    assert result.diagram_regen_attempts == 0
    assert result.diagram_judgements == {}
    assert result.needs_review is False


@pytest.mark.asyncio
async def test_gate_runs_narrator_after_quality_passes() -> None:
    """narrator.render is called on the final (post-quality-retry) plan."""
    plan = _make_plan()
    planner = _StubPlanner([plan])
    judge = _StubJudge([_passing_judgement(score=5)])
    diag_gen = _StubDiagramGen(initial_diagrams=[_make_diagram()])
    qa = _StubQA()
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test",
        concept_index=0,
        curriculum=object(),
    )

    assert result.narration is not None
    assert result.narration.topic_id == "topic-1"
    # The narration text contains the choreography step content.
    assert "Step 1." in result.narration.full_text_with_markers
    assert "Step 3 payoff." in result.narration.full_text_with_markers


@pytest.mark.asyncio
async def test_gate_handles_planner_returning_none() -> None:
    """Planner gives up internally → gate returns empty result with needs_review=True."""
    planner = _StubPlanner([None])
    judge = _StubJudge([])
    diag_gen = _StubDiagramGen(initial_diagrams=[])
    qa = _StubQA()
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test",
        concept_index=0,
        curriculum=object(),
    )

    assert result.plan is None
    assert result.diagrams == []
    assert result.narration is None
    assert result.needs_review is True
    assert judge.call_count == 0  # never reached


@pytest.mark.asyncio
async def test_gate_records_full_judgement_history_in_report() -> None:
    """plan_judgement carries the FINAL judgement; report attempts reflect retries."""
    plan_v1 = _make_plan()
    plan_v2 = _make_plan()
    planner = _StubPlanner([plan_v1, plan_v2])
    judge = _StubJudge([_failing_judgement(score=2), _passing_judgement(score=5)])
    diag_gen = _StubDiagramGen(initial_diagrams=[_make_diagram()])
    qa = _StubQA()
    report = GateReport()
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test",
        concept_index=0,
        curriculum=object(),
        report=report,
    )

    assert result.plan_judgement is not None
    assert result.plan_judgement.score == 5  # the final, higher score
    assert result.plan_regen_attempts == 1
    assert report.topics_seen == 1
    assert report.plan_regens == 1
    assert report.topics_passed == 1


def test_build_diagram_claim_includes_required_elements() -> None:
    """The claim string passed to DiagramQA mentions every required element."""
    requirement = DiagramRequirement(
        diagram_id="d1",
        purpose="Show the throw from two frames.",
        required_elements=[
            ElementRequirement(
                element_id="parabola",
                role="curve",
                description="ball's parabolic path in ground frame",
            ),
            ElementRequirement(
                element_id="vertical-drop",
                role="trajectory",
                description="ball's vertical drop in train frame",
            ),
        ],
    )
    claim = _build_diagram_claim(requirement)
    assert "Show the throw from two frames." in claim
    assert "ball's parabolic path in ground frame" in claim
    assert "ball's vertical drop in train frame" in claim
    assert "curve" in claim
    assert "trajectory" in claim


@pytest.mark.asyncio
async def test_gate_resolves_diagram_id_short_to_long_in_narration() -> None:
    """The gate must thread a diagram_id_resolver into the narrator so the
    manifest's SHOW_DIAGRAM markers use the LONG generate_diagram_uid output
    (matching what LessonDiagramGenerator pins on each Diagram), not the
    planner's short id.

    Bug this guards against: without the resolver, narrations would emit
    `<<SHOW_DIAGRAM:two-frames>>` while the diagram is stored as
    `diagram:physics:topic-1:two_frames` — the frontend can't resolve the
    short id and the slide stays stuck on "loading".
    """
    plan = _make_plan(diagram_id="two-frames", element_id="elem-1")
    diag = _make_diagram(diagram_id="diagram:topic-1:two_frames")
    planner = _StubPlanner([plan])
    judge = _StubJudge([_passing_judgement(score=5)])
    diag_gen = _StubDiagramGen(initial_diagrams=[diag])
    qa = _StubQA()
    gate = _build_gate(planner=planner, diagram_generator=diag_gen, judge=judge, qa=qa)

    result = await gate.gate_one_topic(
        chapter_id="ch1",
        topic_id="topic-1",
        topic_name="Test lesson",
        concept_index=0,
        curriculum=object(),
    )

    assert result.narration is not None
    full_text = result.narration.full_text_with_markers
    # The resolver maps "two-frames" → "diagram:topic-1:two_frames" via
    # generate_diagram_uid. The narration must use the LONG UID.
    assert "<<SHOW_DIAGRAM:diagram:topic-1:two_frames>>" in full_text
    # And must NOT contain the bare short id as a SHOW_DIAGRAM target.
    assert "<<SHOW_DIAGRAM:two-frames>>" not in full_text
    # diagrams_referenced should also be the long form.
    assert result.narration.diagrams_referenced == ["diagram:topic-1:two_frames"]
