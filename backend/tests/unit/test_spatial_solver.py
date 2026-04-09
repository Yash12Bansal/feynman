"""Tests for the MaxRects-based spatial solver."""

import pytest

from feynman.agent.spatial_solver import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    ELEMENT_PADDING,
    MIN_USEFUL_SIZE,
    PlacementResult,
    Rect,
    SpatialRelation,
    SpatialSolver,
)


# ── Rect geometry ────────────────────────────────────────────────


class TestRect:
    def test_properties(self):
        r = Rect(100, 200, 300, 150)
        assert r.right == 400
        assert r.bottom == 350
        assert r.center_x == 250
        assert r.center_y == 275
        assert r.area == 45000

    def test_overlaps_true(self):
        a = Rect(0, 0, 100, 100)
        b = Rect(50, 50, 100, 100)
        assert a.overlaps(b)
        assert b.overlaps(a)

    def test_overlaps_false_adjacent(self):
        a = Rect(0, 0, 100, 100)
        b = Rect(100, 0, 100, 100)  # touching, not overlapping
        assert not a.overlaps(b)

    def test_overlaps_false_separated(self):
        a = Rect(0, 0, 50, 50)
        b = Rect(200, 200, 50, 50)
        assert not a.overlaps(b)

    def test_contains_true(self):
        outer = Rect(0, 0, 200, 200)
        inner = Rect(10, 10, 50, 50)
        assert outer.contains(inner)
        assert not inner.contains(outer)

    def test_contains_self(self):
        r = Rect(10, 10, 100, 100)
        assert r.contains(r)

    def test_contains_exact_edge(self):
        outer = Rect(0, 0, 100, 100)
        inner = Rect(0, 0, 100, 100)
        assert outer.contains(inner)


# ── SpatialSolver: empty board ──────────────────────────────────


class TestEmptyBoard:
    def test_can_fit_anything_reasonable(self):
        s = SpatialSolver()
        assert s.can_fit(500, 400)
        assert s.can_fit(1920, 1080)

    def test_cannot_fit_larger_than_board(self):
        s = SpatialSolver()
        assert not s.can_fit(2000, 100)
        assert not s.can_fit(100, 1200)

    def test_free_space_100_percent(self):
        s = SpatialSolver()
        assert s.free_space_percentage() == pytest.approx(1.0)

    def test_largest_free_region_is_full_board(self):
        s = SpatialSolver()
        largest = s.largest_free_region()
        assert largest is not None
        assert largest.width == BOARD_WIDTH
        assert largest.height == BOARD_HEIGHT

    def test_single_free_rect(self):
        s = SpatialSolver()
        assert len(s.free_rects) == 1

    def test_density_all_zero(self):
        s = SpatialSolver()
        density = s.density_by_quadrant()
        for v in density.values():
            assert v == pytest.approx(0.0)


# ── SpatialSolver: single element ──────────────────────────────


class TestSingleElement:
    def setup_method(self):
        self.solver = SpatialSolver()
        # Place a 400x300 element in the center
        self.solver.update_occupied("el-1", Rect(760, 390, 400, 300))

    def test_occupied_tracked(self):
        assert "el-1" in self.solver.occupied
        assert self.solver.occupied["el-1"].width == 400

    def test_free_space_reduced(self):
        pct = self.solver.free_space_percentage()
        expected = 1 - (400 * 300) / (BOARD_WIDTH * BOARD_HEIGHT)
        assert pct == pytest.approx(expected, abs=0.01)

    def test_free_rects_surround_element(self):
        # Should have free rects around the occupied element
        rects = self.solver.free_rects
        assert len(rects) > 0
        # No free rect should overlap the occupied element
        occ = self.solver.occupied["el-1"]
        for fr in rects:
            assert not fr.overlaps(occ)

    def test_can_fit_beside_element(self):
        # 400px element at x=760. ~760px free on left, ~760px free on right.
        assert self.solver.can_fit(700, 200)

    def test_remove_restores_full_board(self):
        self.solver.remove("el-1")
        assert self.solver.free_space_percentage() == pytest.approx(1.0)
        largest = self.solver.largest_free_region()
        assert largest is not None
        assert largest.area == pytest.approx(BOARD_WIDTH * BOARD_HEIGHT)


# ── SpatialSolver: multiple elements ────────────────────────────


class TestMultipleElements:
    def setup_method(self):
        self.solver = SpatialSolver()
        # Top-left diagram
        self.solver.update_occupied("diagram-1", Rect(50, 50, 500, 400))
        # Right side equation
        self.solver.update_occupied("eq-1", Rect(600, 100, 300, 80))
        # Bottom text
        self.solver.update_occupied("text-1", Rect(100, 600, 400, 150))

    def test_no_free_rect_overlaps_occupied(self):
        for fr in self.solver.free_rects:
            for occ in self.solver.occupied.values():
                assert not fr.overlaps(occ)

    def test_density_nonzero_in_used_quadrants(self):
        density = self.solver.density_by_quadrant()
        # Top-left has diagram-1 (500x400 starting at 50,50)
        assert density["top-left"] > 0.1
        # eq-1 at (600,100,300,80) — right edge 900, midpoint 960 → still top-left
        # bottom text at (100,600) → bottom-left
        assert density["bottom-left"] > 0.0

    def test_bulk_update_replaces_all(self):
        self.solver.update_all({"new-1": Rect(0, 0, 100, 100)})
        assert len(self.solver.occupied) == 1
        assert "new-1" in self.solver.occupied
        assert "diagram-1" not in self.solver.occupied

    def test_clear_resets_everything(self):
        self.solver.clear()
        assert len(self.solver.occupied) == 0
        assert self.solver.free_space_percentage() == pytest.approx(1.0)


# ── find_placement: anchor-relative ─────────────────────────────


class TestAnchorPlacement:
    def setup_method(self):
        self.solver = SpatialSolver()
        # Anchor in center-left area
        self.solver.update_occupied("anchor", Rect(200, 400, 400, 200))

    def test_right_of_anchor(self):
        result = self.solver.find_placement(
            200, 100, anchor_id="anchor", relation=SpatialRelation.RIGHT_OF
        )
        assert result is not None
        # Should be to the right of anchor.right (600) + padding
        assert result.x >= 200 + 400  # anchor.right

    def test_below_anchor(self):
        result = self.solver.find_placement(
            200, 100, anchor_id="anchor", relation=SpatialRelation.BELOW
        )
        assert result is not None
        assert result.y >= 400 + 200  # anchor.bottom

    def test_above_anchor(self):
        result = self.solver.find_placement(
            200, 100, anchor_id="anchor", relation=SpatialRelation.ABOVE
        )
        assert result is not None
        assert result.y + 100 <= 400  # above anchor.y

    def test_left_of_anchor(self):
        result = self.solver.find_placement(
            150, 100, anchor_id="anchor", relation=SpatialRelation.LEFT_OF
        )
        assert result is not None
        assert result.x + 150 <= 200  # left of anchor.x

    def test_centered_on_anchor(self):
        result = self.solver.find_placement(
            100, 50, anchor_id="anchor", relation=SpatialRelation.CENTERED
        )
        assert result is not None
        # Should be roughly centered on anchor
        anchor_cx = 200 + 400 / 2
        anchor_cy = 400 + 200 / 2
        assert abs(result.x + 50 - anchor_cx) < 1
        assert abs(result.y + 25 - anchor_cy) < 1

    def test_nonexistent_anchor_falls_back(self):
        result = self.solver.find_placement(
            200, 100, anchor_id="nonexistent", relation=SpatialRelation.RIGHT_OF
        )
        # Falls back to best-fit
        assert result is not None
        assert result.confidence < 0.9  # lower confidence for fallback

    def test_no_anchor_uses_best_fit(self):
        result = self.solver.find_placement(200, 100)
        assert result is not None
        assert result.reason == "best-fit free region"


# ── find_placement: fallback when anchor space is blocked ────────


class TestPlacementFallback:
    def test_anchor_blocked_right_falls_back(self):
        solver = SpatialSolver()
        # Anchor at far right edge
        solver.update_occupied("anchor", Rect(1700, 400, 200, 200))
        result = solver.find_placement(
            300, 100, anchor_id="anchor", relation=SpatialRelation.RIGHT_OF
        )
        # Right of anchor would go off-board, so falls back to best-fit
        assert result is not None
        assert result.confidence < 0.9

    def test_board_nearly_full_returns_none(self):
        solver = SpatialSolver()
        # Fill the board almost completely
        solver.update_occupied("big", Rect(0, 0, 1920, 1080))
        result = solver.find_placement(200, 200)
        assert result is None

    def test_can_fit_returns_false_when_full(self):
        solver = SpatialSolver()
        solver.update_occupied("big", Rect(0, 0, 1920, 1080))
        assert not solver.can_fit(100, 100)


# ── Placement: no overlap guarantee ─────────────────────────────


class TestPlacementNoOverlap:
    def test_placement_doesnt_overlap_existing(self):
        solver = SpatialSolver()
        solver.update_occupied("a", Rect(100, 100, 300, 200))
        solver.update_occupied("b", Rect(500, 100, 300, 200))

        result = solver.find_placement(200, 150)
        assert result is not None
        placed = Rect(result.x, result.y, result.width, result.height)
        for occ in solver.occupied.values():
            assert not placed.overlaps(occ)


# ── reading_order ────────────────────────────────────────────────


class TestReadingOrder:
    def test_empty_board(self):
        solver = SpatialSolver()
        assert solver.reading_order() == []

    def test_left_to_right_same_row(self):
        solver = SpatialSolver()
        solver.update_occupied("b", Rect(500, 100, 100, 50))
        solver.update_occupied("a", Rect(100, 100, 100, 50))
        solver.update_occupied("c", Rect(900, 100, 100, 50))
        assert solver.reading_order() == ["a", "b", "c"]

    def test_top_to_bottom_different_rows(self):
        solver = SpatialSolver()
        solver.update_occupied("bottom", Rect(100, 800, 100, 50))
        solver.update_occupied("top", Rect(100, 100, 100, 50))
        solver.update_occupied("mid", Rect(100, 450, 100, 50))
        assert solver.reading_order() == ["top", "mid", "bottom"]

    def test_mixed_rows_and_columns(self):
        solver = SpatialSolver()
        # Row 1: two elements
        solver.update_occupied("1b", Rect(500, 100, 100, 50))
        solver.update_occupied("1a", Rect(100, 100, 100, 50))
        # Row 2: one element
        solver.update_occupied("2a", Rect(300, 500, 100, 50))
        order = solver.reading_order()
        assert order == ["1a", "1b", "2a"]


# ── neighbors_of ─────────────────────────────────────────────────


class TestNeighbors:
    def test_close_neighbors(self):
        solver = SpatialSolver()
        solver.update_occupied("a", Rect(100, 100, 100, 50))
        solver.update_occupied("b", Rect(250, 100, 100, 50))  # close
        solver.update_occupied("c", Rect(1500, 800, 100, 50))  # far
        neighbors = solver.neighbors_of("a")
        assert "b" in neighbors
        assert "c" not in neighbors

    def test_nonexistent_element(self):
        solver = SpatialSolver()
        assert solver.neighbors_of("nope") == []

    def test_self_not_included(self):
        solver = SpatialSolver()
        solver.update_occupied("a", Rect(100, 100, 100, 50))
        solver.update_occupied("b", Rect(110, 110, 100, 50))
        neighbors = solver.neighbors_of("a")
        assert "a" not in neighbors


# ── density_by_quadrant ──────────────────────────────────────────


class TestDensity:
    def test_top_left_only(self):
        solver = SpatialSolver()
        # Element fully in top-left quadrant
        solver.update_occupied("tl", Rect(0, 0, 400, 300))
        density = solver.density_by_quadrant()
        assert density["top-left"] > 0.1
        assert density["bottom-right"] == pytest.approx(0.0)

    def test_element_spanning_quadrants(self):
        solver = SpatialSolver()
        # Element in the exact center, spanning all 4 quadrants
        solver.update_occupied("center", Rect(860, 440, 200, 200))
        density = solver.density_by_quadrant()
        # Should contribute to all 4 quadrants
        for v in density.values():
            assert v > 0.0


# ── zone_hint ────────────────────────────────────────────────────


class TestZoneHint:
    def test_top_left_zone(self):
        solver = SpatialSolver()
        result = solver.find_placement(100, 50)
        assert result is not None
        assert result.zone_hint == "top-left"

    def test_anchor_placement_has_zone(self):
        solver = SpatialSolver()
        solver.update_occupied("anchor", Rect(200, 200, 200, 200))
        result = solver.find_placement(
            100, 50, anchor_id="anchor", relation=SpatialRelation.RIGHT_OF
        )
        assert result is not None
        assert result.zone_hint != ""


# ── MaxRects correctness ────────────────────────────────────────


class TestMaxRectsAlgorithm:
    def test_small_rects_pruned(self):
        solver = SpatialSolver(width=200, height=200)
        # Occupy most of the space, leaving only tiny gaps
        solver.update_occupied("big", Rect(0, 0, 200, 200 - MIN_USEFUL_SIZE + 1))
        # The remaining strip is < MIN_USEFUL_SIZE height
        for fr in solver.free_rects:
            assert fr.width >= MIN_USEFUL_SIZE
            assert fr.height >= MIN_USEFUL_SIZE

    def test_no_duplicate_free_rects(self):
        solver = SpatialSolver()
        solver.update_occupied("a", Rect(400, 300, 200, 200))
        solver.update_occupied("b", Rect(700, 300, 200, 200))
        # No two free rects should be identical
        seen = set()
        for fr in solver.free_rects:
            key = (fr.x, fr.y, fr.width, fr.height)
            assert key not in seen, f"Duplicate free rect: {key}"
            seen.add(key)

    def test_custom_board_size(self):
        solver = SpatialSolver(width=800, height=600)
        largest = solver.largest_free_region()
        assert largest is not None
        assert largest.width == 800
        assert largest.height == 600
