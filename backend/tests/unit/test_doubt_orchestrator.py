"""DoubtOrchestrator unit tests.

Phase 2A: snapshot + restore + checklist behavior.
Phase 2B: watchdog (soft nudge / force-resolve), voice-keyword auto-tick,
state cleanup, no-leak guarantee across many push/pop cycles.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from feynman.agent.doubt_orchestrator import (
    DEFAULT_RETURN_CUE,
    FORCED_RETURN_CUE,
    ChecklistItem,
    DoubtOrchestrator,
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


def _swap_fast_orchestrator(
    tc: TeachingContext, *, soft: float = 0.05, force: float = 10.0
) -> DoubtOrchestrator:
    """Replace `tc.doubt_orchestrator` with a fast-timing instance for watchdog
    tests. Default 50ms soft nudge / 10s force-resolve so a single short
    sleep exercises the soft-nudge path without paying the full force wait.
    """
    tc.doubt_orchestrator = DoubtOrchestrator(
        tc,
        soft_nudge_after_s=soft,
        force_resolve_after_s=force,
    )
    return tc.doubt_orchestrator


def _checklist(*specs: tuple[str, list[str]]) -> list[ChecklistItem]:
    return [ChecklistItem(description=desc, auto_satisfied_by=tools) for desc, tools in specs]


async def _push_doubt(
    tc: TeachingContext,
    *,
    concept: str = "ratio constancy",
    checklist: list[ChecklistItem] | None = None,
    on_soft_nudge=None,
    force_resolve=None,
) -> tuple[UUID, BranchContext]:
    """Helper: push a doubt branch + register with orchestrator."""
    parent_id = tc.state_machine.current.id
    branch = await tc.state_machine.push_branch(concept=concept)
    await tc.doubt_orchestrator.on_push(
        branch,
        concept,
        parent_branch_id=parent_id,
        checklist=checklist,
        on_soft_nudge=on_soft_nudge,
        force_resolve=force_resolve,
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


# ── Phase 2B: watchdog timing ──────────────────────────────────────────────────


async def test_soft_nudge_fires_at_60s(tc: TeachingContext):
    """Watchdog awaits the soft-nudge callback after `soft_nudge_after_s`."""
    _swap_fast_orchestrator(tc, soft=0.05, force=10.0)
    nudge: AsyncMock = AsyncMock()
    _, branch = await _push_doubt(tc, on_soft_nudge=nudge)

    # Give the watchdog enough time to clear the soft-nudge sleep but not the
    # full force-resolve window.
    await asyncio.sleep(0.15)

    nudge.assert_awaited_once()
    state = tc.doubt_orchestrator.get_state(branch.id)
    assert state is not None
    assert state.soft_nudge_fired is True
    assert state.force_resolve_fired is False


async def test_force_resolve_fires_at_120s(tc: TeachingContext):
    """Watchdog awaits the force-resolve callback after `force_resolve_after_s`."""
    _swap_fast_orchestrator(tc, soft=0.02, force=0.05)
    force_cb: AsyncMock = AsyncMock()
    _, branch = await _push_doubt(tc, force_resolve=force_cb)

    await asyncio.sleep(0.15)

    force_cb.assert_awaited_once()
    state = tc.doubt_orchestrator.get_state(branch.id)
    # The mock callback didn't pop, so state is still in _active.
    assert state is not None
    assert state.soft_nudge_fired is True
    assert state.force_resolve_fired is True


async def test_force_resolve_bypasses_checklist(tc: TeachingContext):
    """Watchdog fires force-resolve even if every checklist item is pending."""
    _swap_fast_orchestrator(tc, soft=0.005, force=0.02)
    items = _checklist(
        ("show diagram", ["draw_design_diagram"]),
        ("explain ratios", ["write_step"]),
        ("tie back", ["pin_label_near"]),
    )
    force_cb: AsyncMock = AsyncMock()
    _, branch = await _push_doubt(tc, checklist=items, force_resolve=force_cb)

    # Confirm the gate would block normal resolve.
    allowed, _reason = tc.doubt_orchestrator.is_resolution_allowed(branch.id)
    assert allowed is False

    await asyncio.sleep(0.10)

    # Force-resolve fires regardless of the checklist gate.
    force_cb.assert_awaited_once()
    state = tc.doubt_orchestrator.get_state(branch.id)
    assert state is not None
    assert state.force_resolve_fired is True
    # Items are still pending — the gate semantics are unchanged; force-resolve
    # bypasses the gate, it doesn't tick items.
    assert all(i.status == "pending" for i in state.checklist)


async def test_watchdog_cancelled_on_normal_resolve(tc: TeachingContext):
    """on_pop cancels the watchdog before any callback fires."""
    _swap_fast_orchestrator(tc, soft=0.5, force=10.0)
    nudge: AsyncMock = AsyncMock()
    force_cb: AsyncMock = AsyncMock()
    _, branch = await _push_doubt(tc, on_soft_nudge=nudge, force_resolve=force_cb)

    popped = await tc.state_machine.pop_branch()
    await tc.doubt_orchestrator.on_pop(popped)

    # Wait past the soft-nudge window — neither callback should fire.
    await asyncio.sleep(0.6)

    nudge.assert_not_awaited()
    force_cb.assert_not_awaited()
    assert branch.id not in tc.doubt_orchestrator._timeout_tasks
    assert branch.id not in tc.doubt_orchestrator._callbacks


async def test_orchestrator_state_clean_after_force_resolve(tc: TeachingContext):
    """After force-resolve fires and the callback runs on_pop, all state is clean."""
    orch = _swap_fast_orchestrator(tc, soft=0.02, force=0.05)

    async def _force_cb(branch_to_resolve: BranchContext) -> None:
        # Simulate the real `_force_resolve_doubt` callback, which pops the
        # state machine and runs the orchestrator's pop+restore.
        popped = await tc.state_machine.pop_branch()
        await orch.on_pop(popped, forced=True)

    _, branch = await _push_doubt(tc, force_resolve=_force_cb)
    await asyncio.sleep(0.15)

    assert branch.id not in orch._active
    assert branch.id not in orch._timeout_tasks
    assert branch.id not in orch._callbacks


async def test_10_consecutive_doubts_no_leaks(tc: TeachingContext):
    """10 sequential push+pop cycles leave _active / _timeout_tasks / _callbacks empty."""
    # Slow timing so no watchdog fires during the test.
    orch = _swap_fast_orchestrator(tc, soft=10.0, force=20.0)

    for i in range(10):
        _, branch = await _push_doubt(tc, concept=f"doubt-{i}")
        popped = await tc.state_machine.pop_branch()
        await orch.on_pop(popped)
        # Yield once so cancelled watchdog tasks get cleaned up.
        await asyncio.sleep(0)
        assert branch.id not in orch._active
        assert branch.id not in orch._callbacks
        # The cancelled task may linger one tick — but it's done() and the
        # next push reuses the dict slot.

    assert orch._active == {}
    assert orch._callbacks == {}
    # Every timeout task is done (cancelled or finished); none are leaking
    # active work.
    for task in orch._timeout_tasks.values():
        assert task.done()


# ── Phase 2B: voice-keyword auto-tick ──────────────────────────────────────────


async def test_auto_tick_from_voice_keyword(tc: TeachingContext):
    """on_voice_emitted ticks items whose `keywords` appear in the transcript.

    Match is case-insensitive substring. Empty keyword lists never match.
    Ticking a done item is a no-op.
    """
    items = [
        ChecklistItem(
            description="tie back to ladder",
            auto_satisfied_by=[],
            keywords=["ladder"],
        ),
        ChecklistItem(
            description="explain ratio",
            auto_satisfied_by=[],
            keywords=["ratio", "fraction"],
        ),
        ChecklistItem(
            description="visual only",
            auto_satisfied_by=["draw_design_diagram"],
            keywords=[],
        ),
    ]
    _, branch = await _push_doubt(tc, checklist=items)

    # Case 1: exact substring
    tc.doubt_orchestrator.on_voice_emitted(
        "So look at the ladder leaning against the wall",
        branch.id,
    )
    assert branch.checklist[0].status == "done"
    assert branch.checklist[1].status == "pending"
    assert branch.checklist[2].status == "pending"

    # Case 2: case-insensitive (LADDER would have already ticked, so use ratio)
    tc.doubt_orchestrator.on_voice_emitted(
        "The RATIO stays the same regardless of triangle size",
        branch.id,
    )
    assert branch.checklist[1].status == "done"

    # Case 3: substring inside another word ("ladders" matches "ladder")
    items2 = [
        ChecklistItem(description="mention ladder", auto_satisfied_by=[], keywords=["ladder"]),
    ]
    _, branch2 = await _push_doubt(tc, concept="ladder doubt", checklist=items2)
    tc.doubt_orchestrator.on_voice_emitted("Two ladders side by side", branch2.id)
    assert branch2.checklist[0].status == "done"

    # Case 4: no keywords → never matches, even if voice mentions description words
    assert branch.checklist[2].status == "pending"
    tc.doubt_orchestrator.on_voice_emitted("visual only message", branch.id)
    assert branch.checklist[2].status == "pending"

    # Case 5: empty transcript / unknown branch → silently no-op
    tc.doubt_orchestrator.on_voice_emitted("", branch.id)
    tc.doubt_orchestrator.on_voice_emitted("ladder", uuid4())  # unknown branch
