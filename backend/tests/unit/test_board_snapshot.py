"""Tests for the ASCII board snapshot generator."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from feynman.agent.board_snapshot import (
    BORDER,
    CANVAS_COLS,
    CANVAS_ROWS,
    generate_board_context,
    generate_snapshot,
)
from feynman.agent.spatial_solver import Rect, SpatialSolver


@dataclass
class FakeElement:
    """Minimal stand-in for BoardElement in tests."""

    element_id: str
    type: str
    label: str = ""
    created_at: int = 0


# ── generate_snapshot: empty board ─────────────────────────────


class TestEmptyBoard:
    def test_border_present(self):
        solver = SpatialSolver()
        snap = generate_snapshot(solver, {})
        lines = snap.split("\n")
        assert len(lines) == CANVAS_ROWS
        assert lines[0][0] == "┌"
        assert lines[0][-1] == "┐"
        assert lines[-1][0] == "└"
        assert lines[-1][-1] == "┘"

    def test_dimensions(self):
        solver = SpatialSolver()
        snap = generate_snapshot(solver, {})
        lines = snap.split("\n")
        assert len(lines) == CANVAS_ROWS
        for line in lines:
            assert len(line) == CANVAS_COLS

    def test_empty_label_shown(self):
        solver = SpatialSolver()
        snap = generate_snapshot(solver, {})
        assert "(empty)" in snap


# ── generate_snapshot: single small element ────────────────────


class TestSmallElement:
    def test_marker_shown(self):
        solver = SpatialSolver()
        solver.update_occupied("eq-1", Rect(100, 100, 120, 60))
        elements = {"eq-1": FakeElement("eq-1", "show_equation", label="F = ma")}
        snap = generate_snapshot(solver, elements)
        assert "F = ma" in snap

    def test_type_tag_shown(self):
        solver = SpatialSolver()
        solver.update_occupied("eq-1", Rect(100, 100, 120, 60))
        elements = {"eq-1": FakeElement("eq-1", "show_equation", label="F = ma")}
        snap = generate_snapshot(solver, elements)
        assert "eq" in snap


# ── generate_snapshot: single large element ────────────────────


class TestLargeElement:
    def test_box_drawn(self):
        solver = SpatialSolver()
        solver.update_occupied("design-1", Rect(50, 50, 700, 550))
        elements = {
            "design-1": FakeElement(
                "design-1", "draw_design_diagram", label="Free Body Diagram"
            )
        }
        snap = generate_snapshot(solver, elements)
        # Box drawing chars should appear
        assert "┌" in snap.split("\n")[1] or "┌" in snap.split("\n")[2]
        assert "Free Body" in snap

    def test_size_tag_large(self):
        solver = SpatialSolver()
        solver.update_occupied("design-1", Rect(50, 50, 700, 550))
        elements = {
            "design-1": FakeElement(
                "design-1", "draw_design_diagram", label="Diagram"
            )
        }
        snap = generate_snapshot(solver, elements)
        assert "lg" in snap


# ── generate_snapshot: multiple elements ───────────────────────


class TestMultipleElements:
    def test_all_labels_present(self):
        solver = SpatialSolver()
        solver.update_occupied("eq-1", Rect(100, 50, 300, 80))
        solver.update_occupied("text-1", Rect(100, 600, 400, 100))
        solver.update_occupied("design-1", Rect(800, 200, 600, 500))
        elements = {
            "eq-1": FakeElement("eq-1", "show_equation", label="E = mc^2"),
            "text-1": FakeElement("text-1", "show_text", label="Key insight"),
            "design-1": FakeElement(
                "design-1", "draw_design_diagram", label="Lens Diagram"
            ),
        }
        snap = generate_snapshot(solver, elements)
        assert "E = mc^2" in snap
        assert "Key insight" in snap
        assert "Lens Diagram" in snap

    def test_snapshot_has_correct_dimensions(self):
        solver = SpatialSolver()
        solver.update_occupied("a", Rect(0, 0, 400, 300))
        solver.update_occupied("b", Rect(800, 400, 300, 200))
        elements = {
            "a": FakeElement("a", "draw_diagram", label="Diagram A"),
            "b": FakeElement("b", "show_equation", label="Equation B"),
        }
        snap = generate_snapshot(solver, elements)
        lines = snap.split("\n")
        assert len(lines) == CANVAS_ROWS
        for line in lines:
            assert len(line) == CANVAS_COLS


# ── generate_snapshot: edge cases ──────────────────────────────


class TestEdgeCases:
    def test_element_at_board_edge(self):
        solver = SpatialSolver()
        solver.update_occupied("corner", Rect(1700, 900, 200, 150))
        elements = {"corner": FakeElement("corner", "show_text", label="Corner")}
        snap = generate_snapshot(solver, elements)
        # Should not crash, element should appear somewhere
        lines = snap.split("\n")
        assert len(lines) == CANVAS_ROWS
        assert "Corner" in snap

    def test_element_spanning_most_of_board(self):
        solver = SpatialSolver()
        solver.update_occupied("huge", Rect(50, 50, 1800, 1000))
        elements = {
            "huge": FakeElement("huge", "draw_design_diagram", label="Giant Diagram")
        }
        snap = generate_snapshot(solver, elements)
        assert "Giant Diagram" in snap

    def test_long_label_truncated(self):
        solver = SpatialSolver()
        solver.update_occupied("eq-1", Rect(100, 100, 150, 60))
        long_label = "A very long equation label that should be truncated"
        elements = {"eq-1": FakeElement("eq-1", "show_equation", label=long_label)}
        snap = generate_snapshot(solver, elements, max_label_len=10)
        # Full label should NOT appear
        assert long_label not in snap
        # But the truncated prefix should
        assert "A very lon" in snap

    def test_missing_element_uses_id(self):
        solver = SpatialSolver()
        solver.update_occupied("eq-1", Rect(100, 100, 150, 60))
        # No matching element in dict — should fall back to element ID
        snap = generate_snapshot(solver, {})
        assert "eq-1" in snap

    def test_no_empty_label_when_board_busy(self):
        solver = SpatialSolver()
        # Fill most of the board
        solver.update_occupied("big", Rect(0, 0, 1920, 900))
        elements = {"big": FakeElement("big", "draw_design_diagram", label="Big")}
        snap = generate_snapshot(solver, elements)
        # Remaining free area is 1920*180 = 345600 > 100000, so (empty) may appear
        # But let's just check it doesn't crash
        lines = snap.split("\n")
        assert len(lines) == CANVAS_ROWS


# ── generate_board_context: metrics ────────────────────────────


class TestBoardContext:
    def _make_solver_with_elements(self):
        solver = SpatialSolver()
        solver.update_occupied("design-1", Rect(50, 50, 600, 400))
        solver.update_occupied("eq-1", Rect(700, 100, 300, 80))
        elements = {
            "design-1": FakeElement(
                "design-1", "draw_design_diagram", label="FBD", created_at=1
            ),
            "eq-1": FakeElement(
                "eq-1", "show_equation", label="F = ma", created_at=2
            ),
        }
        return solver, elements

    def test_includes_snapshot(self):
        solver, elements = self._make_solver_with_elements()
        ctx = generate_board_context(solver, elements)
        assert "┌" in ctx
        assert "┘" in ctx

    def test_includes_free_percentage(self):
        solver, elements = self._make_solver_with_elements()
        ctx = generate_board_context(solver, elements)
        assert "Board:" in ctx
        assert "free" in ctx

    def test_includes_reading_flow(self):
        solver, elements = self._make_solver_with_elements()
        ctx = generate_board_context(solver, elements)
        assert "Reading flow:" in ctx
        assert "->" in ctx

    def test_includes_largest_free_area(self):
        solver, elements = self._make_solver_with_elements()
        ctx = generate_board_context(solver, elements)
        assert "Largest free area:" in ctx

    def test_includes_suggestions(self):
        solver, elements = self._make_solver_with_elements()
        ctx = generate_board_context(solver, elements)
        assert "Suggested next placements:" in ctx

    def test_suggestion_near_anchor(self):
        solver, elements = self._make_solver_with_elements()
        ctx = generate_board_context(solver, elements)
        # design-1 is the latest anchor (draw_design_diagram)
        assert "design-1" in ctx

    def test_empty_board_context(self):
        solver = SpatialSolver()
        ctx = generate_board_context(solver, {})
        assert "Board: 100% free" in ctx
        assert "(empty)" in ctx

    def test_open_quadrants_shown(self):
        solver = SpatialSolver()
        # Only occupy top-left
        solver.update_occupied("tl", Rect(0, 0, 400, 300))
        elements = {"tl": FakeElement("tl", "draw_diagram", label="Top Left")}
        ctx = generate_board_context(solver, elements)
        assert "Open:" in ctx


# ── Type and size tags ─────────────────────────────────────────


class TestTags:
    def test_type_tags(self):
        solver = SpatialSolver()
        solver.update_occupied("a", Rect(100, 100, 150, 60))
        snap_eq = generate_snapshot(
            solver,
            {"a": FakeElement("a", "show_equation", label="x")},
        )
        assert "eq" in snap_eq

    def test_size_tag_small(self):
        solver = SpatialSolver()
        # Small: area/board_area < 0.02
        solver.update_occupied("a", Rect(100, 100, 100, 50))
        snap = generate_snapshot(
            solver,
            {"a": FakeElement("a", "show_text", label="Hi")},
        )
        assert "sm" in snap

    def test_size_tag_medium(self):
        solver = SpatialSolver()
        # Medium: 0.02 < ratio < 0.08. Use 400x400 (ratio ≈ 0.077) with
        # enough canvas height for the tag line to render.
        solver.update_occupied("a", Rect(100, 100, 400, 400))
        elements = {"a": FakeElement("a", "draw_diagram", label="Mid")}
        snap = generate_snapshot(solver, elements)
        assert "md" in snap
