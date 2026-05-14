"""Python DSL for diagram authoring — compiles to existing DiagramSpec JSON.

Used by the design agent's Python-sandbox path (Phase 3 of
`docs/design/16-diagram-awareness-rearchitecture.md`). The LLM authors a
small Python script using this library; the sandbox executes it; the
library produces a dict matching ``design_agent/backend/schema.py:DiagramSpec``
which flows to the frontend through the existing wire format unchanged.

Phase 3-1 shipped the walking skeleton with five primitives (line, rect,
circle, text, arrow). Phase 3-2 (this revision) rounds the surface out
to the full ``DiagramSpec`` element set — arc, ellipse, path, latex,
nested groups via ``add_group``, and inset plots via ``add_graph``.
Geometric helpers, anchor points on returned handles, and STEM
composites land in Phase 3-3+ per the active-feature state file.
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
    """Reference returned by every primitive call (Canvas + GroupHandle).

    Phase 3-2 surfaces only ``id``/``role``/``semantic``. Phase 3-3 adds
    anchor points (``top_center``, ``midpoint``, etc.) and ``bounds``.
    """

    id: str
    role: str | None = None
    semantic: str | None = None


class _PrimitiveMixin:
    """Shared ``add_*`` methods for ``Canvas`` and ``GroupHandle``.

    Subclasses must expose two attributes:

    - ``_root``: a ``Canvas`` instance — owns the (shared) id counter and
      flat ``_dictionary`` mapping. ``Canvas`` sets this to ``self``;
      ``GroupHandle`` stores the owning canvas.
    - ``_elements``: the ``list[dict]`` to which this primitive's element
      dicts get appended. For ``Canvas`` it's the top-level elements
      list; for ``GroupHandle`` it's the ``elements`` slot of the group's
      ``svg_group`` dict (mutated in-place via list aliasing).

    The dictionary is intentionally flat — children of a group register
    in the owning canvas's dictionary so the teaching agent can target
    them by role exactly like a top-level element. This matches the
    direct-JSON convention.
    """

    _root: Canvas
    _elements: list[dict[str, Any]]

    # ── shapes ─────────────────────────────────────────────────────

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
        element_id = id or self._root._next_id("line")
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
        self._root._register(element_id, role, semantic)
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
        element_id = id or self._root._next_id("rect")
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
        self._root._register(element_id, role, semantic)
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
        element_id = id or self._root._next_id("circle")
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
        self._root._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_ellipse(
        self,
        center: Point,
        rx: float,
        ry: float,
        *,
        id: str | None = None,
        stroke: str = DEFAULT_INK,
        stroke_width: float = DEFAULT_STROKE_WIDTH,
        fill: str = "none",
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        element_id = id or self._root._next_id("ellipse")
        self._elements.append(
            {
                "type": "svg_ellipse",
                "id": element_id,
                "cx": float(center[0]),
                "cy": float(center[1]),
                "rx": float(rx),
                "ry": float(ry),
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "fill": fill,
            }
        )
        self._root._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_arc(
        self,
        center: Point,
        radius: float,
        start_angle_deg: float,
        end_angle_deg: float,
        *,
        id: str | None = None,
        stroke: str = DEFAULT_INK,
        stroke_width: float = DEFAULT_STROKE_WIDTH,
        stroke_dasharray: str = "",
        fill: str = "none",
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        """Circular arc segment.

        Angles in **degrees**. 0° = positive x-axis (3 o'clock). Positive
        angles sweep clockwise in screen space (since SVG y grows down).
        These conventions match the frontend renderer exactly — angles
        you pass here are the angles the screen draws.
        """
        element_id = id or self._root._next_id("arc")
        self._elements.append(
            {
                "type": "svg_arc",
                "id": element_id,
                "cx": float(center[0]),
                "cy": float(center[1]),
                "r": float(radius),
                "startAngle": float(start_angle_deg),
                "endAngle": float(end_angle_deg),
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
                "fill": fill,
            }
        )
        self._root._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_path(
        self,
        d: str,
        *,
        id: str | None = None,
        stroke: str = DEFAULT_INK,
        stroke_width: float = DEFAULT_STROKE_WIDTH,
        stroke_dasharray: str = "",
        fill: str = "none",
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        """Raw SVG path. ``d`` is the standard ``d=`` attribute string."""
        element_id = id or self._root._next_id("path")
        self._elements.append(
            {
                "type": "svg_path",
                "id": element_id,
                "d": d,
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
                "fill": fill,
            }
        )
        self._root._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    # ── text + math ─────────────────────────────────────────────────

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
        element_id = id or self._root._next_id("text")
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
        self._root._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    def add_latex(
        self,
        position: Point,
        expression: str,
        *,
        id: str | None = None,
        font_size: float = 16,
        color: str = DEFAULT_INK,
        role: str | None = None,
        semantic: str | None = None,
    ) -> ElementHandle:
        """KaTeX math at a pixel position.

        ``expression`` is a LaTeX string — author it as a Python raw
        string (``r"\\frac{1}{2}"``) so backslashes survive the trip to
        the frontend's KaTeX renderer without doubling.
        """
        element_id = id or self._root._next_id("latex")
        self._elements.append(
            {
                "type": "svg_latex",
                "id": element_id,
                "expression": expression,
                "x": float(position[0]),
                "y": float(position[1]),
                "fontSize": float(font_size),
                "color": color,
            }
        )
        self._root._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    # ── vector arrow ─────────────────────────────────────────────────

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
        element_id = id or self._root._next_id("arrow")
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
        self._root._register(element_id, role, semantic)
        return ElementHandle(id=element_id, role=role, semantic=semantic)

    # ── composites: group + graph ────────────────────────────────────

    def add_group(
        self,
        *,
        transform: str = "",
        id: str | None = None,
        role: str | None = None,
        semantic: str | None = None,
    ) -> GroupHandle:
        """Group children under an SVG ``transform``.

        The returned ``GroupHandle`` exposes the same ``add_*`` surface
        as the canvas (including ``add_group`` itself, so groups can
        nest). Children of the group register in the **flat** top-level
        dictionary so annotation targeting works on nested elements the
        same way it does on top-level elements.
        """
        element_id = id or self._root._next_id("group")
        children: list[dict[str, Any]] = []
        self._elements.append(
            {
                "type": "svg_group",
                "id": element_id,
                "transform": transform,
                "elements": children,
            }
        )
        self._root._register(element_id, role, semantic)
        return GroupHandle(_root=self._root, _elements=children, id=element_id)

    def add_graph(
        self,
        position: Point,
        width: float,
        height: float,
        *,
        id: str | None = None,
        x_domain: tuple[float, float] = (-10, 10),
        y_domain: tuple[float, float] = (-10, 10),
        x_label: str = "",
        y_label: str = "",
        background_color: str = "#14141b",
        border_color: str = "#2a2a3a",
        show_grid: bool = True,
        role: str | None = None,
        semantic: str | None = None,
    ) -> GraphHandle:
        """Inset plot with axes and curves at a pixel position.

        Curves are added via the returned ``GraphHandle.add_curve``. Curve
        expressions are evaluated **client-side as JavaScript math** —
        write ``"sin(x)"`` not ``"math.sin(x)"``. Built-in names: ``sin``,
        ``cos``, ``tan``, ``sqrt``, ``abs``, ``PI``, ``E``, ``log``,
        ``exp``, ``pow``, ``floor``, ``ceil``, ``min``, ``max``.
        """
        element_id = id or self._root._next_id("graph")
        curves: list[dict[str, Any]] = []
        self._elements.append(
            {
                "type": "graph",
                "id": element_id,
                "x": float(position[0]),
                "y": float(position[1]),
                "width": float(width),
                "height": float(height),
                "xDomain": (float(x_domain[0]), float(x_domain[1])),
                "yDomain": (float(y_domain[0]), float(y_domain[1])),
                "xLabel": x_label,
                "yLabel": y_label,
                "backgroundColor": background_color,
                "borderColor": border_color,
                "showGrid": show_grid,
                "curves": curves,
            }
        )
        self._root._register(element_id, role, semantic)
        return GraphHandle(_curves=curves, id=element_id)


@dataclass
class GroupHandle(_PrimitiveMixin):
    """Container handle returned by ``Canvas.add_group``.

    Owns a child-element list; primitive calls append into it. The
    enclosing canvas's id counter and dictionary are shared via
    ``_root``, so children's IDs stay globally unique and their
    role/semantic metadata lands in the top-level dictionary.
    """

    _root: Canvas
    _elements: list[dict[str, Any]]
    id: str


@dataclass
class GraphHandle:
    """Handle returned by ``Canvas.add_graph`` for adding curves."""

    _curves: list[dict[str, Any]]
    id: str

    def add_curve(
        self,
        expression: str,
        *,
        color: str = "#7fd4ff",
        stroke_width: float = 2.0,
    ) -> None:
        """Add a JS-math curve. ``x`` is the independent variable."""
        self._curves.append(
            {
                "expression": expression,
                "color": color,
                "strokeWidth": float(stroke_width),
            }
        )


@dataclass
class Canvas(_PrimitiveMixin):
    """Diagram-authoring surface backed by the existing DiagramSpec wire format.

    Usage from sandbox code::

        canvas = Canvas(title="Right triangle")
        canvas.add_line(start=(100, 400), end=(400, 400), role="adjacent")
        canvas.add_line(start=(400, 400), end=(400, 100), role="opposite")
        canvas.add_line(start=(100, 400), end=(400, 100), role="hypotenuse")
        canvas.add_text(position=(250, 420), text="adjacent")

    The sandbox captures the ``canvas`` instance after the script runs
    and calls ``.export()`` to obtain the wire-format dict.
    """

    width: int = 900
    height: int = 650
    title: str = "Untitled Diagram"
    description: str = ""
    background_color: str = DEFAULT_BG
    _elements: list[dict[str, Any]] = field(default_factory=list)
    _dictionary: dict[str, dict[str, Any]] = field(default_factory=dict)
    _id_counter: int = 0

    def __post_init__(self) -> None:
        # ``_PrimitiveMixin`` reads ``self._root``; for ``Canvas``, that's self.
        self._root = self

    # ------------------------------------------------------------------
    # ID generation + dictionary registration (shared via ``_root``)
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

        Phase 3-4 will make ``role`` mandatory and auto-derive ``semantic``
        when missing. For now we keep it optional so existing direct-JSON
        parity is preserved.
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
