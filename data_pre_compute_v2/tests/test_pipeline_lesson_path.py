"""Pipeline cutover tests — doc 19 Phase H.

Strategy: target the orchestrator method `_run_lesson_pipeline_for_chapter`
and the module-level helpers (`_build_chapter_script_from_narrations`,
`_topic_name_for`) directly. The full `pipeline.run()` is NOT exercised end-
to-end here — that requires PDF parsing, BookSkeleton extraction, and the
Neo4j writer, none of which are unit-testable. Phase H's real
integration is the manual re-ingest documented in the plan.

The `LessonQualityGate` is monkeypatched with a stub that returns canned
`GateResult`s. The orchestrator's job is composition; we don't re-test the
gate's internals (they're covered by `test_lesson_quality_gate.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge import PlanJudgement
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (
    LessonNarrationSegment,
    TopicNarration,
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
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_quality_gate import (
    GateResult,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    Diagram,
    DiagramRenderer,
    Topic,
)
from lecture_pipeline_v2.pipeline import (
    CurriculumPipelineV2,
    _build_chapter_script_from_narrations,
    _topic_name_for,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _config() -> PipelineConfig:
    return PipelineConfig(llm=LLMConfig(api_key="test", model="claude-sonnet-4-test"))


def _topic(topic_id: str, name: str, chapter_id: str = "ch1") -> Topic:
    return Topic(
        topic_id=topic_id,
        chapter_id=chapter_id,
        section_number="1.1",
        within_chapter_order=0,
        topic_name=name,
        orig_book_content="raw",
        our_understanding="ours",
    )


def _chapter(chapter_id: str = "ch1") -> Chapter:
    return Chapter(
        chapter_id=chapter_id,
        chapter_index=1,
        title="Chapter X",
        summary="s",
        page_start=1,
        page_end=10,
        topic_ids=[],
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


def _make_lesson_plan(topic_id: str = "t1") -> LessonPlan:
    return LessonPlan(
        topic_id=topic_id,
        title="Test lesson",
        hook=Hook(type=HookType.paradox, text="A real-feeling hook."),
        crucial_facts=["the test fact"],
        diagrams=[
            DiagramRequirement(
                diagram_id="d1",
                purpose="Purpose for d1",
                required_elements=[
                    ElementRequirement(element_id="elem-1", role="r", description="d")
                ],
            )
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
                narration="A question?",
                actions=[],
                is_question=True,
            ),
            ChoreographyStep(
                narration="A payoff.",
                actions=[],
                is_payoff=True,
                presses_crucial_fact=True,
            ),
        ],
    )


def _make_narration(topic_id: str, text: str = "Hello world.") -> TopicNarration:
    seg = LessonNarrationSegment(
        step_index=0,
        raw_narration=text,
        text_with_markers=text,
        target_duration_seconds=1.0,
    )
    return TopicNarration(
        topic_id=topic_id,
        segments=[seg],
        full_text_with_markers=text,
        diagrams_referenced=["d1"],
    )


def _make_diagram(diagram_id: str, topic_id: str = "t1") -> Diagram:
    return Diagram(
        diagram_id=diagram_id,
        renderer=DiagramRenderer.SVG,
        render_data={"title": diagram_id, "elements": [], "dictionary": {}},
        description="Test diagram",
        linked_topic_ids=[topic_id],
        linked_beat_id="",
        presentation_mode="build_up",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helper tests
# ─────────────────────────────────────────────────────────────────────────────


def test_build_chapter_script_from_narrations_happy_path() -> None:
    """Two narrations → segments with topic_id + narration_chapter + narration_standalone."""
    n1 = _make_narration("t1", "Topic one text.")
    n2 = _make_narration("t2", "Topic two text.")
    result = _build_chapter_script_from_narrations(
        chapter_id="ch1", narrations=[n1, n2]
    )
    assert result["chapter_id"] == "ch1"
    segments = result["segments"]
    assert len(segments) == 2
    assert segments[0]["topic_id"] == "t1"
    assert segments[0]["narration_chapter"] == "Topic one text."
    assert segments[0]["narration_standalone"] == "Topic one text."
    assert segments[1]["topic_id"] == "t2"
    assert segments[1]["narration_chapter"] == "Topic two text."


def test_build_chapter_script_skips_empty_text() -> None:
    """A narration with empty full_text_with_markers is dropped."""
    n1 = _make_narration("t1", "Real text.")
    n_empty = TopicNarration(
        topic_id="t2",
        segments=[],
        full_text_with_markers="",
        diagrams_referenced=[],
    )
    result = _build_chapter_script_from_narrations(
        chapter_id="ch1", narrations=[n1, n_empty]
    )
    assert len(result["segments"]) == 1
    assert result["segments"][0]["topic_id"] == "t1"


def test_topic_name_for_returns_name() -> None:
    topics = [_topic("t1", "First"), _topic("t2", "Second")]
    assert _topic_name_for(topics, "t2") == "Second"


def test_topic_name_for_returns_none_when_missing() -> None:
    assert _topic_name_for([_topic("t1", "First")], "nonexistent") is None


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator method tests (monkeypatch the gate)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _GateCallRecord:
    topic_id: str
    concept_index: int


class _StubGate:
    """Fake LessonQualityGate. Returns canned GateResults per topic."""

    def __init__(self, results_by_topic: dict[str, GateResult]) -> None:
        self.results_by_topic = results_by_topic
        self.calls: list[_GateCallRecord] = []

    async def gate_one_topic(
        self,
        *,
        chapter_id: str,
        topic_id: str,
        topic_name: str,
        concept_index: int,
        curriculum: Any,
        report: Any = None,
    ) -> GateResult:
        self.calls.append(
            _GateCallRecord(topic_id=topic_id, concept_index=concept_index)
        )
        return self.results_by_topic.get(
            topic_id,
            GateResult(
                topic_id=topic_id,
                plan=None,
                diagrams=[],
                narration=None,
                needs_review=True,
            ),
        )


def _install_gate_stub(
    monkeypatch: pytest.MonkeyPatch,
    results_by_topic: dict[str, GateResult],
) -> _StubGate:
    stub = _StubGate(results_by_topic)

    def _stub_factory(*args: Any, **kwargs: Any) -> _StubGate:
        return stub

    monkeypatch.setattr("lecture_pipeline_v2.pipeline.LessonQualityGate", _stub_factory)
    return stub


@pytest.mark.asyncio
async def test_run_lesson_pipeline_for_chapter_populates_chapter_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: 2 topics, each returns a GateResult → chapter.lesson_plans,
    lesson_narrations, assembled_chapter_script populated."""
    chapter = _chapter()
    topics = [_topic("t1", "First"), _topic("t2", "Second")]
    plan_a = _make_lesson_plan(topic_id="t1")
    plan_b = _make_lesson_plan(topic_id="t2")
    diag_a = _make_diagram("diagram:ch1:d1_a")
    diag_b = _make_diagram("diagram:ch1:d1_b")
    nar_a = _make_narration("t1", "Topic A narration. <<PAUSE:short>>")
    nar_b = _make_narration("t2", "Topic B narration.")

    _install_gate_stub(
        monkeypatch,
        {
            "t1": GateResult(
                topic_id="t1",
                plan=plan_a,
                diagrams=[diag_a],
                narration=nar_a,
                plan_judgement=PlanJudgement(
                    passed=True, score=5, issue="", suggestion=""
                ),
                needs_review=False,
            ),
            "t2": GateResult(
                topic_id="t2",
                plan=plan_b,
                diagrams=[diag_b],
                narration=nar_b,
                plan_judgement=PlanJudgement(
                    passed=True, score=5, issue="", suggestion=""
                ),
                needs_review=False,
            ),
        },
    )

    pipeline = CurriculumPipelineV2(_config())
    new_diagrams = await pipeline._run_lesson_pipeline_for_chapter(
        chapter=chapter,
        topics_for_chapter=topics,
        lecture_plan=_lecture_plan(["t1", "t2"]),
        diagrams_by_topic={},
        existing_diagram_ids=set(),
        notify=lambda _phase, _msg: None,
    )

    assert len(chapter.lesson_plans) == 2
    assert chapter.lesson_plans[0].topic_id == "t1"
    assert chapter.lesson_plans[1].topic_id == "t2"
    assert len(chapter.lesson_narrations) == 2
    # assembled_chapter_script built from narrations.
    script = chapter.assembled_chapter_script
    assert script is not None
    assert script["chapter_id"] == "ch1"
    assert len(script["segments"]) == 2
    assert script["segments"][0]["topic_id"] == "t1"
    assert script["segments"][1]["topic_id"] == "t2"
    # Returned diagrams.
    assert {d.diagram_id for d in new_diagrams} == {
        diag_a.diagram_id,
        diag_b.diagram_id,
    }


@pytest.mark.asyncio
async def test_run_lesson_pipeline_handles_gate_returning_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the gate returns plan=None for a topic, that topic is SKIPPED
    (no lesson_plan/narration appended) but the loop continues to the next."""
    chapter = _chapter()
    topics = [_topic("t1", "First"), _topic("t2", "Second")]
    plan_b = _make_lesson_plan(topic_id="t2")
    nar_b = _make_narration("t2", "Topic B works.")

    _install_gate_stub(
        monkeypatch,
        {
            "t1": GateResult(
                topic_id="t1",
                plan=None,
                diagrams=[],
                narration=None,
                needs_review=True,
            ),
            "t2": GateResult(
                topic_id="t2",
                plan=plan_b,
                diagrams=[],
                narration=nar_b,
                needs_review=False,
            ),
        },
    )

    pipeline = CurriculumPipelineV2(_config())
    await pipeline._run_lesson_pipeline_for_chapter(
        chapter=chapter,
        topics_for_chapter=topics,
        lecture_plan=_lecture_plan(["t1", "t2"]),
        diagrams_by_topic={},
        existing_diagram_ids=set(),
        notify=lambda _phase, _msg: None,
    )

    # t1 (plan=None) is skipped; t2 contributes one entry.
    assert len(chapter.lesson_plans) == 1
    assert chapter.lesson_plans[0].topic_id == "t2"
    assert len(chapter.lesson_narrations) == 1
    assert chapter.lesson_narrations[0].topic_id == "t2"


@pytest.mark.asyncio
async def test_run_lesson_pipeline_dedupes_diagrams_by_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If two topics produce the same diagram_id, only one ends up in the
    returned new_diagrams list."""
    chapter = _chapter()
    topics = [_topic("t1", "First"), _topic("t2", "Second")]
    plan_a = _make_lesson_plan(topic_id="t1")
    plan_b = _make_lesson_plan(topic_id="t2")
    shared_diag = _make_diagram("diagram:ch1:shared")

    _install_gate_stub(
        monkeypatch,
        {
            "t1": GateResult(
                topic_id="t1",
                plan=plan_a,
                diagrams=[shared_diag],
                narration=_make_narration("t1"),
                needs_review=False,
            ),
            "t2": GateResult(
                topic_id="t2",
                plan=plan_b,
                diagrams=[shared_diag],  # SAME id
                narration=_make_narration("t2"),
                needs_review=False,
            ),
        },
    )

    pipeline = CurriculumPipelineV2(_config())
    new_diagrams = await pipeline._run_lesson_pipeline_for_chapter(
        chapter=chapter,
        topics_for_chapter=topics,
        lecture_plan=_lecture_plan(["t1", "t2"]),
        diagrams_by_topic={},
        existing_diagram_ids=set(),
        notify=lambda _phase, _msg: None,
    )

    assert len(new_diagrams) == 1
    assert new_diagrams[0].diagram_id == "diagram:ch1:shared"


@pytest.mark.asyncio
async def test_run_lesson_pipeline_respects_existing_diagram_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagrams whose IDs are already in `existing_diagram_ids` are NOT
    re-added to the new_diagrams list (the caller already has them)."""
    chapter = _chapter()
    topics = [_topic("t1", "First")]
    plan_a = _make_lesson_plan(topic_id="t1")
    existing_diag = _make_diagram("diagram:ch1:already_seen")

    _install_gate_stub(
        monkeypatch,
        {
            "t1": GateResult(
                topic_id="t1",
                plan=plan_a,
                diagrams=[existing_diag],
                narration=_make_narration("t1"),
                needs_review=False,
            ),
        },
    )

    pipeline = CurriculumPipelineV2(_config())
    new_diagrams = await pipeline._run_lesson_pipeline_for_chapter(
        chapter=chapter,
        topics_for_chapter=topics,
        lecture_plan=_lecture_plan(["t1"]),
        diagrams_by_topic={},
        existing_diagram_ids={"diagram:ch1:already_seen"},
        notify=lambda _phase, _msg: None,
    )

    assert new_diagrams == []


@pytest.mark.asyncio
async def test_run_lesson_pipeline_applies_prosody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lesson pipeline applies LessonProsody to gate-returned narrations
    so that question segments get `<<PAUSE:long>>` (not just `<<PAUSE:short>>`)."""
    chapter = _chapter()
    topics = [_topic("t1", "First")]
    plan_a = _make_lesson_plan(topic_id="t1")
    # Build a narration whose sole segment IS a question — Phase E would add
    # PAUSE:short; LessonProsody must upgrade it to PAUSE:long.
    question_seg = LessonNarrationSegment(
        step_index=0,
        raw_narration="A question?",
        text_with_markers="A question? <<PAUSE:short>>",
        target_duration_seconds=1.0,
        is_question=True,
    )
    nar = TopicNarration(
        topic_id="t1",
        segments=[question_seg],
        full_text_with_markers="A question? <<PAUSE:short>>",
        diagrams_referenced=[],
    )

    _install_gate_stub(
        monkeypatch,
        {
            "t1": GateResult(
                topic_id="t1",
                plan=plan_a,
                diagrams=[],
                narration=nar,
                needs_review=False,
            ),
        },
    )

    pipeline = CurriculumPipelineV2(_config())
    await pipeline._run_lesson_pipeline_for_chapter(
        chapter=chapter,
        topics_for_chapter=topics,
        lecture_plan=_lecture_plan(["t1"]),
        diagrams_by_topic={},
        existing_diagram_ids=set(),
        notify=lambda _phase, _msg: None,
    )

    assert len(chapter.lesson_narrations) == 1
    final_text = chapter.lesson_narrations[0].full_text_with_markers
    # Prosody upgraded the question pause to long.
    assert "<<PAUSE:long>>" in final_text
    # And no leftover short pause.
    assert "<<PAUSE:short>>" not in final_text


@pytest.mark.asyncio
async def test_run_lesson_pipeline_swallows_gate_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception inside `gate.gate_one_topic` for one topic does NOT crash
    the chapter — the topic is skipped and the loop continues."""
    chapter = _chapter()
    topics = [_topic("t1", "First"), _topic("t2", "Second")]
    plan_b = _make_lesson_plan(topic_id="t2")

    class _ExplodingGate:
        async def gate_one_topic(self, *, topic_id: str, **kwargs: Any) -> GateResult:
            if topic_id == "t1":
                raise RuntimeError("simulated gate failure")
            return GateResult(
                topic_id="t2",
                plan=plan_b,
                diagrams=[],
                narration=_make_narration("t2"),
                needs_review=False,
            )

    monkeypatch.setattr(
        "lecture_pipeline_v2.pipeline.LessonQualityGate",
        lambda *args, **kwargs: _ExplodingGate(),
    )

    pipeline = CurriculumPipelineV2(_config())
    await pipeline._run_lesson_pipeline_for_chapter(
        chapter=chapter,
        topics_for_chapter=topics,
        lecture_plan=_lecture_plan(["t1", "t2"]),
        diagrams_by_topic={},
        existing_diagram_ids=set(),
        notify=lambda _phase, _msg: None,
    )

    # t1 crashed → skipped. t2 succeeded → 1 plan + 1 narration.
    assert len(chapter.lesson_plans) == 1
    assert chapter.lesson_plans[0].topic_id == "t2"
    assert len(chapter.lesson_narrations) == 1


def test_use_lesson_pipeline_defaults_to_true() -> None:
    """The doc-19 stack is the default. Legacy must be opted INTO via config."""
    cfg = PipelineConfig()
    assert cfg.enrichment.use_lesson_pipeline is True
    assert cfg.enrichment.lesson_pipeline.max_quality_retries == 1
    assert cfg.enrichment.lesson_pipeline.plan_min_score == 3


def test_chapter_model_has_lesson_fields() -> None:
    """Chapter model exposes lesson_plans + lesson_narrations as defaults."""
    ch = _chapter()
    assert ch.lesson_plans == []
    assert ch.lesson_narrations == []
