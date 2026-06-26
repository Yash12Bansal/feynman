"""ULQF quality gates — pass/fail thresholds on metric values."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import MetricValue, QualityDimension


class QualityGateResult(BaseModel):
    gate_id: str
    name: str
    passed: bool
    metric_id: str
    threshold: float
    actual: float | int | str | bool | None
    severity: str = "warning"


_DEFAULT_GATES: list[tuple[str, str, str, float, bool]] = [
    # gate_id, name, metric_id, min_score_0_100, higher_is_better
    ("QG-01", "lesson_plan_coverage", "LP-01", 90.0, True),
    ("QG-02", "crucial_facts_pressed", "LP-08", 90.0, True),
    ("QG-03", "question_payoff_pairs", "LP-16", 90.0, True),
    ("QG-04", "assembled_script", "EDU-62", 100.0, True),
    ("QG-05", "low_needs_review", "CE-12", 95.0, True),
    ("QG-06", "book_example_coverage", "BE-01", 90.0, True),
    ("QG-07", "plan_judge_pass_rate", "LP-31", 70.0, True),
    ("QG-08", "domain_fit", "EDU-domain-fit", 60.0, True),
    ("QG-09", "low_analogy_leakage", "EDU-analogy-leakage", 70.0, True),
]


def evaluate_gates(metrics: list[MetricValue]) -> list[QualityGateResult]:
    by_id = {m.metric_id: m for m in metrics if m.level == "run"}
    results: list[QualityGateResult] = []
    for gate_id, name, metric_id, threshold, higher_is_better in _DEFAULT_GATES:
        m = by_id.get(metric_id)
        if m is None or m.score_0_100 is None:
            continue
        score = m.score_0_100
        passed = score >= threshold if higher_is_better else score <= threshold
        results.append(
            QualityGateResult(
                gate_id=gate_id,
                name=name,
                passed=passed,
                metric_id=metric_id,
                threshold=threshold,
                actual=m.value,
                severity="error" if gate_id in {"QG-01", "QG-04"} else "warning",
            )
        )
    return results
