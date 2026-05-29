# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Phase 9 — Board Cortex integration tests, edge cases, and performance benchmarks.

# Tests the full pipeline: scenario plan → tool calls → verify placements don't overlap.
# Also covers edge cases: empty board, massive element, dense board, multi-board isolation,
# doubt branch solver state, flat summary fallback, and zone-only backward compatibility.
# """

# from __future__ import annotations

# import time
# from unittest.mock import AsyncMock, MagicMock

# import pytest

# from feynman.agent.board import BoardManager
# from feynman.agent.board_flow import analyze_flow
# from feynman.agent.board_snapshot import generate_board_context, generate_snapshot
# from feynman.agent.board_state import BoardState
# from feynman.agent.placement_executor import resolve_placement
# from feynman.agent.scenario_planner import (
#     TeachingScenario,
#     detect_scenario,
#     plan_scenario,
# )
# from feynman.agent.spatial_solver import Rect, SpatialSolver
# from feynman.visuals.schemas import (
#     BoardZone,
#     DrawDesignDiagramInstruction,
#     ShowEquationInstruction,
#     ShowTextInstruction,
#     StepEquationInstruction,
# )

# # ── Helpers ────────────────────────────────────────────────


# def _make_mock_ctx(board_manager: BoardManager | None = None) -> MagicMock:
#     """Mock RunContext with real BoardManager."""
#     ctx = MagicMock()
#     ctx.wait_for_playout = AsyncMock()
#     ctx.session.room_io.room.local_participant.publish_data = AsyncMock()

#     userdata = MagicMock()
#     userdata.board_manager = board_manager or BoardManager()
#     userdata.current_concept = None
#     userdata.lesson_plan = None
#     userdata.current_concept_index = 0
#     userdata.board_verifier = None
#     ctx.userdata = userdata
#     return ctx


# # ── Edge Cases: Empty Board ───────────────────────────────


# class TestEmptyBoard:
#     def test_resolve_placement_empty_board(self):
#         """resolve_placement on empty board places near top-left."""
#         solver = SpatialSolver()
#         instr = ShowTextInstruction(text="Hello world")
#         instr.element_id = "text-1"
#         resolve_placement(instr, solver)
#         assert instr.position_x is not None
#         assert instr.position_y is not None
#         # Should be near top-left (best-fit on empty board)
#         assert instr.position_x < 500
#         assert instr.position_y < 300

#     def test_scenario_plan_empty_board(self):
#         """Scenario plan on empty board allocates full space."""
#         solver = SpatialSolver()
#         plan = plan_scenario(TeachingScenario.CONCEPT_INTRO, solver)
#         assert len(plan.slots) > 0
#         # Slots should fit within the board
#         for slot in plan.slots:
#             assert slot.rect.x >= 0
#             assert slot.rect.y >= 0
#             assert slot.rect.right <= 1920
#             assert slot.rect.bottom <= 1080


# # ── Edge Cases: Massive Element (80%) ─────────────────────


# class TestMassiveElement:
#     def test_solver_finds_remaining_20_percent(self):
#         """Board with 80% occupied → solver places in remaining 20%."""
#         solver = SpatialSolver()
#         # 80% of 1920x1080 = ~1,658,880 px²
#         # A rect filling left 80% of the board
#         solver.update_occupied("big", Rect(0, 0, 1536, 1080))  # 1536/1920 = 80%

#         # Should still find space for a 300x200 element
#         result = solver.find_placement(300, 200)
#         assert result is not None
#         # Should be in the remaining right strip (1536..1920)
#         assert result.x >= 1536

#     def test_placement_after_massive_element(self):
#         """resolve_placement works after 80% fill."""
#         solver = SpatialSolver()
#         solver.update_occupied("big", Rect(0, 0, 1536, 1080))

#         instr = ShowEquationInstruction(latex="E=mc^2")
#         instr.element_id = "eq-1"
#         resolve_placement(instr, solver)
#         assert instr.position_x is not None
#         assert instr.position_x >= 1536

#     def test_largest_free_region_after_massive(self):
#         """largest_free_region returns the 20% strip."""
#         solver = SpatialSolver()
#         solver.update_occupied("big", Rect(0, 0, 1536, 1080))
#         largest = solver.largest_free_region()
#         assert largest is not None
#         assert largest.width >= 350  # ~384px wide
#         assert largest.height >= 1000  # Full height

#     def test_snapshot_shows_free_space_with_massive(self):
#         """Snapshot with massive element still labels free region."""
#         solver = SpatialSolver()
#         solver.update_occupied("big", Rect(0, 0, 1536, 1080))
#         snapshot = generate_snapshot(
#             solver, {"big": MagicMock(type="draw_design_diagram", label="Big Diagram")}
#         )
#         assert "(empty)" in snapshot


# # ── Edge Cases: Dense Board (20+ elements) ────────────────


# class TestDenseBoard:
#     def _fill_board_grid(self, solver: SpatialSolver, count: int = 20) -> None:
#         """Fill a board with a grid of elements."""
#         cols = 5
#         w, h = 350, 200
#         gap = 10
#         for i in range(count):
#             r = i // cols
#             c = i % cols
#             x = c * (w + gap)
#             y = r * (h + gap)
#             solver.update_occupied(f"el-{i}", Rect(x, y, w, h))

#     def test_rebuild_free_rects_performance(self):
#         """_rebuild_free_rects < 5ms with 20 elements."""
#         solver = SpatialSolver()
#         self._fill_board_grid(solver, 20)

#         start = time.perf_counter()
#         # Trigger rebuild by adding one more
#         solver.update_occupied("extra", Rect(0, 900, 100, 50))
#         elapsed_ms = (time.perf_counter() - start) * 1000
#         assert elapsed_ms < 15, f"rebuild took {elapsed_ms:.1f}ms (limit: 15ms)"

#     def test_find_placement_performance(self):
#         """find_placement < 1ms with 20 elements."""
#         solver = SpatialSolver()
#         self._fill_board_grid(solver, 20)

#         start = time.perf_counter()
#         solver.find_placement(200, 100)
#         elapsed_ms = (time.perf_counter() - start) * 1000
#         assert elapsed_ms < 5, f"find_placement took {elapsed_ms:.1f}ms (limit: 5ms)"

#     def test_generate_snapshot_performance(self):
#         """generate_snapshot < 10ms with 20 elements."""
#         solver = SpatialSolver()
#         self._fill_board_grid(solver, 20)
#         elements = {f"el-{i}": MagicMock(type="show_text", label=f"El {i}") for i in range(20)}

#         start = time.perf_counter()
#         snapshot = generate_snapshot(solver, elements)
#         elapsed_ms = (time.perf_counter() - start) * 1000
#         assert elapsed_ms < 10, f"snapshot took {elapsed_ms:.1f}ms (limit: 10ms)"
#         assert len(snapshot) > 0

#     def test_flow_analysis_dense_board(self):
#         """analyze_flow handles 20+ elements without error."""
#         solver = SpatialSolver()
#         self._fill_board_grid(solver, 20)
#         result = analyze_flow(solver)
#         assert result.crowding_zones  # Should be crowded
#         assert result.suggested_action in ("scroll_right", "rebalance")

#     def test_no_free_rect_overlaps_occupied(self):
#         """After 20 elements, no free region overlaps any occupied element."""
#         solver = SpatialSolver()
#         self._fill_board_grid(solver, 20)
#         for rect in solver._free_rects:
#             for eid, occ in solver.occupied.items():
#                 assert not rect.overlaps(occ), f"Free rect overlaps {eid}"


# # ── Multi-Board Solver Isolation ──────────────────────────


# class TestMultiBoardSolverIsolation:
#     def test_solver_state_per_board(self):
#         """Each board has its own SpatialSolver with independent state."""
#         bm = BoardManager()

#         # Board 1: add elements
#         board1 = bm.active_board
#         board1.state.spatial_solver.update_occupied("el-1", Rect(100, 100, 300, 200))
#         assert len(board1.state.spatial_solver.occupied) == 1

#         # Switch to board 2
#         board2 = bm.create_and_switch("Board 2", "branch-1")
#         assert len(board2.state.spatial_solver.occupied) == 0  # Fresh solver

#         # Board 1 still has its element
#         assert len(board1.state.spatial_solver.occupied) == 1

#     def test_solver_restored_on_switch_back(self):
#         """Switching back to board 1 shows original solver state."""
#         bm = BoardManager()
#         board1_id = bm.active_id

#         board1 = bm.active_board
#         board1.state.spatial_solver.update_occupied("text-1", Rect(50, 50, 400, 150))

#         # Create board 2
#         board2 = bm.create_and_switch("Board 2", "branch-1")
#         board2.state.spatial_solver.update_occupied("eq-1", Rect(200, 200, 300, 100))

#         # Switch back to board 1
#         bm.switch_to(board1_id)
#         active_solver = bm.active_board.state.spatial_solver
#         assert "text-1" in active_solver.occupied
#         assert "eq-1" not in active_solver.occupied

#     def test_placement_uses_correct_board_solver(self):
#         """resolve_placement uses the active board's solver."""
#         bm = BoardManager()

#         # Board 1: fill left half
#         board1 = bm.active_board
#         board1.state.spatial_solver.update_occupied("blocker", Rect(0, 0, 960, 1080))

#         # Board 2: empty
#         board2 = bm.create_and_switch("Board 2", "branch-1")

#         # Placement on board 2 should use board 2's empty solver
#         instr = ShowTextInstruction(text="Fresh start")
#         instr.element_id = "text-1"
#         resolve_placement(instr, board2.state.spatial_solver)
#         assert instr.position_x is not None
#         # Should be near top-left since board 2 is empty
#         assert instr.position_x < 500


# # ── Doubt Branch Solver State ─────────────────────────────


# class TestDoubtBranchSolverState:
#     def test_doubt_board_has_fresh_solver(self):
#         """Pushing a doubt board gives a fresh solver."""
#         bm = BoardManager()
#         main_board = bm.active_board
#         main_board.state.spatial_solver.update_occupied("diagram-1", Rect(100, 100, 500, 400))

#         # Push doubt board
#         doubt_board = bm.push_board("doubt: What is force?", "doubt-1")
#         assert len(doubt_board.state.spatial_solver.occupied) == 0

#     def test_pop_restores_main_solver(self):
#         """Popping doubt board restores main board's solver state."""
#         bm = BoardManager()
#         main_board = bm.active_board
#         main_board.state.spatial_solver.update_occupied("diagram-1", Rect(100, 100, 500, 400))

#         # Push and add to doubt board
#         doubt_board = bm.push_board("doubt: What is force?", "doubt-1")
#         doubt_board.state.spatial_solver.update_occupied("eq-1", Rect(200, 200, 300, 100))

#         # Pop
#         bm.pop_board()
#         restored = bm.active_board.state.spatial_solver
#         assert "diagram-1" in restored.occupied
#         assert "eq-1" not in restored.occupied

#     def test_nested_doubt_solver_isolation(self):
#         """Nested doubt branches maintain independent solver states."""
#         bm = BoardManager()

#         # Main board
#         bm.active_board.state.spatial_solver.update_occupied("main-el", Rect(0, 0, 400, 300))

#         # Doubt level 1
#         doubt1 = bm.push_board("doubt 1", "d1")
#         doubt1.state.spatial_solver.update_occupied("d1-el", Rect(100, 100, 200, 150))

#         # Doubt level 2
#         doubt2 = bm.push_board("doubt 2", "d2")
#         assert len(doubt2.state.spatial_solver.occupied) == 0

#         # Pop level 2 → back to doubt 1
#         bm.pop_board()
#         assert "d1-el" in bm.active_board.state.spatial_solver.occupied
#         assert "main-el" not in bm.active_board.state.spatial_solver.occupied

#         # Pop level 1 → back to main
#         bm.pop_board()
#         assert "main-el" in bm.active_board.state.spatial_solver.occupied


# # ── Zone-Only Backward Compatibility ──────────────────────


# class TestZoneOnlyBackwardCompat:
#     def test_zone_only_instruction_placed(self):
#         """Instruction with zone but no near/placement still gets positioned."""
#         solver = SpatialSolver()
#         instr = ShowEquationInstruction(latex="F=ma", zone=BoardZone.TOP_CENTER)
#         instr.element_id = "eq-1"
#         resolve_placement(instr, solver)
#         assert instr.position_x is not None
#         # Should be in the top-center area
#         assert 400 < instr.position_x < 1500
#         assert instr.position_y < 400

#     def test_zone_used_when_size_hint_only(self):
#         """Zone + size_hint (no near) → zone strategy fires, not intent."""
#         from feynman.visuals.schemas import PlacementIntent, SizeHint

#         solver = SpatialSolver()
#         instr = DrawDesignDiagramInstruction(
#             description="Diagram",
#             spec={"width": 500, "height": 400, "elements": []},
#             zone=BoardZone.CENTER_LEFT,
#         )
#         instr.element_id = "design-1"
#         # Simulate _build_placement with only size_hint
#         instr.placement = PlacementIntent(near=None, relation=None, size_hint=SizeHint.LARGE)

#         resolve_placement(instr, solver)
#         assert instr.position_x is not None
#         # Should be in center-left zone area, NOT at top-left (20, 20)
#         assert instr.position_x < 700
#         assert instr.position_y > 100

#     def test_zone_only_all_nine_zones_work(self):
#         """All 9 zones produce valid placements."""
#         for zone in BoardZone:
#             solver = SpatialSolver()
#             instr = ShowTextInstruction(text="Test", zone=zone)
#             instr.element_id = f"text-{zone.value}"
#             resolve_placement(instr, solver)
#             assert instr.position_x is not None, f"Zone {zone.value} failed"
#             assert instr.position_y is not None, f"Zone {zone.value} failed"
#             assert 0 <= instr.position_x <= 1920
#             assert 0 <= instr.position_y <= 1080


# # ── Flat Summary Fallback ─────────────────────────────────


# class TestFlatSummaryFallback:
#     def test_board_state_summary_without_bounds(self):
#         """BoardState.summary() works without scene graph bounds data."""
#         bs = BoardState()
#         instr = ShowTextInstruction(text="Hello")
#         instr.element_id = "text-1"
#         instr.zone = BoardZone.TOP_LEFT
#         bs.record(instr)

#         summary = bs.summary()
#         assert "text-1" in summary
#         # Should produce a text-based summary (no ASCII snapshot since no bounds)

#     def test_generate_board_context_empty_solver(self):
#         """generate_board_context works with solver that has no occupied rects."""
#         solver = SpatialSolver()
#         context = generate_board_context(solver, {})
#         assert "free" in context.lower()  # Should mention free space


# # ── Full Integration: Scenario → Placements → No Overlap ─


# class TestScenarioPlacementIntegration:
#     @pytest.mark.asyncio()
#     async def test_derivation_scenario_three_tools_no_overlap(self):
#         """Derivation scenario → 3 tool calls → all placed without overlap."""
#         from feynman.agent.tools import _publish_visual

#         ctx = _make_mock_ctx()

#         # Set up scenario plan on active board
#         board_state = ctx.userdata.board_manager.active_board.state
#         scenario = detect_scenario("Derive the fundamental equation of motion", ["force diagram"])
#         board_state.scenario_plan = plan_scenario(scenario, board_state.spatial_solver)

#         # Tool 1: Design diagram
#         instr1 = DrawDesignDiagramInstruction(
#             description="Free body diagram",
#             spec={"title": "Forces", "width": 400, "height": 300, "elements": [{"id": "e1"}]},
#         )
#         await _publish_visual(ctx, instr1)

#         # Tool 2: Equation
#         instr2 = ShowEquationInstruction(latex="F = ma")
#         await _publish_visual(ctx, instr2)

#         # Tool 3: Step equation
#         from feynman.visuals.schemas import EquationStep

#         instr3 = StepEquationInstruction(
#             steps=[
#                 EquationStep(latex="F = ma"),
#                 EquationStep(latex="a = F/m"),
#             ]
#         )
#         await _publish_visual(ctx, instr3)

#         # All should be positioned
#         for i, instr in enumerate([instr1, instr2, instr3]):
#             assert instr.position_x is not None, f"Instruction {i + 1} not positioned"
#             assert instr.position_y is not None, f"Instruction {i + 1} not positioned"

#         # Verify no pairwise overlap using solver's occupied rects
#         occupied = board_state.spatial_solver.occupied
#         ids = list(occupied.keys())
#         for i in range(len(ids)):
#             for j in range(i + 1, len(ids)):
#                 r1 = occupied[ids[i]]
#                 r2 = occupied[ids[j]]
#                 assert not r1.overlaps(r2), f"{ids[i]} overlaps {ids[j]}"

#     @pytest.mark.asyncio()
#     async def test_concept_intro_scenario_no_overlap(self):
#         """Concept intro pattern: text title + diagram + equation."""
#         from feynman.agent.tools import _publish_visual

#         ctx = _make_mock_ctx()

#         board_state = ctx.userdata.board_manager.active_board.state
#         plan = plan_scenario(TeachingScenario.CONCEPT_INTRO, board_state.spatial_solver)
#         board_state.scenario_plan = plan

#         instr1 = ShowTextInstruction(text="Newton's Second Law", title="Forces and Motion")
#         await _publish_visual(ctx, instr1)

#         instr2 = DrawDesignDiagramInstruction(
#             description="Free body diagram",
#             spec={"title": "FBD", "width": 500, "height": 400, "elements": []},
#         )
#         await _publish_visual(ctx, instr2)

#         instr3 = ShowEquationInstruction(latex="\\vec{F} = m\\vec{a}")
#         await _publish_visual(ctx, instr3)

#         # All placed
#         for instr in [instr1, instr2, instr3]:
#             assert instr.position_x is not None

#         # No overlap in occupied rects
#         occupied = list(board_state.spatial_solver.occupied.values())
#         for i in range(len(occupied)):
#             for j in range(i + 1, len(occupied)):
#                 assert not occupied[i].overlaps(occupied[j])


# # ── Graceful Degradation Chain ────────────────────────────


# class TestGracefulDegradation:
#     def test_full_board_leaves_unpositioned(self):
#         """When board is 100% full, instruction stays unpositioned (zone flex fallback)."""
#         solver = SpatialSolver()
#         solver.update_occupied("full", Rect(0, 0, 1920, 1080))

#         instr = ShowEquationInstruction(latex="x=1")
#         instr.element_id = "eq-1"
#         resolve_placement(instr, solver)
#         # Should be unpositioned — frontend falls back to zone flex layout
#         assert instr.position_x is None

#     def test_scenario_then_zone_fallback(self):
#         """If scenario slots all filled, zone fallback kicks in."""
#         solver = SpatialSolver()
#         plan = plan_scenario(TeachingScenario.SINGLE_FOCUS, solver)  # Only 2 slots

#         # Fill all slots
#         instr1 = ShowTextInstruction(text="Title")
#         instr1.element_id = "text-1"
#         resolve_placement(instr1, solver, plan)

#         instr2 = DrawDesignDiagramInstruction(
#             description="diagram",
#             spec={"width": 400, "height": 300, "elements": []},
#         )
#         instr2.element_id = "design-1"
#         resolve_placement(instr2, solver, plan)

#         # Third instruction — no slots left, falls through to zone or auto
#         instr3 = ShowEquationInstruction(latex="F=ma", zone=BoardZone.BOTTOM_CENTER)
#         instr3.element_id = "eq-1"
#         resolve_placement(instr3, solver, plan)
#         assert instr3.position_x is not None  # Zone or auto fallback worked

#     def test_no_intent_no_zone_auto_placement(self):
#         """No placement intent, no zone → solver auto-picks best spot."""
#         solver = SpatialSolver()
#         solver.update_occupied("left", Rect(0, 0, 960, 1080))

#         instr = ShowEquationInstruction(latex="y=mx+b")
#         instr.element_id = "eq-1"
#         resolve_placement(instr, solver)
#         assert instr.position_x is not None
#         assert instr.position_x >= 960  # Should be in the free right half


# # ── Rapid-Fire Sequential Updates ─────────────────────────


# class TestRapidFireUpdates:
#     @pytest.mark.asyncio()
#     async def test_sequential_tool_calls_no_corruption(self):
#         """5 rapid tool calls don't corrupt board state."""
#         from feynman.agent.tools import _publish_visual

#         ctx = _make_mock_ctx()
#         board_state = ctx.userdata.board_manager.active_board.state

#         for i in range(5):
#             instr = ShowTextInstruction(text=f"Item {i}")
#             await _publish_visual(ctx, instr)
#             assert instr.element_id is not None

#         # All 5 recorded in board state (solver.occupied is populated by
#         # frontend bounds reports, not by _publish_visual directly).
#         assert len(board_state._elements) == 5

#         # All have unique element IDs
#         ids = list(board_state._elements.keys())
#         assert len(set(ids)) == 5

#         # All were positioned by the placement executor
#         # (position_x set even without bounds data, via solver auto-placement)
#         published_calls = ctx.session.room_io.room.local_participant.publish_data.call_args_list
#         assert len(published_calls) == 5
