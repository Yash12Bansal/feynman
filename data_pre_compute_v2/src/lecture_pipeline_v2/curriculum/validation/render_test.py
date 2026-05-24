"""Render-test diagrams via a lightweight SVG synthesiser.

This is a *structural* render test — it converts the DiagramSpec into an SVG
string and checks for malformed elements. We don't actually rasterise here
(that happens in the media phase). Diagrams that fail render are flagged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..models import Diagram, DiagramRenderer

logger = logging.getLogger(__name__)


REQUIRED_FIELDS_BY_ELEMENT_TYPE = {
    "svg_line": ["x1", "y1", "x2", "y2"],
    "svg_rect": ["x", "y", "width", "height"],
    "svg_circle": ["cx", "cy", "r"],
    "svg_ellipse": ["cx", "cy", "rx", "ry"],
    "svg_path": ["d"],
    "svg_text": ["x", "y", "text"],
    "svg_arc": ["cx", "cy", "r", "startAngle", "endAngle"],
    "svg_arrow": ["x1", "y1", "x2", "y2"],
    "svg_latex": ["x", "y", "expression"],
    "svg_group": ["elements"],
    "graph": ["x", "y", "width", "height"],
}


@dataclass
class DiagramRenderReport:
    diagrams_checked: int = 0
    diagrams_passed: int = 0
    diagrams_flagged: int = 0
    elapsed_seconds: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Diagram render test — {self.diagrams_passed}/{self.diagrams_checked} passed, "
            f"{self.diagrams_flagged} flagged, "
            f"{self.elapsed_seconds:.1f}s"
        )


class DiagramRenderTester:
    """Structural render checks on the DiagramSpec.

    Flagging here removes broken diagrams from the pipeline (they won't be
    ingested); the topic's other diagrams are unaffected.
    """

    def test_all(
        self, diagrams: list[Diagram]
    ) -> tuple[list[Diagram], DiagramRenderReport]:
        import time

        report = DiagramRenderReport()
        start = time.monotonic()

        kept: list[Diagram] = []
        for diagram in diagrams:
            report.diagrams_checked += 1
            try:
                self._test_one(diagram)
                report.diagrams_passed += 1
                kept.append(diagram)
            except ValueError as e:
                logger.warning(
                    "Diagram %s failed render test: %s", diagram.diagram_id, e
                )
                report.failures.append((diagram.diagram_id, str(e)))
                report.diagrams_flagged += 1

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return kept, report

    def _test_one(self, diagram: Diagram) -> None:
        if diagram.renderer == DiagramRenderer.MANIM:
            return  # manim has its own validation path
        spec = diagram.render_data
        if not isinstance(spec, dict):
            raise ValueError("render_data is not a dict")
        elements = spec.get("elements")
        if not isinstance(elements, list) or not elements:
            raise ValueError("no elements")

        ids: set[str] = set()
        self._validate_elements(elements, ids)

        # Phase 1 (precompute-lecture-overhaul): the design_agent prompt requires
        # a non-empty `dictionary` mapping element_id → semantic metadata.
        # Mark legacy / mal-formed specs needs_review but keep them — the
        # downstream pipeline still works, just without role-based addressing.
        dictionary = spec.get("dictionary")
        if not isinstance(dictionary, dict) or not dictionary:
            logger.info(
                "Diagram %s has no semantic dictionary — marking needs_review",
                diagram.diagram_id,
            )
            diagram.needs_review = True

    def _validate_elements(self, elements: list, ids: set[str]) -> None:
        for el in elements:
            if not isinstance(el, dict):
                raise ValueError("element is not a dict")
            etype = el.get("type")
            if not etype:
                raise ValueError("element missing 'type'")
            required = REQUIRED_FIELDS_BY_ELEMENT_TYPE.get(etype)
            if required is None:
                raise ValueError(f"unknown element type: {etype}")
            for f in required:
                if f not in el:
                    raise ValueError(f"{etype} element missing required field '{f}'")
            eid = el.get("id")
            if eid:
                if eid in ids:
                    raise ValueError(f"duplicate element id: {eid}")
                ids.add(eid)
            if etype == "svg_group":
                children = el.get("elements") or []
                if not isinstance(children, list):
                    raise ValueError("svg_group elements must be a list")
                self._validate_elements(children, ids)
            if etype == "svg_latex":
                expr = (el.get("expression") or "").strip()
                if not expr:
                    raise ValueError("svg_latex has empty expression")
