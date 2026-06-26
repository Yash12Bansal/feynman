"""Composite quality indices — ULQF hierarchy."""

from __future__ import annotations

from .models import MetricValue, QualityIndices


def _mean_scores(metric_ids: list[str], metrics: list[MetricValue]) -> float | None:
    by_id = {m.metric_id: m for m in metrics if m.level == "run"}
    scores = [
        by_id[mid].score_0_100
        for mid in metric_ids
        if mid in by_id and by_id[mid].score_0_100 is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def compute_indices(metrics: list[MetricValue]) -> QualityIndices:
    """TQI / EQI / LEI / LES from normalized subscores."""

    tqi = _mean_scores(
        [
            "CE-05",
            "CE-06",
            "CE-07",
            "CE-08",
            "CE-12",
            "CE-15",
            "LP-02",
            "LP-10",
            "P-13",
        ],
        metrics,
    )
    eqi = _mean_scores(
        [
            "LP-08",
            "LP-16",
            "LP-21",
            "LP-31",
            "EDU-20",
            "NR-48",
            "NR-clarity",
            "NR-engagement",
            "EDU-51",
            "EDU-52",
            "EDU-domain-fit",
            "EDU-analogy-leakage",
            "EDU-factual-grounding",
            "BE-01",
            "DG-34",
        ],
        metrics,
    )
    lei = _mean_scores(
        [
            "LP-01",
            "CA-03",
            "CA-05",
            "EDU-62",
            "BE-01",
        ],
        metrics,
    )

    components = [s for s in (tqi, eqi, lei) if s is not None]
    if not components:
        les = None
    else:
        # Weights from ULQF: technical + educational + learning (no RLI yet).
        weights = []
        weighted_sum = 0.0
        if tqi is not None:
            weighted_sum += 0.40 * tqi
            weights.append(0.40)
        if eqi is not None:
            weighted_sum += 0.35 * eqi
            weights.append(0.35)
        if lei is not None:
            weighted_sum += 0.25 * lei
            weights.append(0.25)
        les = round(weighted_sum, 2)

    return QualityIndices(
        technical_quality_index=tqi,
        educational_quality_index=eqi,
        learning_effectiveness_index=lei,
        lecture_excellence_score=les,
    )
