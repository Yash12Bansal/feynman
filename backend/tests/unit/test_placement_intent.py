"""Tests for PlacementIntent schema, serialization, and backward compatibility."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter

from feynman.visuals.instructions import VisualInstruction
from feynman.visuals.schemas import (
    AnnotateInstruction,
    BoardZone,
    ClearInstruction,
    DrawDesignDiagramInstruction,
    DrawDiagramInstruction,
    DrawSceneInstruction,
    HighlightInstruction,
    HighlightWalkInstruction,
    PlacementIntent,
    ScrollViewInstruction,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    SizeHint,
    StepEquationInstruction,
    SwitchBoardInstruction,
)


# ── PlacementIntent model ────────────────────────────────────


class TestPlacementIntentModel:
    def test_defaults(self):
        pi = PlacementIntent()
        assert pi.near is None
        assert pi.relation is None
        assert pi.size_hint == SizeHint.MEDIUM

    def test_full_construction(self):
        pi = PlacementIntent(
            near="eq-1",
            relation="right_of",
            size_hint=SizeHint.LARGE,
        )
        assert pi.near == "eq-1"
        assert pi.relation == "right_of"
        assert pi.size_hint == SizeHint.LARGE

        # Round-trip through dict.
        data = pi.model_dump()
        restored = PlacementIntent(**data)
        assert restored == pi

    def test_size_hint_values(self):
        assert set(SizeHint) == {"small", "medium", "large", "full"}


# ── Serialization exclusion ──────────────────────────────────


class TestSerializationExclusion:
    def test_placement_excluded_from_model_dump(self):
        instr = ShowTextInstruction(
            type="show_text",
            text="hello",
            placement=PlacementIntent(near="eq-1", relation="below"),
        )
        data = instr.model_dump(exclude_none=True)
        assert "placement" not in data

    def test_placement_excluded_with_by_alias(self):
        """Matches the exact serialization path in _publish_visual()."""
        instr = ShowEquationInstruction(
            type="show_equation",
            latex="E = mc^2",
            placement=PlacementIntent(near="design-1", size_hint=SizeHint.SMALL),
        )
        data = instr.model_dump(exclude_none=True, by_alias=True)
        assert "placement" not in data

    def test_position_xy_included(self):
        instr = ShowTextInstruction(
            type="show_text",
            text="positioned",
            position_x=100.5,
            position_y=200.0,
        )
        data = instr.model_dump(exclude_none=True)
        assert data["position_x"] == 100.5
        assert data["position_y"] == 200.0

    def test_position_xy_excluded_when_none(self):
        instr = ShowTextInstruction(type="show_text", text="no position")
        data = instr.model_dump(exclude_none=True)
        assert "position_x" not in data
        assert "position_y" not in data

    @pytest.mark.parametrize(
        "cls,kwargs",
        [
            (ClearInstruction, {"type": "clear"}),
            (ShowTextInstruction, {"type": "show_text", "text": "hi"}),
            (ShowEquationInstruction, {"type": "show_equation", "latex": "x"}),
            (
                StepEquationInstruction,
                {
                    "type": "step_equation",
                    "steps": [{"latex": "x=1"}],
                },
            ),
            (
                DrawDiagramInstruction,
                {"type": "draw_diagram", "description": "d"},
            ),
            (
                ShowGraphInstruction,
                {
                    "type": "show_graph",
                    "graph_type": "line",
                    "series": [{"label": "s", "data": [{"x": 0, "y": 0}]}],
                },
            ),
            (
                HighlightInstruction,
                {"type": "highlight", "target_id": "eq-1"},
            ),
            (
                AnnotateInstruction,
                {
                    "type": "annotate",
                    "action": "circle",
                    "target_id": "eq-1",
                },
            ),
            (SwitchBoardInstruction, {"type": "switch_board"}),
            (ScrollViewInstruction, {"type": "scroll_view"}),
            (
                DrawSceneInstruction,
                {"type": "draw_scene", "description": "scene"},
            ),
            (
                DrawDesignDiagramInstruction,
                {"type": "draw_design_diagram"},
            ),
        ],
        ids=lambda v: v.__name__ if isinstance(v, type) else None,
    )
    def test_position_fields_on_all_types(self, cls, kwargs):
        instr = cls(
            **kwargs,
            position_x=50.0,
            position_y=75.0,
            placement=PlacementIntent(near="a"),
        )
        data = instr.model_dump(exclude_none=True, by_alias=True)
        assert data["position_x"] == 50.0
        assert data["position_y"] == 75.0
        assert "placement" not in data


# ── Wire round-trip ──────────────────────────────────────────


_VI = TypeAdapter(VisualInstruction)


class TestWireRoundTrip:
    def test_position_xy_json_roundtrip(self):
        instr = ShowEquationInstruction(
            type="show_equation",
            latex="F = ma",
            label="Newton",
            position_x=300.0,
            position_y=150.0,
        )
        wire = json.dumps(instr.model_dump(exclude_none=True, by_alias=True))
        parsed = _VI.validate_json(wire)
        assert parsed.position_x == 300.0
        assert parsed.position_y == 150.0

    def test_placement_not_in_json(self):
        instr = ShowTextInstruction(
            type="show_text",
            text="test",
            placement=PlacementIntent(near="design-1", relation="right_of"),
        )
        wire = json.dumps(instr.model_dump(exclude_none=True, by_alias=True))
        assert '"placement"' not in wire
        assert '"near"' not in wire


# ── Backward compatibility ───────────────────────────────────


class TestBackwardCompat:
    def test_existing_instruction_unchanged(self):
        """Instructions without new fields serialize identically to before."""
        instr = ShowEquationInstruction(
            type="show_equation",
            latex="x^2",
            zone=BoardZone.TOP_LEFT,
        )
        data = instr.model_dump(exclude_none=True)
        assert "position_x" not in data
        assert "position_y" not in data
        assert "placement" not in data
        assert data["zone"] == "top-left"

    def test_zone_and_position_coexist(self):
        instr = ShowTextInstruction(
            type="show_text",
            text="both",
            zone=BoardZone.CENTER_CENTER,
            position_x=960.0,
            position_y=540.0,
        )
        data = instr.model_dump(exclude_none=True)
        assert data["zone"] == "center-center"
        assert data["position_x"] == 960.0
        assert data["position_y"] == 540.0
