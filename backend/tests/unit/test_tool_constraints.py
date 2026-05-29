# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Phase 2B — `state_constrained` decorator + applied-tool integration tests.

# Verifies the decorator gates LLM tool calls based on the current
# `TeachingState` and that the three applied tools (`advance_concept`,
# `start_doubt_branch`, `switch_board`) raise `ToolConstraintError` when
# called inside `HANDLING_DOUBT`.

# Tests use a real `TeachingContext` + `TeachingStateMachine` so the
# decorator's `ctx.userdata.state_machine.current.state` chain is exercised
# end-to-end (mocking that chain would skip the very behaviour under test).
# """

# from __future__ import annotations

# from unittest.mock import MagicMock
# from uuid import uuid4

# import pytest

# from feynman.agent.state_machine import TeachingStateMachine
# from feynman.agent.states import TeachingState
# from feynman.agent.teaching_context import TeachingContext
# from feynman.common.exceptions import ToolConstraintError


# @pytest.fixture
# def tc() -> TeachingContext:
#     sid = uuid4()
#     return TeachingContext(
#         session_id=sid,
#         state_machine=TeachingStateMachine(session_id=sid),
#     )


# def _ctx(tc: TeachingContext) -> MagicMock:
#     """Mock RunContext with userdata pointing at a real TC."""
#     ctx = MagicMock()
#     ctx.userdata = tc
#     return ctx


# # ── Per-tool integration tests ─────────────────────────────────────────────────


# async def test_state_constrained_blocks_in_handling_doubt(tc: TeachingContext):
#     """advance_concept inside HANDLING_DOUBT raises with the documented message."""
#     from feynman.agent.tools import advance_concept

#     # `push_branch` puts the state machine into HANDLING_DOUBT.
#     await tc.state_machine.push_branch(concept="some doubt")
#     assert tc.state_machine.current.state == TeachingState.HANDLING_DOUBT

#     with pytest.raises(ToolConstraintError, match="advance the lesson"):
#         await advance_concept(_ctx(tc))


# async def test_state_constrained_allows_in_teaching(tc: TeachingContext):
#     """advance_concept on the root TEACHING branch passes the gate.

#     With no lesson plan loaded, the body returns the free-form sentinel —
#     the point is that the decorator did NOT block the call.
#     """
#     from feynman.agent.tools import advance_concept

#     assert tc.state_machine.current.state == TeachingState.TEACHING

#     result = await advance_concept(_ctx(tc))
#     assert "No lesson plan" in result


# async def test_nested_doubt_blocked(tc: TeachingContext):
#     """start_doubt_branch inside HANDLING_DOUBT raises the nested-doubt error."""
#     from feynman.agent.tools import start_doubt_branch

#     await tc.state_machine.push_branch(concept="first doubt")

#     with pytest.raises(ToolConstraintError, match="nested doubt"):
#         await start_doubt_branch(_ctx(tc), related_concept="another doubt")


# async def test_switch_board_blocked_in_doubt(tc: TeachingContext):
#     """switch_board inside HANDLING_DOUBT raises with the documented message."""
#     from feynman.agent.tools import switch_board

#     await tc.state_machine.push_branch(concept="x")

#     with pytest.raises(ToolConstraintError, match="switch boards"):
#         await switch_board(_ctx(tc), board_id="some-board")
