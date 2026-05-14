# 15 — Doubt Orchestrator

> Make the doubt branch reliable. Replace prompt-only branching (LLM decides everything) with a deterministic orchestrator that auto-snapshots parent state, auto-restores it on resolution, enforces a checklist before pop, time-bounds the doubt, and constrains tool access in `HANDLING_DOUBT` state.

**Status**: Design
**Date**: 2026-05-10
**Depends on**: `docs/design/12-aanya-demo-v0.md` §4 (doubt branch detail)
**Blocks**: Aanya demo build (Phase C in plan)

---

## 1. Why this matters

We just made the doubt branch real-time (`12-aanya-demo-v0.md` §3 beat 4) — the student asks whatever they actually want to ask, and the LLM responds live. This raises the reliability bar dramatically. With a scripted doubt, every behavior was predictable. With a real one, the LLM is making decisions the demo's success depends on:

- **Deciding to branch** when the student asks a clarifying question
- **Generating the response** to whatever was actually asked
- **Deciding when the doubt is resolved** and calling `resolve_doubt`
- **Remembering where it was** on the parent thread so the return is clean

Each of these is a place the LLM can fail. And every demo failure in front of a mom kills a validation session.

The current code (`tools.py:1637–1730`, `state_machine.py:36–106`) provides the *mechanics* — push/pop, board switch, anticipation engine — but the *policy* is entirely in the LLM's head. That has worked for prototypes; it will not work for production-grade demos to skeptical parents.

This doc specifies a deterministic **doubt orchestrator** that wraps the existing tools with five concrete guardrails. The LLM still reasons about content; the orchestrator handles state.

### The five failure modes we're eliminating

| Failure mode | What happens today | What the orchestrator does |
|---|---|---|
| LLM forgets to call `resolve_doubt` | Agent meanders inside the doubt forever | Force-resolve at 120s with polite fallback voice |
| LLM resolves before answering the question | Doubt branch is a no-op; student feels unheard | Resolution checklist must be ticked before `resolve_doubt` is allowed |
| LLM loses place on parent thread after pop | Awkward "now where were we?" silence | Auto-restore: system speaks return cue and restores highlight state |
| LLM advances the lesson while in HANDLING_DOUBT | Lesson skips ahead while still mid-doubt | Tool constraint: cannot advance concept index |
| LLM starts a nested doubt during a doubt | Stack confusion, hard to recover | Tool constraint: `start_doubt_branch` disabled inside HANDLING_DOUBT (v0) |

---

## 2. Architecture overview

A new module `backend/src/feynman/agent/doubt_orchestrator.py`. It wraps the existing branching primitives and provides:

- **State**: a `DoubtState` per active branch (return anchor, checklist, started_at, soft-nudge-fired, force-resolve scheduled)
- **Hooks**: called from `tools.py` on `start_doubt_branch` / `resolve_doubt`
- **Validation**: gates `resolve_doubt` based on checklist completion
- **Background tasks**: time-bound watchdog that fires soft nudges and force-resolve

```
                       ┌──────────────────────────────────────┐
                       │       LLM / agent                    │
                       │   (tools call, voice, visuals)       │
                       └───────────┬──────────────────────────┘
                                   │ start_doubt_branch / resolve_doubt
                                   ▼
                       ┌──────────────────────────────────────┐
                       │   DoubtOrchestrator                  │
                       │   - on_push() snapshots state        │
                       │   - on_pop() restores state          │
                       │   - is_resolution_allowed() gates    │
                       │   - timeout watchdog                 │
                       └───┬─────────────────────────┬────────┘
                           │                         │
                           ▼                         ▼
                  state_machine.py         tools.py (visual emit, voice)
                  push/pop_branch          ↑
                  board_manager            │ filtered tool registry per state
                  push/pop_board           │
```

LLM still calls `start_doubt_branch(related_concept=...)` and `resolve_doubt()` — same surface. Orchestrator runs underneath, does the deterministic work.

---

## 3. The five guardrails (detailed)

### 3.1 Auto-snapshot on push

When `start_doubt_branch` fires, the orchestrator snapshots parent state into a `ReturnAnchor`:

```python
class ReturnAnchor(BaseModel):
    parent_branch_id: str
    parent_concept_index: int
    last_beat_index: int  # which beat in the current ConceptTeachingPlan we paused at
    last_voice_anchor: str  # the last sentence-end the agent emitted before the branch
    active_highlights: list[str]  # element_ids of currently-glowing diagram parts
    active_annotations: list[str]  # ids of pinned labels / callouts / brackets currently visible
    notebook_cursor: int  # last entry index in the parent notebook
    timestamp: datetime
```

Snapshot capture happens inside the orchestrator's `on_push(branch_context)` method. The `BranchContext` gains a new field `return_anchor: ReturnAnchor` populated at push time.

### 3.2 Auto-restore on pop

When `resolve_doubt` fires (and validation passes — see 3.3), the orchestrator:

1. Pops the branch (existing `state_machine.pop_branch`).
2. Reactivates parent board (existing `board_manager.pop_board`).
3. **Re-publishes the visual highlights from the snapshot** — every element_id in `active_highlights` gets a fresh `highlight_pulse` to re-establish presence (annotations from the snapshot are already part of the parent board's state and don't need re-firing).
4. **Emits the verbatim return cue** — speaks `"OK — back to your ladder. Let's use what we just wrote down."` (or the lesson's specified return cue, set on the parent ConceptTeachingPlan) automatically. The LLM does not have to remember.

The LLM's prompt is also updated to indicate the return-anchor is restored, so its next utterance picks up smoothly from the parent context.

### 3.3 Resolution checklist

When `start_doubt_branch` fires, the existing `plan_doubt()` (in `concept_planner.py`) generates a structured plan. We extend its output with a **resolution checklist** — a small list of items the agent must touch before the orchestrator will allow `resolve_doubt`.

```python
class ChecklistItem(BaseModel):
    description: str  # "show diagram explaining ratio constancy"
    status: Literal["pending", "done"] = "pending"
    auto_satisfied_by: list[str] = []  # tool names that auto-tick this item
        # e.g. ["draw_design_diagram", "draw_diagram"] for "show diagram"
```

Example checklist for a "why is sin = opp/hyp?" doubt:
```
1. show diagram explaining ratio constancy   [auto-satisfied by draw_*_diagram]
2. explain why ratios are angle-dependent    [auto-satisfied by ≥10s of voice in this branch]
3. tie back to ladder                        [auto-satisfied by mentioning "ladder" or pin_label_near("hypotenuse")]
```

Auto-satisfaction logic in the orchestrator: when the agent calls a tool or speaks, the orchestrator checks each pending checklist item's `auto_satisfied_by` and ticks accordingly.

The agent can also explicitly tick an item via a new low-level tool `mark_doubt_step_complete(step_index: int)`, used as an escape hatch when auto-detection misses something.

When `resolve_doubt` is called: orchestrator's `is_resolution_allowed()` checks all items are `done`. If not, the call returns an error to the LLM: `"Cannot resolve yet — checklist items 2, 3 still pending. Complete them or call mark_doubt_step_complete to override."`

### 3.4 Time bounds

A background watchdog is scheduled when the doubt branch starts:

```python
asyncio.create_task(self._timeout_watchdog(branch_id))

async def _timeout_watchdog(self, branch_id: str):
    await asyncio.sleep(60)  # soft nudge at 60s
    if branch_id in self._active_doubts:
        await self._fire_soft_nudge(branch_id)
    await asyncio.sleep(60)  # 60–120s window
    if branch_id in self._active_doubts:
        await self._force_resolve(branch_id)
```

**Soft nudge (60s)**: a system message injected into the agent's prompt: *"This doubt branch has been running 60 seconds. Wrap up your explanation in the next beat or two — call resolve_doubt soon."*

**Force-resolve (120s)**: orchestrator calls `resolve_doubt` itself, bypassing checklist validation. Voice fallback: *"Let's circle back to that next time — we still have ground to cover."* This is the polite escape hatch when the LLM has wandered too long.

Both timeouts are tunable per-lesson via config; defaults above are the v0 demo values.

### 3.5 Tool constraints in HANDLING_DOUBT state

A new tool-availability filter in `tools.py`. When the state machine is in `HANDLING_DOUBT`, certain tools are gated:

| Tool | HANDLING_DOUBT | Reason |
|---|---|---|
| `start_doubt_branch` | ❌ disabled | No nested doubts in v0 (architecture supports; we don't optimize) |
| `resolve_doubt` | ✅ allowed (subject to checklist gate) | Required for branch closure |
| `advance_concept` | ❌ disabled | Cannot skip ahead while mid-doubt |
| `switch_board` (to non-doubt board) | ❌ disabled | Cannot escape doubt board sideways |
| `draw_design_diagram`, `draw_diagram`, `draw_scene` | ✅ allowed | Used in doubt explanation |
| `pin_label_near`, `draw_callout`, `bracket`, `highlight_pulse` | ✅ allowed | Annotation tools work normally |
| `write_*` (notebook tools) | ✅ allowed (writes to doubt page) | Doubt notebook entries |
| `listen_for_user_input` | ❌ disabled | Listen-mode is for confirmation problem only |
| `mark_doubt_step_complete` | ✅ allowed | Used to tick checklist manually |

Implementation: each tool function wrapped with a state check decorator:

```python
@state_constrained(allowed_states={TeachingState.HANDLING_DOUBT, TeachingState.TEACHING})
async def draw_design_diagram(...): ...

@state_constrained(forbidden_states={TeachingState.HANDLING_DOUBT})
async def advance_concept(...): ...
```

Calls to disabled tools return an error to the LLM explaining why, e.g. `"start_doubt_branch is disabled inside an active doubt branch (no nested doubts in v0). Resolve current doubt first."`

---

## 4. The orchestrator module

New file: `backend/src/feynman/agent/doubt_orchestrator.py`. ~200 LOC.

```python
class DoubtOrchestrator:
    """Deterministic state management for doubt branches.
    Hooks into tools.py's start_doubt_branch / resolve_doubt.
    """
    def __init__(self, tc: TeachingContext):
        self._tc = tc
        self._active: dict[str, DoubtState] = {}  # branch_id -> state
        self._timeout_tasks: dict[str, asyncio.Task] = {}

    async def on_push(self, branch_context: BranchContext, related_concept: str) -> None:
        """Called from start_doubt_branch after push_branch and push_board."""
        anchor = self._capture_return_anchor()
        checklist = await self._build_checklist(related_concept)
        state = DoubtState(
            branch_id=branch_context.id,
            related_concept=related_concept,
            return_anchor=anchor,
            checklist=checklist,
            started_at=datetime.utcnow(),
        )
        self._active[branch_context.id] = state
        branch_context.return_anchor = anchor  # also stash on BranchContext
        branch_context.checklist = checklist
        self._timeout_tasks[branch_context.id] = asyncio.create_task(
            self._timeout_watchdog(branch_context.id)
        )

    def is_resolution_allowed(self, branch_id: str) -> tuple[bool, str]:
        """Called from resolve_doubt before pop. Returns (allowed, reason_if_not)."""
        if branch_id not in self._active:
            return (True, "")  # not tracked; allow
        state = self._active[branch_id]
        pending = [i for i, item in enumerate(state.checklist) if item.status == "pending"]
        if pending:
            descriptions = ", ".join(state.checklist[i].description for i in pending)
            return (False, f"Cannot resolve: pending checklist items: {descriptions}")
        return (True, "")

    async def on_pop(self, branch_context: BranchContext, *, forced: bool = False) -> None:
        """Called from resolve_doubt after pop_branch and pop_board.
        Auto-restores parent state via voice + highlight re-firing."""
        state = self._active.pop(branch_context.id, None)
        if state:
            await self._restore_parent_state(state.return_anchor, forced=forced)
            task = self._timeout_tasks.pop(branch_context.id, None)
            if task and not task.done():
                task.cancel()

    def on_tool_invoked(self, tool_name: str, branch_id: str | None = None) -> None:
        """Called from tools.py on every tool call. Auto-ticks checklist items."""
        if branch_id and branch_id in self._active:
            state = self._active[branch_id]
            for item in state.checklist:
                if item.status == "pending" and tool_name in item.auto_satisfied_by:
                    item.status = "done"

    def on_voice_emitted(self, transcript: str, branch_id: str | None) -> None:
        """Called when agent speaks. Auto-ticks based on content keywords."""
        if branch_id and branch_id in self._active:
            state = self._active[branch_id]
            # text-keyword auto-satisfaction (e.g. "ladder" mentioned ticks the tie-back item)
            ...

    async def _timeout_watchdog(self, branch_id: str) -> None:
        try:
            await asyncio.sleep(60)
            if branch_id in self._active:
                await self._fire_soft_nudge(branch_id)
            await asyncio.sleep(60)
            if branch_id in self._active:
                await self._force_resolve(branch_id)
        except asyncio.CancelledError:
            pass

    async def _force_resolve(self, branch_id: str) -> None:
        # Bypasses checklist; emits fallback voice line; calls resolve_doubt internally
        ...

    async def _fire_soft_nudge(self, branch_id: str) -> None:
        # Injects a system message into agent's prompt
        ...

    def _capture_return_anchor(self) -> ReturnAnchor:
        # Snapshot tc state: concept_index, current_beat_index, voice anchor, highlights, annotations, notebook cursor
        ...

    async def _restore_parent_state(self, anchor: ReturnAnchor, *, forced: bool) -> None:
        # Re-fire highlight_pulse for each element in anchor.active_highlights
        # Emit return cue voice line (verbatim from parent ConceptTeachingPlan or fallback)
        ...

    async def _build_checklist(self, related_concept: str) -> list[ChecklistItem]:
        # Calls plan_doubt() with checklist-generation flag; returns the list
        ...
```

---

## 5. State machine extensions

`backend/src/feynman/agent/state_machine.py`:

```python
@dataclass
class BranchContext:
    state: TeachingState
    concept: str
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # NEW:
    return_anchor: ReturnAnchor | None = None  # set on doubt push
    checklist: list[ChecklistItem] = field(default_factory=list)  # set on doubt push
    started_at: datetime | None = None  # set on doubt push
```

No changes to push/pop/depth logic — just additional fields populated by the orchestrator.

---

## 6. Tool constraint decorators

New file `backend/src/feynman/agent/tool_constraints.py` (~50 LOC):

```python
def state_constrained(
    *,
    allowed_states: set[TeachingState] | None = None,
    forbidden_states: set[TeachingState] | None = None,
    error_template: str | None = None,
):
    """Decorator that enforces tool availability based on current TeachingState."""
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(ctx, *args, **kwargs):
            tc = _get_teaching_context(ctx)
            current = tc.state_machine.current.state
            if forbidden_states and current in forbidden_states:
                raise ToolConstraintError(
                    error_template
                    or f"{fn.__name__} is disabled in {current.name} state"
                )
            if allowed_states and current not in allowed_states:
                raise ToolConstraintError(
                    error_template
                    or f"{fn.__name__} is only available in {[s.name for s in allowed_states]}"
                )
            return await fn(ctx, *args, **kwargs)
        return wrapper
    return decorator
```

`ToolConstraintError` is caught at the LLM tool-call layer and surfaced back to the LLM as a normal tool error, with the explanation in the message.

---

## 7. Hooks into tools.py

Update `backend/src/feynman/agent/tools.py:1637–1730`:

```python
@tool
async def start_doubt_branch(ctx, related_concept: str):
    if not _is_doubt_allowed(tc):  # state machine check (forbids nested in v0)
        raise ToolConstraintError("Cannot start a doubt while already inside one")
    branch = await tc.state_machine.push_branch(concept=related_concept)
    tc.board_manager.push_board(name=f"Doubt: {related_concept}", branch_id=branch.id)
    await tc.doubt_orchestrator.on_push(branch, related_concept)  # <-- NEW
    asyncio.create_task(tc.anticipation.warm_doubt(related_concept))
    asyncio.create_task(plan_doubt(related_concept, ctx))
    await _update_agent_prompt(ctx)
    return {"branch_id": branch.id, "checklist": [item.description for item in branch.checklist]}

@tool
async def resolve_doubt(ctx):
    branch = tc.state_machine.current
    allowed, reason = tc.doubt_orchestrator.is_resolution_allowed(branch.id)  # <-- NEW
    if not allowed:
        raise ToolConstraintError(reason)
    await tc.state_machine.pop_branch()
    tc.board_manager.pop_board()
    tc.anticipation.clear_doubt_cache()
    await tc.doubt_orchestrator.on_pop(branch, forced=False)  # <-- NEW (auto-restore)
    await _update_agent_prompt(ctx)

# Internal version called by orchestrator's force-resolve path
async def _force_resolve_doubt(ctx, branch_id):
    branch = ...
    await tc.state_machine.pop_branch()
    tc.board_manager.pop_board()
    tc.anticipation.clear_doubt_cache()
    await tc.doubt_orchestrator.on_pop(branch, forced=True)  # forced path uses fallback voice
    await _update_agent_prompt(ctx)

@tool
async def mark_doubt_step_complete(ctx, step_index: int):  # <-- NEW
    branch = tc.state_machine.current
    if branch.state != TeachingState.HANDLING_DOUBT:
        raise ToolConstraintError("Not in a doubt branch")
    if step_index < 0 or step_index >= len(branch.checklist):
        raise ToolConstraintError(f"step_index {step_index} out of range")
    branch.checklist[step_index].status = "done"
```

Other tools get the `@state_constrained` decorator:

```python
@tool
@state_constrained(forbidden_states={TeachingState.HANDLING_DOUBT})
async def advance_concept(ctx): ...

@tool
@state_constrained(forbidden_states={TeachingState.HANDLING_DOUBT})
async def listen_for_user_input(ctx, timeout_s: int = 8): ...
```

The auto-tick hook (`on_tool_invoked`, `on_voice_emitted`) is wired in the existing `_publish_visual` helper and the voice emission path so every action automatically ticks the relevant checklist items.

---

## 8. Implementation Phases

This feature splits into two sub-phases. Each phase has a coherent mental model — happy-path determinism in 2A, safety nets in 2B — and ends with a verification gate before the next begins. The split ensures the trickier async-and-state-machine work (watchdog, decorator-level constraints) gets dedicated focus rather than being rushed at the end of a 4-day marathon.

| Phase | Scope | Days | Cumulative |
|---|---|---|---|
| **2A — Core (snapshot + restore + checklist)** | Module skeleton, BranchContext extensions, auto-snapshot, auto-restore, checklist gate, auto-tick | 2 | day 5 (cumulative across docs 14+15) |
| **2B — Safety (watchdog + constraints + tests)** | Time-bound watchdog, force-resolve, tool_constraints decorator, apply across tools, end-to-end stress tests | 2 | day 7 |

**Cross-feature ordering**: this doc's phases require `14-agent-diagram-awareness.md` Phase 1A and 1B to be complete first. Sequence is 1A → 1B → 2A → 2B, after which Phase C (Aanya demo build per `13-aanya-demo-build-list.md`) is unblocked. Phase 1C from doc 14, if added, slots after 2B.

### Phase 2A — Core: Snapshot + Restore + Checklist (2 days)

**Goal**: every requirement from §3.1, §3.2, §3.3, §4, §5, §7 belonging to happy-path determinism is implemented. Doubt branches push and pop cleanly with state preserved; checklist gates premature resolution. Time bounds and tool constraints come in 2B.

#### Scope

| Requirement | File | Section |
|---|---|---|
| `ReturnAnchor` Pydantic model (parent_branch_id, parent_concept_index, last_beat_index, last_voice_anchor, active_highlights, active_annotations, notebook_cursor, timestamp) | `backend/src/feynman/agent/doubt_orchestrator.py` (NEW) | §3.1 |
| `ChecklistItem` Pydantic model (description, status, auto_satisfied_by) | `backend/src/feynman/agent/doubt_orchestrator.py` (NEW) | §3.3 |
| `DoubtState` internal type (branch_id, related_concept, return_anchor, checklist, started_at) | same | §4 |
| `DoubtOrchestrator` class skeleton (init, `_active`, `_timeout_tasks`, hook signatures) | same | §4 |
| `BranchContext` extensions: `return_anchor`, `checklist`, `started_at` fields | `backend/src/feynman/agent/state_machine.py` | §5 |
| `_capture_return_anchor()` — snapshots concept_index, beat_index, voice_anchor, active_highlights, active_annotations, notebook_cursor | `doubt_orchestrator.py` | §3.1 |
| `on_push(branch_context, related_concept)` — fires snapshot, builds checklist, registers state, schedules watchdog (no-op stub in 2A) | `doubt_orchestrator.py` | §4 |
| `_build_checklist(related_concept)` — calls `plan_doubt`, extracts checklist items | `doubt_orchestrator.py` | §3.3 |
| `plan_doubt` produces checklist as part of `ConceptTeachingPlan` (controlled-vocab prompt) | `backend/src/feynman/agent/concept_planner.py` | §3.3 |
| `is_resolution_allowed(branch_id) -> tuple[bool, str]` — gates `resolve_doubt` on checklist completion; returns descriptive error listing pending items | `doubt_orchestrator.py` | §3.3 |
| `on_pop(branch_context, forced=False)` — auto-restores parent state; cancels watchdog | `doubt_orchestrator.py` | §3.2 |
| `_restore_parent_state(anchor, forced)` — re-fires `highlight_pulse` for each `active_highlights` element + emits return cue voice line | `doubt_orchestrator.py` | §3.2 |
| `on_tool_invoked(tool_name, branch_id)` — auto-ticks checklist items via `auto_satisfied_by` | `doubt_orchestrator.py` | §3.3 |
| `on_voice_emitted(transcript, branch_id)` — keyword-based auto-tick (conservative; tool-call ticks preferred) | `doubt_orchestrator.py` | §3.3 |
| `mark_doubt_step_complete(step_index)` tool (manual override / escape hatch) | `backend/src/feynman/agent/tools.py` | §3.3 |
| Hooks in `start_doubt_branch` to call `tc.doubt_orchestrator.on_push(...)` after `push_branch` + `push_board` | `backend/src/feynman/agent/tools.py` | §7 |
| Hooks in `resolve_doubt` to gate via `is_resolution_allowed` then call `on_pop` after `pop_branch` + `pop_board` | `backend/src/feynman/agent/tools.py` | §7 |
| `tc.doubt_orchestrator` instance on TeachingContext | `backend/src/feynman/agent/teaching_context.py` | §4 |
| `on_tool_invoked` wired in `_publish_visual` (every tool call routes through orchestrator) | `backend/src/feynman/agent/tools.py` (publish helpers) | §7 |
| `on_voice_emitted` wired in voice emission path (TTS → orchestrator hook) | `backend/src/feynman/agent/voice.py` (or wherever TTS fires) | §7 |
| System-prompt section showing checklist visibility to LLM | `backend/src/feynman/agent/prompts.py` | §4 |
| LLM prompt updated to indicate return-anchor restored on pop (so next utterance picks up smoothly from parent context) | `backend/src/feynman/agent/prompts.py` | §3.2 |

#### Tests (must pass before 2B starts)

| Test | File | What it verifies |
|---|---|---|
| `test_auto_snapshot_captures_state` | `backend/tests/agent/test_doubt_orchestrator.py` (NEW) | After `start_doubt_branch`, `BranchContext.return_anchor` has correct concept_index, beat_index, active_highlights, notebook_cursor |
| `test_auto_restore_replays_highlights` | same | After `resolve_doubt`, parent's `highlight_pulse` fires for each element in snapshot |
| `test_auto_restore_emits_return_cue` | same | Verbatim return cue fires automatically without LLM call |
| `test_checklist_gate_blocks_premature_resolve` | same | 3-item checklist; only 2 ticked; `resolve_doubt` raises `ToolConstraintError` listing pending items |
| `test_checklist_gate_allows_complete_resolve` | same | 3-item checklist; all ticked (auto + manual); `resolve_doubt` succeeds |
| `test_auto_tick_from_tool_call` | same | Item with `auto_satisfied_by=["draw_design_diagram"]`; calling that tool ticks the item |
| `test_auto_tick_from_voice_keyword` | same | Item with keyword "ladder" auto-ticks when voice emission contains it |
| `test_mark_doubt_step_complete_manual_override` | same | `mark_doubt_step_complete(2)` ticks item 2 even without auto-trigger |
| `test_plan_doubt_produces_checklist` | `backend/tests/agent/test_concept_planner.py` | `plan_doubt(concept)` returns `ConceptTeachingPlan` with non-empty checklist |
| Manual: dry-run a doubt with 3 ad-hoc questions | n/a | All branch correctly; auto-tick fires; resolve cleanly |

#### Completion gate

All 9 backend tests green + manual dry-run + `ruff` clean on touched files. Doubt branch resolves cleanly with state preserved on the happy path. Time bounds and tool constraints are not yet enforced — the agent could still wander forever or call illegal tools, but those are 2B's job.

#### Completion note template

```
## Phase 2A — DONE [date]
- DoubtOrchestrator with on_push, on_pop, is_resolution_allowed, auto-tick hooks
- BranchContext gained return_anchor, checklist, started_at
- plan_doubt now produces checklist (N items per doubt)
- mark_doubt_step_complete tool registered
- Auto-restore replays highlights + return cue (verbatim)
- 9/9 backend tests green. Manual dry-run: 3/3 ad-hoc doubts resolve cleanly. Phase 2B can start.
- Open question / known issue: [auto-tick keyword sensitivity tuning?]
```

### Phase 2B — Safety: Watchdog + Constraints + Tests (2 days)

**Goal**: every remaining requirement from §3.4, §3.5, §6, §7 is implemented. Doubt branch is bounded by time and constrained by tool-availability rules; integration stress tests pass; Phase C (Aanya demo) is unblocked.

#### Scope

| Requirement | File | Section |
|---|---|---|
| `_timeout_watchdog(branch_id)` async task — 60s soft + 120s hard | `backend/src/feynman/agent/doubt_orchestrator.py` | §3.4 |
| `_fire_soft_nudge(branch_id)` — injects system message into agent prompt (*"This doubt branch has been running 60 seconds. Wrap up your explanation in the next beat or two — call resolve_doubt soon."*) | `doubt_orchestrator.py` | §3.4 |
| `_force_resolve(branch_id)` — bypasses checklist; emits fallback voice; calls internal pop | `doubt_orchestrator.py` | §3.4 |
| Fallback voice line constant ("Let's circle back to that next time — we still have ground to cover") | `doubt_orchestrator.py` constants | §3.4 |
| `_force_resolve_doubt(ctx, branch_id)` internal version (called by orchestrator, bypasses LLM tool path) | `backend/src/feynman/agent/tools.py` | §7 |
| Watchdog cancellation on normal `resolve_doubt` (clean shutdown of timeout task in `on_pop`) | `doubt_orchestrator.py` `on_pop` | §3.4 |
| Watchdog timing tunable per-lesson via config (defaults 60/120) | `doubt_orchestrator.py` + config wiring | §3.4 |
| `tool_constraints.py` — `state_constrained` decorator + `ToolConstraintError` exception | `backend/src/feynman/agent/tool_constraints.py` (NEW, ~50 LOC) | §6 |
| Apply `@state_constrained(forbidden_states={HANDLING_DOUBT})` to `start_doubt_branch` (no nested doubts in v0) | `backend/src/feynman/agent/tools.py` | §3.5 |
| Apply `@state_constrained(forbidden_states={HANDLING_DOUBT})` to `advance_concept` | `backend/src/feynman/agent/tools.py` | §3.5 |
| Apply `@state_constrained(forbidden_states={HANDLING_DOUBT})` to `listen_for_user_input` | `backend/src/feynman/agent/tools.py` | §3.5 |
| Apply `@state_constrained` to `switch_board` for non-doubt boards (forbidden in HANDLING_DOUBT) | `backend/src/feynman/agent/tools.py` | §3.5 |
| `ToolConstraintError` surface to LLM (caught at tool-call layer; returned as tool error message with explanation) | `backend/src/feynman/livekit/worker.py` (or tool-call adapter) | §6 |

#### Tests (must pass before Phase C / Aanya demo starts)

| Test | File | What it verifies |
|---|---|---|
| `test_soft_nudge_fires_at_60s` | `backend/tests/agent/test_doubt_orchestrator.py` | Doubt running 65s → soft nudge system message added to agent prompt |
| `test_force_resolve_fires_at_120s` | same | Doubt running 130s → force-resolve fires; fallback voice emitted; parent state restored |
| `test_force_resolve_bypasses_checklist` | same | Force-resolve completes even if 0 of 3 checklist items ticked |
| `test_watchdog_cancelled_on_normal_resolve` | same | If `resolve_doubt` fires at 30s, watchdog task is cancelled; no soft nudge fires later |
| `test_state_constrained_blocks_in_handling_doubt` | `backend/tests/agent/test_tool_constraints.py` (NEW) | Calling `advance_concept` while in HANDLING_DOUBT raises `ToolConstraintError` with documented message |
| `test_state_constrained_allows_in_teaching` | same | Calling `advance_concept` while in TEACHING succeeds |
| `test_nested_doubt_blocked` | same | Calling `start_doubt_branch` inside HANDLING_DOUBT raises `ToolConstraintError` ("nested doubts disabled in v0") |
| `test_listen_blocked_in_doubt` | same | Calling `listen_for_user_input` inside HANDLING_DOUBT raises `ToolConstraintError` |
| `test_orchestrator_state_clean_after_force_resolve` | `test_doubt_orchestrator.py` | After force-resolve, orchestrator's `_active` and `_timeout_tasks` dicts are clean |
| `test_10_consecutive_doubts_no_leaks` | same | 10 sequential push+pop cycles → no leaked timeout tasks, no checklist contamination |
| Manual: stress test artificially extending doubt to 130s | n/a | Demo behavior is graceful, not jarring |
| End-to-end demo dry-run | n/a | Full Aanya beat-4 flow with 3 different ad-hoc doubts; orchestrator handles all 5 guardrails correctly |

#### Completion gate

All 10 backend tests pass + stress test + end-to-end dry-run + `ruff` clean. Both features (docs 14 and 15) fully integrated. Phase C (Aanya demo build) is unblocked.

#### Completion note template

```
## Phase 2B — DONE [date]
- Watchdog with 60s soft nudge + 120s force-resolve
- Force-resolve fallback voice in place
- tool_constraints.py decorator applied to 4 tools (start_doubt_branch, advance_concept, listen_for_user_input, switch_board for non-doubt)
- All 5 guardrails verified in integration tests
- 10/10 backend tests green. Stress test passes. Phase C unblocked.
- Phase B (foundational features across docs 14 and 15) COMPLETE.
```

### Phase Boundary Discipline (RLM protocol)

**Active feature state file**: `~/.claude/projects/-Users-yashbansal-proj-feynman/memory/active-features/foundational-features.md` — same file used by docs 14 and 15 phases. Tracks 1A → 1B → 2A → 2B (and 1C if added).

**Each phase ends with:**
1. All listed tests green
2. `ruff` clean on touched files
3. Completion note appended to state file using the template above
4. Git commit with phase identifier (e.g., "Phase 2A complete: doubt orchestrator core")

**Each phase begins with:**
1. 5-min re-orient: read relevant section of design doc + prior phase's completion note + immediately-relevant files
2. Confirm prior phase's gate is green (all tests still pass)
3. Update state file: mark phase as in_progress

**Rollback rule**: if any phase slips >0.5 days, stop and re-plan rather than rush.

### Decision Points

| Decision | When | Default |
|---|---|---|
| Adjust 60s/120s time bounds? | After 2B's stress test in real session | Keep defaults; tune only if dry-runs show wrong timing |
| Tighten or loosen auto-tick keyword logic? | During 2A | Conservative auto-tick; rely more on tool-call ticks; manual override available |
| Enable nested doubts? | If demo dry-run reveals need | NO. Architecture supports; v0 disabled. v1.1 reconsider. |
| Update Aanya demo spec to use new tools? | End of Phase 2B | Yes. Updates Beats 2/5/6 to use `pin_label_near` + `bracket`; §4 references orchestrator behavior. |

### Risks & Mitigations (cross-phase)

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| 2A auto-tick too eager (false positives) | Medium | Doubt resolves before properly answered | Conservative keyword matching; rely more on tool-call ticks; manual override available |
| 2A `plan_doubt` produces bad checklists | Medium | Checklist items vague or impossible to auto-tick | Provide controlled vocabulary in planning prompt with examples; manually curate doubt-library checklists for Aanya demo |
| 2B time bounds feel too tight (60s/120s) | Low | Real doubts get force-resolved | Increase to 90s/180s if dry-run shows premature firing; tunable per-lesson via config |
| 2B tool constraints break legitimate edge cases | Medium | Agent can't do something it should | Each constraint is documented + can be tuned; ToolConstraintError messages tell us what to fix |
| Voice emission hook adds latency | Low | Microseconds per tool call | Measure during integration; orchestrator hooks are O(1) per call |

---

## 9. Acceptance criteria

The orchestrator is ready to integrate with the Aanya demo when:

1. **Auto-snapshot test**: unit test calls `start_doubt_branch`, asserts `BranchContext.return_anchor` is populated with current concept_index, beat_index, last voice anchor, active highlights, notebook cursor.

2. **Auto-restore test**: integration test pushes a doubt, fires some agent activity (visual + voice), calls `resolve_doubt`. Verifies parent highlights are re-fired automatically and the return cue voice line is emitted without LLM intervention.

3. **Checklist gate test**: integration test pushes a doubt with a 3-item checklist, ticks 2, calls `resolve_doubt` — must fail with clear error. Ticks 3rd, calls `resolve_doubt` — must succeed.

4. **Auto-tick test**: integration test pushes a doubt where checklist item 1 is `auto_satisfied_by=["draw_design_diagram"]`. Calls `draw_design_diagram`. Verifies item 1 status is `"done"` without explicit `mark_doubt_step_complete`.

5. **Time-bound test**: integration test pushes a doubt, lets it run 130s without resolving. Verifies (a) soft nudge fires at 60s (system message in agent prompt), (b) force-resolve fires at 120s with the fallback voice line, (c) parent state is restored.

6. **Tool constraint test**: integration test pushes a doubt, attempts to call `start_doubt_branch` (nested doubt), `advance_concept`, `listen_for_user_input` — each must raise `ToolConstraintError` with the documented error message.

7. **End-to-end demo dry-run**: run a stub of beat 4 from the Aanya demo with three different ad-hoc questions. Each should branch correctly, tick checklist items as the agent responds, and resolve cleanly with auto-restore.

8. **Stress test**: run 10 consecutive doubt branches in a single session (hypothetical extended demo). Verify orchestrator state is clean between branches; no leaked timeout tasks; no checklist contamination.

---

## 10. Risks & open questions

1. **Auto-tick is too eager / not eager enough.** A keyword-based auto-tick may misfire (the agent says "ladder" out of context and ticks "tie back to ladder" prematurely). Mitigation: keep auto-tick conservative; rely on tool-name auto-tick (more deterministic) plus explicit `mark_doubt_step_complete` for content-based ticks. Tune empirically.

2. **Force-resolve voice fallback feels jarring to a kid.** The auto "let's circle back to that next time" line may feel dismissive if it fires unexpectedly. Mitigation: make the wording warmer; only fire after 120s (long enough that the demo is genuinely off-track); log every force-resolve for review.

3. **Checklist generation by `plan_doubt` may produce bad checklists.** LLM may generate checklist items that are too vague or impossible to auto-tick. Mitigation: provide a controlled vocabulary in the planning prompt, with examples; review and curate the doubt-library checklists for the Aanya demo manually.

4. **Return-anchor restoration breaks if parent state changed during the doubt** (e.g., notebook cursor shifted because of an unrelated event). Mitigation: snapshot is taken at push time; restoration replays it idempotently. If parent state diverges meaningfully, the worst case is a redundant highlight or annotation — not a broken board.

5. **Latency added by orchestrator hooks.** Each tool call now passes through `on_tool_invoked`. Negligible (microseconds), but worth measuring during integration.

---

## 11. Out of scope

- **Nested doubts** — architecture supports them via stack; v0 disables them via tool constraint. Re-enable in v1+ when we have a use case.
- **Custom checklist per lesson** — v0 uses `plan_doubt`-generated checklists with manual curation for the demo. v1+ adds per-lesson curated checklist authoring.
- **Persistent doubt history across sessions** — orchestrator state is per-session; no cross-session memory of "this kid asked this doubt last week." Comes via knowledge graph in v1+.
- **Doubt branch analytics** — telemetry on how often the orchestrator's safeguards fire (force-resolve, tool-constraint denials, etc.) is logged but not surfaced to a dashboard in v0.
- **Voice sentiment detection** for soft-nudge tuning — v0 uses fixed time bounds; future versions could detect agent confidence drop and nudge sooner.

---

## 12. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-05-10 | Five guardrails: auto-snapshot, auto-restore, checklist, time bounds, tool constraints | Each addresses a specific LLM failure mode that breaks the demo |
| 2026-05-10 | Auto-restore re-fires highlights; return cue auto-emitted | LLM-managed restoration is fragile; system management is reliable |
| 2026-05-10 | Resolution checklist with auto-tick + manual override | Pure auto-tick is too brittle; pure manual is too friction-heavy; hybrid balances both |
| 2026-05-10 | Time bounds: 60s soft nudge, 120s force-resolve | Soft nudge gives the LLM a chance to wrap; hard limit prevents runaway |
| 2026-05-10 | Force-resolve voice fallback: "Let's circle back to that next time — we still have ground to cover" | Polite, kid-friendly, doesn't blame anyone |
| 2026-05-10 | Tool constraints in HANDLING_DOUBT: no advance_concept, no nested doubt, no listen_for_user_input | Each represents an "escape hatch" the LLM might mistakenly take during a doubt |
| 2026-05-10 | Nested doubts disabled in v0 | Architecture supports; disabling avoids stack-confusion failure mode for now |
| 2026-05-10 | Build splits into Phase 2A (core: snapshot + restore + checklist, 2d) + Phase 2B (safety: watchdog + constraints, 2d) | Each sub-phase has its own coherent testing concern (state-introspection vs async-watchdog vs decorator); tests for time-bounded async are not skipped at end of marathon; happy-path landed and verified before safety net is layered in |

---

## 13. Next artifacts

- After this doc and `14-agent-diagram-awareness.md` are locked: Phase B build (~7 days)
- After Phase B: update `12-aanya-demo-v0.md` §4 to reference the orchestrator's auto-restore behavior
- After Phase B: update `13-aanya-demo-build-list.md` to remove redundant doubt-handling concerns (orchestrator covers them)
- Then Aanya demo sprint (Phase C, 6–8 days)
