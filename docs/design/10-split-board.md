# 10 — Split Board: Slide + Notebook

> Kill the 2D layout problem by making it structurally impossible. The board is two panels with distinct rendering semantics, not a free-form canvas.

**Status**: Design
**Date**: 2026-04-14
**Supersedes**: Large portions of `06-board-intelligence-and-latency.md` and `09-board-cortex.md` (see "Delete List" below)
**Depends on**: Anticipation engine (already built), design_agent pipeline (already built)

---

## 1. Why This Matters

Two prior attempts (design docs 06 and 09) built elaborate systems to help the LLM reason about 2D space on the board — SceneGraph, BoardGraph, SpatialSolver (MaxRects), ASCII snapshots, scenario planners, board flow analysis, board verifier. Nine phases shipped in each. The board still feels random and the composition still feels untaught-looking.

**The root cause is the framing, not the implementation.** Both docs took it as given that the LLM must perform 2D layout. They piled compensating machinery on top. The IJCAI 2025 survey doc 09 itself cites (42–80% spatial reasoning degradation as complexity grows) was treated as something to route around, not as a signal to abandon the frame.

Real classroom teachers don't do arbitrary 2D layout either. Watch any physics/math lesson: diagram (or apparatus) on one side of the board, working (equations, steps, answer) on the other. That's it. The "intelligence" on a teaching board isn't 2D composition — it's **notebook composition**: aligning equals signs, indenting sub-steps, crossing out mistakes, boxing the final answer, knowing when to flip the page.

This design reframes the board as two panels with different rendering semantics, matching how teachers actually work.

---

## 2. The Metaphor

```
┌──────────────────────┬──────────────────────────────────────────┐
│                      │                                          │
│                      │  SCRIBE PAGE                             │
│      SLIDE           │  ──────────────────────                  │
│   (one diagram       │  Newton's Second Law                     │
│    at a time,        │                                          │
│    pre-computed,     │    F = m · a                             │
│    stroke-revealed)  │    ─────                                 │
│                      │    a = F / m                             │
│    [diagram]         │    ─────                                 │
│                      │    a = 10 N / 2 kg                       │
│                      │    ─────                                 │
│                      │    a = 5 m/s²   ┃ boxed answer ┃         │
│                      │                                          │
│                      │                                          │
│      ~38%            │                    ~62%                  │
└──────────────────────┴──────────────────────────────────────────┘
```

### The Slide (left, ~38%)

- Holds **exactly one** design diagram or scene at a time.
- Always visible, never scrolled away.
- Swap atomically with a cross-fade when the concept changes.
- Pre-computed via the anticipation engine whenever possible.
- When live generation is needed (e.g., unplanned doubts), show the **drafting-marks loading animation** until the spec arrives, then stroke-reveal it.

### The Notebook (right, ~62%)

- A vertical page. Entries stack top-to-bottom.
- Entry kinds: `equation`, `step`, `text`, `section_header`, `key_point`, `answer` (boxed).
- Supports `align_group` (consecutive equations align at `=`), `indent` (sub-steps), `strikethrough` (mistake), `boxed` (final answer).
- When the page is full, the agent explicitly calls `new_page(carry_forward?)` — no silent reflow, no forced scroll. The page-turn is a dignified 400ms transition.

### Three Modes (agent-selectable per concept)

| Mode | Layout | When |
|---|---|---|
| `split` (default) | Slide + Notebook | 80%+ of concepts |
| `slide_full` | Slide expands to 100% | Apparatus intro, complex diagram walkthrough, animation |
| `notebook_full` | Notebook expands to 100% | Pure derivation, text-heavy concept, no visual needed |

Mode transitions: 500ms ease, at most **one per concept**. The agent picks mode when calling `advance_concept`; can't flip mid-concept (too jittery).

---

## 3. Why This Works

### Constraint is intelligence

A two-slot interface with typed content can't be misused the way a 9-zone grid can. The LLM never chooses "where" — only "what." This directly eliminates the spatial reasoning failure the IJCAI survey describes.

### Matches classroom cognition

- **Dual-coding (Paivio 1971, Mayer 2009)**: visual + verbal in separate channels. Diagram-left / text-right matches LTR reading order and the established spatial contiguity principle.
- **Working memory segregation**: students who see a stable diagram while derivation unfolds keep referential anchors intact. Reflow destroys anchors.
- **Teaching as temporal sequence**: boards are the residue of a sequence, not a composition. Notebook entries are temporal by nature — append-only.

### Latency becomes structural

- Slide's single-diagram rule means the anticipation engine pre-generates **one diagram per concept** — tractable and always worthwhile.
- Notebook entries are all fast tools (equations, text, steps) — ~0ms generation.
- The only real latency risk is off-plan slide swaps (doubt diagrams, mid-concept pivots). The drafting-marks loader makes that wait feel authored.

### Deletes more than it adds

See Delete List (§8). We remove ~2500 LOC of working but flawed machinery. The codebase gets simpler.

---

## 4. Contract Changes

### New instruction fields

All visual instructions gain:

```json
{
  "panel": "slide" | "notebook" | "reference",
  "notebook": {            // only for panel=notebook
    "kind": "equation" | "step" | "text" | "section_header" | "key_point" | "answer",
    "align_group": "string?",
    "indent": 0..3,
    "boxed": bool
  }
}
```

The `panel` field is **stamped by the backend** in `_publish_visual` based on the tool type — not chosen by the LLM. The LLM doesn't know about panels.

Deprecated (still accepted for back-compat during migration):
- `zone`, `position_x`, `position_y`, `placement`. Ignored in split-board rendering path.

### New tool surface

On the notebook side, we collapse the current 7-way scattered tool set into a focused set:

| Tool | Produces Notebook entry with |
|---|---|
| `write_equation(latex, align_with?)` | `kind=equation`, align_group set if `align_with` |
| `write_step(text, indent=0)` | `kind=step` |
| `write_text(text, style)` | `kind=text` or `key_point` depending on style |
| `write_section(title)` | `kind=section_header` |
| `write_answer(content)` | `kind=answer`, `boxed=true` |
| `strikethrough(element_id)` | mutation, adds `struck=true` to target |
| `new_page(carry_forward?)` | clears notebook; optional carry_forward element_ids preserved at top |

On the slide side:

| Tool | Behavior |
|---|---|
| `show_slide(spec \| scene_spec)` | Replace active slide with cross-fade + stroke reveal |
| `clear_slide()` | Fade out, leave empty |
| `highlight_slide_element(id)` | Existing highlight behavior, scoped to slide |

Deprecated and removed over Phases 2–7:
`show_equation`, `step_equation`, `show_text`, `show_graph` (merged into notebook tools); `draw_design_diagram`, `modify_design_diagram`, `draw_scene`, `draw_diagram` (become `show_slide` variants); `switch_board`, `scroll_view` (replaced by slide swap + `new_page`).

### Prompt shrinkage

The board context injected into the teaching prompt drops from ~2–4KB ASCII snapshot + metrics + flow + graph to ~10 lines of state:

```
SLIDE: "Free-body diagram of block on incline"
NOTEBOOK (page 1, 6/10 lines used):
  last: eq-3 "F = ma" (align group g-2 with eq-2)
  section: "Newton's 2nd Law"
UPCOMING: "Solve for acceleration" (next concept)
```

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────┐
│  Teaching Agent (LLM)                               │
│  Sees: panel state (10 lines)                       │
│  Calls: write_equation, show_slide, new_page, etc.  │
└────────────────────┬────────────────────────────────┘
                     │
          ┌──────────┴───────────┐
          ▼                      ▼
┌──────────────────┐   ┌──────────────────────┐
│ NotebookState    │   │ SlideState           │
│ - entries[]      │   │ - active: spec \| None │
│ - page_num       │   │ - pending: spec \| None│
│ - align_groups   │   │ - swap_token           │
└────────┬─────────┘   └──────────┬───────────┘
         │                        │
         └─────────┬──────────────┘
                   ▼
         ┌──────────────────────┐
         │ Frontend             │
         │ - SlidePanel         │
         │ - Notebook           │
         │ - DraftingLoader     │
         └──────────────────────┘
```

No SpatialSolver. No SceneGraph 2D queries on the primary path. No ASCII snapshot. No scenario planner. No board flow analyzer. No placement executor.

BoardGraph (semantic relationships) is retained for cross-element references ("F_net relates to the arrow in the diagram") but is advisory, not layout-determining.

---

## 6. Phases

Each phase is a merge-ready unit. Tests alongside code.

### Phase 1 — Visual prototype (frontend only, mocked)

**Goal**: Validate the metaphor feels right *before* any backend work. If the prototype doesn't feel teacher-like, kill it and rethink.

**Deliverable**: `/dev/split-board` dev route showing a scripted Newton's 2nd Law lesson. Control bar lets Yash step through: new slide → section header → equation → aligned equation → step → boxed answer → new page.

**Files** (all new):
- `frontend/src/engine/whiteboard/split/SlidePanel.tsx`
- `frontend/src/engine/whiteboard/split/Notebook.tsx`
- `frontend/src/engine/whiteboard/split/DraftingLoader.tsx`
- `frontend/src/engine/whiteboard/split/NotebookEntry.tsx`
- `frontend/src/engine/whiteboard/split/SplitBoard.tsx` (composition)
- `frontend/src/engine/whiteboard/split/types.ts`
- `frontend/src/engine/whiteboard/split/SplitBoard.css`
- `frontend/src/screens/SplitBoardPrototype.tsx`
- Route entry in `frontend/src/App.tsx` (or equivalent)

**Acceptance**: Yash opens `/dev/split-board`, clicks through the scripted lesson, and says "this feels like a teacher."

### Phase 2 — Backend contract + routing

**Goal**: Add `panel` to every instruction and stamp it in `_publish_visual`. Route existing tools by type. No behavior change yet — the old WhiteboardScene ignores `panel`, the new SplitBoard will consume it in Phase 3.

**Files**:
- `contracts/visuals.schema.json`
- `backend/src/feynman/visuals/schemas.py`
- `frontend/src/types/visuals.ts`
- `backend/src/feynman/agent/tools.py` — `_publish_visual` stamps `panel` based on tool type
- `backend/tests/unit/test_panel_routing.py` (new)

### Phase 3 — Wire SplitBoard into live classroom

**Goal**: Replace `WhiteboardScene` with `SplitBoard` behind a feature flag (`VITE_SPLIT_BOARD=1`). Live agent output drives live split board.

**Files**:
- `frontend/src/engine/whiteboard/WhiteboardScene.tsx` — gate on flag, delegate to SplitBoard
- `frontend/src/engine/whiteboard/useBoardStore.ts` — partition instructions by `panel`
- `frontend/src/screens/ClassroomScreen.tsx` — pass flag through

### Phase 4 — Loading animation + stroke reveal

**Goal**: The drafting-marks loader plays while a slide is pending; when the spec arrives, it stroke-reveals (not fade-in).

**Files**:
- `frontend/src/engine/whiteboard/split/DraftingLoader.tsx` — grid + 3-4 neon lines converging + compass arc (SVG stroke-dasharray)
- `frontend/src/engine/whiteboard/content/DesignDiagramContent.tsx` — stroke-reveal mode using per-element `stroke-dasharray` animation, ordered by spec element order, ~1.2s total
- Respect `prefers-reduced-motion` — static final state, no animation

### Phase 5 — Notebook primitives + write tools

**Goal**: Backend `notebook.py` module; new write tools replacing scattered equation/text/graph tools.

**Files**:
- `backend/src/feynman/agent/notebook.py` (new) — NotebookEntry, NotebookPage, NotebookState
- `backend/src/feynman/agent/tools.py` — new tools: `write_equation`, `write_step`, `write_text`, `write_section`, `write_answer`, `strikethrough`, `new_page`
- `backend/src/feynman/agent/prompts.py` — replace board context with compact panel state
- `backend/tests/unit/test_notebook.py` (new)
- `backend/tests/unit/test_write_tools.py` (new)

Old tools (`show_equation`, `step_equation`, `show_text`, `show_graph`) proxied to new ones for one release, then removed.

### Phase 6 — Notebook rendering polish

**Goal**: Make the notebook *feel written*.

- Equation alignment: elements in same `align_group` measure rendered widths, re-flow to align at `=`.
- Strikethrough: animated pen stroke across (200ms).
- Box: animated rectangle draw-in (300ms).
- Page turn: 400ms flip animation; optional `carry_forward` elements fade-stay at the top of the new page.
- Indent: 24px per level, subtle vertical hint line.

### Phase 7 — Shed the old machinery

**Goal**: Delete dead code. This phase is a *net-negative-LOC* phase.

**Delete** (see §8 for full list):
- `spatial_solver.py`, `placement_executor.py`, `scenario_planner.py`, `board_flow.py`, `board_snapshot.py`, `board_verifier.py`, `scene_graph.py`
- All `test_*.py` for the above
- `PlacementIntent`, `SizeHint`, `position_x/y`, `placement` fields from schemas (after Phase 3 flag flip to default-on)
- `zone-layout.ts`, `BoardNavigator.tsx`, `scroll_view` plumbing
- `highlight_walk` stays (useful), `annotate` stays (useful), `clear_cluster` dies

Approximate LOC delta: **−2500 / +0** (excluding already-added Phases 1–6).

### Phase 8 — Cross-panel references + doubt cards + polish

**Goal**: Final polish.
- `reference_slide(element_id)` — when notebook text mentions a diagram element, glow pulses on slide + subtle dotted bridge line drawn from notebook entry to slide element for 1.2s.
- **Doubt branches**: spawn as a card peeling out of the notebook's right margin; resolves by tucking back in. Main lesson notebook state untouched.
- Mode switches (`slide_full`, `notebook_full`) with 500ms transitions.
- Final typographic / divider / corner-rounding pass.

---

## 7. Open Questions (answered with defaults)

| Question | Default decision | Revisit if |
|---|---|---|
| Compare two diagrams side by side? | Sequence them with a cross-fade swap; don't split the slide. | Users repeatedly complain that comparison is awkward. |
| Notebook overflow mid-derivation? | Agent should call `new_page` *before* the last step of a long derivation. Add to prompt. | Agents fail to anticipate; add a soft-warning injection when notebook > 80% full. |
| Equation `=` alignment — how precise? | Measure-then-snap at render time; align to the latest entry in the group. | Perf cost > 20ms per entry (unlikely at notebook scale). |
| What happens to infinite canvas? | Removed. Pages replace tiles. | Users request multi-page recall; can add notebook page history (scroll-back). |
| Preserve doubt branch visuals on return to main? | No — doubt card tucks away, notebook state pre-doubt is restored. Slide reverts to pre-doubt. | Users want doubt artifacts retained — then persist the doubt card as a sidebar. |

---

## 8. Delete List (Phase 7)

### Backend

- `backend/src/feynman/agent/spatial_solver.py` — MaxRects solver
- `backend/src/feynman/agent/placement_executor.py` — intent → coordinate resolver
- `backend/src/feynman/agent/scenario_planner.py` — teaching scenario detection + slot plan
- `backend/src/feynman/agent/board_flow.py` — flow analysis + scroll advice + cleanup suggestions
- `backend/src/feynman/agent/board_snapshot.py` — 72×18 ASCII snapshot
- `backend/src/feynman/agent/board_verifier.py` — Haiku vision verification (or adapt to slide-content verification)
- `backend/src/feynman/agent/scene_graph.py` — 2D spatial model (only if `highlight_walk` targeting still works; else retain minimal bounds-tracking)
- `backend/src/feynman/agent/size_estimator.py` — pre-render size estimation
- Related tests: `test_spatial_solver.py`, `test_size_estimator.py`, `test_board_snapshot.py`, `test_placement_intent.py`, `test_placement_executor.py`, `test_scenario_planner.py`, `test_board_flow.py`, `test_board_verifier.py`, `test_board_cortex_integration.py`

### Contract / schema

- `position_x`, `position_y`, `placement`, `zone`, `PlacementIntent`, `SizeHint` — from schemas and contracts
- `switch_board` (multi-board) — replaced by slide swap / new page
- `scroll_view`, `_tileX`, `_tileY` — infinite canvas

### Frontend

- `frontend/src/engine/whiteboard/zone-layout.ts`
- `frontend/src/engine/whiteboard/BoardNavigator.tsx`
- `frontend/src/engine/whiteboard/BoardCapture.tsx` (if board_verifier is deleted)
- Zone-related CSS
- Tile / camera state in `useBoardStore.ts`
- Infinite-canvas handling in `WhiteboardScene.tsx`

### Keep

- `board_graph.py` — semantic relationships (useful for cross-panel references)
- `anticipation.py` — pre-generation, already working
- `design_bridge.py` — slide generation pipeline
- `highlight_walk`, `annotate`, `clear` tools (scoped per panel)
- `BoundsReporter` (adapted) — reports notebook entry heights for page-fullness calculation

Approximate delete: ~2500 LOC + corresponding tests.

---

## 9. Risks

1. **Some lessons do genuinely need two diagrams side by side** (compare two setups, before/after). Default: sequence with swap. If this becomes a repeated pain point, add a `slide_split` mode (internal two-column split of the slide only, not a reintroduction of full 2D layout).
2. **Equation `=` alignment is non-trivial on every append** — requires measure-then-snap. Fallback: left-align everything as a P1 polish item. Notebook is still better than current state even without alignment.
3. **Off-plan doubt diagrams still take 5–15s to generate**. Drafting-marks loader helps; voice ("let me sketch this for you…") covers the remainder. If doubts become too latency-painful, invest in streaming SVG generation (separate project).
4. **Phase 7 deletes working code**. Tests die. That's OK — the tests protect the old architecture. The new architecture has its own tests (Phases 1, 2, 5). No migration period needs to keep old tests green.
5. **Agent retraining on new tool surface**: prompts change significantly in Phase 5. Expect a period of prompt tuning. Budget: 1–2 days of lesson QA per core subject.

---

## 10. Acceptance for the Whole Effort

The split-board effort is "done" when:

1. A teacher watching a live lesson can't tell the AI has any spatial-layout constraints — it *just looks like a teacher's board*.
2. Off-plan diagrams feel authored (loader + voice) rather than dead-waits.
3. Derivations look like a textbook page, not a web layout.
4. Deleting Phase 7 code causes zero user-visible regressions.
5. The board context block in the teaching prompt is under 500 tokens (down from ~2–4KB).

---

## 11. Phase Sequencing Rationale

Phase 1 is front-loaded visual prototype so Yash can veto the direction in a day instead of three weeks. Phase 7 (deletion) is deferred until Phase 3 has flipped the flag on by default — we keep the old path usable until the new path is proven live.

Phases 1 → 3 get us "split board live, looks right." That's the minimum ship. Phases 4–6 are polish and real-feel. Phase 8 is the magic details.

If we had to ship at Phase 3, the product would already feel meaningfully better than today. Phases 4–8 are compounding delight.
