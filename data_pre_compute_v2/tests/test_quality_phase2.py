"""QEE Phase 2 — snapshot metrics, gates, narration judge."""

from __future__ import annotations

import pytest

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge import PlanJudgement
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import TopicNarration
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    ChoreographyStep,
    Hook,
    HookType,
    LessonPlan,
)
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    CurriculumExtractionResult,
    ExtractionSource,
    Topic,
)
from lecture_pipeline_v2.quality import RunMetadata, evaluate_extraction
from lecture_pipeline_v2.quality.evaluate import evaluate_extraction_async
from lecture_pipeline_v2.quality.judges.narration_judge import NarrationJudge
from lecture_pipeline_v2.quality.snapshot import (
    ChapterQualitySnapshot,
    NarrationJudgementRecord,
    QualitySnapshot,
    TopicGateRecord,
    ValidationGateSnapshot,
)


def _minimal_plan(topic_id: str) -> LessonPlan:
    return LessonPlan(
        topic_id=topic_id,
        title="Simple Interest",
        hook=Hook(type=HookType.question, text="How much interest on ₹10,000?"),
        crucial_facts=["I = P × r × t"],
        diagrams=[],
        choreography=[
            ChoreographyStep(
                narration="Banks pay interest on deposits.",
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="But does interest compound on itself?",
                is_question=True,
            ),
            ChoreographyStep(
                narration="Simple interest uses principal only.",
                is_payoff=True,
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="Multiply principal, rate, and time.",
                presses_crucial_fact=True,
            ),
        ],
    )


def _extraction_with_snapshot() -> CurriculumExtractionResult:
    topic_id = "topic:finance:simple_interest:1_1"
    chapter_id = "chapter:finance:simple_interest"
    topic = Topic(
        topic_id=topic_id,
        chapter_id=chapter_id,
        section_number="1.1",
        within_chapter_order=1,
        topic_name="What simple interest means",
        orig_book_content="Simple interest is fixed percentage of principal per year.",
        our_understanding="Simple interest pays on the original amount only.",
        book_examples=[],
    )
    chapter = Chapter(
        chapter_id=chapter_id,
        chapter_index=1,
        title="Simple Interest",
        summary="Intro",
        page_start=1,
        page_end=1,
        topic_ids=[topic_id],
        lesson_plans=[_minimal_plan(topic_id)],
        lesson_narrations=[
            TopicNarration(
                topic_id=topic_id,
                full_text_with_markers="Banks pay simple interest on your deposit.",
            )
        ],
        assembled_chapter_script={
            "chapter_id": chapter_id,
            "segments": [{"topic_id": topic_id, "narration_chapter": "Banks pay."}],
        },
    )
    snapshot = QualitySnapshot(
        persona_id="finance_teacher",
        validation=ValidationGateSnapshot(
            semantic_topics_checked=10,
            semantic_topics_flagged=1,
            semantic_wrong_count=0,
            diagram_render_checked=5,
            diagram_render_failed=0,
        ),
        chapters=[
            ChapterQualitySnapshot(
                chapter_id=chapter_id,
                topic_gates=[
                    TopicGateRecord(
                        topic_id=topic_id,
                        plan_judgement=PlanJudgement(
                            passed=True, score=4, issue="", suggestion=""
                        ),
                        plan_regen_attempts=0,
                    )
                ],
                book_coverage_pct=100.0,
                book_coverage_gaps=0,
                lesson_gate_passed=1,
                lesson_gate_seen=1,
            )
        ],
        narration_judgements=[
            NarrationJudgementRecord(
                topic_id=topic_id,
                domain_fit_score=85,
                analogy_leakage_score=10,
                clarity_score=80,
                engagement_score=75,
                factual_grounding_score=90,
            )
        ],
    )
    return CurriculumExtractionResult(
        subject="finance",
        textbook_title="Simple Interest",
        source=ExtractionSource(
            textbook_title="Simple Interest",
            extractor_model="claude-opus-4-8",
        ),
        chapters=[chapter],
        topics=[topic],
        quality_snapshot=snapshot,
    )


def test_snapshot_metrics_populate_phase2_ids() -> None:
    report = evaluate_extraction(
        _extraction_with_snapshot(),
        run=RunMetadata(persona_id="finance_teacher", total_elapsed_seconds=120.0),
    )
    assert report.metric("LP-31") is not None
    assert report.metric("BE-01") is not None
    assert report.metric("EDU-domain-fit") is not None
    assert report.metric("CO-10") is not None
    assert report.gates
    assert any(g.gate_id == "QG-08" for g in report.gates)


def test_quality_snapshot_roundtrip(tmp_path) -> None:
    extraction = _extraction_with_snapshot()
    path = tmp_path / "extraction.json"
    extraction.save(path)
    loaded = CurriculumExtractionResult.load(path)
    assert loaded.quality_snapshot is not None
    assert loaded.quality_snapshot.chapters[0].topic_gates[0].plan_judgement is not None


@pytest.mark.asyncio
async def test_narration_judge_with_mock_provider() -> None:
    class _MockProvider:
        async def agenerate_tool_use(self, *_args, **_kwargs):  # noqa: ANN001
            return {
                "domain_fit_score": 90,
                "analogy_leakage_score": 5,
                "clarity_score": 88,
                "engagement_score": 82,
                "factual_grounding_score": 91,
                "issue": "",
            }

    from lecture_pipeline_v2.config import LLMConfig, PipelineConfig

    topic = Topic(
        topic_id="t1",
        chapter_id="c1",
        section_number="1.1",
        within_chapter_order=1,
        topic_name="Interest",
        orig_book_content="Principal times rate times time.",
        our_understanding="I = PRT",
    )
    judge = NarrationJudge(
        PipelineConfig(llm=LLMConfig(api_key="test", model="test")),
        provider=_MockProvider(),
    )
    result = await judge.judge_topic(
        subject="finance",
        topic=topic,
        narration_excerpt="When you deposit ₹10,000, the bank pays simple interest.",
        persona_id="finance_teacher",
    )
    assert result.domain_fit_score == 90
    assert result.analogy_leakage_score == 5


@pytest.mark.asyncio
async def test_evaluate_async_with_judges(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockProvider:
        async def agenerate_tool_use(self, *_args, **_kwargs):  # noqa: ANN001
            return {
                "domain_fit_score": 70,
                "analogy_leakage_score": 30,
                "clarity_score": 75,
                "engagement_score": 72,
                "factual_grounding_score": 80,
                "issue": "",
            }

    from lecture_pipeline_v2.config import LLMConfig, PipelineConfig

    import lecture_pipeline_v2.quality.evaluate as evaluate_mod

    async def _patched_run(extraction, *, config, persona_id):  # noqa: ANN001
        judge = NarrationJudge(
            config or PipelineConfig(llm=LLMConfig(api_key="test", model="test")),
            provider=_MockProvider(),
        )
        records = []
        for chapter in extraction.chapters:
            for narration in chapter.lesson_narrations:
                topic = extraction.topic_by_id(narration.topic_id)
                if topic is None:
                    continue
                result = await judge.judge_topic(
                    subject=extraction.subject,
                    topic=topic,
                    narration_excerpt=narration.full_text_with_markers or "text",
                    persona_id=persona_id,
                )
                records.append(
                    NarrationJudgementRecord(
                        topic_id=topic.topic_id,
                        domain_fit_score=result.domain_fit_score,
                        analogy_leakage_score=result.analogy_leakage_score,
                        clarity_score=result.clarity_score,
                        engagement_score=result.engagement_score,
                        factual_grounding_score=result.factual_grounding_score,
                    )
                )
        return records

    monkeypatch.setattr(evaluate_mod, "_run_narration_judges", _patched_run)

    extraction = _extraction_with_snapshot()
    extraction.quality_snapshot.narration_judgements = []
    report = await evaluate_extraction_async(
        extraction,
        run=RunMetadata(persona_id="feynman"),
        with_judges=True,
    )
    assert report.metric("EDU-domain-fit") is not None
    assert report.metric("EDU-domain-fit").value == 70.0
