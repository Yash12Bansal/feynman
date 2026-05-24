"""Diagram fallback rendering — DiagramSpec → SVG string → PNG.

Converts our DiagramSpec element schema into a raw SVG string we write to
disk, then rasterise to PNG via cairosvg if available (otherwise we keep the
SVG file and use that as the fallback). For svg_latex we render the LaTeX as
plain text since cairo can't render KaTeX server-side — that's good enough
for a fallback image; the live renderer handles the math properly.

Manim diagrams are out of scope here — they're flagged for future rendering.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from html import escape

from ..models import Diagram, DiagramRenderer
from .artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


@dataclass
class DiagramRenderReport:
    diagrams_seen: int = 0
    pngs_written: int = 0
    svgs_written: int = 0
    skipped_manim: int = 0
    skipped_existing: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"Diagram fallback — {self.pngs_written} PNGs, {self.svgs_written} SVGs, "
            f"{self.skipped_existing} reused, "
            f"{self.skipped_manim} manim skipped, "
            f"{len(self.failures)} failures, "
            f"{self.elapsed_seconds:.1f}s"
        )


class DiagramFallbackRenderer:
    def __init__(self, store: ArtifactStore):
        self.store = store
        self._cairo = self._load_cairo()

    @staticmethod
    def _load_cairo():
        try:
            import cairosvg

            return cairosvg
        except ImportError:
            logger.info("cairosvg not installed — falling back to SVG-only artifacts")
            return None

    def render_all(self, diagrams: list[Diagram]) -> DiagramRenderReport:
        report = DiagramRenderReport(diagrams_seen=len(diagrams))
        start = time.monotonic()

        for diagram in diagrams:
            try:
                self._render_one(diagram, report)
            except Exception as e:
                logger.warning("Render failed for %s: %s", diagram.diagram_id, e)
                report.failures.append((diagram.diagram_id, str(e)))

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    def _render_one(self, diagram: Diagram, report: DiagramRenderReport) -> None:
        if diagram.renderer == DiagramRenderer.MANIM:
            report.skipped_manim += 1
            return

        svg_text = self._spec_to_svg(diagram.render_data)
        svg_path = self.store.diagram_path(diagram.diagram_id, "svg")

        if svg_path.exists() and diagram.fallback_image_url:
            report.skipped_existing += 1
            return

        svg_path.write_text(svg_text, encoding="utf-8")
        report.svgs_written += 1

        if self._cairo is not None:
            png_path = self.store.diagram_path(diagram.diagram_id, "png")
            try:
                self._cairo.svg2png(
                    bytestring=svg_text.encode("utf-8"),
                    write_to=str(png_path),
                    output_width=int(diagram.render_data.get("width", 900)),
                    output_height=int(diagram.render_data.get("height", 650)),
                )
                diagram.fallback_image_url = self.store.url_for(png_path)
                report.pngs_written += 1
                return
            except Exception as e:
                logger.warning(
                    "cairosvg failed for %s — falling back to SVG-only: %s",
                    diagram.diagram_id,
                    e,
                )

        diagram.fallback_image_url = self.store.url_for(svg_path)

    def _spec_to_svg(self, spec: dict) -> str:
        width = int(spec.get("width", 900))
        height = int(spec.get("height", 650))
        bg = spec.get("backgroundColor", "#ffffff")
        elements = spec.get("elements", [])

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{escape(bg)}"/>',
        ]
        for el in elements:
            parts.append(self._element_to_svg(el))
        parts.append("</svg>")
        return "\n".join(parts)

    def _element_to_svg(self, el: dict) -> str:
        etype = el.get("type")
        eid = el.get("id", "")
        if etype == "svg_line":
            return (
                f'<line id="{escape(eid)}" '
                f'x1="{el.get("x1", 0)}" y1="{el.get("y1", 0)}" '
                f'x2="{el.get("x2", 100)}" y2="{el.get("y2", 100)}" '
                f'stroke="{escape(el.get("stroke", "#000"))}" '
                f'stroke-width="{el.get("strokeWidth", 2)}" '
                f'stroke-dasharray="{escape(el.get("strokeDasharray", ""))}"/>'
            )
        if etype == "svg_rect":
            return (
                f'<rect id="{escape(eid)}" '
                f'x="{el.get("x", 0)}" y="{el.get("y", 0)}" '
                f'width="{el.get("width", 100)}" height="{el.get("height", 50)}" '
                f'rx="{el.get("rx", 0)}" '
                f'fill="{escape(el.get("fill", "none"))}" '
                f'stroke="{escape(el.get("stroke", "#000"))}" '
                f'stroke-width="{el.get("strokeWidth", 2)}"/>'
            )
        if etype == "svg_circle":
            return (
                f'<circle id="{escape(eid)}" '
                f'cx="{el.get("cx", 0)}" cy="{el.get("cy", 0)}" r="{el.get("r", 10)}" '
                f'fill="{escape(el.get("fill", "none"))}" '
                f'stroke="{escape(el.get("stroke", "#000"))}" '
                f'stroke-width="{el.get("strokeWidth", 2)}" '
                f'stroke-dasharray="{escape(el.get("strokeDasharray", ""))}"/>'
            )
        if etype == "svg_ellipse":
            return (
                f'<ellipse id="{escape(eid)}" '
                f'cx="{el.get("cx", 0)}" cy="{el.get("cy", 0)}" '
                f'rx="{el.get("rx", 10)}" ry="{el.get("ry", 5)}" '
                f'fill="{escape(el.get("fill", "none"))}" '
                f'stroke="{escape(el.get("stroke", "#000"))}" '
                f'stroke-width="{el.get("strokeWidth", 2)}"/>'
            )
        if etype == "svg_path":
            return (
                f'<path id="{escape(eid)}" '
                f'd="{escape(el.get("d", "M 0 0"))}" '
                f'stroke="{escape(el.get("stroke", "#000"))}" '
                f'stroke-width="{el.get("strokeWidth", 2)}" '
                f'fill="{escape(el.get("fill", "none"))}" '
                f'stroke-dasharray="{escape(el.get("strokeDasharray", ""))}"/>'
            )
        if etype == "svg_text":
            return (
                f'<text id="{escape(eid)}" '
                f'x="{el.get("x", 0)}" y="{el.get("y", 0)}" '
                f'font-size="{el.get("fontSize", 14)}" '
                f'fill="{escape(el.get("fill", "#000"))}" '
                f'text-anchor="{escape(el.get("textAnchor", "middle"))}" '
                f'font-weight="{escape(el.get("fontWeight", "normal"))}">'
                f"{escape(str(el.get('text', '')))}</text>"
            )
        if etype == "svg_arc":
            return self._arc_to_svg(el)
        if etype == "svg_arrow":
            return self._arrow_to_svg(el)
        if etype == "svg_latex":
            # Render LaTeX as plain text in the fallback PNG/SVG.
            return (
                f'<text id="{escape(eid)}" '
                f'x="{el.get("x", 0)}" y="{el.get("y", 0)}" '
                f'font-size="{el.get("fontSize", 16)}" '
                f'fill="{escape(el.get("color") or "#000")}" '
                f'font-style="italic" '
                f'text-anchor="middle">'
                f"{escape(str(el.get('expression', '')))}</text>"
            )
        if etype == "svg_group":
            children = "".join(
                self._element_to_svg(child) for child in el.get("elements", [])
            )
            return (
                f'<g id="{escape(eid)}" transform="{escape(el.get("transform", ""))}">'
                f"{children}</g>"
            )
        return ""

    @staticmethod
    def _arc_to_svg(el: dict) -> str:
        import math

        cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
        r = float(el.get("r", 50))
        start = math.radians(float(el.get("startAngle", 0)))
        end = math.radians(float(el.get("endAngle", 90)))
        x1 = cx + r * math.cos(start)
        y1 = cy + r * math.sin(start)
        x2 = cx + r * math.cos(end)
        y2 = cy + r * math.sin(end)
        large_arc = 1 if (end - start) > math.pi else 0
        d = f"M {x1} {y1} A {r} {r} 0 {large_arc} 1 {x2} {y2}"
        return (
            f'<path id="{escape(el.get("id", ""))}" '
            f'd="{d}" '
            f'stroke="{escape(el.get("stroke", "#000"))}" '
            f'stroke-width="{el.get("strokeWidth", 2)}" '
            f'fill="{escape(el.get("fill", "none"))}"/>'
        )

    @staticmethod
    def _arrow_to_svg(el: dict) -> str:
        eid = escape(el.get("id", ""))
        x1, y1 = el.get("x1", 0), el.get("y1", 0)
        x2, y2 = el.get("x2", 100), el.get("y2", 100)
        stroke = escape(el.get("stroke", "#000"))
        width = el.get("strokeWidth", 2)
        marker_id = f"arrowhead_{eid}"
        return (
            f'<defs><marker id="{marker_id}" markerWidth="10" markerHeight="10" '
            f'refX="9" refY="3" orient="auto" markerUnits="strokeWidth">'
            f'<path d="M0,0 L0,6 L9,3 z" fill="{stroke}"/></marker></defs>'
            f'<line id="{eid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{width}" '
            f'marker-end="url(#{marker_id})"/>'
        )
