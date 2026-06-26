"""Unified Lecture Quality Framework (ULQF) — Quality Evaluation Engine.

Phase 1: deterministic metrics from ``extraction.json``.
Phase 2: snapshot metrics + LLM narration judges.
Design: ``docs/design/24-quality-evaluation-engine.md``
"""

from .compare import compare_reports
from .evaluate import (
    evaluate_extraction,
    evaluate_extraction_async,
    merge_narration_judgements,
)
from .gates import QualityGateResult
from .models import (
    QualityComparison,
    QualityDimension,
    QualityReport,
    RunMetadata,
)

QualityReport.model_rebuild()

__all__ = [
    "QualityComparison",
    "QualityDimension",
    "QualityGateResult",
    "QualityReport",
    "RunMetadata",
    "compare_reports",
    "evaluate_extraction",
    "evaluate_extraction_async",
    "merge_narration_judgements",
]
