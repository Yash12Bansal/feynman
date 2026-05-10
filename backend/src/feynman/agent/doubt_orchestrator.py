"""Doubt branch orchestrator — deterministic state management for student doubts.

The teaching agent's `start_doubt_branch` / `resolve_doubt` tools provide the
mechanics (push/pop, board switch). The orchestrator owns the *policy*: snapshot
parent state on push, restore it on pop, gate resolution on a checklist, and
bound the doubt by elapsed time so the LLM cannot run a branch forever.

Phase 2A landed snapshot + restore + checklist + tool-call auto-tick. Phase 2B
fills the safety net: watchdog (60s soft nudge + 120s force-resolve),
voice-keyword auto-tick, and per-branch callbacks for nudge / force-resolve.
The `@state_constrained` decorator (sibling module `tool_constraints.py`)
forbids a small set of escape-hatch tools while inside `HANDLING_DOUBT`.

Hooks called from `tools.py`:
- `on_push(branch, related_concept, *, parent_branch_id, checklist=None,
   on_soft_nudge=None, force_resolve=None)` — after `push_branch` + `push_board`
- `is_resolution_allowed(branch_id)` — before `resolve_doubt`'s pop
- `on_pop(branch, publish_visual=..., say=..., forced=False)` — after pop
- `on_tool_invoked(tool_name, branch_id)` — from `_publish_visual`
- `on_voice_emitted(transcript, branch_id)` — from worker.py's
  `conversation_item_added` handler when `role == "assistant"`
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from feynman.agent.state_machine import BranchContext
    from feynman.agent.teaching_context import TeachingContext
    from feynman.visuals.schemas import _BaseInstruction

logger = structlog.get_logger()


DEFAULT_RETURN_CUE = "OK — back to your ladder. Let's use what we just wrote down."
FORCED_RETURN_CUE = "Let's circle back to that next time — we still have ground to cover."

# Watchdog defaults (seconds). Override per-instance via DoubtOrchestrator(...,
# soft_nudge_after_s=..., force_resolve_after_s=...). Tests pass tiny values
# so they don't sleep for real minutes.
DEFAULT_SOFT_NUDGE_AFTER_S = 60.0
DEFAULT_FORCE_RESOLVE_AFTER_S = 120.0


class ChecklistItem(BaseModel):
    """One requirement the agent must satisfy before `resolve_doubt` is allowed.

    Items auto-tick when a tool listed in `auto_satisfied_by` is invoked, when
    a keyword in `keywords` appears in the agent's emitted voice, or via the
    explicit `mark_doubt_step_complete(step_index)` tool when the agent knows
    it has addressed the requirement but no auto-trigger fired.
    """

    description: str = Field(..., min_length=1, max_length=240)
    status: Literal["pending", "done"] = "pending"
    auto_satisfied_by: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ReturnAnchor(BaseModel):
    """Snapshot of parent state captured at doubt push, replayed at pop."""

    parent_branch_id: UUID
    parent_concept_index: int
    last_beat_index: int = 0
    last_voice_anchor: str = ""
    active_highlights: list[str] = Field(default_factory=list)
    active_annotations: list[str] = Field(default_factory=list)
    notebook_cursor: int = 0
    timestamp: datetime

    model_config = {"arbitrary_types_allowed": True}


class DoubtState(BaseModel):
    """Per-branch doubt state held in the orchestrator's `_active` map.

    `soft_nudge_fired` / `force_resolve_fired` are introspection flags used by
    `prompts.py` (to render the soft-nudge sentence) and tests. The watchdog
    sets them when its sleeps elapse.
    """

    branch_id: UUID
    related_concept: str
    return_anchor: ReturnAnchor
    checklist: list[ChecklistItem]
    started_at: datetime
    soft_nudge_fired: bool = False
    force_resolve_fired: bool = False

    model_config = {"arbitrary_types_allowed": True}


PublishCallback = Callable[["_BaseInstruction"], Awaitable[None]]
SayCallback = Callable[[str], Awaitable[None]]
SoftNudgeCallback = Callable[["BranchContext"], Awaitable[None]]
ForceResolveCallback = Callable[["BranchContext"], Awaitable[None]]


@dataclass
class _BranchCallbacks:
    """Per-branch callbacks captured at `on_push`. Stored separately from the
    Pydantic `DoubtState` because callables don't fit cleanly in BaseModel."""

    branch_ref: BranchContext
    on_soft_nudge: SoftNudgeCallback | None = None
    force_resolve: ForceResolveCallback | None = None


class DoubtOrchestrator:
    """Deterministic state management for doubt branches.

    The watchdog runs on `asyncio.create_task(_timeout_watchdog(...))` driven by
    the event loop. `soft_nudge_after_s` and `force_resolve_after_s` are tunable
    per-instance — tests pass tiny values so they don't sleep real minutes.
    """

    def __init__(
        self,
        tc: TeachingContext,
        *,
        soft_nudge_after_s: float = DEFAULT_SOFT_NUDGE_AFTER_S,
        force_resolve_after_s: float = DEFAULT_FORCE_RESOLVE_AFTER_S,
    ) -> None:
        self._tc = tc
        self._active: dict[UUID, DoubtState] = {}
        self._timeout_tasks: dict[UUID, asyncio.Task[None]] = {}
        self._callbacks: dict[UUID, _BranchCallbacks] = {}
        self._soft_nudge_after_s = soft_nudge_after_s
        self._force_resolve_after_s = force_resolve_after_s

    # ── Hooks called from tools.py ────────────────────────────────────────

    async def on_push(
        self,
        branch_context: BranchContext,
        related_concept: str,
        *,
        parent_branch_id: UUID,
        checklist: list[ChecklistItem] | None = None,
        on_soft_nudge: SoftNudgeCallback | None = None,
        force_resolve: ForceResolveCallback | None = None,
    ) -> DoubtState:
        """Snapshot parent state, register the new doubt branch.

        `parent_branch_id` must be captured by the caller *before* `push_branch`
        runs — by the time `on_push` fires, `tc.state_machine.current` is the
        new doubt branch.

        `checklist` is supplied by the caller (typically derived from the
        `plan_doubt`-produced `ConceptTeachingPlan.resolution_checklist`).
        If absent, an empty checklist is used and resolution is unblocked.

        `on_soft_nudge` and `force_resolve` are watchdog callbacks. The
        watchdog awaits them at the configured timing. `force_resolve` is
        responsible for invoking the orchestrator's `on_pop(forced=True)` —
        the watchdog body sets the flag and delegates everything else.
        """
        anchor = self._capture_return_anchor(parent_branch_id)
        items = list(checklist) if checklist else []
        state = DoubtState(
            branch_id=branch_context.id,
            related_concept=related_concept,
            return_anchor=anchor,
            checklist=items,
            started_at=datetime.utcnow(),
        )
        self._active[branch_context.id] = state
        self._callbacks[branch_context.id] = _BranchCallbacks(
            branch_ref=branch_context,
            on_soft_nudge=on_soft_nudge,
            force_resolve=force_resolve,
        )
        branch_context.return_anchor = anchor
        branch_context.checklist = items
        branch_context.started_at = state.started_at

        logger.info(
            "doubt_orchestrator.pushed",
            branch_id=str(branch_context.id),
            related_concept=related_concept,
            checklist_size=len(items),
            active_highlights=anchor.active_highlights,
            active_annotations=anchor.active_annotations,
            notebook_cursor=anchor.notebook_cursor,
        )

        self._timeout_tasks[branch_context.id] = asyncio.create_task(
            self._timeout_watchdog(branch_context.id)
        )

        return state

    def is_resolution_allowed(self, branch_id: UUID) -> tuple[bool, str]:
        """Gate `resolve_doubt` on checklist completion.

        Returns `(True, "")` if every item is `done` (or the branch isn't
        tracked — defensive fallback). Returns `(False, reason)` otherwise,
        with `reason` listing the still-pending items so the LLM can address
        them or call `mark_doubt_step_complete` to override.
        """
        state = self._active.get(branch_id)
        if state is None:
            return (True, "")
        pending = [item.description for item in state.checklist if item.status == "pending"]
        if pending:
            return (
                False,
                "Cannot resolve yet — still pending: "
                + "; ".join(pending)
                + ". Address these or call mark_doubt_step_complete(step_index) to override.",
            )
        return (True, "")

    async def on_pop(
        self,
        branch_context: BranchContext,
        *,
        publish_visual: PublishCallback | None = None,
        say: SayCallback | None = None,
        forced: bool = False,
    ) -> ReturnAnchor | None:
        """Restore parent state. Returns the anchor that was replayed (or None).

        Side effects driven by the caller-supplied callbacks:
        - `publish_visual` fires a fresh `highlight_pulse` for each id in
          `active_highlights` to re-establish presence on the parent slide.
        - `say` emits the verbatim return cue (or the forced fallback when
          `forced=True`).
        """
        state = self._active.pop(branch_context.id, None)
        self._callbacks.pop(branch_context.id, None)
        task = self._timeout_tasks.pop(branch_context.id, None)
        if task and not task.done():
            task.cancel()

        if state is None:
            return None

        await self._restore_parent_state(
            state.return_anchor,
            publish_visual=publish_visual,
            say=say,
            forced=forced,
        )

        logger.info(
            "doubt_orchestrator.popped",
            branch_id=str(branch_context.id),
            related_concept=state.related_concept,
            forced=forced,
        )
        return state.return_anchor

    def on_tool_invoked(self, tool_name: str, branch_id: UUID | None) -> None:
        """Tick checklist items whose `auto_satisfied_by` includes `tool_name`."""
        if branch_id is None:
            return
        state = self._active.get(branch_id)
        if state is None:
            return
        for item in state.checklist:
            if item.status == "pending" and tool_name in item.auto_satisfied_by:
                item.status = "done"
                logger.info(
                    "doubt_orchestrator.checklist_auto_ticked",
                    branch_id=str(branch_id),
                    tool=tool_name,
                    item=item.description,
                )

    def on_voice_emitted(self, transcript: str, branch_id: UUID | None) -> None:
        """Tick checklist items whose `keywords` appear as substrings in the
        agent's emitted speech. Match is case-insensitive.

        Conservative by design: substring match only, no regex. The LLM may
        emit no keywords at all — `keywords` is opt-in, populated by
        `plan_doubt` when it decides a step is verbal-only.
        """
        if branch_id is None or not transcript:
            return
        state = self._active.get(branch_id)
        if state is None:
            return
        haystack = transcript.lower()
        for item in state.checklist:
            if item.status != "pending" or not item.keywords:
                continue
            matched = next(
                (kw for kw in item.keywords if kw and kw.lower() in haystack),
                None,
            )
            if matched is not None:
                item.status = "done"
                logger.info(
                    "doubt_orchestrator.checklist_voice_ticked",
                    branch_id=str(branch_id),
                    keyword=matched,
                    item=item.description,
                )

    def mark_step_complete(self, branch_id: UUID, step_index: int) -> None:
        """Manual override path for `mark_doubt_step_complete` tool."""
        state = self._active.get(branch_id)
        if state is None:
            from feynman.common.exceptions import ToolConstraintError

            raise ToolConstraintError(
                "Not in a tracked doubt branch — mark_doubt_step_complete is a no-op."
            )
        if step_index < 0 or step_index >= len(state.checklist):
            from feynman.common.exceptions import ToolConstraintError

            raise ToolConstraintError(
                f"step_index {step_index} out of range "
                f"(0..{len(state.checklist) - 1 if state.checklist else 0})"
            )
        state.checklist[step_index].status = "done"
        logger.info(
            "doubt_orchestrator.checklist_manual_ticked",
            branch_id=str(branch_id),
            step_index=step_index,
            item=state.checklist[step_index].description,
        )

    # ── Read-only views ──────────────────────────────────────────────────

    def get_state(self, branch_id: UUID) -> DoubtState | None:
        return self._active.get(branch_id)

    @property
    def active_branch_ids(self) -> list[UUID]:
        return list(self._active.keys())

    # ── Internals ────────────────────────────────────────────────────────

    def _capture_return_anchor(self, parent_branch_id: UUID) -> ReturnAnchor:
        tc = self._tc
        return ReturnAnchor(
            parent_branch_id=parent_branch_id,
            parent_concept_index=tc.current_concept_index,
            last_beat_index=tc.last_beat_index,
            last_voice_anchor="",  # Phase 2B fills this when on_voice_emitted lands.
            active_highlights=list(tc.active_highlights),
            active_annotations=list(tc.active_annotations),
            notebook_cursor=len(tc.audit.events_for("routing")),
            timestamp=datetime.utcnow(),
        )

    async def _restore_parent_state(
        self,
        anchor: ReturnAnchor,
        *,
        publish_visual: PublishCallback | None,
        say: SayCallback | None,
        forced: bool,
    ) -> None:
        # Restore the live overlay tracking on the parent context. The doubt
        # board cleared these at push; on resume they reflect the parent again.
        self._tc.active_highlights = list(anchor.active_highlights)
        self._tc.active_annotations = list(anchor.active_annotations)

        # Re-fire `highlight_pulse` for every parent overlay id captured at push.
        if publish_visual is not None and anchor.active_highlights:
            from feynman.visuals.schemas import HighlightPulseInstruction, SyncMode

            for el_id in anchor.active_highlights:
                instr = HighlightPulseInstruction(
                    target_element_id=el_id,
                    sync_mode=SyncMode.IMMEDIATE,
                )
                try:
                    await publish_visual(instr)
                except Exception:
                    logger.warning(
                        "doubt_orchestrator.replay_highlight_failed",
                        element_id=el_id,
                        exc_info=True,
                    )

        # Surface the verbatim return cue (no LLM call).
        if say is not None:
            cue = self._return_cue(forced=forced)
            try:
                await say(cue)
            except Exception:
                logger.warning(
                    "doubt_orchestrator.return_cue_failed",
                    forced=forced,
                    exc_info=True,
                )

    def _return_cue(self, *, forced: bool) -> str:
        if forced:
            return FORCED_RETURN_CUE
        # Prefer the parent ConceptTeachingPlan's transition_to_next if it's a
        # natural-sounding return cue; fall back to the default. The LLM's
        # transition lines are sometimes addressed to "the next concept" rather
        # than "the resumed lesson" — keep things conservative and use the
        # default unless the plan provided an explicit `return_cue` field
        # (added in a future phase).
        return DEFAULT_RETURN_CUE

    async def _timeout_watchdog(self, branch_id: UUID) -> None:
        """Bound the doubt branch by elapsed time.

        Sleeps until `soft_nudge_after_s`, fires the soft nudge, then sleeps
        the remainder until `force_resolve_after_s` and fires force-resolve.
        Each step re-checks `_active` so a normal pop short-circuits cleanly.
        Cancellation (from `on_pop`) is silently absorbed.
        """
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(self._soft_nudge_after_s)
            if branch_id not in self._active:
                return
            await self._fire_soft_nudge(branch_id)

            remainder = max(0.0, self._force_resolve_after_s - self._soft_nudge_after_s)
            if remainder > 0:
                await asyncio.sleep(remainder)
            if branch_id not in self._active:
                return
            await self._force_resolve(branch_id)

    async def _fire_soft_nudge(self, branch_id: UUID) -> None:
        state = self._active.get(branch_id)
        if state is None:
            return
        state.soft_nudge_fired = True
        logger.info(
            "doubt_orchestrator.soft_nudge_fired",
            branch_id=str(branch_id),
            elapsed_s=(datetime.utcnow() - state.started_at).total_seconds(),
        )
        cb = self._callbacks.get(branch_id)
        if cb is not None and cb.on_soft_nudge is not None:
            try:
                await cb.on_soft_nudge(cb.branch_ref)
            except Exception:
                logger.warning(
                    "doubt_orchestrator.soft_nudge_callback_failed",
                    branch_id=str(branch_id),
                    exc_info=True,
                )

    async def _force_resolve(self, branch_id: UUID) -> None:
        state = self._active.get(branch_id)
        if state is None:
            return
        state.force_resolve_fired = True
        logger.warning(
            "doubt_orchestrator.force_resolve_fired",
            branch_id=str(branch_id),
            elapsed_s=(datetime.utcnow() - state.started_at).total_seconds(),
            pending_items=[i.description for i in state.checklist if i.status == "pending"],
        )
        cb = self._callbacks.get(branch_id)
        if cb is None or cb.force_resolve is None:
            # No caller-supplied force-resolve — best we can do is log and
            # leave state intact for manual inspection. The branch stays in
            # `_active` so the on_pop call from the LLM (if it ever fires)
            # still cleans up.
            return
        try:
            await cb.force_resolve(cb.branch_ref)
        except Exception:
            logger.error(
                "doubt_orchestrator.force_resolve_callback_failed",
                branch_id=str(branch_id),
                exc_info=True,
            )
