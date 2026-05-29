# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for Phase 2: Modify Tool + Board-Aware Generation.

# Covers:
# - Design spec storage on BoardState and BoardManager
# - modify_design_diagram_spec prompt construction
# - modify_design_diagram tool flow
# - Prompt instructions inclusion
# """

# from __future__ import annotations

# from unittest.mock import AsyncMock, MagicMock, patch
# from uuid import uuid4

# import pytest

# from feynman.agent.board import BoardManager
# from feynman.agent.board_state import BoardState
# from feynman.agent.session_audit import SessionAudit
# from feynman.agent.spatial_solver import Rect
# from feynman.visuals.schemas import (
#     DrawDesignDiagramInstruction,
#     ShowTextInstruction,
# )

# # ── Sample spec for tests ─────────────────────────────────────

# SAMPLE_SPEC: dict = {
#     "title": "Free Body Diagram",
#     "description": "Forces on a block",
#     "width": 900,
#     "height": 650,
#     "elements": [
#         {"id": "weight-arrow", "type": "svg_arrow", "x1": 450, "y1": 300, "x2": 450, "y2": 500},
#         {"id": "normal-arrow", "type": "svg_arrow", "x1": 450, "y1": 300, "x2": 450, "y2": 100},
#         {"id": "friction-arrow", "type": "svg_arrow", "x1": 450, "y1": 300, "x2": 250, "y2": 300},
#     ],
# }

# MODIFIED_SPEC: dict = {
#     "title": "Free Body Diagram",
#     "description": "Forces on a block with applied force",
#     "width": 900,
#     "height": 650,
#     "elements": [
#         {"id": "weight-arrow", "type": "svg_arrow", "x1": 450, "y1": 300, "x2": 450, "y2": 500},
#         {"id": "normal-arrow", "type": "svg_arrow", "x1": 450, "y1": 300, "x2": 450, "y2": 100},
#         {"id": "friction-arrow", "type": "svg_arrow", "x1": 450, "y1": 300, "x2": 250, "y2": 300},
#         {"id": "applied-arrow", "type": "svg_arrow", "x1": 450, "y1": 300, "x2": 650, "y2": 300},
#     ],
# }


# # ── BoardState spec storage ────────────────────────────────────


# class TestBoardStateSpecStorage:
#     def test_store_and_retrieve(self) -> None:
#         bs = BoardState()
#         bs.store_design_spec("design-1", SAMPLE_SPEC)
#         assert bs.get_design_spec("design-1") is SAMPLE_SPEC

#     def test_get_nonexistent_returns_none(self) -> None:
#         bs = BoardState()
#         assert bs.get_design_spec("design-99") is None

#     def test_overwrite_spec(self) -> None:
#         bs = BoardState()
#         bs.store_design_spec("design-1", SAMPLE_SPEC)
#         bs.store_design_spec("design-1", MODIFIED_SPEC)
#         assert bs.get_design_spec("design-1") is MODIFIED_SPEC

#     def test_spec_cleared_on_remove(self) -> None:
#         bs = BoardState()
#         bs.store_design_spec("design-1", SAMPLE_SPEC)
#         bs.remove("design-1")
#         assert bs.get_design_spec("design-1") is None

#     def test_spec_cleared_on_clear(self) -> None:
#         bs = BoardState()
#         bs.store_design_spec("design-1", SAMPLE_SPEC)
#         bs.store_design_spec("design-2", MODIFIED_SPEC)
#         bs.clear()
#         assert bs.get_design_spec("design-1") is None
#         assert bs.get_design_spec("design-2") is None

#     def test_remove_nonexistent_spec_is_noop(self) -> None:
#         """Removing an element without a stored spec should not raise."""
#         bs = BoardState()
#         # Record an element first so remove has something to pop from _elements.
#         instr = ShowTextInstruction(text="Hello", element_id="text-1")
#         bs.record(instr)
#         bs.remove("text-1")  # No spec stored — should not raise.


# # ── BoardManager spec delegation ──────────────────────────────


# class TestBoardManagerSpecStorage:
#     def test_store_and_retrieve_active_board(self) -> None:
#         bm = BoardManager()
#         bm.store_design_spec("design-1", SAMPLE_SPEC)
#         assert bm.get_design_spec("design-1") is SAMPLE_SPEC

#     def test_get_spec_cross_board(self) -> None:
#         """Spec stored on board-1 should be retrievable even when board-2 is active."""
#         bm = BoardManager()
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         # Create and switch to a new board.
#         bm.create_and_switch("Board 2", uuid4())
#         assert bm.active_id == "board-2"

#         # Should still find the spec on board-1.
#         assert bm.get_design_spec("design-1") is SAMPLE_SPEC

#     def test_get_spec_nonexistent_returns_none(self) -> None:
#         bm = BoardManager()
#         assert bm.get_design_spec("design-99") is None

#     def test_store_on_active_not_visible_from_wrong_board(self) -> None:
#         """Spec stored on board-2 should be found when board-1 is active."""
#         bm = BoardManager()

#         # Switch to board-2, store spec there.
#         bm.create_and_switch("Board 2", uuid4())
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         # Switch back to board-1.
#         bm.switch_to("board-1")
#         assert bm.active_id == "board-1"

#         # Cross-board search should find it.
#         assert bm.get_design_spec("design-1") is SAMPLE_SPEC


# # ── modify_design_diagram_spec ─────────────────────────────────


# class TestModifyDesignDiagramSpec:
#     @pytest.mark.asyncio
#     async def test_sends_existing_spec_in_message(self) -> None:
#         """Verify the existing spec is included in the user message to Claude."""
#         with patch(
#             "feynman.agent.design_bridge._route_call",
#             new_callable=AsyncMock,
#             return_value=MODIFIED_SPEC,
#         ) as mock_call:
#             from feynman.agent.design_bridge import modify_design_diagram_spec

#             result = await modify_design_diagram_spec(
#                 SAMPLE_SPEC, "Add an applied force arrow pointing right"
#             )

#             assert result is MODIFIED_SPEC
#             mock_call.assert_called_once()
#             user_message = mock_call.call_args[0][0]
#             # Verify the spec JSON is in the message.
#             assert '"Free Body Diagram"' in user_message
#             assert "weight-arrow" in user_message
#             # Verify the modification instruction is in the message.
#             assert "Add an applied force arrow pointing right" in user_message

#     @pytest.mark.asyncio
#     async def test_passes_model_and_max_tokens(self) -> None:
#         with patch(
#             "feynman.agent.design_bridge._route_call",
#             new_callable=AsyncMock,
#             return_value=MODIFIED_SPEC,
#         ) as mock_call:
#             from feynman.agent.design_bridge import modify_design_diagram_spec

#             await modify_design_diagram_spec(
#                 SAMPLE_SPEC, "change color", model="haiku", max_tokens=8000
#             )

#             _, kwargs = mock_call.call_args
#             assert kwargs["model"] == "haiku"
#             assert kwargs["max_tokens"] == 8000


# # ── modify_design_diagram tool ─────────────────────────────────


# def _make_mock_ctx(board_manager: BoardManager | None = None) -> MagicMock:
#     """Create a mock RunContext with TeachingContext userdata."""
#     ctx = MagicMock()
#     ctx.wait_for_playout = AsyncMock()
#     ctx.session.room_io.room.local_participant.publish_data = AsyncMock()
#     ctx.session.current_agent.update_instructions = AsyncMock()

#     userdata = MagicMock()
#     userdata.board_manager = board_manager or BoardManager()
#     userdata.audit = SessionAudit()
#     userdata.current_concept_index = 0
#     userdata.current_concept = None
#     userdata.lesson_plan = None
#     userdata.anticipation = MagicMock()
#     userdata.anticipation.match = MagicMock(return_value=None)
#     # Phase 5a-2: short-circuit the diagram-verification scheduler — these
#     # tests don't exercise the perception loop.
#     userdata.board_verifier = None
#     ctx.userdata = userdata
#     return ctx


# class TestModifyDesignDiagramTool:
#     @pytest.mark.asyncio
#     async def test_nonexistent_target_returns_error(self) -> None:
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         result = await modify_design_diagram(
#             ctx, target_id="design-99", modification="change color"
#         )
#         assert "No design diagram found" in result
#         assert "design-99" in result

#     @pytest.mark.asyncio
#     async def test_modify_retrieves_and_sends_spec(self) -> None:
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         bm = ctx.userdata.board_manager

#         # Pre-store a spec as if draw_design_diagram was called.
#         instr = DrawDesignDiagramInstruction(title="FBD", spec=SAMPLE_SPEC, element_id="design-1")
#         bm.record(instr)
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         with patch(
#             "feynman.agent.design_bridge.modify_design_diagram_spec",
#             new_callable=AsyncMock,
#             return_value=MODIFIED_SPEC,
#         ) as mock_modify:
#             result = await modify_design_diagram(
#                 ctx,
#                 target_id="design-1",
#                 modification="Add applied force",
#             )

#             mock_modify.assert_called_once_with(SAMPLE_SPEC, "Add applied force")
#             assert "design-1" in result
#             assert "Modified" in result

#     @pytest.mark.asyncio
#     async def test_modify_publishes_same_element_id(self) -> None:
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         bm = ctx.userdata.board_manager

#         instr = DrawDesignDiagramInstruction(title="FBD", spec=SAMPLE_SPEC, element_id="design-1")
#         bm.record(instr)
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         with patch(
#             "feynman.agent.design_bridge.modify_design_diagram_spec",
#             new_callable=AsyncMock,
#             return_value=MODIFIED_SPEC,
#         ):
#             await modify_design_diagram(ctx, target_id="design-1", modification="Add force")

#             # Check that publish_data was called with JSON containing the same element_id.
#             publish_call = ctx.session.room_io.room.local_participant.publish_data
#             assert publish_call.called
#             import json

#             published_json = json.loads(publish_call.call_args[0][0])
#             assert published_json["element_id"] == "design-1"

#     @pytest.mark.asyncio
#     async def test_modify_updates_stored_spec(self) -> None:
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         bm = ctx.userdata.board_manager

#         instr = DrawDesignDiagramInstruction(title="FBD", spec=SAMPLE_SPEC, element_id="design-1")
#         bm.record(instr)
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         with patch(
#             "feynman.agent.design_bridge.modify_design_diagram_spec",
#             new_callable=AsyncMock,
#             return_value=MODIFIED_SPEC,
#         ):
#             await modify_design_diagram(ctx, target_id="design-1", modification="Add force")

#             # The stored spec should now be the modified one.
#             assert bm.get_design_spec("design-1") is MODIFIED_SPEC

#     @pytest.mark.asyncio
#     async def test_modify_records_audit_event(self) -> None:
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         bm = ctx.userdata.board_manager
#         audit = ctx.userdata.audit

#         instr = DrawDesignDiagramInstruction(title="FBD", spec=SAMPLE_SPEC, element_id="design-1")
#         bm.record(instr)
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         with patch(
#             "feynman.agent.design_bridge.modify_design_diagram_spec",
#             new_callable=AsyncMock,
#             return_value=MODIFIED_SPEC,
#         ):
#             await modify_design_diagram(ctx, target_id="design-1", modification="Add force")

#             assert audit.count("modify_diagram", "modified") == 1

#     @pytest.mark.asyncio
#     async def test_modify_returns_sub_element_ids(self) -> None:
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         bm = ctx.userdata.board_manager

#         instr = DrawDesignDiagramInstruction(title="FBD", spec=SAMPLE_SPEC, element_id="design-1")
#         bm.record(instr)
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         with patch(
#             "feynman.agent.design_bridge.modify_design_diagram_spec",
#             new_callable=AsyncMock,
#             return_value=MODIFIED_SPEC,
#         ):
#             result = await modify_design_diagram(
#                 ctx, target_id="design-1", modification="Add applied force"
#             )

#             # MODIFIED_SPEC has 4 elements with IDs.
#             assert "applied-arrow" in result
#             assert "weight-arrow" in result

#     @pytest.mark.asyncio
#     async def test_modify_failure_returns_fallback_message(self) -> None:
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         bm = ctx.userdata.board_manager

#         instr = DrawDesignDiagramInstruction(title="FBD", spec=SAMPLE_SPEC, element_id="design-1")
#         bm.record(instr)
#         bm.store_design_spec("design-1", SAMPLE_SPEC)

#         with patch(
#             "feynman.agent.design_bridge.modify_design_diagram_spec",
#             new_callable=AsyncMock,
#             side_effect=ValueError("Claude returned invalid JSON"),
#         ):
#             result = await modify_design_diagram(
#                 ctx, target_id="design-1", modification="break things"
#             )

#             assert "Failed to modify" in result
#             assert "draw_design_diagram" in result


# # ── Prompt instructions ────────────────────────────────────────


# class TestModifyDiagramPromptInstructions:
#     def test_modify_instructions_in_prompt(self) -> None:
#         from feynman.agent.prompts import build_teaching_prompt
#         from feynman.agent.teaching_context import TeachingContext

#         tc = TeachingContext(
#             session_id=uuid4(),
#             state_machine=MagicMock(),
#         )
#         prompt = build_teaching_prompt(None, tc)
#         assert "modify_design_diagram" in prompt
#         assert "modify vs draw_design_diagram" in prompt

#     def test_modify_instructions_with_lesson_plan(self) -> None:
#         from feynman.agent.prompts import build_teaching_prompt
#         from feynman.agent.teaching_context import TeachingContext

#         plan = MagicMock()
#         plan.topic = "Newton's Laws"
#         plan.grade_level = "Grade 9"
#         plan.objective = "Understand forces"
#         plan.concepts = []

#         sm = MagicMock()
#         sm.depth = 1  # Not in a doubt branch.
#         tc = TeachingContext(
#             session_id=uuid4(),
#             state_machine=sm,
#         )
#         tc._lesson_plan = plan
#         prompt = build_teaching_prompt(plan, tc)
#         assert "modify_design_diagram" in prompt


# class TestModifyPreservesPosition:
#     @pytest.mark.asyncio
#     async def test_modify_keeps_existing_position(self) -> None:
#         """Modified diagram preserves its original x,y position."""
#         from feynman.agent.tools import modify_design_diagram

#         ctx = _make_mock_ctx()
#         bm = ctx.userdata.board_manager
#         ctx.userdata.board_verifier = None

#         # Simulate draw_design_diagram having placed design-1 with bounds.
#         original_spec = {"title": "Forces", "width": 400, "height": 300, "elements": [{"id": "e1"}]}
#         instr = DrawDesignDiagramInstruction(
#             title="Forces",
#             description="Force diagram",
#             spec=original_spec,
#         )
#         instr.element_id = "design-1"
#         instr.position_x = 200.0
#         instr.position_y = 150.0
#         bm.record(instr)
#         bm.store_design_spec("design-1", original_spec)

#         # Add the element to the spatial solver (simulating bounds report).
#         board_state = bm.active_board.state
#         board_state.spatial_solver.update_occupied("design-1", Rect(200, 150, 400, 300))

#         # Modify the diagram.
#         modified_spec = {
#             "title": "Forces v2",
#             "width": 500,
#             "height": 400,
#             "elements": [{"id": "e1"}, {"id": "e2"}],
#         }
#         with patch(
#             "feynman.agent.design_bridge.modify_design_diagram_spec",
#             new_callable=AsyncMock,
#             return_value=modified_spec,
#         ):
#             result = await modify_design_diagram(
#                 ctx,
#                 target_id="design-1",
#                 modification="add friction vector",
#             )

#         assert "design-1" in result
#         # Verify the published instruction has the ORIGINAL position, not a new one.
#         published_calls = ctx.session.room_io.room.local_participant.publish_data.call_args_list
#         assert len(published_calls) >= 1
#         import json

#         last_payload = json.loads(published_calls[-1][0][0])
#         assert last_payload["position_x"] == 200.0
#         assert last_payload["position_y"] == 150.0
