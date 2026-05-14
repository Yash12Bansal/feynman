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
