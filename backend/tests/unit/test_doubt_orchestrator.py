"""Phase 2A — DoubtOrchestrator core tests.

Verifies snapshot + restore + checklist behavior. Watchdog timing and
voice-keyword auto-tick are Phase 2B and have their own test files.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from feynman.agent.doubt_orchestrator import (
    DEFAULT_RETURN_CUE,
    FORCED_RETURN_CUE,
    ChecklistItem,
)
from feynman.agent.state_machine import BranchContext, TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.common.exceptions import ToolConstraintError
from feynman.visuals.schemas import HighlightPulseInstruction


@pytest.fixture
def tc() -> TeachingContext:
    """A minimal TeachingContext with the orchestrator wired up."""
    sid = uuid4()
    return TeachingContext(
        session_id=sid,
        state_machine=TeachingStateMachine(session_id=sid),
    )


def _checklist(*specs: tuple[str, list[str]]) -> list[ChecklistItem]:
    return [ChecklistItem(description=desc, auto_satisfied_by=tools) for desc, tools in specs]


async def _push_doubt(
    tc: TeachingContext,
    *,
    concept: str = "ratio constancy",
    checklist: list[ChecklistItem] | None = None,
) -> tuple[UUID, BranchContext]:
    """Helper: push a doubt branch + register with orchestrator."""
    parent_id = tc.state_machine.current.id
    branch = await tc.state_machine.push_branch(concept=concept)
    await tc.doubt_orchestrator.on_push(
        branch,
        concept,
        parent_branch_id=parent_id,
        checklist=checklist,
    )
    return parent_id, branch


# ─────────────────────────────────────────────────────────────────────────────


async def test_auto_snapshot_captures_state(tc: TeachingContext):
    """on_push snapshots concept_index, active_highlights, active_annotations,
    notebook_cursor, parent_branch_id, started_at."""
    tc.current_concept_index = 2
    tc.last_beat_index = 4
    tc.active_highlights = ["el-hypotenuse-1", "el-opposite-2"]
    tc.active_annotations = ["pin-7"]
    # Seed the audit log so notebook_cursor is non-zero.
    tc.audit.record("routing", "tool_call", "dummy")
    tc.audit.record("routing", "tool_call", "dummy")

    parent_id, branch = await _push_doubt(
        tc,
        checklist=_checklist(("show diagram", ["draw_design_diagram"])),
    )

    assert branch.return_anchor is not None
    anchor = branch.return_anchor
    assert anchor.parent_branch_id == parent_id
    assert anchor.parent_concept_index == 2
    assert anchor.last_beat_index == 4
    assert anchor.active_highlights == ["el-hypotenuse-1", "el-opposite-2"]
    assert anchor.active_annotations == ["pin-7"]
    assert anchor.notebook_cursor == 2
    assert anchor.last_voice_anchor == ""  # Phase 2B fills this
    assert branch.started_at is not None
    assert len(branch.checklist) == 1


async def test_auto_restore_replays_highlights(tc: TeachingContext):
    """on_pop fires a highlight_pulse for each id captured in the snapshot."""
    tc.active_highlights = ["el-1", "el-2", "el-3"]

    await _push_doubt(tc)

    publish_mock: AsyncMock = AsyncMock()
    say_mock: AsyncMock = AsyncMock()
    popped = await tc.state_machine.pop_branch()
    await tc.doubt_orchestrator.on_pop(
        popped,
        publish_visual=publish_mock,
        say=say_mock,
    )

    assert publish_mock.await_count == 3
    fired_ids = [call.args[0].target_element_id for call in publish_mock.await_args_list]
    assert fired_ids == ["el-1", "el-2", "el-3"]
    for call in publish_mock.await_args_list:
        assert isinstance(call.args[0], HighlightPulseInstruction)


async def test_auto_restore_emits_return_cue(tc: TeachingContext):
    """on_pop emits the verbatim default cue (not the forced fallback)."""
    await _push_doubt(tc)

    say_mock: AsyncMock = AsyncMock()
    popped = await tc.state_machine.pop_branch()
    await tc.doubt_orchestrator.on_pop(popped, say=say_mock, forced=False)

    say_mock.assert_awaited_once_with(DEFAULT_RETURN_CUE)


async def test_auto_restore_forced_uses_fallback_cue(tc: TeachingContext):
    """Forced pop emits the polite fallback cue instead of the default."""
    await _push_doubt(tc)

    say_mock: AsyncMock = AsyncMock()
    popped = await tc.state_machine.pop_branch()
    await tc.doubt_orchestrator.on_pop(popped, say=say_mock, forced=True)

    say_mock.assert_awaited_once_with(FORCED_RETURN_CUE)


async def test_auto_restore_restores_overlay_tracking(tc: TeachingContext):
    """After pop, tc.active_highlights / active_annotations reflect the parent."""
    tc.active_highlights = ["el-1"]
    tc.active_annotations = ["pin-A"]
    await _push_doubt(tc)

    # Doubt accrues its own overlays during the branch.
    tc.active_highlights.clear()
    tc.active_annotations.clear()
    tc.active_highlights.extend(["doubt-el-1", "doubt-el-2"])
    tc.active_annotations.append("doubt-pin")

    popped = await tc.state_machine.pop_branch()
    await tc.doubt_orchestrator.on_pop(popped)

    assert tc.active_highlights == ["el-1"]
    assert tc.active_annotations == ["pin-A"]


async def test_checklist_gate_blocks_premature_resolve(tc: TeachingContext):
    """3-item checklist with 2 ticked → is_resolution_allowed returns False."""
    items = _checklist(
        ("show diagram", ["draw_design_diagram"]),
        ("explain ratios", ["write_step"]),
        ("tie back to ladder", ["pin_label_near"]),
    )
    _, branch = await _push_doubt(tc, checklist=items)

    branch.checklist[0].status = "done"
    branch.checklist[1].status = "done"

    allowed, reason = tc.doubt_orchestrator.is_resolution_allowed(branch.id)
    assert allowed is False
    assert "tie back to ladder" in reason
    assert "show diagram" not in reason  # already done
    assert "mark_doubt_step_complete" in reason  # tells LLM the override path


async def test_checklist_gate_allows_complete_resolve(tc: TeachingContext):
    """All items ticked → is_resolution_allowed returns True."""
    items = _checklist(
        ("show diagram", ["draw_design_diagram"]),
        ("explain ratios", ["write_step"]),
        ("tie back", ["pin_label_near"]),
    )
    _, branch = await _push_doubt(tc, checklist=items)

    for item in branch.checklist:
        item.status = "done"

    allowed, reason = tc.doubt_orchestrator.is_resolution_allowed(branch.id)
    assert allowed is True
    assert reason == ""


async def test_checklist_gate_allows_when_branch_untracked(tc: TeachingContext):
    """Defensive fallback: unknown branch_id is allowed (no-op gate)."""
    allowed, reason = tc.doubt_orchestrator.is_resolution_allowed(uuid4())
    assert allowed is True
    assert reason == ""


async def test_auto_tick_from_tool_call(tc: TeachingContext):
    """on_tool_invoked ticks items whose auto_satisfied_by lists the tool."""
    items = _checklist(
        ("show diagram", ["draw_design_diagram", "draw_scene"]),
        ("write equation", ["write_equation"]),
        ("tie back", ["pin_label_near"]),
    )
    _, branch = await _push_doubt(tc, checklist=items)

    tc.doubt_orchestrator.on_tool_invoked("draw_design_diagram", branch.id)
    assert branch.checklist[0].status == "done"
    assert branch.checklist[1].status == "pending"
    assert branch.checklist[2].status == "pending"

    tc.doubt_orchestrator.on_tool_invoked("pin_label_near", branch.id)
    assert branch.checklist[2].status == "done"

    # Calling a tool not in any auto_satisfied_by list is a no-op.
    tc.doubt_orchestrator.on_tool_invoked("show_graph", branch.id)
    assert branch.checklist[1].status == "pending"


async def test_mark_doubt_step_complete_manual_override(tc: TeachingContext):
    """mark_step_complete ticks an item without auto-trigger; range is checked."""
    items = _checklist(
        ("show diagram", ["draw_design_diagram"]),
        ("explain ratios", ["write_step"]),
    )
    _, branch = await _push_doubt(tc, checklist=items)

    tc.doubt_orchestrator.mark_step_complete(branch.id, 1)
    assert branch.checklist[1].status == "done"
    assert branch.checklist[0].status == "pending"

    with pytest.raises(ToolConstraintError, match="out of range"):
        tc.doubt_orchestrator.mark_step_complete(branch.id, 5)

    with pytest.raises(ToolConstraintError, match="out of range"):
        tc.doubt_orchestrator.mark_step_complete(branch.id, -1)

    with pytest.raises(ToolConstraintError, match="tracked doubt"):
        tc.doubt_orchestrator.mark_step_complete(uuid4(), 0)


async def test_orchestrator_state_clean_after_pop(tc: TeachingContext):
    """After on_pop, _active no longer contains the branch_id; watchdog cancelled."""
    _, branch = await _push_doubt(tc)
    assert branch.id in tc.doubt_orchestrator.active_branch_ids

    popped = await tc.state_machine.pop_branch()
    await tc.doubt_orchestrator.on_pop(popped)

    assert branch.id not in tc.doubt_orchestrator.active_branch_ids
    assert tc.doubt_orchestrator.get_state(branch.id) is None
