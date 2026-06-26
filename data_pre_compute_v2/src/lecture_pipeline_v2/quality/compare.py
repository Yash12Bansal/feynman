"""Compare two ULQF quality reports."""

from __future__ import annotations

from typing import Any

from .models import MetricDelta, QualityComparison, QualityReport
from .registry import IMPLEMENTED_METRICS


def _numeric_delta(baseline: Any, candidate: Any) -> float | None:
    if isinstance(baseline, (int, float)) and isinstance(candidate, (int, float)):
        return round(float(candidate) - float(baseline), 4)
    return None


def _improved(
    metric_id: str,
    baseline: Any,
    candidate: Any,
    delta: float | None,
) -> bool | None:
    if delta is None:
        if isinstance(baseline, bool) and isinstance(candidate, bool):
            if baseline == candidate:
                return None
            return candidate and not baseline
        return None
    higher_is_better = IMPLEMENTED_METRICS.get(metric_id, None)
    if higher_is_better is None:
        return delta > 0 if delta != 0 else None
    if higher_is_better.higher_is_better:
        return delta > 0
    return delta < 0


def compare_reports(
    baseline: QualityReport,
    candidate: QualityReport,
    *,
    baseline_label: str | None = None,
    candidate_label: str | None = None,
) -> QualityComparison:
    base_label = baseline_label or baseline.run.label or "baseline"
    cand_label = candidate_label or candidate.run.label or "candidate"

    base_by_id = {m.metric_id: m for m in baseline.metrics if m.level == "run"}
    cand_by_id = {m.metric_id: m for m in candidate.metrics if m.level == "run"}

    all_ids = sorted(set(base_by_id) | set(cand_by_id))
    deltas: list[MetricDelta] = []

    for metric_id in all_ids:
        b = base_by_id.get(metric_id)
        c = cand_by_id.get(metric_id)
        b_val = b.value if b else None
        c_val = c.value if c else None
        delta = _numeric_delta(b_val, c_val)
        name = (c or b).name if (c or b) else metric_id
        dimension = (c or b).dimension if (c or b) else IMPLEMENTED_METRICS[metric_id].dimension
        deltas.append(
            MetricDelta(
                metric_id=metric_id,
                name=name,
                dimension=dimension,
                baseline=b_val,
                candidate=c_val,
                delta=delta,
                improved=_improved(metric_id, b_val, c_val, delta),
            )
        )

    index_deltas: dict[str, float] = {}
    for key, b_attr, c_attr in (
        ("TQI", "technical_quality_index", "technical_quality_index"),
        ("EQI", "educational_quality_index", "educational_quality_index"),
        ("LEI", "learning_effectiveness_index", "learning_effectiveness_index"),
        ("LES", "lecture_excellence_score", "lecture_excellence_score"),
    ):
        b_score = getattr(baseline.indices, b_attr)
        c_score = getattr(candidate.indices, c_attr)
        if b_score is not None and c_score is not None:
            index_deltas[key] = round(c_score - b_score, 2)

    return QualityComparison(
        baseline_label=base_label,
        candidate_label=cand_label,
        index_deltas=index_deltas,
        metric_deltas=deltas,
    )
