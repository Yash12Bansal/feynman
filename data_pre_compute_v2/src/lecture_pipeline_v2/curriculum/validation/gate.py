"""Validation gate — orchestrates structural, semantic, and render checks.

The gate **never blocks ingestion** — it only flags individual nodes via
needs_review and removes broken diagrams. Catastrophic structural errors
(missing chapters, duplicate IDs) raise an exception and abort the run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ...llm.base import LLMProvider
from ..anchors.models import ExtractionAnchors
from ..models import CurriculumExtractionResult
from .render_test import DiagramRenderReport, DiagramRenderTester
from .semantic import SemanticValidationReport, SemanticValidator
from .structural import StructuralValidator
from .models import ValidationReport

logger = logging.getLogger(__name__)


class ValidationGateError(Exception):
    pass


@dataclass
class GateReport:
    structural: ValidationReport
    semantic: SemanticValidationReport
    render: DiagramRenderReport
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"Validation gate complete in {self.elapsed_seconds:.1f}s\n"
            f"    {self.structural.summary()}\n"
            f"    {self.semantic.summary()}\n"
            f"    {self.render.summary()}"
        )


class ValidationGate:
    def __init__(self, llm: LLMProvider, *, semantic_sample_rate: float = 0.20):
        self.structural = StructuralValidator()
        self.semantic = SemanticValidator(llm, sample_rate=semantic_sample_rate)
        self.render = DiagramRenderTester()

    def run(
        self,
        extraction: CurriculumExtractionResult,
        anchors_by_chapter: dict[str, ExtractionAnchors] | None = None,
    ) -> GateReport:
        start = time.monotonic()

        structural = self.structural.validate(extraction, anchors_by_chapter)
        if any(i.code in {"DUPLICATE_ID", "CIRCULAR_PREREQ"} for i in structural.issues if i.level == "error"):
            raise ValidationGateError(
                "Structural validation found catastrophic errors (duplicate IDs or "
                "circular prereqs). Aborting before any external writes."
            )

        kept_diagrams, render_report = self.render.test_all(extraction.diagrams)
        dropped_ids = {d.diagram_id for d in extraction.diagrams} - {
            d.diagram_id for d in kept_diagrams
        }
        if dropped_ids:
            extraction.diagrams = kept_diagrams
            for topic in extraction.topics:
                topic.has_diagram_ids = [
                    did for did in topic.has_diagram_ids if did not in dropped_ids
                ]

        semantic = self.semantic.validate(extraction)

        report = GateReport(
            structural=structural, semantic=semantic, render=render_report,
            elapsed_seconds=time.monotonic() - start,
        )
        logger.info(report.summary())
        return report
