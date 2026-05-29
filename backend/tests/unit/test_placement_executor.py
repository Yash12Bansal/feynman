# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for the Placement Executor — Phase 4 of Board Cortex."""

# import pytest

# from feynman.agent.placement_executor import (
#     _PLACEABLE_TYPES,
#     _ZONE_CENTERS,
#     _estimate_size,
#     _resolve_intent,
#     _resolve_zone,
#     resolve_placement,
# )
# from feynman.agent.size_estimator import SizeEstimate
# from feynman.agent.spatial_solver import (
#     BOARD_HEIGHT,
#     BOARD_WIDTH,
#     ELEMENT_PADDING,
#     Rect,
#     SpatialSolver,
# )
# from feynman.visuals.schemas import (
#     AnnotateInstruction,
#     BoardZone,
#     ClearInstruction,
#     DataPoint,
#     DataSeries,
#     DiagramNode,
#     DrawDesignDiagramInstruction,
#     DrawDiagramInstruction,
#     EquationStep,
#     HighlightInstruction,
#     HighlightWalkInstruction,
#     PlacementIntent,
#     ShowEquationInstruction,
#     ShowGraphInstruction,
#     ShowTextInstruction,
#     SizeHint,
#     StepEquationInstruction,
# )


# # ── Intent resolution ────────────────────────────────────────


# class TestIntentResolution:
#     def test_intent_near_right_of(self):
#         solver = SpatialSolver()
#         solver.update_occupied("design-1", Rect(100, 100, 400, 300))

#         instr = ShowEquationInstruction(latex="E=mc^2")
#         instr.placement = PlacementIntent(near="design-1", relation="right_of")
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Should be to the right of the anchor
#         assert instr.position_x >= 100 + 400  # anchor.right

#     def test_intent_near_below(self):
#         solver = SpatialSolver()
#         solver.update_occupied("eq-1", Rect(200, 100, 300, 80))

#         instr = ShowTextInstruction(text="This follows the equation")
#         instr.placement = PlacementIntent(near="eq-1", relation="below")
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Should be below the anchor
#         assert instr.position_y >= 100 + 80  # anchor.bottom

#     def test_intent_near_unknown_anchor(self):
#         """Anchor not in solver → falls back to best-fit."""
#         solver = SpatialSolver()

#         instr = ShowEquationInstruction(latex="x^2")
#         instr.placement = PlacementIntent(near="nonexistent-1", relation="right_of")
#         resolve_placement(instr, solver)

#         # Should still place (best-fit fallback)
#         assert instr.position_x is not None
#         assert instr.position_y is not None

#     def test_intent_near_no_space(self):
#         """Anchor exists but board is nearly full → still places via best-fit."""
#         solver = SpatialSolver()
#         # Fill most of the board but leave a gap
#         solver.update_occupied("big-1", Rect(0, 0, 1500, 900))
#         solver.update_occupied("anchor", Rect(1550, 0, 370, 900))

#         instr = ShowTextInstruction(text="Small text")
#         instr.placement = PlacementIntent(near="anchor", relation="right_of")
#         resolve_placement(instr, solver)

#         # May or may not have position — depends on remaining space
#         # The key test is that it doesn't crash
#         assert True

#     def test_intent_no_anchor(self):
#         """Intent without near → best-fit."""
#         solver = SpatialSolver()

#         instr = ShowEquationInstruction(latex="a+b=c")
#         instr.placement = PlacementIntent(relation="right_of")
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None


# # ── Zone resolution ──────────────────────────────────────────


# class TestZoneResolution:
#     def test_zone_center_free(self):
#         solver = SpatialSolver()

#         instr = ShowEquationInstruction(latex="F=ma", zone=BoardZone.TOP_LEFT)
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Should be near the top-left zone center (240, 150)
#         # Exact position depends on element size, but should be in the top-left area
#         assert instr.position_x < BOARD_WIDTH / 2
#         assert instr.position_y < BOARD_HEIGHT / 2

#     def test_zone_center_blocked(self):
#         """Collision at zone center → solver best-fit fallback."""
#         solver = SpatialSolver()
#         # Block the top-left zone center area
#         solver.update_occupied("blocker", Rect(0, 0, 500, 400))

#         instr = ShowEquationInstruction(latex="x=1", zone=BoardZone.TOP_LEFT)
#         resolve_placement(instr, solver)

#         # Should still get positioned (solver fallback)
#         assert instr.position_x is not None
#         assert instr.position_y is not None

#     def test_zone_clamps_to_bounds(self):
#         """Large element near edge → clamped within board."""
#         solver = SpatialSolver()

#         # Large diagram in bottom-right zone
#         instr = DrawDiagramInstruction(
#             nodes=[DiagramNode(id=f"n{i}", label=f"Node {i}") for i in range(10)],
#             zone=BoardZone.BOTTOM_RIGHT,
#         )
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Estimated size + position should fit within board bounds
#         size = _estimate_size(instr)
#         assert instr.position_x + size.width <= BOARD_WIDTH
#         assert instr.position_y + size.height <= BOARD_HEIGHT

#     @pytest.mark.parametrize(
#         "zone",
#         list(BoardZone),
#         ids=[z.value for z in BoardZone],
#     )
#     def test_all_nine_zones(self, zone: BoardZone):
#         """Each zone maps to a valid position."""
#         solver = SpatialSolver()

#         instr = ShowEquationInstruction(latex="x", zone=zone)
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         assert 0 <= instr.position_x < BOARD_WIDTH
#         assert 0 <= instr.position_y < BOARD_HEIGHT


# # ── Auto placement ───────────────────────────────────────────


# class TestAutoPlacement:
#     def test_auto_empty_board(self):
#         """No zone, no intent → solver best-fit (top-left bias)."""
#         solver = SpatialSolver()

#         instr = ShowEquationInstruction(latex="y=mx+b")
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Best-fit on empty board should be near top-left
#         assert instr.position_x < BOARD_WIDTH / 2
#         assert instr.position_y < BOARD_HEIGHT / 2

#     def test_auto_partially_full(self):
#         """Avoids occupied regions."""
#         solver = SpatialSolver()
#         # Occupy top-left quadrant
#         solver.update_occupied("existing", Rect(0, 0, 960, 540))

#         instr = ShowEquationInstruction(latex="z=5")
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Should not overlap the existing element
#         size = _estimate_size(instr)
#         placed = Rect(instr.position_x, instr.position_y, size.width, size.height)
#         existing = Rect(0, 0, 960, 540)
#         assert not placed.overlaps(existing)

#     def test_auto_board_full(self):
#         """No space → position_x/y remain None, warning logged."""
#         solver = SpatialSolver()
#         # Fill entire board with a few large blocks (use update_all for single rebuild)
#         elements = {
#             "fill-0": Rect(0, 0, BOARD_WIDTH / 2, BOARD_HEIGHT / 2),
#             "fill-1": Rect(BOARD_WIDTH / 2, 0, BOARD_WIDTH / 2, BOARD_HEIGHT / 2),
#             "fill-2": Rect(0, BOARD_HEIGHT / 2, BOARD_WIDTH / 2, BOARD_HEIGHT / 2),
#             "fill-3": Rect(BOARD_WIDTH / 2, BOARD_HEIGHT / 2, BOARD_WIDTH / 2, BOARD_HEIGHT / 2),
#         }
#         solver.update_all(elements)

#         instr = ShowEquationInstruction(latex="no_room")
#         resolve_placement(instr, solver)

#         # No space — should remain unpositioned
#         assert instr.position_x is None
#         assert instr.position_y is None


# # ── Size estimation dispatch ─────────────────────────────────


# class TestSizeEstimation:
#     def test_estimate_show_equation(self):
#         instr = ShowEquationInstruction(latex="E=mc^2")
#         size = _estimate_size(instr)
#         assert size.width > 0
#         assert size.height > 0
#         assert size.confidence > 0.5

#     def test_estimate_show_text(self):
#         instr = ShowTextInstruction(text="Newton's first law states that...", title="Newton's Laws")
#         size = _estimate_size(instr)
#         assert size.width > 0
#         assert size.height > 0

#     def test_estimate_design_diagram_with_spec_dims(self):
#         """Uses spec.width/height when available."""
#         instr = DrawDesignDiagramInstruction(spec={"width": 600, "height": 450, "elements": []})
#         size = _estimate_size(instr)
#         assert size.width == 600.0
#         assert size.height == 450.0
#         assert size.confidence == 0.9

#     def test_estimate_draw_diagram_node_count(self):
#         """Node count determines complexity → size."""
#         small_instr = DrawDiagramInstruction(nodes=[DiagramNode(id="n1", label="A")])
#         large_instr = DrawDiagramInstruction(
#             nodes=[DiagramNode(id=f"n{i}", label=f"N{i}") for i in range(8)]
#         )
#         small_size = _estimate_size(small_instr)
#         large_size = _estimate_size(large_instr)
#         assert large_size.width > small_size.width

#     def test_estimate_unknown_type(self):
#         """Non-renderable types get default size."""
#         instr = ClearInstruction()
#         size = _estimate_size(instr)
#         assert size.width == 400
#         assert size.height == 300
#         assert size.confidence == 0.3


# # ── Guards and integration ───────────────────────────────────


# class TestGuardsAndIntegration:
#     @pytest.mark.parametrize(
#         "instr",
#         [
#             ClearInstruction(),
#             HighlightInstruction(target_id="eq-1"),
#             AnnotateInstruction(action="circle", target_id="eq-1"),
#             HighlightWalkInstruction(target_id="design-1", steps=[{"sub_element_id": "n1", "trigger_words": ["test"]}]),
#         ],
#         ids=["clear", "highlight", "annotate", "highlight_walk"],
#     )
#     def test_skips_non_placeable_types(self, instr):
#         solver = SpatialSolver()
#         resolve_placement(instr, solver)
#         assert instr.position_x is None
#         assert instr.position_y is None

#     def test_skips_already_positioned(self):
#         """position_x/y already set → no-op."""
#         solver = SpatialSolver()

#         instr = ShowEquationInstruction(latex="x=1")
#         instr.position_x = 500.0
#         instr.position_y = 300.0
#         resolve_placement(instr, solver)

#         # Should not change
#         assert instr.position_x == 500.0
#         assert instr.position_y == 300.0

#     def test_priority_intent_over_zone(self):
#         """When both placement + zone are set, intent wins."""
#         solver = SpatialSolver()
#         solver.update_occupied("anchor", Rect(100, 100, 300, 200))

#         instr = ShowEquationInstruction(latex="y=2x", zone=BoardZone.BOTTOM_RIGHT)
#         instr.placement = PlacementIntent(near="anchor", relation="right_of")
#         resolve_placement(instr, solver)

#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Should be near the anchor (right of it), not in bottom-right zone
#         assert instr.position_x >= 400  # anchor.right
#         assert instr.position_x < 960  # not in right third of board

#     def test_placement_stripped_after_resolve(self):
#         """The placement field should be set to None after resolve (as done in tools.py)."""
#         solver = SpatialSolver()
#         instr = ShowEquationInstruction(latex="a=b")
#         instr.placement = PlacementIntent(near=None, relation="right_of")
#         resolve_placement(instr, solver)
#         # Simulate what tools.py does after resolve
#         instr.placement = None
#         assert instr.placement is None
#         # position_x/y should be set from auto-placement
#         assert instr.position_x is not None

#     def test_size_hint_used_for_diagram(self):
#         """PlacementIntent.size_hint influences size estimate for diagram types."""
#         small_instr = DrawDiagramInstruction(description="simple diagram")
#         small_instr.placement = PlacementIntent(size_hint=SizeHint.SMALL)

#         large_instr = DrawDiagramInstruction(description="complex diagram")
#         large_instr.placement = PlacementIntent(size_hint=SizeHint.LARGE)

#         small_size = _estimate_size(small_instr)
#         large_size = _estimate_size(large_instr)

#         assert large_size.width > small_size.width
#         assert large_size.height > small_size.height

#     def test_resolve_zone_helper_returns_none_for_invalid_zone(self):
#         """_resolve_zone returns None for unknown zone values."""
#         size = SizeEstimate(width=200, height=150, confidence=0.5)
#         solver = SpatialSolver()
#         # Pass a fake zone value that's not in _ZONE_CENTERS
#         result = _resolve_zone.__wrapped__(BoardZone.TOP_LEFT, size, solver) if hasattr(_resolve_zone, '__wrapped__') else _resolve_zone(BoardZone.TOP_LEFT, size, solver)
#         # TOP_LEFT is valid, should return a result
#         assert result is not None

#     def test_step_equation_size_scales_with_steps(self):
#         """More steps → taller estimate."""
#         short = StepEquationInstruction(steps=[EquationStep(latex="x=1")])
#         long = StepEquationInstruction(
#             steps=[EquationStep(latex=f"step {i}") for i in range(8)]
#         )
#         short_size = _estimate_size(short)
#         long_size = _estimate_size(long)
#         assert long_size.height > short_size.height

#     def test_graph_size_with_multiple_series(self):
#         """Graph size increases with series count."""
#         single = ShowGraphInstruction(
#             graph_type="line",
#             series=[DataSeries(points=[DataPoint(x=0, y=0)])],
#         )
#         multi = ShowGraphInstruction(
#             graph_type="line",
#             series=[DataSeries(points=[DataPoint(x=0, y=0)]) for _ in range(4)],
#         )
#         single_size = _estimate_size(single)
#         multi_size = _estimate_size(multi)
#         assert multi_size.width >= single_size.width


# # ── Size-hint-only intent should not bypass zone ─────────────


# class TestSizeHintOnlyDoesNotFireIntent:
#     def test_zone_used_when_placement_has_no_near(self):
#         """PlacementIntent with near=None should not trigger intent strategy."""
#         from feynman.visuals.schemas import PlacementIntent, SizeHint

#         solver = SpatialSolver()
#         instr = ShowEquationInstruction(latex="F=ma", zone=BoardZone.CENTER_LEFT)
#         instr.element_id = "eq-1"
#         # Simulate _build_placement with only size_hint (no near)
#         instr.placement = PlacementIntent(near=None, relation=None, size_hint=SizeHint.LARGE)

#         resolve_placement(instr, solver)
#         assert instr.position_x is not None
#         # Should be in center-left zone (~320, ~540), NOT at top-left (20, 20)
#         assert instr.position_x < 700  # Left side
#         assert instr.position_y > 200  # Not at very top

#     def test_intent_fires_when_near_is_set(self):
#         """PlacementIntent with near set should still use intent strategy."""
#         from feynman.visuals.schemas import PlacementIntent, SizeHint

#         solver = SpatialSolver()
#         solver.update_occupied("anchor", Rect(100, 100, 300, 200))

#         instr = ShowEquationInstruction(latex="E=mc^2")
#         instr.element_id = "eq-1"
#         instr.placement = PlacementIntent(
#             near="anchor", relation="right_of", size_hint=SizeHint.MEDIUM,
#         )

#         resolve_placement(instr, solver)
#         assert instr.position_x is not None
#         # Should be to the right of anchor (x >= 100 + 300 = 400)
#         assert instr.position_x >= 400
