# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for Phase 7 — Board Flow Intelligence."""


# from feynman.agent.board_flow import (
#     FlowAnalysis,
#     ScrollAdvice,
#     advise_scroll,
#     analyze_flow,
#     reserve_for_upcoming,
#     suggest_cleanup,
# )
# from feynman.agent.board_graph import BoardGraph, BoardRelation
# from feynman.agent.spatial_solver import Rect, SpatialSolver

# # ── Helpers ────────────────────────────────────────────────


# class _FakeElement:
#     """Minimal stand-in for BoardElement in tests."""

#     def __init__(
#         self,
#         *,
#         type: str = "show_text",
#         created_at: int = 0,
#         concept_title: str = "",
#         concept_index: int | None = None,
#     ):
#         self.type = type
#         self.created_at = created_at
#         self.concept_title = concept_title
#         self.concept_index = concept_index


# def _fill_board(solver: SpatialSolver, rects: dict[str, Rect]) -> None:
#     """Register multiple occupied rects on a solver."""
#     for eid, rect in rects.items():
#         solver.update_occupied(eid, rect)


# # ── analyze_flow ───────────────────────────────────────────


# class TestAnalyzeFlow:
#     def test_empty_board(self):
#         solver = SpatialSolver(1920, 1080)
#         result = analyze_flow(solver)
#         assert isinstance(result, FlowAnalysis)
#         assert result.reading_direction == "left_to_right"
#         assert result.density_balance == 0.0
#         assert result.suggested_action == "continue"
#         assert result.crowding_zones == []

#     def test_single_element(self):
#         solver = SpatialSolver(1920, 1080)
#         solver.update_occupied("text-1", Rect(100, 100, 300, 200))
#         result = analyze_flow(solver)
#         assert result.reading_direction == "left_to_right"
#         assert result.suggested_action == "continue"

#     def test_left_to_right_flow(self):
#         solver = SpatialSolver(1920, 1080)
#         # Three elements arranged horizontally.
#         solver.update_occupied("a", Rect(100, 200, 200, 150))
#         solver.update_occupied("b", Rect(500, 200, 200, 150))
#         solver.update_occupied("c", Rect(900, 200, 200, 150))
#         result = analyze_flow(solver)
#         assert result.reading_direction == "left_to_right"

#     def test_top_to_bottom_flow(self):
#         solver = SpatialSolver(1920, 1080)
#         # Three elements arranged vertically.
#         solver.update_occupied("a", Rect(400, 50, 200, 100))
#         solver.update_occupied("b", Rect(400, 300, 200, 100))
#         solver.update_occupied("c", Rect(400, 600, 200, 100))
#         result = analyze_flow(solver)
#         assert result.reading_direction == "top_to_bottom"

#     def test_crowded_top_left(self):
#         solver = SpatialSolver(1920, 1080)
#         # Large element in top-left quadrant filling >70%.
#         solver.update_occupied("big", Rect(0, 0, 900, 500))
#         result = analyze_flow(solver)
#         assert "top-left" in result.crowding_zones

#     def test_full_board_suggests_scroll(self):
#         solver = SpatialSolver(1920, 1080)
#         # Fill most of the board.
#         solver.update_occupied("a", Rect(0, 0, 960, 540))
#         solver.update_occupied("b", Rect(960, 0, 960, 540))
#         solver.update_occupied("c", Rect(0, 540, 960, 540))
#         solver.update_occupied("d", Rect(960, 540, 800, 400))
#         result = analyze_flow(solver)
#         assert result.suggested_action == "scroll_right"

#     def test_weight_center_reflects_element_positions(self):
#         solver = SpatialSolver(1920, 1080)
#         # Single element at top-left.
#         solver.update_occupied("a", Rect(0, 0, 200, 200))
#         result = analyze_flow(solver)
#         assert result.weight_center[0] < solver.width / 2
#         assert result.weight_center[1] < solver.height / 2

#     def test_balanced_board_low_density_balance(self):
#         solver = SpatialSolver(1920, 1080)
#         # One element per quadrant, roughly equal size.
#         solver.update_occupied("a", Rect(100, 100, 200, 150))
#         solver.update_occupied("b", Rect(1100, 100, 200, 150))
#         solver.update_occupied("c", Rect(100, 600, 200, 150))
#         solver.update_occupied("d", Rect(1100, 600, 200, 150))
#         result = analyze_flow(solver)
#         assert result.density_balance < 0.3


# # ── advise_scroll ──────────────────────────────────────────


# class TestAdviseScroll:
#     def test_plenty_of_room_returns_none(self):
#         solver = SpatialSolver(1920, 1080)
#         solver.update_occupied("a", Rect(100, 100, 300, 200))
#         elements = {"a": _FakeElement(created_at=1)}
#         assert advise_scroll(solver, elements) is None

#     def test_filling_up_suggests_scroll(self):
#         solver = SpatialSolver(1920, 1080)
#         # Fill ~70% of the board.
#         solver.update_occupied("a", Rect(0, 0, 1400, 1080))
#         elements = {"a": _FakeElement(created_at=1)}
#         advice = advise_scroll(solver, elements)
#         assert advice is not None
#         assert isinstance(advice, ScrollAdvice)
#         assert advice.direction in ("right", "down")

#     def test_urgency_scales_with_density(self):
#         solver_70 = SpatialSolver(1920, 1080)
#         solver_70.update_occupied("a", Rect(0, 0, 1600, 960))
#         advice_65 = advise_scroll(solver_70, {"a": _FakeElement(created_at=1)})

#         solver_90 = SpatialSolver(1920, 1080)
#         solver_90.update_occupied("a", Rect(0, 0, 1800, 1060))
#         advice_90 = advise_scroll(solver_90, {"a": _FakeElement(created_at=1)})

#         assert advice_65 is not None
#         assert advice_90 is not None
#         assert advice_90.urgency >= advice_65.urgency

#     def test_prefers_right_direction(self):
#         solver = SpatialSolver(1920, 1080)
#         # Content on left side, board filling up.
#         solver.update_occupied("a", Rect(0, 0, 960, 1080))
#         solver.update_occupied("b", Rect(960, 0, 600, 1080))
#         elements = {
#             "a": _FakeElement(created_at=1),
#             "b": _FakeElement(created_at=2),
#         }
#         advice = advise_scroll(solver, elements)
#         assert advice is not None
#         assert advice.direction == "right"

#     def test_reason_includes_percentage(self):
#         solver = SpatialSolver(1920, 1080)
#         solver.update_occupied("a", Rect(0, 0, 1500, 1080))
#         advice = advise_scroll(solver, {"a": _FakeElement(created_at=1)})
#         assert advice is not None
#         assert "%" in advice.reason

#     def test_empty_board_returns_none(self):
#         solver = SpatialSolver(1920, 1080)
#         assert advise_scroll(solver, {}) is None


# # ── suggest_cleanup ────────────────────────────────────────


# class TestSuggestCleanup:
#     def test_no_elements_returns_empty(self):
#         graph = BoardGraph()
#         result = suggest_cleanup({}, graph, current_concept_index=3)
#         assert result == []

#     def test_current_concept_not_suggested(self):
#         graph = BoardGraph()
#         elements = {
#             "text-1": _FakeElement(concept_index=3, concept_title="Current", created_at=1),
#         }
#         result = suggest_cleanup(elements, graph, current_concept_index=3)
#         assert result == []

#     def test_previous_concept_not_suggested(self):
#         """Elements from concept_index - 1 are preserved (conservative)."""
#         graph = BoardGraph()
#         elements = {
#             "text-1": _FakeElement(concept_index=2, concept_title="Previous", created_at=1),
#         }
#         result = suggest_cleanup(elements, graph, current_concept_index=3)
#         assert result == []

#     def test_old_isolated_element_suggested(self):
#         graph = BoardGraph()
#         elements = {
#             "text-1": _FakeElement(
#                 concept_index=0, concept_title="Intro", created_at=1
#             ),
#         }
#         result = suggest_cleanup(elements, graph, current_concept_index=3)
#         assert len(result) == 1
#         assert result[0].element_id == "text-1"
#         assert "Intro" in result[0].reason

#     def test_element_with_edges_excluded(self):
#         graph = BoardGraph()
#         graph.add_edge("text-1", "design-1", BoardRelation.SUPPORTS)
#         elements = {
#             "text-1": _FakeElement(
#                 concept_index=0, concept_title="Intro", created_at=1
#             ),
#         }
#         result = suggest_cleanup(elements, graph, current_concept_index=3)
#         assert result == []

#     def test_oldest_first_ordering(self):
#         graph = BoardGraph()
#         elements = {
#             "text-2": _FakeElement(concept_index=0, concept_title="Intro", created_at=5),
#             "text-1": _FakeElement(concept_index=0, concept_title="Intro", created_at=1),
#             "eq-1": _FakeElement(concept_index=0, concept_title="Intro", created_at=3),
#         }
#         result = suggest_cleanup(elements, graph, current_concept_index=3)
#         assert [c.element_id for c in result] == ["text-1", "eq-1", "text-2"]

#     def test_max_three_candidates(self):
#         graph = BoardGraph()
#         elements = {
#             f"text-{i}": _FakeElement(
#                 concept_index=0, concept_title="Intro", created_at=i
#             )
#             for i in range(5)
#         }
#         result = suggest_cleanup(elements, graph, current_concept_index=3)
#         assert len(result) == 3

#     def test_no_concept_index_skipped(self):
#         """Elements without concept_index are never suggested for cleanup."""
#         graph = BoardGraph()
#         elements = {
#             "text-1": _FakeElement(concept_index=None, concept_title="", created_at=1),
#         }
#         result = suggest_cleanup(elements, graph, current_concept_index=3)
#         assert result == []


# # ── reserve_for_upcoming ──────────────────────────────────


# class TestReserveForUpcoming:
#     def test_no_upcoming_returns_empty(self):
#         solver = SpatialSolver(1920, 1080)
#         assert reserve_for_upcoming(solver, []) == []

#     def test_diagram_hint_gets_large_estimate(self):
#         solver = SpatialSolver(1920, 1080)
#         hints = reserve_for_upcoming(solver, [("Optics", "Draw lens diagram")])
#         assert len(hints) == 1
#         assert hints[0].estimated_width == 500
#         assert hints[0].estimated_height == 400
#         assert hints[0].concept_title == "Optics"

#     def test_no_hint_gets_smaller_estimate(self):
#         solver = SpatialSolver(1920, 1080)
#         hints = reserve_for_upcoming(solver, [("Equations", None)])
#         assert len(hints) == 1
#         assert hints[0].estimated_width == 400
#         assert hints[0].estimated_height == 200

#     def test_full_board_returns_empty(self):
#         solver = SpatialSolver(1920, 1080)
#         solver.update_occupied("a", Rect(0, 0, 1920, 1080))
#         assert reserve_for_upcoming(solver, [("Topic", None)]) == []

#     def test_suggested_zone_is_valid(self):
#         solver = SpatialSolver(1920, 1080)
#         hints = reserve_for_upcoming(solver, [("Topic", "diagram")])
#         assert len(hints) == 1
#         # Zone should be a valid zone string.
#         parts = hints[0].suggested_zone.split("-")
#         assert len(parts) == 2
#         assert parts[0] in ("top", "center", "bottom")
#         assert parts[1] in ("left", "center", "right")
