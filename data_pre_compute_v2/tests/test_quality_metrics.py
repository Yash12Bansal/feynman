"""ULQF quality metrics tests."""

from __future__ import annotations

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
from lecture_pipeline_v2.quality import RunMetadata, compare_reports, evaluate_extraction


def _minimal_plan(topic_id: str) -> LessonPlan:
    return LessonPlan(
        topic_id=topic_id,
        title="Simple Interest",
        hook=Hook(
            type=HookType.question,
            text="If you leave ₹10,000 in a savings account, how much extra do you get after one year?",
        ),
        crucial_facts=["I = P × r × t", "Simple interest uses principal only"],
        diagrams=[],
        choreography=[
            ChoreographyStep(
                narration="You deposit money; the bank pays you for keeping it there.",
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="The payment is a fixed percentage of the original amount.",
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="But wait — does the bank pay interest on interest too?",
                is_question=True,
            ),
            ChoreographyStep(
                narration="No — simple interest always uses the starting principal.",
                is_payoff=True,
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="That starting amount is what we call principal.",
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="Multiply principal, rate, and time to get interest.",
                presses_crucial_fact=True,
            ),
        ],
    )


def _minimal_extraction() -> CurriculumExtractionResult:
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
        summary="Intro to simple interest",
        page_start=1,
        page_end=1,
        topic_ids=[topic_id],
        lesson_plans=[_minimal_plan(topic_id)],
        assembled_chapter_script={
            "chapter_id": chapter_id,
            "segments": [
                {
                    "topic_id": topic_id,
                    "narration_chapter": "Banks pay you for depositing money. Simple interest uses principal only.",
                    "narration_standalone": "Simple interest uses principal only.",
                }
            ],
        },
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
    )


def test_evaluate_extraction_produces_indices() -> None:
    report = evaluate_extraction(
        _minimal_extraction(),
        run=RunMetadata(label="finance-default", persona_id="default"),
    )
    assert report.subject == "finance"
    assert report.indices.lecture_excellence_score is not None
    assert report.indices.lecture_excellence_score > 0
    lp01 = report.metric("LP-01")
    assert lp01 is not None
    assert lp01.value == 100.0


def test_compare_reports_detects_les_delta() -> None:
    base = evaluate_extraction(
        _minimal_extraction(), run=RunMetadata(label="baseline")
    )
    worse = _minimal_extraction()
    worse.topics[0].needs_review = True
    cand = evaluate_extraction(worse, run=RunMetadata(label="candidate"))
    comparison = compare_reports(base, cand)
    assert "LES" in comparison.index_deltas
    assert comparison.index_deltas["LES"] <= 0


def test_quality_report_roundtrip(tmp_path) -> None:
    report = evaluate_extraction(_minimal_extraction())
    path = tmp_path / "quality.json"
    report.save(str(path))
    loaded = type(report).load(str(path))
    assert loaded.indices.lecture_excellence_score == report.indices.lecture_excellence_score
