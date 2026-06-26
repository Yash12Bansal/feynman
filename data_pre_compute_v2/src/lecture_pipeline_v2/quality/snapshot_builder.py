"""Build QualitySnapshot from pipeline reports."""

from __future__ import annotations

import dataclasses

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_quality_gate import (
    GateReport as LessonGateReport,
    GateResult,
)
from lecture_pipeline_v2.curriculum.validation.book_coverage import BookCoverageReport
from lecture_pipeline_v2.curriculum.validation.gate import GateReport as ValidationGateReport

from .snapshot import (
    ChapterQualitySnapshot,
    DiagramJudgementRecord,
    TopicGateRecord,
    ValidationGateSnapshot,
)


def validation_gate_snapshot(report: ValidationGateReport) -> ValidationGateSnapshot:
    sem_wrong = sum(
        1 for i in report.semantic.issues if i.code == "SEMANTIC_WRONG"
    )
    sem_drift = sum(
        1 for i in report.semantic.issues if i.code == "SEMANTIC_DRIFT"
    )
    render = report.render
    return ValidationGateSnapshot(
        structural_errors=report.structural.error_count,
        structural_warnings=report.structural.warning_count,
        semantic_topics_checked=report.semantic.topics_checked,
        semantic_topics_flagged=report.semantic.topics_flagged,
        semantic_wrong_count=sem_wrong,
        semantic_drift_count=sem_drift,
        diagram_render_checked=render.diagrams_checked,
        diagram_render_failed=render.diagrams_flagged,
    )


def _diagram_qa_score(qa: object) -> int | None:
    score = getattr(qa, "score", None)
    if score is None and isinstance(qa, dict):
        score = qa.get("score")
    if score is None and dataclasses.is_dataclass(qa):
        score = getattr(qa, "score", None)
    return int(score) if score is not None else None


def topic_gate_record(result: GateResult) -> TopicGateRecord:
    diagram_records: list[DiagramJudgementRecord] = []
    for diagram_id, qa in result.diagram_judgements.items():
        score = _diagram_qa_score(qa)
        if score is None:
            continue
        passed = getattr(qa, "passed", None)
        if passed is None and isinstance(qa, dict):
            passed = qa.get("passed", True)
        if passed is None:
            passed = True
        issue = getattr(qa, "issue", "") or (
            qa.get("issue", "") if isinstance(qa, dict) else ""
        )
        diagram_records.append(
            DiagramJudgementRecord(
                diagram_id=diagram_id,
                score=score,
                passed=bool(passed),
                issue=str(issue),
            )
        )
    return TopicGateRecord(
        topic_id=result.topic_id,
        plan_judgement=result.plan_judgement,
        plan_regen_attempts=result.plan_regen_attempts,
        diagram_judgements=diagram_records,
        needs_review=result.needs_review,
    )


def chapter_quality_snapshot(
    chapter_id: str,
    *,
    topic_results: list[GateResult],
    coverage: BookCoverageReport,
    gate_report: LessonGateReport,
) -> ChapterQualitySnapshot:
    return ChapterQualitySnapshot(
        chapter_id=chapter_id,
        topic_gates=[topic_gate_record(r) for r in topic_results],
        book_coverage_pct=round(coverage.coverage_pct * 100.0, 2),
        book_coverage_gaps=len(coverage.gaps),
        lesson_gate_passed=gate_report.topics_passed,
        lesson_gate_seen=gate_report.topics_seen,
    )
