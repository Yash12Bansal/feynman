"""Python DSL for diagram authoring — compiles to existing DiagramSpec JSON.

Used by the design agent's Python-sandbox path (Phase 3 of
`docs/design/16-diagram-awareness-rearchitecture.md`). The LLM authors a
small Python script using this library; the sandbox executes it; the
library produces a dict matching ``design_agent/backend/schema.py:DiagramSpec``
which flows to the frontend through the existing wire format unchanged.

Phase 3-1 (walking skeleton) ships 5 primitives — line, rect, circle,
text, arrow — and the Canvas class. Later phases add the rest of the
DiagramSpec primitive set, geometric helpers, anchor points, and STEM
composites. See the active-features state file for the full plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]

DEFAULT_INK = "#e8e8ee"
DEFAULT_BG = "transparent"
DEFAULT_STROKE_WIDTH = 2.0


@dataclass
class ElementHandle:
    """Reference returned by every ``Canvas.add_*`` call.

    Phase 3-1 surfaces only ``id``. Phase 3-3 adds anchor points
    (``top_center``, ``midpoint``, etc.) and ``bounds``.
    """

    id: str
    role: str | None = None
    semantic: str | None = None


@dataclass
class Canvas:
    """Diagram-authoring surface backed by the existing DiagramSpec wire format.

    Usage from sandbox code::

        canvas = Canvas(title="Right triangle")
        a = canvas.add_line(start=(100, 400), end=(400, 400), role="adjacent")
        b = canvas.add_line(start=(400, 400), end=(400, 100), role="opposite")
        c = canvas.add_line(start=(100, 400), end=(400, 100), role="hypotenuse")
        canvas.add_text(position=(250, 420), text="adjacent")

    The Python script ends with ``return canvas.export()`` (or, in the
    sandbox, just leaving ``canvas`` as the last expression — the sandbox
    captures the canvas instance and calls ``.export()``).
    """

    width: int = 900
    height: int = 650
    title: str = "Untitled Diagram"
    description: str = ""
    background_color: str = DEFAULT_BG
    _elements: list[dict[str, Any]] = field(default_factory=list)
    _dictionary: dict[str, dict[str, Any]] = field(default_factory=dict)
    _id_counter: int = 0

    # ------------------------------------------------------------------
    # ID generation + dictionary registration
    # ------------------------------------------------------------------

    def _next_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}_{self._id_counter}"

    def _register(
        self,
        element_id: str,
        role: str | None,
        semantic: str | None,
    ) -> None:
        """Add a dictionary entry if the caller supplied semantic metadata.

        Phase 3-4 makes ``role`` mandatory and auto-derives ``semantic``
        when missing. For the walking skeleton we keep it optional so
        existing direct-JSON parity is preserved.
        """
        if role is None and semantic is None:
            return
        self._dictionary[element_id] = {
            "role": role or "element",
            "semantic": semantic or role or element_id,
            "position": "center",
            "spatial_relations": [],
        }

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------

    def add_line(
        self,
        start: Point,
        end: Point,
        *,
        id: str | None = None,
        stroke: str = DEFAULT_INK,
        stroke_width: float = DEFAULT_STROKE_WIDTH,
        stroke_dasharray: str = "",
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        element_id = id or self._next_id("line")
        self._elements.append(
            {
                "type": "svg_line",
                "id": element_id,
                "x1": float(start[0]),
                "y1": float(start[1]),
                "x2": float(end[0]),
                "y2": float(end[1]),
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
            }
        )
        self._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_rect(
        self,
        top_left: Point,
        width: float,
        height: float,
        *,
        id: str | None = None,
        stroke: str = DEFAULT_INK,
        stroke_width: float = DEFAULT_STROKE_WIDTH,
        fill: str = "none",
        corner_radius: float = 0,
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        element_id = id or self._next_id("rect")
        self._elements.append(
            {
                "type": "svg_rect",
                "id": element_id,
                "x": float(top_left[0]),
                "y": float(top_left[1]),
                "width": float(width),
                "height": float(height),
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "fill": fill,
                "rx": float(corner_radius),
            }
        )
        self._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_circle(
        self,
        center: Point,
        radius: float,
        *,
        id: str | None = None,
        stroke: str = DEFAULT_INK,
        stroke_width: float = DEFAULT_STROKE_WIDTH,
        stroke_dasharray: str = "",
        fill: str = "none",
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        element_id = id or self._next_id("circle")
        self._elements.append(
            {
                "type": "svg_circle",
                "id": element_id,
                "cx": float(center[0]),
                "cy": float(center[1]),
                "r": float(radius),
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
                "fill": fill,
            }
        )
        self._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_text(
        self,
        position: Point,
        text: str,
        *,
        id: str | None = None,
        font_size: float = 12,
        fill: str = DEFAULT_INK,
        text_anchor: str = "middle",
        font_weight: str = "normal",
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        element_id = id or self._next_id("text")
        self._elements.append(
            {
                "type": "svg_text",
                "id": element_id,
                "x": float(position[0]),
                "y": float(position[1]),
                "text": text,
                "fontSize": float(font_size),
                "fill": fill,
                "textAnchor": text_anchor,
                "fontWeight": font_weight,
            }
        )
        self._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_arrow(
        self,
        start: Point,
        end: Point,
        *,
        id: str | None = None,
        stroke: str = "#7fd4ff",  # neon cyan default — matches existing prompt
        stroke_width: float = 2.5,
        stroke_dasharray: str = "",
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        element_id = id or self._next_id("arrow")
        self._elements.append(
            {
                "type": "svg_arrow",
                "id": element_id,
                "x1": float(start[0]),
                "y1": float(start[1]),
                "x2": float(end[0]),
                "y2": float(end[1]),
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
            }
        )
        self._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def export(self) -> dict[str, Any]:
        """Return a dict matching ``design_agent/backend/schema.py:DiagramSpec``.

        The dict shape exactly matches what the existing direct-JSON path
        emits, so downstream code (Pydantic validation, WS publishing,
        frontend rendering, annotation dictionary lookup) is unchanged.
        """
        return {
            "title": self.title,
            "description": self.description,
            "width": self.width,
            "height": self.height,
            "backgroundColor": self.background_color,
            "elements": list(self._elements),
            "parameters": [],
            "animations": [],
            "dictionary": dict(self._dictionary),
        }
