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

from feynman.visuals.canvas_dsl import Canvas, ElementHandle


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
