"""Python DSL for diagram authoring — compiles to existing DiagramSpec JSON.

Used by the design agent's Python-sandbox path (Phase 3 of
`docs/design/16-diagram-awareness-rearchitecture.md`). The LLM authors a
small Python script using this library; the sandbox executes it; the
library produces a dict matching ``design_agent/backend/schema.py:DiagramSpec``
which flows to the frontend through the existing wire format unchanged.

Phase 3-3 (this revision) adds module-level geometric helpers
(``midpoint``, ``polar``, ``perpendicular_to``, ``parallel_at_distance``,
``intersect``, ``tangent_to``) and per-shape ``ElementHandle`` subclasses
that surface anchor points (``rect.top_center``, ``circle.boundary_at_angle``,
``line.midpoint``, etc.). Together these let the LLM compose parametric
scenes exactly — the "precision payoff" the Python path was built for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]

DEFAULT_INK = "#e8e8ee"
DEFAULT_BG = "transparent"
DEFAULT_STROKE_WIDTH = 2.0


# ── geometric helpers ─────────────────────────────────────────────
#
# Convention (one place, applies to every helper, anchor, and primitive
# below): angles in **degrees**, 0° = +x axis (right), positive sweep
# clockwise on screen (because SVG y grows down). ``polar`` and
# ``CircleHandle.boundary_at_angle`` agree with ``add_arc``.
#
# The ``side`` argument (``perpendicular_to``, ``parallel_at_distance``,
# ``tangent_to``) refers to which side of the reference direction the
# result sits on. ``side="left"`` is the **screen-up** side for a
# left-to-right reference direction — matches the physics intuition for
# "normal force on top of an inclined surface."


def midpoint(p1: Point, p2: Point) -> Point:
    """Arithmetic midpoint of segment p1→p2."""
    return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)


def polar(center: Point, radius: float, angle_deg: float) -> Point:
    """Point at ``radius`` from ``center`` at ``angle_deg``.

    0° = right, +90° = screen-down (matches ``add_arc`` and the frontend
    ``arcPath`` helper).
    """
    theta = math.radians(angle_deg)
    return (
        center[0] + radius * math.cos(theta),
        center[1] + radius * math.sin(theta),
    )


def _unit_perpendicular(p1: Point, p2: Point, side: str) -> Point:
    """Unit perpendicular to the p1→p2 direction. Internal."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-12:
        raise ValueError("perpendicular direction undefined: p1 and p2 are coincident")
    ux, uy = dx / length, dy / length
    # "left" of unit direction (ux, uy) in screen space (y-down) is
    # (uy, -ux). For a left-to-right direction (1, 0), that's (0, -1) —
    # screen-up, matching the "normal force on top of an incline" convention.
    if side == "left":
        return (uy, -ux)
    if side == "right":
        return (-uy, ux)
    raise ValueError(f"side must be 'left' or 'right', got {side!r}")


def perpendicular_to(
    p1: Point,
    p2: Point,
    base: Point,
    length: float,
    side: str = "left",
) -> Point:
    """Endpoint of a perpendicular vector anchored at ``base``.

    The vector is perpendicular to the ``p1→p2`` direction, has the
    given ``length``, and sits on the chosen ``side`` (``"left"`` is
    screen-up for a left-to-right reference direction). Drops in as the
    ``end=`` argument of ``add_arrow`` for normal-force or
    perpendicular-velocity diagrams.
    """
    perp = _unit_perpendicular(p1, p2, side)
    return (base[0] + perp[0] * length, base[1] + perp[1] * length)


def parallel_at_distance(
    p1: Point,
    p2: Point,
    distance: float,
    side: str = "left",
) -> tuple[Point, Point]:
    """Endpoints of a segment parallel to ``p1→p2``, offset by ``distance``.

    The offset direction follows ``side`` semantics (``"left"`` = screen-up
    for a left-to-right reference direction).
    """
    perp = _unit_perpendicular(p1, p2, side)
    ox, oy = perp[0] * distance, perp[1] * distance
    return ((p1[0] + ox, p1[1] + oy), (p2[0] + ox, p2[1] + oy))


def intersect(
    line1: tuple[Point, Point],
    line2: tuple[Point, Point],
) -> Point:
    """Intersection of two infinite lines (each defined by two points).

    Raises ``ValueError`` on parallel or coincident lines (the sandbox
    surfaces this as a clear ``SandboxError``).
    """
    (x1, y1), (x2, y2) = line1
    (x3, y3), (x4, y4) = line2
    det = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(det) < 1e-9:
        raise ValueError("intersect: lines are parallel or coincident")
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / det
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def tangent_to(
    circle_center: Point,
    radius: float,
    external_point: Point,
    side: str = "left",
) -> Point:
    """Tangent contact point on the circle from an external point.

    Two tangent lines exist from any external point; ``side`` picks one.
    ``"left"`` is the tangent on the screen-up side of the external→center
    direction (for a left-to-right external→center direction). Raises
    ``ValueError`` if the external point is inside the circle
    (``|external_point - center| < radius``).
    """
    cx, cy = circle_center
    px, py = external_point
    dx, dy = cx - px, cy - py
    d = math.hypot(dx, dy)
    if d < radius:
        raise ValueError(f"tangent_to: external_point distance {d:.6f} < radius {radius:.6f}")
    if d < 1e-12:
        raise ValueError("tangent_to: external_point coincides with circle center")
    # Boundary case d == radius: tangent point IS the external point; the
    # formula below returns external_point cleanly because ``leg`` is zero.
    leg = math.sqrt(max(0.0, d * d - radius * radius))
    ux, uy = dx / d, dy / d  # unit external → center
    if side == "left":
        wx, wy = uy, -ux
    elif side == "right":
        wx, wy = -uy, ux
    else:
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")
    cos_alpha = leg / d
    sin_alpha = radius / d
    return (
        px + leg * cos_alpha * ux + leg * sin_alpha * wx,
        py + leg * cos_alpha * uy + leg * sin_alpha * wy,
    )


# ── handles ───────────────────────────────────────────────────────


@dataclass
class ElementHandle:
    """Reference returned by every primitive call (base class).

    Subclasses below add anchor-point fields (frozen at construction
    time, no cost to read repeatedly). ``isinstance(h, ElementHandle)``
    holds for every handle the library returns, so existing
    annotation-targeting code keeps working unchanged.
    """

    id: str
    role: str | None = None
    semantic: str | None = None


@dataclass(kw_only=True)
class RectHandle(ElementHandle):
    """Handle for ``add_rect`` with nine corner/edge anchor points."""

    top_left: Point
    top_center: Point
    top_right: Point
    middle_left: Point
    center: Point
    middle_right: Point
    bottom_left: Point
    bottom_center: Point
    bottom_right: Point


@dataclass(kw_only=True)
class CircleHandle(ElementHandle):
    """Handle for ``add_circle`` with cardinal anchors + boundary lookup."""

    center: Point
    top: Point
    right: Point
    bottom: Point
    left: Point
    radius: float

    def boundary_at_angle(self, angle_deg: float) -> Point:
        """Point on the circle boundary at ``angle_deg``.

        0° = right; +90° = screen-down (matches ``polar`` and ``add_arc``).
        """
        return polar(self.center, self.radius, angle_deg)


@dataclass(kw_only=True)
class EllipseHandle(ElementHandle):
    """Handle for ``add_ellipse`` with cardinal anchors + parametric boundary."""

    center: Point
    top: Point
    right: Point
    bottom: Point
    left: Point
    rx: float
    ry: float

    def boundary_at_angle(self, angle_deg: float) -> Point:
        """Parametric point on the ellipse boundary at ``angle_deg``.

        Computes ``(cx + rx·cos θ, cy + ry·sin θ)`` — the parametric
        position, not the geodesic-angle position. Good enough for label
        placement and angle-marker anchors.
        """
        theta = math.radians(angle_deg)
        return (
            self.center[0] + self.rx * math.cos(theta),
            self.center[1] + self.ry * math.sin(theta),
        )


@dataclass(kw_only=True)
class LineHandle(ElementHandle):
    """Handle for ``add_line`` with endpoint + midpoint + parametric lookup."""

    start: Point
    end: Point
    midpoint: Point

    def point_at(self, t: float) -> Point:
        """Point on the line at parameter ``t`` ∈ [0, 1]."""
        return (
            self.start[0] + t * (self.end[0] - self.start[0]),
            self.start[1] + t * (self.end[1] - self.start[1]),
        )


@dataclass(kw_only=True)
class ArcHandle(ElementHandle):
    """Handle for ``add_arc`` with endpoint anchors + arc parameters."""

    center: Point
    radius: float
    start_angle_deg: float
    end_angle_deg: float
    start: Point
    end: Point


@dataclass(kw_only=True)
class ArrowHandle(ElementHandle):
    """Handle for ``add_arrow`` — mirrors ``LineHandle`` (start, end, midpoint)."""

    start: Point
    end: Point
    midpoint: Point

    def point_at(self, t: float) -> Point:
        return (
            self.start[0] + t * (self.end[0] - self.start[0]),
            self.start[1] + t * (self.end[1] - self.start[1]),
        )


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
    ) -> LineHandle:
        element_id = id or self._root._next_id("line")
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        self._elements.append(
            {
                "type": "svg_line",
                "id": element_id,
                "x1": sx,
                "y1": sy,
                "x2": ex,
                "y2": ey,
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
            }
        )
        self._root._register(element_id, role, semantic)
        return LineHandle(
            id=element_id,
            role=role,
            semantic=semantic,
            start=(sx, sy),
            end=(ex, ey),
            midpoint=((sx + ex) / 2.0, (sy + ey) / 2.0),
        )

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
    ) -> RectHandle:
        element_id = id or self._root._next_id("rect")
        x, y = float(top_left[0]), float(top_left[1])
        w, h = float(width), float(height)
        self._elements.append(
            {
                "type": "svg_rect",
                "id": element_id,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "fill": fill,
                "rx": float(corner_radius),
            }
        )
        self._root._register(element_id, role, semantic)
        hw, hh = w / 2.0, h / 2.0
        return RectHandle(
            id=element_id,
            role=role,
            semantic=semantic,
            top_left=(x, y),
            top_center=(x + hw, y),
            top_right=(x + w, y),
            middle_left=(x, y + hh),
            center=(x + hw, y + hh),
            middle_right=(x + w, y + hh),
            bottom_left=(x, y + h),
            bottom_center=(x + hw, y + h),
            bottom_right=(x + w, y + h),
        )

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
    ) -> CircleHandle:
        element_id = id or self._root._next_id("circle")
        cx, cy = float(center[0]), float(center[1])
        r = float(radius)
        self._elements.append(
            {
                "type": "svg_circle",
                "id": element_id,
                "cx": cx,
                "cy": cy,
                "r": r,
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
                "fill": fill,
            }
        )
        self._root._register(element_id, role, semantic)
        return CircleHandle(
            id=element_id,
            role=role,
            semantic=semantic,
            center=(cx, cy),
            top=(cx, cy - r),
            right=(cx + r, cy),
            bottom=(cx, cy + r),
            left=(cx - r, cy),
            radius=r,
        )

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
    ) -> EllipseHandle:
        element_id = id or self._root._next_id("ellipse")
        cx, cy = float(center[0]), float(center[1])
        rx_f, ry_f = float(rx), float(ry)
        self._elements.append(
            {
                "type": "svg_ellipse",
                "id": element_id,
                "cx": cx,
                "cy": cy,
                "rx": rx_f,
                "ry": ry_f,
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "fill": fill,
            }
        )
        self._root._register(element_id, role, semantic)
        return EllipseHandle(
            id=element_id,
            role=role,
            semantic=semantic,
            center=(cx, cy),
            top=(cx, cy - ry_f),
            right=(cx + rx_f, cy),
            bottom=(cx, cy + ry_f),
            left=(cx - rx_f, cy),
            rx=rx_f,
            ry=ry_f,
        )

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
    ) -> ArcHandle:
        """Circular arc segment.

        Angles in **degrees**. 0° = positive x-axis (3 o'clock). Positive
        angles sweep clockwise in screen space (since SVG y grows down).
        These conventions match the frontend renderer exactly — angles
        you pass here are the angles the screen draws.
        """
        element_id = id or self._root._next_id("arc")
        cx, cy = float(center[0]), float(center[1])
        r = float(radius)
        sa, ea = float(start_angle_deg), float(end_angle_deg)
        self._elements.append(
            {
                "type": "svg_arc",
                "id": element_id,
                "cx": cx,
                "cy": cy,
                "r": r,
                "startAngle": sa,
                "endAngle": ea,
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
                "fill": fill,
            }
        )
        self._root._register(element_id, role, semantic)
        return ArcHandle(
            id=element_id,
            role=role,
            semantic=semantic,
            center=(cx, cy),
            radius=r,
            start_angle_deg=sa,
            end_angle_deg=ea,
            start=polar((cx, cy), r, sa),
            end=polar((cx, cy), r, ea),
        )

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
    ) -> ArrowHandle:
        element_id = id or self._root._next_id("arrow")
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        self._elements.append(
            {
                "type": "svg_arrow",
                "id": element_id,
                "x1": sx,
                "y1": sy,
                "x2": ex,
                "y2": ey,
                "stroke": stroke,
                "strokeWidth": float(stroke_width),
                "strokeDasharray": stroke_dasharray,
            }
        )
        self._root._register(element_id, role, semantic)
        return ArrowHandle(
            id=element_id,
            role=role,
            semantic=semantic,
            start=(sx, sy),
            end=(ex, ey),
            midpoint=((sx + ex) / 2.0, (sy + ey) / 2.0),
        )

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
        """Always add a dictionary entry; auto-derive role/semantic when omitted.

        Phase 3-4 closes the loop on annotation targeting: every element
        gets a dictionary entry, so the fail-loud annotation tools always
        have something to resolve. Explicit ``role``/``semantic`` from the
        caller still win; when omitted, we fall back to:

        - ``role`` = the auto-generated ``element_id`` (e.g. ``"circle_3"``)
        - ``semantic`` = ``f"a {type_short}"`` from the id's prefix (e.g. ``"a circle"``)
        """
        type_short = element_id.rsplit("_", 1)[0] if "_" in element_id else element_id
        final_role = role or element_id
        final_semantic = semantic or role or f"a {type_short}"
        self._dictionary[element_id] = {
            "role": final_role,
            "semantic": final_semantic,
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
