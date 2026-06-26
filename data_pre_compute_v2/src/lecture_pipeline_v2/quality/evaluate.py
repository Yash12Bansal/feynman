"""Evaluate extraction.json against ULQF metrics."""

from __future__ import annotations

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.models import CurriculumExtractionResult

from .collectors import collect_all, collect_cost
from .context import EvaluationContext
from .gates import QualityGateResult, evaluate_gates
from .indices import compute_indices
from .judges.narration_judge import NarrationJudge
from .models import MetricValue, QualityIndices, QualityReport, RunMetadata
from .registry import definition
from .snapshot import NarrationJudgementRecord, QualitySnapshot


def _build_report(
    extraction: CurriculumExtractionResult,
    ctx: EvaluationContext,
) -> QualityReport:
    metrics = collect_all(ctx)
    indices = compute_indices(metrics)
    metrics.extend(collect_cost(ctx, les=indices.lecture_excellence_score))
    metrics.extend(_index_metrics(indices))
    gates = evaluate_gates(metrics)
    return QualityReport(
        subject=extraction.subject,
        textbook_title=extraction.textbook_title,
        run=ctx.run,
        metrics=metrics,
        indices=indices,
        gates=gates,
    )


def evaluate_extraction(
    extraction: CurriculumExtractionResult,
    *,
    run: RunMetadata | None = None,
) -> QualityReport:
    ctx = EvaluationContext(extraction=extraction, run=run or RunMetadata())
    return _build_report(extraction, ctx)


async def evaluate_extraction_async(
    extraction: CurriculumExtractionResult,
    *,
    run: RunMetadata | None = None,
    with_judges: bool = False,
    config: PipelineConfig | None = None,
) -> QualityReport:
    run_meta = run or RunMetadata()
    ctx = EvaluationContext(extraction=extraction, run=run_meta)

    if with_judges:
        judgements = await _run_narration_judges(
            extraction,
            config=config,
            persona_id=run_meta.persona_id,
        )
        ctx.narration_judgements = judgements

    return _build_report(extraction, ctx)


async def _run_narration_judges(
    extraction: CurriculumExtractionResult,
    *,
    config: PipelineConfig | None,
    persona_id: str | None,
) -> list[NarrationJudgementRecord]:
    cfg = config or PipelineConfig.load()
    judge = NarrationJudge(cfg)
    records: list[NarrationJudgementRecord] = []

    for chapter in extraction.chapters:
        narrations_by_topic = {n.topic_id: n for n in chapter.lesson_narrations}
        for topic_id, narration in narrations_by_topic.items():
            topic = extraction.topic_by_id(topic_id)
            if topic is None:
                continue
            excerpt = narration.full_text_with_markers or ""
            result = await judge.judge_topic(
                subject=extraction.subject,
                topic=topic,
                narration_excerpt=excerpt,
                persona_id=persona_id,
            )
            skipped = bool(
                result.issue
                and (
                    result.issue.startswith("api_error")
                    or result.issue.startswith("empty_narration")
                    or result.issue.startswith("no_tool_payload")
                    or result.issue.startswith("parse_error")
                )
            )
            records.append(
                NarrationJudgementRecord(
                    topic_id=topic_id,
                    domain_fit_score=result.domain_fit_score,
                    analogy_leakage_score=result.analogy_leakage_score,
                    clarity_score=result.clarity_score,
                    engagement_score=result.engagement_score,
                    factual_grounding_score=result.factual_grounding_score,
                    skipped=skipped and "api_error" in result.issue,
                    issue=result.issue,
                )
            )

    return records


def merge_narration_judgements(
    extraction: CurriculumExtractionResult,
    judgements: list[NarrationJudgementRecord],
    *,
    persona_id: str | None = None,
) -> CurriculumExtractionResult:
    snap = extraction.quality_snapshot or QualitySnapshot(persona_id=persona_id)
    updated = snap.model_copy(update={"narration_judgements": judgements})
    if persona_id:
        updated = updated.model_copy(update={"persona_id": persona_id})
    return extraction.model_copy(update={"quality_snapshot": updated})


def _index_metrics(indices: QualityIndices) -> list[MetricValue]:
    out: list[MetricValue] = []
    for metric_id, value in (
        ("TQI", indices.technical_quality_index),
        ("EQI", indices.educational_quality_index),
        ("LEI", indices.learning_effectiveness_index),
        ("LES", indices.lecture_excellence_score),
    ):
        if value is None:
            continue
        d = definition(metric_id)
        out.append(
            MetricValue(
                metric_id=metric_id,
                name=d.name,
                dimension=d.dimension,
                value=value,
                unit=d.unit,
                level="run",
                score_0_100=value,
            )
        )
    return out


__all__ = [
    "QualityGateResult",
    "evaluate_extraction",
    "evaluate_extraction_async",
    "merge_narration_judgements",
]
