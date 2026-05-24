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


# ── composite handles (Phase 3-5) ─────────────────────────────────
#
# Each composite handle inherits from ``ElementHandle`` so
# ``isinstance(h, ElementHandle)`` keeps holding for downstream code.
# The handle's ``id`` is the wrapping group's id — composites create a
# transparent ``svg_group`` so annotation can target the whole composite
# AND any of its sub-elements by role. Sub-handles are exposed as named
# fields so callers can write ``fbd.weight.midpoint`` or ``lens.f``.


@dataclass(kw_only=True)
class RightTriangleHandle(ElementHandle):
    """Handle for ``add_right_triangle`` — three legs + right-angle marker."""

    adjacent: LineHandle
    opposite: LineHandle
    hypotenuse: LineHandle
    right_angle_marker: RectHandle
    corner_right_angle: Point
    corner_adjacent: Point
    corner_opposite: Point
    centroid: Point


@dataclass(kw_only=True)
class FreeBodyHandle(ElementHandle):
    """Handle for ``add_free_body_diagram`` — object box + force arrows + labels.

    Convenience properties (``weight``, ``normal_force``, ``applied_force``)
    look up canonical force names in ``forces``; they return ``None`` if
    the named force wasn't passed.
    """

    box: RectHandle
    forces: dict[str, ArrowHandle]
    labels: dict[str, ElementHandle]
    center: Point
    top: Point
    bottom: Point
    left: Point
    right: Point

    @property
    def weight(self) -> ArrowHandle | None:
        return self.forces.get("mg") or self.forces.get("weight")

    @property
    def normal_force(self) -> ArrowHandle | None:
        return self.forces.get("N") or self.forces.get("normal_force")

    @property
    def applied_force(self) -> ArrowHandle | None:
        return self.forces.get("F") or self.forces.get("applied_force")


@dataclass(kw_only=True)
class RayHandle(ElementHandle):
    """Handle for ``add_ray`` — a directed segment from a point at an angle."""

    shaft: ElementHandle  # ``LineHandle`` or ``ArrowHandle`` depending on ``arrow=``
    start: Point
    end: Point
    midpoint: Point
    angle_deg: float
    length: float

    def point_at(self, t: float) -> Point:
        """Point on the ray at parameter ``t`` ∈ [0, 1]."""
        return (
            self.start[0] + t * (self.end[0] - self.start[0]),
            self.start[1] + t * (self.end[1] - self.start[1]),
        )


@dataclass(kw_only=True)
class LensHandle(ElementHandle):
    """Handle for ``add_lens`` — biconvex/biconcave body + principal axis + focal points."""

    body: ElementHandle
    axis: LineHandle
    optical_center: CircleHandle
    f_left: CircleHandle | None
    f_right: CircleHandle | None
    center: Point
    top: Point
    bottom: Point
    f: Point  # right focal point
    f_prime: Point  # left focal point (IGCSE convention)
    focal_length: float
    lens_type: str


@dataclass(kw_only=True)
class LewisAtomHandle:
    """Python-side container for one atom in a Lewis structure.

    Not an ``ElementHandle`` — the atom itself has no single SVG element,
    only its ``symbol_text`` glyph and its surrounding ``lone_pair_dots``.
    Use ``handle.lewis_structure.atoms[i].symbol_text`` to target the
    symbol; the dots are individual ``CircleHandle`` instances.
    """

    symbol: str
    position: Point
    symbol_text: ElementHandle
    lone_pair_dots: list[CircleHandle] = field(default_factory=list)


@dataclass(kw_only=True)
class LewisStructureHandle(ElementHandle):
    """Handle for ``add_lewis_structure`` — atoms (with lone pairs) + bonds."""

    atoms: list[LewisAtomHandle]
    bonds: list[LineHandle]
    centroid: Point


# ── private helpers (Phase 3-5) ───────────────────────────────────


_FORCE_COLOR_WEIGHT = "#ff7fc6"  # pink — gravity / weight
_FORCE_COLOR_NORMAL = "#7fd4ff"  # cyan — normal force (also default)
_FORCE_COLOR_APPLIED = "#9effc9"  # green — applied / contact force
_FORCE_COLOR_FRICTION = "#ffaf7f"  # orange — friction-family forces


def _route_force_color(name: str) -> str:
    """Pick a canonical color for a force by name.

    ``"mg"`` / ``"weight"`` → pink, ``"N"`` / anything containing
    ``"normal"`` → cyan, ``"F"`` / anything containing ``"applied"`` →
    green, ``"f_*"`` (friction family) → orange. Else cyan.
    """
    lower = name.lower()
    if name == "mg" or lower == "weight":
        return _FORCE_COLOR_WEIGHT
    if name == "N" or "normal" in lower:
        return _FORCE_COLOR_NORMAL
    if name == "F" or "applied" in lower:
        return _FORCE_COLOR_APPLIED
    if lower.startswith("f_"):
        return _FORCE_COLOR_FRICTION
    return _FORCE_COLOR_NORMAL


def _route_force_role(name: str) -> str:
    """Pick a canonical role for a force by name.

    Mirrors ``_route_force_color`` but returns role strings. Custom
    names (``"T"``, ``"F_friction"``, ...) keep their original name as
    the role.
    """
    lower = name.lower()
    if name == "mg" or lower == "weight":
        return "weight"
    if name == "N" or "normal" in lower:
        return "normal_force"
    if name == "F" or "applied" in lower:
        return "applied_force"
    return name


def _lens_path(center: Point, height: float, lens_type: str, focal_length: float) -> str:
    """SVG path ``d`` string for a biconvex (convex) or biconcave (concave) lens.

    Curvature is curriculum-neutral — the formula picks a visually
    balanced radius. Two arcs joined at the top and bottom of the lens
    body; ``sweep-flag=1`` bulges outward (convex), ``sweep-flag=0``
    bulges inward (concave).
    """
    cx, cy = center
    h = height
    r = max(focal_length * 2.5, h * 0.7)
    top = f"{cx},{cy - h / 2}"
    bot = f"{cx},{cy + h / 2}"
    if lens_type == "convex":
        return f"M {top} A {r},{r} 0 0,1 {bot} A {r},{r} 0 0,1 {top} Z"
    if lens_type == "concave":
        return f"M {top} A {r},{r} 0 0,0 {bot} A {r},{r} 0 0,0 {top} Z"
    raise ValueError(f"lens_type must be 'convex' or 'concave', got {lens_type!r}")


def _lone_pair_angles(
    atom_index: int,
    atoms: list[dict[str, Any]],
    bonds: list[dict[str, Any]],
    needed: int,
) -> list[float]:
    """Return up to ``needed`` screen-CW angles for lone-pair dot placement.

    Candidate directions are the four compass points {0°, 90°, 180°, 270°}.
    Any candidate within 45° of an existing bond's direction is blocked.
    Returns the first ``needed`` unblocked candidates (in compass order).
    """
    candidates: list[float] = [0.0, 90.0, 180.0, 270.0]
    ap = atoms[atom_index]["position"]
    blocked: set[float] = set()
    for bond in bonds:
        i, j = bond["between"]
        if atom_index == i:
            other = atoms[j]["position"]
        elif atom_index == j:
            other = atoms[i]["position"]
        else:
            continue
        dx, dy = other[0] - ap[0], other[1] - ap[1]
        bond_angle = math.degrees(math.atan2(dy, dx)) % 360.0
        for cand in candidates:
            diff = abs((bond_angle - cand + 180.0) % 360.0 - 180.0)
            if diff < 45.0:
                blocked.add(cand)
                break
    available = [c for c in candidates if c not in blocked]
    return available[:needed]


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

    # ── STEM composites (Phase 3-5) ─────────────────────────────────
    #
    # Each composite wraps a few primitives + geometric helpers under a
    # transparent ``svg_group`` (so the composite's role targets the
    # whole thing AND each sub-element keeps its own role for finer
    # annotation). Composites compose from primitives, never escape
    # registration, and never reach past the existing wire format.

    def add_right_triangle(
        self,
        *,
        origin: Point,
        legs: tuple[float, float],
        orientation: str = "right_up",
        right_angle_marker_size: float = 20,
        stroke: str = DEFAULT_INK,
        hypotenuse_stroke: str = "#7fd4ff",
        stroke_width: float = DEFAULT_STROKE_WIDTH,
        hypotenuse_stroke_width: float = 3,
        id: str | None = None,
        role: str | None = None,
        semantic: str | None = None,
    ) -> RightTriangleHandle:
        """A right triangle with adjacent + opposite + hypotenuse + right-angle marker.

        ``origin`` is the right-angle vertex. ``legs`` is
        ``(adjacent_length, opposite_length)`` in pixels. ``orientation``
        picks which screen quadrant the triangle occupies relative to
        the origin:

        - ``"right_up"`` (default): adjacent extends right, opposite up
        - ``"right_down"``: adjacent right, opposite down
        - ``"left_up"``: adjacent left, opposite up
        - ``"left_down"``: adjacent left, opposite down

        Sub-elements register with roles ``"adjacent"``, ``"opposite"``,
        ``"hypotenuse"``, ``"right_angle_marker"``. The composite itself
        registers under ``role`` (or the auto-generated id).
        """
        sign_map = {
            "right_up": (1.0, -1.0),
            "right_down": (1.0, 1.0),
            "left_up": (-1.0, -1.0),
            "left_down": (-1.0, 1.0),
        }
        if orientation not in sign_map:
            raise ValueError(f"orientation must be one of {sorted(sign_map)}, got {orientation!r}")
        sx_sign, sy_sign = sign_map[orientation]
        ox, oy = float(origin[0]), float(origin[1])
        a, b = float(legs[0]), float(legs[1])
        corner_adjacent: Point = (ox + sx_sign * a, oy)
        corner_opposite: Point = (ox, oy + sy_sign * b)
        centroid: Point = (
            (ox + corner_adjacent[0] + corner_opposite[0]) / 3.0,
            (oy + corner_adjacent[1] + corner_opposite[1]) / 3.0,
        )
        m = float(right_angle_marker_size)
        marker_tl: Point = (
            ox if sx_sign > 0 else ox - m,
            oy if sy_sign > 0 else oy - m,
        )

        composite_id = id or self._root._next_id("right_triangle")
        final_semantic = semantic or "a right triangle"
        group = self.add_group(id=composite_id, role=role, semantic=final_semantic)
        adjacent = group.add_line(
            start=(ox, oy),
            end=corner_adjacent,
            stroke=stroke,
            stroke_width=stroke_width,
            role="adjacent",
            semantic="the adjacent side",
        )
        opposite = group.add_line(
            start=(ox, oy),
            end=corner_opposite,
            stroke=stroke,
            stroke_width=stroke_width,
            role="opposite",
            semantic="the opposite side",
        )
        hypotenuse = group.add_line(
            start=corner_adjacent,
            end=corner_opposite,
            stroke=hypotenuse_stroke,
            stroke_width=hypotenuse_stroke_width,
            role="hypotenuse",
            semantic="the hypotenuse",
        )
        marker = group.add_rect(
            top_left=marker_tl,
            width=m,
            height=m,
            stroke=stroke,
            stroke_width=stroke_width,
            role="right_angle_marker",
            semantic="the right-angle marker",
        )
        return RightTriangleHandle(
            id=composite_id,
            role=role,
            semantic=semantic,
            adjacent=adjacent,
            opposite=opposite,
            hypotenuse=hypotenuse,
            right_angle_marker=marker,
            corner_right_angle=(ox, oy),
            corner_adjacent=corner_adjacent,
            corner_opposite=corner_opposite,
            centroid=centroid,
        )

    def add_free_body_diagram(
        self,
        *,
        center: Point,
        forces: list[dict[str, Any]],
        box_size: float = 80,
        box_stroke: str = DEFAULT_INK,
        id: str | None = None,
        role: str | None = None,
        semantic: str | None = None,
    ) -> FreeBodyHandle:
        """An FBD: square object box with force arrows + labels around it.

        Each ``forces`` entry is a dict with keys:

        - ``name`` (required, str): label and role-key (``"N"``, ``"mg"``,
          ``"F"``, ``"T"``, ``"F_friction"``, ...).
        - ``direction_deg`` (required, float): screen-CW; 0=right, 90=down,
          -90=up.
        - ``magnitude`` (optional, float, default 80): arrow length in pixels.
        - ``color`` (optional, str): overrides the name-based routing.
        - ``label_offset`` (optional, tuple): extra (dx, dy) past the arrow tip
          for the label.

        Color routing by name: ``mg``/``weight`` → pink, ``N``/``normal`` → cyan,
        ``F``/``applied`` → green, ``f_*`` (friction family) → orange.
        Convenience aliases: ``fbd.weight``, ``fbd.normal_force``, ``fbd.applied_force``.
        """
        cx, cy = float(center[0]), float(center[1])
        s = float(box_size)
        hs = s / 2.0

        composite_id = id or self._root._next_id("free_body")
        final_semantic = semantic or "a free body diagram"
        group = self.add_group(id=composite_id, role=role, semantic=final_semantic)

        box = group.add_rect(
            top_left=(cx - hs, cy - hs),
            width=s,
            height=s,
            stroke=box_stroke,
            role="object",
            semantic="the object",
        )

        force_handles: dict[str, ArrowHandle] = {}
        label_handles: dict[str, ElementHandle] = {}
        for spec in forces:
            name = str(spec["name"])
            direction_deg = float(spec["direction_deg"])
            magnitude = float(spec.get("magnitude", 80))
            color = spec.get("color") or _route_force_color(name)
            label_offset = spec.get("label_offset")
            force_role = _route_force_role(name)

            tip = polar((cx, cy), magnitude, direction_deg)
            arrow = group.add_arrow(
                start=(cx, cy),
                end=tip,
                stroke=color,
                role=force_role,
                semantic=f"the {name} force",
            )
            force_handles[name] = arrow

            if label_offset is not None:
                lx, ly = float(label_offset[0]), float(label_offset[1])
                label_pos = (tip[0] + lx, tip[1] + ly)
            else:
                extra = polar((0.0, 0.0), 14.0, direction_deg)
                label_pos = (tip[0] + extra[0], tip[1] + extra[1])
            label = group.add_text(
                position=label_pos,
                text=name,
                fill=color,
                role=f"{force_role}_label",
                semantic=f"label for {name}",
            )
            label_handles[name] = label

        return FreeBodyHandle(
            id=composite_id,
            role=role,
            semantic=semantic,
            box=box,
            forces=force_handles,
            labels=label_handles,
            center=(cx, cy),
            top=(cx, cy - hs),
            bottom=(cx, cy + hs),
            left=(cx - hs, cy),
            right=(cx + hs, cy),
        )

    def add_ray(
        self,
        *,
        from_point: Point,
        angle_deg: float,
        length: float,
        arrow: bool = True,
        stroke: str = "#7fd4ff",
        stroke_width: float = 2.5,
        stroke_dasharray: str = "",
        id: str | None = None,
        role: str | None = None,
        semantic: str | None = None,
    ) -> RayHandle:
        """A directed segment from ``from_point`` at ``angle_deg`` (screen-CW).

        With ``arrow=True`` (default), the segment is rendered with an
        arrowhead; with ``arrow=False``, it's a plain line. The end point
        is computed via ``polar`` — no need to type
        ``(x + cos(θ)*L, y + sin(θ)*L)``.
        """
        fx, fy = float(from_point[0]), float(from_point[1])
        ang = float(angle_deg)
        length_f = float(length)
        end = polar((fx, fy), length_f, ang)
        mid: Point = ((fx + end[0]) / 2.0, (fy + end[1]) / 2.0)

        composite_id = id or self._root._next_id("ray")
        final_semantic = semantic or "a ray"
        group = self.add_group(id=composite_id, role=role, semantic=final_semantic)

        shaft: ElementHandle
        if arrow:
            shaft = group.add_arrow(
                start=(fx, fy),
                end=end,
                stroke=stroke,
                stroke_width=stroke_width,
                stroke_dasharray=stroke_dasharray,
                role="ray_shaft",
                semantic="the ray",
            )
        else:
            shaft = group.add_line(
                start=(fx, fy),
                end=end,
                stroke=stroke,
                stroke_width=stroke_width,
                stroke_dasharray=stroke_dasharray,
                role="ray_shaft",
                semantic="the ray",
            )
        return RayHandle(
            id=composite_id,
            role=role,
            semantic=semantic,
            shaft=shaft,
            start=(fx, fy),
            end=end,
            midpoint=mid,
            angle_deg=ang,
            length=length_f,
        )

    def add_lens(
        self,
        *,
        center: Point,
        focal_length: float,
        height: float = 200,
        lens_type: str = "convex",
        axis_extent: float = 250,
        show_focal_points: bool = True,
        stroke: str = DEFAULT_INK,
        id: str | None = None,
        role: str | None = None,
        semantic: str | None = None,
    ) -> LensHandle:
        """A biconvex or biconcave lens with principal axis + focal points.

        ``lens_type`` is ``"convex"`` (biconvex, default) or ``"concave"``
        (biconcave). ``focal_length`` positions the focal-point dots at
        ``(center.x ± focal_length, center.y)``. Set
        ``show_focal_points=False`` to omit the dots; the F/F' anchor
        fields still resolve correctly.
        """
        if lens_type not in ("convex", "concave"):
            raise ValueError(f"lens_type must be 'convex' or 'concave', got {lens_type!r}")
        cx, cy = float(center[0]), float(center[1])
        fl = float(focal_length)
        h = float(height)
        ext = float(axis_extent)

        composite_id = id or self._root._next_id("lens")
        final_semantic = semantic or f"a {lens_type} lens"
        group = self.add_group(id=composite_id, role=role, semantic=final_semantic)

        body = group.add_path(
            d=_lens_path((cx, cy), h, lens_type, fl),
            stroke=stroke,
            stroke_width=2.5,
            role="lens_body",
            semantic=f"the {lens_type} lens body",
        )
        axis = group.add_line(
            start=(cx - ext, cy),
            end=(cx + ext, cy),
            stroke=stroke,
            stroke_width=1.5,
            stroke_dasharray="4 4",
            role="principal_axis",
            semantic="the principal axis",
        )
        optical_center = group.add_circle(
            center=(cx, cy),
            radius=4,
            stroke=stroke,
            fill=stroke,
            role="optical_center",
            semantic="the optical center",
        )

        f_left: CircleHandle | None = None
        f_right: CircleHandle | None = None
        if show_focal_points:
            f_left = group.add_circle(
                center=(cx - fl, cy),
                radius=4,
                stroke=stroke,
                fill=stroke,
                role="focal_point_left",
                semantic="the left focal point F'",
            )
            f_right = group.add_circle(
                center=(cx + fl, cy),
                radius=4,
                stroke=stroke,
                fill=stroke,
                role="focal_point_right",
                semantic="the right focal point F",
            )

        return LensHandle(
            id=composite_id,
            role=role,
            semantic=semantic,
            body=body,
            axis=axis,
            optical_center=optical_center,
            f_left=f_left,
            f_right=f_right,
            center=(cx, cy),
            top=(cx, cy - h / 2.0),
            bottom=(cx, cy + h / 2.0),
            f=(cx + fl, cy),
            f_prime=(cx - fl, cy),
            focal_length=fl,
            lens_type=lens_type,
        )

    def add_lewis_structure(
        self,
        *,
        atoms: list[dict[str, Any]],
        bonds: list[dict[str, Any]],
        atom_radius: float = 18,
        bond_length_hint: float = 80,
        stroke: str = DEFAULT_INK,
        id: str | None = None,
        role: str | None = None,
        semantic: str | None = None,
    ) -> LewisStructureHandle:
        """A Lewis (electron-dot) structure: atoms + single bonds + lone-pair dots.

        ``atoms`` is a list of dicts with keys ``symbol`` (str),
        ``position`` (tuple), and optional ``lone_pairs`` (int, default 0).
        ``bonds`` is a list of dicts with ``between`` (tuple of atom indices)
        and ``order`` (int — v0 supports order=1; higher orders fall back to a
        single line and emit no error).

        Atoms register with roles ``f"atom_{i}_{symbol}"``; bonds with
        ``f"bond_{i}"``; lone-pair dots with ``f"lone_pair_{atom_index}_<angle>_a/b"``.

        Methane (canonical case): one C at center, four H at compass points,
        ``lone_pairs=0`` everywhere. Water: one O with ``lone_pairs=2`` and
        two H atoms; dots auto-place on the two unoccupied compass directions.
        """
        if not atoms:
            raise ValueError("add_lewis_structure: at least one atom required")

        for k, bond in enumerate(bonds):
            i, j = bond["between"]
            if not (0 <= i < len(atoms) and 0 <= j < len(atoms)):
                raise ValueError(f"bond {k} between=({i}, {j}) out of range for {len(atoms)} atoms")
            if i == j:
                raise ValueError(f"bond {k} is a self-loop on atom {i}")

        positions = [(float(a["position"][0]), float(a["position"][1])) for a in atoms]

        composite_id = id or self._root._next_id("lewis_structure")
        final_semantic = semantic or "a Lewis structure"
        group = self.add_group(id=composite_id, role=role, semantic=final_semantic)

        # Bonds first so atom symbols visually cover the line endpoints.
        bond_handles: list[LineHandle] = []
        for k, bond in enumerate(bonds):
            i, j = bond["between"]
            pi = positions[i]
            pj = positions[j]
            dx, dy = pj[0] - pi[0], pj[1] - pi[1]
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-6:
                raise ValueError(f"bond {k} between coincident atoms {i} and {j}")
            shrink = min(float(atom_radius), seg_len / 3.0)
            ux, uy = dx / seg_len, dy / seg_len
            start = (pi[0] + ux * shrink, pi[1] + uy * shrink)
            end = (pj[0] - ux * shrink, pj[1] - uy * shrink)
            bh = group.add_line(
                start=start,
                end=end,
                stroke=stroke,
                stroke_width=2,
                role=f"bond_{k}",
                semantic=f"bond between {atoms[i]['symbol']} and {atoms[j]['symbol']}",
            )
            bond_handles.append(bh)

        # Atoms with lone-pair dots
        atom_handles: list[LewisAtomHandle] = []
        for idx, atom in enumerate(atoms):
            symbol = str(atom["symbol"])
            position = positions[idx]
            lone_pairs = int(atom.get("lone_pairs", 0))

            symbol_text = group.add_text(
                position=position,
                text=symbol,
                font_size=20,
                fill=stroke,
                font_weight="bold",
                role=f"atom_{idx}_{symbol}",
                semantic=f"atom {symbol} (index {idx})",
            )

            dot_handles: list[CircleHandle] = []
            if lone_pairs > 0:
                angles = _lone_pair_angles(idx, atoms, bonds, lone_pairs)
                radius = float(atom_radius) + 8.0
                for angle in angles:
                    pair_center = polar(position, radius, angle)
                    perp = polar((0.0, 0.0), 3.0, angle + 90.0)
                    d1: Point = (
                        pair_center[0] - perp[0],
                        pair_center[1] - perp[1],
                    )
                    d2: Point = (
                        pair_center[0] + perp[0],
                        pair_center[1] + perp[1],
                    )
                    ang_key = round(angle)
                    ch1 = group.add_circle(
                        center=d1,
                        radius=1.5,
                        stroke=stroke,
                        fill=stroke,
                        role=f"lone_pair_{idx}_{ang_key}_a",
                        semantic=f"lone-pair electron on {symbol}",
                    )
                    ch2 = group.add_circle(
                        center=d2,
                        radius=1.5,
                        stroke=stroke,
                        fill=stroke,
                        role=f"lone_pair_{idx}_{ang_key}_b",
                        semantic=f"lone-pair electron on {symbol}",
                    )
                    dot_handles.extend([ch1, ch2])

            atom_handles.append(
                LewisAtomHandle(
                    symbol=symbol,
                    position=position,
                    symbol_text=symbol_text,
                    lone_pair_dots=dot_handles,
                )
            )

        cx_sum = sum(p[0] for p in positions) / len(positions)
        cy_sum = sum(p[1] for p in positions) / len(positions)
        return LewisStructureHandle(
            id=composite_id,
            role=role,
            semantic=semantic,
            atoms=atom_handles,
            bonds=bond_handles,
            centroid=(cx_sum, cy_sum),
        )


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
