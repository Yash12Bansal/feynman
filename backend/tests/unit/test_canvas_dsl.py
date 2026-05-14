"""Tests for the Python diagram DSL (Phase 3-1).

Verifies that primitives emit valid DiagramSpec dicts (validated against
the real design_agent schema) and that the dictionary is populated when
roles are supplied.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from feynman.visuals.canvas_dsl import (
    ArcHandle,
    ArrowHandle,
    Canvas,
    CircleHandle,
    ElementHandle,
    EllipseHandle,
    LineHandle,
    RectHandle,
    intersect,
    midpoint,
    parallel_at_distance,
    perpendicular_to,
    polar,
    tangent_to,
)


def _load_design_agent_schema():
    schema_path = Path(__file__).resolve().parents[3] / "design_agent" / "backend" / "schema.py"
    if not schema_path.exists():
        pytest.skip(f"design_agent schema not present at {schema_path}")
    spec = importlib.util.spec_from_file_location("design_agent_schema_for_dsl", schema_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["design_agent_schema_for_dsl"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


schema_module = _load_design_agent_schema()
DiagramSpec = schema_module.DiagramSpec


# ── Canvas basics ─────────────────────────────────────────────────


def test_empty_canvas_exports_valid_diagram_spec() -> None:
    canvas = Canvas()
    spec = canvas.export()
    validated = DiagramSpec.model_validate(spec)
    assert validated.elements == []
    assert validated.dictionary == {}


def test_canvas_dimensions_and_title_round_trip() -> None:
    canvas = Canvas(width=1024, height=768, title="Right triangle", description="Adj/opp/hyp")
    spec = canvas.export()
    assert spec["width"] == 1024
    assert spec["height"] == 768
    assert spec["title"] == "Right triangle"
    assert spec["description"] == "Adj/opp/hyp"


# ── Primitives ────────────────────────────────────────────────────


def test_add_line_emits_svg_line_and_returns_handle() -> None:
    canvas = Canvas()
    handle = canvas.add_line(start=(100, 200), end=(300, 400), role="hyp", semantic="hypotenuse")
    assert isinstance(handle, ElementHandle)
    assert handle.role == "hyp"

    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    line = spec["elements"][0]
    assert line["type"] == "svg_line"
    assert line["x1"] == 100.0 and line["y1"] == 200.0
    assert line["x2"] == 300.0 and line["y2"] == 400.0
    assert spec["dictionary"][handle.id]["role"] == "hyp"
    assert spec["dictionary"][handle.id]["semantic"] == "hypotenuse"


def test_add_rect_emits_svg_rect_with_top_left_anchor() -> None:
    canvas = Canvas()
    canvas.add_rect(top_left=(50, 75), width=120, height=80, corner_radius=4)
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    rect = spec["elements"][0]
    assert rect["type"] == "svg_rect"
    assert rect["x"] == 50.0 and rect["y"] == 75.0
    assert rect["width"] == 120.0 and rect["height"] == 80.0
    assert rect["rx"] == 4.0


def test_add_circle_emits_svg_circle() -> None:
    canvas = Canvas()
    canvas.add_circle(center=(450, 325), radius=80)
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    circle = spec["elements"][0]
    assert circle["type"] == "svg_circle"
    assert circle["cx"] == 450.0 and circle["cy"] == 325.0
    assert circle["r"] == 80.0


def test_add_text_emits_svg_text() -> None:
    canvas = Canvas()
    canvas.add_text(position=(250, 420), text="adjacent", font_size=11, text_anchor="start")
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    text = spec["elements"][0]
    assert text["type"] == "svg_text"
    assert text["text"] == "adjacent"
    assert text["fontSize"] == 11.0
    assert text["textAnchor"] == "start"


def test_add_arrow_emits_svg_arrow() -> None:
    canvas = Canvas()
    canvas.add_arrow(start=(450, 325), end=(450, 200), stroke="#7fd4ff")
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    arrow = spec["elements"][0]
    assert arrow["type"] == "svg_arrow"
    assert arrow["x1"] == 450.0 and arrow["y1"] == 325.0
    assert arrow["x2"] == 450.0 and arrow["y2"] == 200.0
    assert arrow["stroke"] == "#7fd4ff"


# ── ID generation + dictionary registration ───────────────────────


def test_auto_generated_ids_are_unique() -> None:
    canvas = Canvas()
    h1 = canvas.add_line(start=(0, 0), end=(1, 1))
    h2 = canvas.add_line(start=(2, 2), end=(3, 3))
    h3 = canvas.add_circle(center=(5, 5), radius=2)
    assert len({h1.id, h2.id, h3.id}) == 3


def test_explicit_id_is_preserved() -> None:
    canvas = Canvas()
    handle = canvas.add_line(start=(0, 0), end=(1, 1), id="hypotenuse")
    assert handle.id == "hypotenuse"
    assert canvas.export()["elements"][0]["id"] == "hypotenuse"


def test_no_dictionary_entry_when_role_and_semantic_omitted() -> None:
    """Phase 3-1 keeps the dictionary opt-in; auto-population lands in 3-4."""
    canvas = Canvas()
    canvas.add_line(start=(0, 0), end=(1, 1))
    canvas.add_circle(center=(2, 2), radius=1)
    spec = canvas.export()
    assert spec["dictionary"] == {}


def test_dictionary_entry_uses_role_when_semantic_omitted() -> None:
    canvas = Canvas()
    handle = canvas.add_circle(center=(2, 2), radius=1, role="moon")
    spec = canvas.export()
    assert spec["dictionary"][handle.id]["role"] == "moon"
    # When semantic is omitted, falls back to role name.
    assert spec["dictionary"][handle.id]["semantic"] == "moon"


# ── Multi-element scenes ──────────────────────────────────────────


def test_right_triangle_scene_validates_against_diagram_spec() -> None:
    """End-to-end: a small scene round-trips through the real schema cleanly."""
    canvas = Canvas(title="Right triangle")
    canvas.add_line(start=(150, 450), end=(550, 450), role="adjacent")
    canvas.add_line(start=(550, 450), end=(550, 150), role="opposite")
    canvas.add_line(start=(150, 450), end=(550, 150), role="hypotenuse")
    canvas.add_rect(top_left=(530, 430), width=20, height=20, role="right_angle_marker")
    canvas.add_text(position=(350, 470), text="adjacent")

    spec = canvas.export()
    validated = DiagramSpec.model_validate(spec)
    assert len(validated.elements) == 5
    assert len(validated.dictionary) == 4  # the text has no role


# ── Phase 3-2: additional primitives ──────────────────────────────


def test_add_ellipse_emits_svg_ellipse() -> None:
    canvas = Canvas()
    handle = canvas.add_ellipse(center=(450, 325), rx=120, ry=60, role="orbit")
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    ell = spec["elements"][0]
    assert ell["type"] == "svg_ellipse"
    assert ell["cx"] == 450.0 and ell["cy"] == 325.0
    assert ell["rx"] == 120.0 and ell["ry"] == 60.0
    assert spec["dictionary"][handle.id]["role"] == "orbit"


def test_add_arc_emits_svg_arc_with_degree_angles() -> None:
    canvas = Canvas()
    canvas.add_arc(
        center=(150, 500),
        radius=40,
        start_angle_deg=0,
        end_angle_deg=-60,
        role="angle_marker",
    )
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    arc = spec["elements"][0]
    assert arc["type"] == "svg_arc"
    # Degrees pass through verbatim — frontend handles deg→rad conversion.
    assert arc["startAngle"] == 0.0
    assert arc["endAngle"] == -60.0
    assert arc["r"] == 40.0


def test_add_path_emits_svg_path_with_raw_d_attribute() -> None:
    canvas = Canvas()
    canvas.add_path(d="M 100 300 Q 200 200, 300 300 T 500 300", role="wave")
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    path = spec["elements"][0]
    assert path["type"] == "svg_path"
    assert path["d"] == "M 100 300 Q 200 200, 300 300 T 500 300"
    assert path["fill"] == "none"


def test_add_latex_emits_svg_latex_preserving_backslashes() -> None:
    """Python raw strings must reach the frontend with backslashes intact."""
    canvas = Canvas()
    canvas.add_latex(position=(450, 100), expression=r"\sin\theta = \frac{a}{b}", role="trig")
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    latex = spec["elements"][0]
    assert latex["type"] == "svg_latex"
    # Backslashes preserved (raw string in caller → no Python escape, no DSL doubling).
    assert latex["expression"] == r"\sin\theta = \frac{a}{b}"
    assert latex["fontSize"] == 16.0


# ── Phase 3-2: groups + nesting ───────────────────────────────────


def test_add_group_returns_handle_with_primitive_methods() -> None:
    canvas = Canvas()
    group = canvas.add_group(transform="translate(100, 50)", role="atom_H")
    group.add_circle(center=(0, 0), radius=20, stroke="#7fd4ff", role="nucleus")
    group.add_latex(position=(0, 6), expression=r"H", role="atom_label")

    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    # Top-level: one svg_group; inside it, two children
    assert len(spec["elements"]) == 1
    grp = spec["elements"][0]
    assert grp["type"] == "svg_group"
    assert grp["transform"] == "translate(100, 50)"
    assert len(grp["elements"]) == 2
    assert grp["elements"][0]["type"] == "svg_circle"
    assert grp["elements"][1]["type"] == "svg_latex"


def test_group_children_register_in_flat_top_level_dictionary() -> None:
    """Annotations target children by role exactly like top-level elements."""
    canvas = Canvas()
    group = canvas.add_group(role="atom")
    nucleus = group.add_circle(
        center=(0, 0), radius=20, role="nucleus", semantic="hydrogen nucleus"
    )
    label = group.add_latex(position=(0, 6), expression=r"H", role="atom_label")

    spec = canvas.export()
    # Dictionary is flat: group + 2 children all addressable
    assert spec["dictionary"][group.id]["role"] == "atom"
    assert spec["dictionary"][nucleus.id]["role"] == "nucleus"
    assert spec["dictionary"][nucleus.id]["semantic"] == "hydrogen nucleus"
    assert spec["dictionary"][label.id]["role"] == "atom_label"


def test_nested_groups_share_canvas_id_counter() -> None:
    """A group inside a group sees the same id counter as the canvas.

    The counter is monotonic and global (not per-prefix), so IDs across all
    primitive types stay unique regardless of how groups and primitives
    interleave. We just assert uniqueness, not specific numbering.
    """
    canvas = Canvas()
    canvas.add_line(start=(0, 0), end=(1, 1))
    outer = canvas.add_group(transform="translate(100, 0)")
    outer.add_group(transform="translate(50, 0)").add_line(start=(0, 0), end=(2, 2))

    all_ids: list[str] = []

    def walk(elements: list[dict]) -> None:
        for e in elements:
            all_ids.append(e["id"])
            if e["type"] == "svg_group":
                walk(e["elements"])

    walk(canvas.export()["elements"])
    # 1 line + 1 outer group + 1 inner group + 1 nested line = 4 unique IDs.
    assert len(all_ids) == 4
    assert len(set(all_ids)) == 4
    # Prefixes reflect element type, not insertion order.
    assert sum(1 for i in all_ids if i.startswith("line_")) == 2
    assert sum(1 for i in all_ids if i.startswith("group_")) == 2


# ── Phase 3-2: graph + curves ──────────────────────────────────────


def test_add_graph_returns_handle_for_curves() -> None:
    canvas = Canvas()
    graph = canvas.add_graph(
        position=(200, 150),
        width=500,
        height=300,
        x_domain=(-6.28, 6.28),
        y_domain=(-1.5, 1.5),
        role="sin_cos_plot",
    )
    graph.add_curve(expression="sin(x)", color="#7fd4ff")
    graph.add_curve(expression="cos(x)", color="#ff7fc6", stroke_width=3)

    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    g = spec["elements"][0]
    assert g["type"] == "graph"
    assert len(g["curves"]) == 2
    # Expressions pass through verbatim — they're evaluated as JS on the client.
    assert g["curves"][0]["expression"] == "sin(x)"
    assert g["curves"][1]["expression"] == "cos(x)"
    assert g["curves"][1]["strokeWidth"] == 3.0
    assert spec["dictionary"][graph.id]["role"] == "sin_cos_plot"


def test_graph_with_zero_curves_is_valid() -> None:
    """An empty plot — useful when the LLM wants to lay axes only."""
    canvas = Canvas()
    canvas.add_graph(position=(0, 0), width=100, height=100)
    spec = canvas.export()
    DiagramSpec.model_validate(spec)
    assert spec["elements"][0]["curves"] == []


# ── Cross-cutting ─────────────────────────────────────────────────


def test_auto_ids_unique_across_all_eleven_primitive_types() -> None:
    """Sweep: each primitive type has its own ID prefix; all globally unique."""
    canvas = Canvas()
    canvas.add_line(start=(0, 0), end=(1, 1))
    canvas.add_rect(top_left=(0, 0), width=10, height=10)
    canvas.add_circle(center=(0, 0), radius=5)
    canvas.add_ellipse(center=(0, 0), rx=10, ry=5)
    canvas.add_arc(center=(0, 0), radius=5, start_angle_deg=0, end_angle_deg=90)
    canvas.add_path(d="M 0 0 L 1 1")
    canvas.add_text(position=(0, 0), text="hi")
    canvas.add_latex(position=(0, 0), expression="x")
    canvas.add_arrow(start=(0, 0), end=(1, 1))
    canvas.add_group()
    canvas.add_graph(position=(0, 0), width=100, height=100)

    ids = [e["id"] for e in canvas.export()["elements"]]
    assert len(ids) == 11
    assert len(set(ids)) == 11
    # Spot-check prefixes
    prefixes = {i.split("_")[0] for i in ids}
    assert prefixes == {
        "line",
        "rect",
        "circle",
        "ellipse",
        "arc",
        "path",
        "text",
        "latex",
        "arrow",
        "group",
        "graph",
    }


# ── Phase 3-3: anchor points on handle subclasses ─────────────────


def test_add_rect_returns_rect_handle_with_nine_anchor_points() -> None:
    canvas = Canvas()
    handle = canvas.add_rect(top_left=(100, 200), width=80, height=60)
    assert isinstance(handle, RectHandle)
    assert isinstance(handle, ElementHandle)  # backward-compatible subclass
    # Corner anchors
    assert handle.top_left == (100.0, 200.0)
    assert handle.top_right == (180.0, 200.0)
    assert handle.bottom_left == (100.0, 260.0)
    assert handle.bottom_right == (180.0, 260.0)
    # Edge midpoints
    assert handle.top_center == (140.0, 200.0)
    assert handle.bottom_center == (140.0, 260.0)
    assert handle.middle_left == (100.0, 230.0)
    assert handle.middle_right == (180.0, 230.0)
    # Body center
    assert handle.center == (140.0, 230.0)


def test_add_circle_returns_circle_handle_with_cardinal_anchors() -> None:
    canvas = Canvas()
    handle = canvas.add_circle(center=(450, 325), radius=80)
    assert isinstance(handle, CircleHandle)
    assert handle.center == (450.0, 325.0)
    assert handle.radius == 80.0
    # Cardinal anchors: top is screen-up (negative y), right is +x, etc.
    assert handle.top == (450.0, 245.0)
    assert handle.right == (530.0, 325.0)
    assert handle.bottom == (450.0, 405.0)
    assert handle.left == (370.0, 325.0)


def test_circle_boundary_at_angle_uses_screen_cw_convention() -> None:
    """0° = right (matches `add_arc`); +90° = screen-down (because SVG y grows down)."""
    canvas = Canvas()
    handle = canvas.add_circle(center=(0, 0), radius=10)
    # 0° → right edge
    p0 = handle.boundary_at_angle(0)
    assert p0[0] == pytest.approx(10.0, abs=1e-9)
    assert p0[1] == pytest.approx(0.0, abs=1e-9)
    # +90° → screen-down edge (positive y)
    p90 = handle.boundary_at_angle(90)
    assert p90[0] == pytest.approx(0.0, abs=1e-9)
    assert p90[1] == pytest.approx(10.0, abs=1e-9)
    # -90° → screen-up edge (negative y)
    pm90 = handle.boundary_at_angle(-90)
    assert pm90[1] == pytest.approx(-10.0, abs=1e-9)


def test_add_ellipse_returns_ellipse_handle_with_parametric_boundary() -> None:
    canvas = Canvas()
    handle = canvas.add_ellipse(center=(0, 0), rx=20, ry=10)
    assert isinstance(handle, EllipseHandle)
    # Cardinal anchors: stretched by rx horizontally, ry vertically.
    assert handle.right == (20.0, 0.0)
    assert handle.bottom == (0.0, 10.0)
    # boundary_at_angle is parametric: (rx cos θ, ry sin θ)
    p45 = handle.boundary_at_angle(45)
    import math as _m

    assert p45[0] == pytest.approx(20 * _m.cos(_m.radians(45)), abs=1e-9)
    assert p45[1] == pytest.approx(10 * _m.sin(_m.radians(45)), abs=1e-9)


def test_add_line_returns_line_handle_with_midpoint_and_point_at() -> None:
    canvas = Canvas()
    handle = canvas.add_line(start=(0, 0), end=(10, 20))
    assert isinstance(handle, LineHandle)
    assert handle.start == (0.0, 0.0)
    assert handle.end == (10.0, 20.0)
    assert handle.midpoint == (5.0, 10.0)
    # point_at parameterization
    assert handle.point_at(0.0) == (0.0, 0.0)
    assert handle.point_at(0.5) == (5.0, 10.0)
    assert handle.point_at(1.0) == (10.0, 20.0)
    assert handle.point_at(0.25) == (2.5, 5.0)


def test_add_arc_returns_arc_handle_with_start_and_end_points() -> None:
    canvas = Canvas()
    # Quarter-arc from 0° (right edge) to 90° (screen-down edge) at radius 10
    handle = canvas.add_arc(center=(0, 0), radius=10, start_angle_deg=0, end_angle_deg=90)
    assert isinstance(handle, ArcHandle)
    assert handle.center == (0.0, 0.0)
    assert handle.radius == 10.0
    assert handle.start_angle_deg == 0.0
    assert handle.end_angle_deg == 90.0
    # start at 0° = right edge
    assert handle.start[0] == pytest.approx(10.0, abs=1e-9)
    assert handle.start[1] == pytest.approx(0.0, abs=1e-9)
    # end at +90° = screen-down edge
    assert handle.end[0] == pytest.approx(0.0, abs=1e-9)
    assert handle.end[1] == pytest.approx(10.0, abs=1e-9)


def test_add_arrow_returns_arrow_handle_with_midpoint() -> None:
    """ArrowHandle mirrors LineHandle so anchors don't surprise the LLM."""
    canvas = Canvas()
    handle = canvas.add_arrow(start=(0, 0), end=(100, 50))
    assert isinstance(handle, ArrowHandle)
    assert handle.midpoint == (50.0, 25.0)
    assert handle.point_at(0.5) == (50.0, 25.0)


# ── Phase 3-3: geometric helper math ──────────────────────────────


def test_midpoint_helper() -> None:
    assert midpoint((0, 0), (10, 20)) == (5.0, 10.0)
    assert midpoint((-4, 6), (4, -6)) == (0.0, 0.0)


def test_polar_helper_zero_degrees_is_right() -> None:
    p = polar((100, 200), 50, 0)
    assert p[0] == pytest.approx(150.0, abs=1e-9)
    assert p[1] == pytest.approx(200.0, abs=1e-9)


def test_polar_helper_ninety_degrees_is_screen_down() -> None:
    """+90° = screen-down (matches add_arc and the frontend arcPath helper)."""
    p = polar((100, 200), 50, 90)
    assert p[0] == pytest.approx(100.0, abs=1e-9)
    assert p[1] == pytest.approx(250.0, abs=1e-9)  # +50 in y = screen-down


def test_perpendicular_to_returns_endpoint_with_correct_length_and_orthogonality() -> None:
    """The vector from base→result is perpendicular to p1→p2 and has the given length."""
    p1, p2 = (0.0, 0.0), (10.0, 0.0)
    base = (5.0, 0.0)
    result = perpendicular_to(p1, p2, base=base, length=5.0)
    # Length from base
    import math as _m

    assert _m.hypot(result[0] - base[0], result[1] - base[1]) == pytest.approx(5.0, abs=1e-9)
    # Orthogonal to (p2 - p1)
    rx, ry = result[0] - base[0], result[1] - base[1]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    assert rx * dx + ry * dy == pytest.approx(0.0, abs=1e-9)


def test_perpendicular_to_side_left_vs_right_mirror_across_base() -> None:
    """left and right endpoints sit on opposite sides of the p1→p2 line, equidistant from base."""
    p1, p2 = (0.0, 0.0), (10.0, 10.0)
    base = (5.0, 5.0)  # on the line
    left = perpendicular_to(p1, p2, base=base, length=4.0, side="left")
    right = perpendicular_to(p1, p2, base=base, length=4.0, side="right")
    # Midpoint of the two endpoints lands back at base — they're mirror images.
    mx = (left[0] + right[0]) / 2.0
    my = (left[1] + right[1]) / 2.0
    assert mx == pytest.approx(base[0], abs=1e-9)
    assert my == pytest.approx(base[1], abs=1e-9)


def test_parallel_at_distance_returns_parallel_segment() -> None:
    p1, p2 = (0.0, 0.0), (10.0, 0.0)
    q1, q2 = parallel_at_distance(p1, p2, distance=5.0)
    # Same direction vector (collinear in same orientation), offset by 5 perpendicular.
    assert q2[0] - q1[0] == pytest.approx(p2[0] - p1[0], abs=1e-9)
    assert q2[1] - q1[1] == pytest.approx(p2[1] - p1[1], abs=1e-9)
    # Side="left" of (+x direction) = screen-up = negative y.
    assert q1[1] == pytest.approx(-5.0, abs=1e-9)
    assert q2[1] == pytest.approx(-5.0, abs=1e-9)


def test_intersect_returns_correct_crossing() -> None:
    line1 = ((0.0, 0.0), (10.0, 10.0))
    line2 = ((0.0, 10.0), (10.0, 0.0))
    p = intersect(line1, line2)
    assert p[0] == pytest.approx(5.0, abs=1e-9)
    assert p[1] == pytest.approx(5.0, abs=1e-9)


def test_intersect_parallel_raises() -> None:
    """Two horizontal lines never meet; helper raises ValueError."""
    with pytest.raises(ValueError, match="parallel"):
        intersect(((0.0, 0.0), (10.0, 0.0)), ((0.0, 5.0), (10.0, 5.0)))


def test_tangent_to_returns_point_on_circle_with_perpendicular_radius() -> None:
    """Two geometric invariants: (a) tangent point is on the circle,
    (b) the radius at the tangent point is perpendicular to the tangent line."""
    center = (0.0, 0.0)
    radius = 5.0
    external = (10.0, 0.0)
    tangent_pt = tangent_to(center, radius, external)
    import math as _m

    # (a) On the circle: |tangent_pt - center| == radius
    assert _m.hypot(tangent_pt[0] - center[0], tangent_pt[1] - center[1]) == pytest.approx(
        radius, abs=1e-6
    )
    # (b) radius ⊥ tangent line: (tangent_pt - center) · (tangent_pt - external) == 0
    rx, ry = tangent_pt[0] - center[0], tangent_pt[1] - center[1]
    tx, ty = tangent_pt[0] - external[0], tangent_pt[1] - external[1]
    assert rx * tx + ry * ty == pytest.approx(0.0, abs=1e-6)


def test_tangent_to_external_point_inside_circle_raises() -> None:
    with pytest.raises(ValueError, match="< radius"):
        tangent_to((0.0, 0.0), 10.0, (3.0, 0.0))


# ── Phase 3-3: composite — anchors + helpers together ─────────────


def test_composite_ramp_uses_anchors_and_helpers_for_precise_perpendicular() -> None:
    """End-to-end: 35° ramp with normal force computed via perpendicular_to + block.center.

    Asserts the angle of the rendered ramp surface and the perpendicularity of
    the normal-force arrow — same invariants the done criterion checks at the
    sandbox level.
    """
    import math as _m

    canvas = Canvas()
    theta_deg = 35.0
    ramp_left = (150.0, 500.0)
    ramp_right = polar(ramp_left, 400.0, -theta_deg)  # negative → screen-up

    ramp = canvas.add_line(start=ramp_left, end=ramp_right, role="incline")
    block = canvas.add_rect(
        top_left=(ramp.midpoint[0] - 25, ramp.midpoint[1] - 50),
        width=50,
        height=50,
        role="block",
    )
    n_tip = perpendicular_to(ramp_left, ramp_right, base=block.center, length=80.0, side="left")
    canvas.add_arrow(start=block.center, end=n_tip, role="normal_force")

    spec = canvas.export()
    line = next(e for e in spec["elements"] if e["type"] == "svg_line")
    arrow = next(e for e in spec["elements"] if e["type"] == "svg_arrow")

    # Ramp surface angle, measured from the rendered line. Screen-CW: rotate
    # by the **screen** y-axis (y grows down), so the math is atan2(-dy, dx)
    # to recover the conventional "above-horizon" angle.
    dx = line["x2"] - line["x1"]
    dy = line["y2"] - line["y1"]
    measured = _m.degrees(_m.atan2(-dy, dx))
    assert measured == pytest.approx(theta_deg, abs=0.5)

    # Normal-force orthogonality: arrow direction · ramp direction ≈ 0
    arr_dx, arr_dy = arrow["x2"] - arrow["x1"], arrow["y2"] - arrow["y1"]
    assert arr_dx * dx + arr_dy * dy == pytest.approx(0.0, abs=1e-6)
