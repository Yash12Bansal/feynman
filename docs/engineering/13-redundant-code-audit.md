# 13 — Redundant-Code Audit + Sequenced Deletion Plan

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-29 (reachability greps run each pass; Group 3 added 2026-05-29)

> **Scope decision (confirmed with the founder this session):** the **interactive live-teaching mode** — the "type a topic, agent teaches live via LLM + ~40 tools + state machine + board manager" path — is **legacy/parked**. It is therefore redundant for the active product, which is exactly three pipelines: (1) precompute generation, (2) precompute teaching / lecture playback (doc 11), (3) Ask Feynman doubt resolution (doc 12).
>
> **This is an audit + a deletion plan. No code is deleted by this document.** Execution is a separate, approved task. Treat Part D as the runbook for that task.

> **Execution status — full-body comment pass done 2026-05-29 (supersedes the initial header-only pass).** All dead code is now **commented out, not deleted**, under a searchable marker so it can be reviewed and removed later. Find it all with: `grep -rn "TODO(DEADCODE)"` (~203 markers). Mechanics: every whole-dead file's *body* is line-commented beneath a top-of-file `TODO(DEADCODE)` header (the modules become empty but importable-as-empty); mixed live/dead files (`worker.py`, `pipeline.py`, `router.py`, `App.tsx`, `ClassroomScreen.tsx`, `config.py`, `models.py`) had only their dead regions commented; and every dead-code **test** is commented too — backend dead-test files fully commented (pytest tolerates empty files), 11 dead frontend test files carry a one-line skipped stub so `vitest` doesn't error on "no tests". **Mislabel caught + fixed:** Group 3's `beat_narration/models.py` is *active* — its `BeatNarration` type is imported by the live `curriculum/models.py:862` — so it was restored (header dropped); only `writer.py`/`prompts.py` there are dead (see Group 3 RETAINED note). The header-only pass had hidden this (headers don't break imports); full-body commenting surfaced it. **Verified clean:** backend `pytest` 229 pass / 0 fail (dead-test files commented out → no longer collected); frontend `tsc` **0 errors** (the 29 baseline errors all lived inside now-emptied dead files); frontend `vitest` 3 fail == baseline (pre-existing active `show_text`→`HandwrittenTextContent` routing bug, *not* dead code) + 11 dead test files skipped; precompute pipeline + CLI import clean after the Group-3 fix, with no uncommented references to any dead symbol.
>
> **Correction the execution surfaced (frontend):** the *active* `whiteboard/InstructionSwitch` (used by the live lecture `SlidePanel`) statically imports the full renderer set — so `engine/content/{TextContent, EquationContent, StepEquationContent}`, all of `whiteboard/scene/**`, `engine/SyncManager`/`useSyncManager`, `engine/elements.ts`, and `whiteboard/board-coords.ts` are **NOT dead** (lecture only exercises the `draw_design_diagram` branch, but the static imports keep the whole closure live). They were left untagged. Only the *legacy* `engine/content/{GraphContent, DiagramContent, HighlightOverlay, HighlightWalkOverlay, highlight-utils}` are dead. To actually remove `scene/` + the text/equation renderers you must first prune `InstructionSwitch`'s unused branches.

## TL;DR

Three groups of redundant code:

- **Group 1 — orphaned regardless** (~no inbound runtime imports, or dev-only). Deletable independently, low risk.
- **Group 2 — the parked interactive subsystem** (~25 backend `agent/` files + a frontend cluster). Reachable *only* from `worker.py`'s interactive entrypoint (and the dev-only `experiments/`). Requires editing `worker.py` first, then the files orphan.
- **Group 3 — the legacy precompute lesson stack** (the `use_lesson_pipeline=False` path inside the *active* precompute generator). Dead-within-a-live-pipeline: the default doc-19 stack supersedes it and nothing sets the flag False. Requires a `pipeline.py` surgery (not just deletions) and has one shared file — `DiagramQA` — that must stay.

**The load-bearing finding that makes this safe:** the Ask Feynman pipeline (`agent/doubt_resolution/*` + `livekit/doubt_delivery.py`) imports **nothing** from Group 2. Verified:

```
$ grep -rn "from feynman.agent" backend/src/feynman/agent/doubt_resolution/ | grep -v doubt_resolution
   (empty)
$ grep -rnE "from feynman.agent.(tools|state_machine|board…|design_bridge|doubt_orchestrator|…) import" \
     backend/src/feynman/agent/doubt_resolution/ backend/src/feynman/livekit/doubt_delivery.py
   (empty)
```

So removing the parked subsystem cannot break precompute teaching or Ask Feynman. The risk is concentrated in three "looks interactive but isn't" catches (Part C), all verified.

---

## Part A — Audit inventory

### Group 1 — orphaned regardless

| Path | Category | Evidence | Confidence |
|---|---|---|---|
| `data_pre_compute/` (entire v1 dir) | Superseded by v2 | No runtime imports anywhere; only 3 comment/docstring mentions (`agent/teaching_context.py:99`, `agent/curriculum_loader.py:3`, `agent/anticipation.py:4`) | **HIGH** |
| `backend/src/feynman/knowledge/` (`models.py`, `schemas.py`, `repository.py`, `service.py`) | Unwired stub module | `grep "feynman.knowledge" backend/src` → 0 importers | **HIGH** |
| `backend/src/feynman/api/ws.py` | Empty stub (docstring only) | Not imported by `api/router.py` (grep on router shows no `ws` import) | **HIGH** |
| `backend/src/feynman/visuals/protocol.py` (`VisualFrame`) | Future-batching stub, never used | Only reference is `visuals/CLAUDE.md:39`; 0 code importers | **HIGH** |
| `backend/src/feynman/experiments/` (diagram_lab testbed) | Dev-only testbed | Wired only via `api/router.py:8,14` (diagtest router); not used by any pipeline | **HIGH** (dev-only) |
| `frontend/src/engine/VisualScene.tsx`, `VisualCard.tsx`, `Canvas.tsx`, `renderer.ts`, `engine/InstructionSwitch.tsx`, and the legacy-only `engine/content/{GraphContent, DiagramContent, HighlightOverlay, HighlightWalkOverlay, highlight-utils}` | Legacy pre-split renderer | Closed cluster: importers are each other + `useVisualChannel` (interactive-only). `engine/CLAUDE.md` marks `Canvas.tsx`/`renderer.ts` "Deprecated." **Corrected (see Execution status):** `engine/content/{TextContent,EquationContent,StepEquationContent}`, `engine/elements.ts`, `engine/SyncManager`/`useSyncManager`, `whiteboard/board-coords.ts`, and `whiteboard/scene/**` are **NOT** dead — the active `whiteboard/InstructionSwitch` imports them. | **HIGH** (for the listed files) |
| `frontend/src/screens/DevHarness.tsx`, `DiagramGenerationTestScreen.tsx`, `SplitBoardPrototype.tsx`, `LecturePreviewScreen.tsx`, `dev-fixtures.ts` | Dev-only screens | Reachable only via `#/dev*` / `#/diagram_generation_test` / `#/lecture-preview` hash routes in `App.tsx`; not the product entry path | **HIGH** (dev-only) |
| `frontend/src/diagram-lab/` | Dev lab UI for `/diagtest` | Used only by `DiagramGenerationTestScreen` (itself dev-only) | **HIGH** (dev-only) |
| `design_agent/frontend/` (entire) | Standalone playground UI | No pipeline references it; separate CRA app | **HIGH** (dev-only) |
| `design_agent/backend/main.py`, `agent.py` | Standalone playground server | Never imported/loaded by any pipeline (only `prompts.py`/`prompts_python.py`/`schema.py` are disk-loaded — see Part B) | **HIGH** (dev-only) |

### Group 2 — the parked interactive subsystem

All reachable **only** from `worker.py`'s interactive entrypoint (`:842-954`) + the dev-only `experiments/`. Verified via `grep -rlE "from feynman.agent.<mod> import" backend/src` — every importer is another Group-2 file, `worker.py`, or `experiments/`.

Backend `agent/` (25 files):

| File | Imported by (non-self) | Notes |
|---|---|---|
| `tools.py` | `worker.py`, `action_tag_dispatch.py` | The ~40 `@function_tool`s; only bound to `FeynmanAgent` (interactive). |
| `tool_constraints.py` | `tools.py` | `@state_constrained`. |
| `state_machine.py` | `worker.py`, `teaching_context.py`, `doubt_orchestrator.py` | Stack branching. |
| `teaching_context.py` | `worker.py`, `tools.py`, `prompts.py`, `diagram_dictionary.py`, `doubt_orchestrator.py` | The interactive session object. |
| `prompts.py` | `worker.py`, `tools.py` | `TEACHING_SYSTEM_PROMPT` + `build_teaching_prompt`. |
| `board.py` | `teaching_context.py` | `BoardManager`. |
| `board_state.py` | `board.py` | |
| `board_graph.py` | `tools.py`, `board_state.py`, `board_snapshot.py`, `board_flow.py` | |
| `board_snapshot.py` | `prompts.py` | ASCII snapshot for the prompt. |
| `board_flow.py` | `board_snapshot.py` | |
| `scene_graph.py` | `worker.py`, `board.py`, `board_state.py` | `BoundsReportPayload` — used in the interactive `bounds` handler (`worker.py:874`). |
| `spatial_solver.py` | `board_state.py`, `board_snapshot.py`, `board_flow.py`, `placement_executor.py`, `scenario_planner.py` | |
| `placement_executor.py` | `tools.py` | |
| `size_estimator.py` | `placement_executor.py` | |
| `scenario_planner.py` | `tools.py`, `board_state.py`, `placement_executor.py` | |
| `diagram_dictionary.py` | `tools.py` | |
| `anticipation.py` | `teaching_context.py` | |
| `lesson_plan.py` | `worker.py`, `tools.py`, `prompts.py`, `teaching_context.py`, `anticipation.py` | |
| `curriculum_loader.py` | `worker.py`, `tools.py`, `lesson_plan.py`, `anticipation.py` | Interactive curriculum load; Ask Feynman uses `doubt_resolution/chapter_loader.py` instead. |
| `notebook.py` | `prompts.py` | Backend notebook reconstruction for the prompt. |
| `drift_state.py` | `worker.py` | Only used in `_periodic_drift_check` (interactive). |
| `board_verifier.py` | `worker.py`, `teaching_context.py` | Vision checks; instantiated only in the interactive branch (`worker.py:863`). |
| `design_bridge.py` | `tools.py`, `anticipation.py`, **`experiments/*`** | Live diagram gen; loads `design_agent` prompts from disk. Coupled to `experiments/` removal. |
| `doubt_orchestrator.py` | `state_machine.py`, `teaching_context.py` | The *interactive* doubt system (NOT Ask Feynman). |

Backend `livekit/` (1 file) + `agent/` (1 file):

| File | Imported by | Notes |
|---|---|---|
| `livekit/action_tag_dispatch.py` | `worker.py` (interactive `tts_node`) | Inline action-tag dispatch. |
| `agent/action_tag_parser.py` | `worker.py`, `action_tag_dispatch.py` | |

Frontend cluster:

| File / area | Imported by (non-self, non-test) | Notes |
|---|---|---|
| `livekit/useVisualChannel.ts` | `ClassroomScreen.tsx` (LiveAgentClassroom) | Live instruction stream. |
| `livekit/useAgentTranscription.ts` | `ClassroomScreen.tsx` | Live transcript → sync. |
| `engine/SyncManager.ts`, `engine/useSyncManager.ts` | `ClassroomScreen.tsx` + legacy `engine/content/*` | Word-sync; lecture playback doesn't use it. |
| `engine/whiteboard/WhiteboardScene.tsx` + non-split scaffolding (`WhiteboardCard`, `BoardNavigator`, `WhiteboardSceneSnapshot`, `useBoardStore`, `board-layout-context`, `zone-layout`, `board-coords`, `scene/*`) | `ClassroomScreen.tsx` (when `!splitBoardEnabled`), `DevHarness` | The non-split board. **KEEP `whiteboard/split/*`, `whiteboard/content/*`, `whiteboard/InstructionSwitch` — those are the lecture render path.** |
| `engine/whiteboard/split/useSplitBoardState.ts` | `ClassroomScreen.tsx` only | LectureViewer uses `useExtractionPlayback` instead — confirmed not a lecture dep. |

### Group 3 — the legacy precompute lesson stack (`use_lesson_pipeline=False`)

Dead code **inside the active precompute generator** (`data_pre_compute_v2/`). The pipeline has two planning/narration stacks chosen by one flag, `EnrichmentConfig.use_lesson_pipeline` (`config.py:253`, **default `True`**):

- **Active (doc-19, "Phase H"):** `LessonPlanner → LessonDiagramGenerator → DiagramQA → LessonNarrator → LessonProsody → LessonQualityGate`, run by `_run_lesson_pipeline_for_chapter` (branch at `pipeline.py:343-381`, helper at `:645`). Builds `assembled_chapter_script` via `_build_chapter_script_from_narrations` (`pipeline.py:820`).
- **Legacy (7b-legacy → 7c-7g):** `ConceptPlanner → DiagramSpecGenerator → BeatNarrationWriter → LengthEnforcer → ScriptAssembler`, run only in the `else` branch (`pipeline.py:382-414`) plus the `concept_plans`-gated stages (`:416-544`).

**Why it's dead:** the doc-19 branch leaves `ch.concept_plans` empty on purpose (`pipeline.py:378-381`), and every legacy stage early-`continue`s when `concept_plans` is empty — so with the default flag the legacy stages are physically present but **no-op**. And nothing sets the flag False:

```
$ grep -rniE "use_lesson_pipeline.*false" data_pre_compute_v2 --include=*.py --include=*.yaml
   (only comments reference the False path — no config or test sets it)
```

This is exactly the cut the local `pipeline.py` edit (discarded 2026-05-29) was reaching for: it commented out `ConceptPlanner` / `DiagramSpecGenerator` / `BeatNarrationWriter` while **keeping `DiagramQA`** — the correct line (see Part B).

Legacy-only files (verified single-caller in the `else` / `concept_plans`-gated path):

| Path | Symbol | Sole caller | Notes |
|---|---|---|---|
| `curriculum/lecture_plan/concept_planner.py` | `ConceptPlanner` | `pipeline.py:384` (else) | per-topic plan via kernel; superseded by `LessonPlanner`. |
| `curriculum/lecture_plan/example_allocator.py` | `allocate_example_beats` | `pipeline.py:413` (else) | superseded by `BookExampleWeaver` (pulled in `a6d28d6`). |
| `curriculum/enrichment/diagram_spec_generator.py` | `DiagramSpecGenerator` | `_run_per_beat_diagram_stage` (`pipeline.py:872`) | no-ops in active path (empty `concept_plans`); superseded by `LessonDiagramGenerator`. |
| `curriculum/beat_narration/writer.py`, `prompts.py` | `BeatNarrationWriter` | `pipeline.py:467` | superseded by `LessonNarrator`. |
| `curriculum/length_enforcer/` (dir) | `LengthEnforcer` | `pipeline.py:511` | superseded by doc-19 length/prosody handling. |
| `curriculum/script_assembler.py` | `ScriptAssembler` | `pipeline.py:529` | active path uses `_build_chapter_script_from_narrations` (`:820`) instead. |
| `curriculum/validation/example_coverage.py` | `validate_example_coverage` | `pipeline.py:500` | superseded by `validation/book_coverage.py` (which says so at `book_coverage.py:9`). |

**SHARED — do NOT remove (see Part B):** `curriculum/enrichment/diagram_qa.py` (`DiagramQA` / `QAResult`) runs in **both** stacks — active at `pipeline.py:673`, legacy at `:879`.

**RETAINED — `curriculum/beat_narration/models.py` (`BeatNarration`) is NOT legacy-only** (caught 2026-05-29 during the soft-delete commenting pass — the precompute analogue of the `agent/states.py` catch). The active `curriculum/models.py` imports it at `:862` (+ `:21` TYPE_CHECKING) for the `Chapter.beat_narrations` field annotation, so emptying it breaks the whole pipeline import. It is **coupled** to that field: delete `models.py` only together with `Chapter.beat_narrations`. `beat_narration/__init__.py` is likewise kept (it exports `BeatNarration`; its dead `.writer`/`.prompts` re-export is commented out, since `from beat_narration.models import …` triggers the package `__init__`). Only `writer.py` + `prompts.py` in this dir are dead.

Coupled dead config + model fields to clean up with the stack: in `config.py`, the `use_lesson_pipeline` flag + `BeatNarrationConfig` / `LengthEnforcerConfig` / `ScriptAssemblerConfig` / `PerBeatDiagramsConfig` (keep `DiagramQAConfig`); in `curriculum/models.py`, the `Chapter.concept_plans` + `Chapter.beat_narrations` fields (`~:772-787`) — the active path uses `lesson_plans` / `lesson_narrations`.

This is a **`pipeline.py` surgery**, not just file deletes — see Part D Phase E.

### Generated-output cruft (not code, mentioned for completeness)

`data_pre_compute_v2/out*/`, `data_pre_compute_v2/artifacts/audio/*`, `artifacts/diagrams/*`, `design_agent/generated/*`, and the `backend/venv/` (alongside `.venv/`) are generated artifacts, not source. They belong in `.gitignore`, not in a code-deletion plan. The git status at session start showed several untracked `out_phase4e_*` and `artifacts/` dirs — worth a separate `.gitignore` cleanup, out of scope here.

---

## Part B — "Looks dead but isn't" (DO NOT delete)

| Path | Why it's alive | Evidence |
|---|---|---|
| `design_agent/backend/prompts.py`, `prompts_python.py`, `schema.py` | **Disk-loaded at runtime by `design_bridge.py`** (not a Python import) | `design_bridge.py:31` `_DESIGN_AGENT_DIR = parents[4]/"design_agent"/"backend"`; `:40` reads `SYSTEM_PROMPT`. **However**, once Group 2 is removed, `design_bridge` goes too → these become authoring-source-only (see Part C cascade). |
| `agent/states.py` (`TeachingState`) | Imported by the **active FastAPI session layer** | `session/models.py:8`, `session/store.py:11`, `session/schemas.py:9`, `session/manager.py:14`. **Must be kept** even after the rest of `agent/` is removed. |
| `agent/doubt_resolution/*` | The Ask Feynman pipeline (doc 12) | Used by `worker.py:_run_lecture_mode`. KEEP. |
| `livekit/doubt_delivery.py`, `livekit/pipeline.py` | Ask Feynman delivery + STT/TTS | KEEP. |
| `feynman_teaching_kernel` | Precompute generation (doc 01 §12) | KEEP (cross-package dep of `data_pre_compute_v2`). |
| `frontend/src/types/visuals.ts` | Compile-time types used across the frontend | KEEP. |
| `frontend/src/engine/whiteboard/split/*`, `whiteboard/content/*`, `whiteboard/InstructionSwitch.tsx` | The lecture render path (`SlidePanel` → `InstructionSwitch` → `DesignDiagramContent`) | KEEP. |
| `data_pre_compute_v2/.../curriculum/enrichment/diagrams.py` | Holds the verbatim copy of the design prompt for precompute | KEEP (it's the precompute's prompt source). |
| `data_pre_compute_v2/.../curriculum/enrichment/diagram_qa.py` (`DiagramQA`, `QAResult`) | Runs in the **active** doc-19 precompute stack (`pipeline.py:673`) as well as the legacy stack (`:879`) | KEEP. Group 3's other 7c-7g files go; this one stays. |

---

## Part C — Required-edit catches (handle, don't blind-delete)

1. **`states.py` is shared.** It's a Group-2-adjacent file but the active session layer depends on it. **Keep it** (or relocate `TeachingState` into `common/` and update the 4 session imports). The session model stores `teaching_state` as this enum.
2. **`experiments/` is wired into the API.** `api/router.py:8` imports `diagtest_router`, `:14` includes it. Deleting `experiments/` requires removing those two lines.
3. **`api/ws.py` is a clean orphan.** Not referenced by `api/router.py`. Delete with no router edit.
4. **`design_bridge` ↔ `experiments` coupling.** `design_bridge.py` is imported by `tools.py` + `anticipation.py` (Group 2) **and** by `experiments/diagram_lab/strategies/*` (Group 1). Both must go before `design_bridge` orphans; otherwise the experiments strategies break.
5. **`design_agent/` cascade.** After `design_bridge` is removed, nothing loads `design_agent/backend/{prompts,prompts_python,schema}.py` at runtime (precompute keeps its own verbatim copy in `diagrams.py`). Decision required: **keep `design_agent/backend/{prompts,prompts_python,schema}.py` as the prompt-authoring source that `diagrams.py` is synced from**, or remove the directory entirely and make `diagrams.py` the sole source. Recommend keeping the three prompt/schema files (they're the human-edited source), removing the standalone `main.py`/`agent.py`/`frontend/`.
6. **Frontend whiteboard split.** `whiteboard/` is mixed: `split/` + `content/` + `InstructionSwitch.tsx` are KEEP (lecture); `WhiteboardScene.tsx` + non-split scaffolding are remove. Before deleting, confirm no `split/*` or `content/*` file imports from `WhiteboardScene.tsx`/`useBoardStore`/`board-layout-context` (a shared `types.ts` is the likely coupling — check and, if needed, split the types file).
7. **`worker.py` is the hinge.** It imports the entire Group-2 surface at module top (`:21-85`). Editing it (Phase B.1) is the prerequisite that orphans everything else.
8. **Group 3 is a `pipeline.py` surgery, not deletions.** The legacy stages are physically interleaved in `run()` and gated on `ch.concept_plans` (empty in the active path). Removing them means editing `run()` — drop the `else` branch (`:382-414`) + the `concept_plans`-gated stages (`:416-544`) + the helper `_run_per_beat_diagram_stage` — not just deleting files.
9. **`DiagramQA` is shared across precompute stacks.** Do not remove `diagram_qa.py` when removing Group 3 — the active doc-19 stack calls it (`pipeline.py:673`). This is the precompute analogue of the `states.py` catch.

---

## Part D — Sequenced deletion plan (execution deferred)

Each phase is an independent commit with its own verification. Order matters: independent removals first, then the worker hinge, then the orphan cascade, then frontend.

### Phase A — Group 1 independent removals (low risk)

1. Delete `data_pre_compute/` (v1). Strip the 3 stale comments referencing it (`agent/teaching_context.py:99`, `agent/curriculum_loader.py:3`, `agent/anticipation.py:4`) — cosmetic.
2. Delete `backend/src/feynman/knowledge/`.
3. Delete `backend/src/feynman/api/ws.py`.
4. Delete `backend/src/feynman/visuals/protocol.py`.
5. Delete `backend/src/feynman/experiments/` **and** remove `api/router.py:8` + `:14`.
6. Frontend: delete dev screens (`DevHarness`, `DiagramGenerationTestScreen`, `SplitBoardPrototype`, `LecturePreviewScreen`, `dev-fixtures.ts`), `diagram-lab/`, and their `App.tsx` hash routes.
7. Delete `design_agent/frontend/`.

**Verify A:** `cd backend && uv run python -c "import feynman.main"` resolves; `make test-backend`; `cd frontend && pnpm build` (tsc catches dangling imports) + `pnpm test`.

### Phase B — interactive backend (the big one)

1. **Edit `worker.py`** — the hinge:
   - Delete the interactive entrypoint branch (`:842-954`).
   - Delete `FeynmanAgent` (`:264-517`), `ALL_TOOLS` (`:98-133`), `strip_action_tags` (`:136-156`), `drain_perception_feedback` (`:159-182`), `_should_run_drift_check`/`_run_drift_check` (`:188-261`).
   - Reduce module-level imports (`:21-85`) to only what `_run_lecture_mode` needs: `doubt_resolution` (`LectureDoubtSession`, `ResolutionPlan`, `load_chapter_by_id`, `doubt_capture`), `livekit.doubt_delivery`, `livekit.pipeline`, `config`, `common.*`. Drop `tools`, `state_machine`, `states`*, `teaching_context`, `prompts`, `board_verifier`, `scene_graph`, `drift_state`, `curriculum_loader`, `lesson_plan`, `action_tag_*`, `plan_concept`.
     - *`states`: only drop the worker's import; the file stays (Part C #1).*
2. **Verify the cluster is orphaned:** re-run `grep -rlE "from feynman.agent.<mod> import" backend/src` for each Group-2 module; expect only other Group-2 files (now also being deleted). Confirm `doubt_resolution/` still imports nothing from them (it never did).
3. **Delete the Group-2 `agent/` files** (all 24 except `states.py`): `tools.py`, `tool_constraints.py`, `state_machine.py`, `teaching_context.py`, `prompts.py`, `board.py`, `board_state.py`, `board_graph.py`, `board_snapshot.py`, `board_flow.py`, `scene_graph.py`, `spatial_solver.py`, `placement_executor.py`, `size_estimator.py`, `scenario_planner.py`, `diagram_dictionary.py`, `anticipation.py`, `lesson_plan.py`, `curriculum_loader.py`, `notebook.py`, `drift_state.py`, `board_verifier.py`, `design_bridge.py`, `doubt_orchestrator.py`. Plus `agent/action_tag_parser.py` + `livekit/action_tag_dispatch.py`.
4. **Cascade:** remove `design_agent/backend/main.py` + `agent.py` (keep `prompts.py`/`prompts_python.py`/`schema.py` per Part C #5). Remove the now-dead `design_agent/generated/` write path (gone with `design_bridge`).
5. Check `agent/__init__.py` re-exports — prune any that reference deleted modules.

**Verify B:** `uv run python -c "import feynman.main, feynman.livekit.worker"` resolves; `make test-backend`; **live smoke**: start worker + open a precomputed chapter + tap Ask Feynman → confirm capture → resolution → delivery → resume all still work (the only paths that should remain).

### Phase C — interactive frontend

1. **Edit `App.tsx`**: drop the `#/dev/live-teacher` route and the dev hash routes (already partly handled in Phase A).
2. **Edit `ClassroomScreen.tsx`**: remove `LiveAgentClassroom` and its imports; collapse to `return <LectureViewer chapterId={lectureChapterId} />` (or route `App.tsx` straight to `LectureViewer` and delete `ClassroomScreen` if it adds nothing).
3. **Delete**: `livekit/useVisualChannel.ts`, `livekit/useAgentTranscription.ts`, `engine/SyncManager.ts`, `engine/useSyncManager.ts`, the legacy engine cluster (`VisualScene.tsx`, `VisualCard.tsx`, `Canvas.tsx`, `renderer.ts`, `elements.ts`, `engine/InstructionSwitch.tsx`, `engine/content/*`), `engine/whiteboard/WhiteboardScene.tsx` + non-split scaffolding (`WhiteboardCard`, `BoardNavigator`, `WhiteboardSceneSnapshot`, `useBoardStore`, `board-layout-context`, `zone-layout`, `board-coords`, `scene/*`), and `engine/whiteboard/split/useSplitBoardState.ts`.
4. **KEEP**: `engine/whiteboard/split/*` (except `useSplitBoardState`), `engine/whiteboard/content/*`, `engine/whiteboard/InstructionSwitch.tsx`, `hooks/useExtractionPlayback.ts`, `screens/LectureViewer.tsx`, `screens/LectureHomeScreen.tsx`, `components/*`, `livekit/RoomProvider.tsx`.
5. Resolve the shared-`types.ts` coupling (Part C #6) before deleting whiteboard scaffolding.

**Verify C:** `pnpm build` (tsc is the safety net — any dangling import fails the build); `pnpm test`; **live smoke**: lecture playback + Ask Feynman in the browser.

### Phase D — final sweep

- Prune now-unused entries from `frontend/src/types/visuals.ts` (live-only instruction types no longer referenced) — type-only, low priority.
- Confirm precompute is untouched: `cd data_pre_compute_v2 && poetry run lecture-pipeline-v2 --help` and a dry-run `ingest-book` on a fixture still work (it's a separate package; nothing above should affect it).
- Update the engineering docs: `03-teaching-state-machine.md` and `04-livekit-agent-worker.md` describe the now-removed interactive subsystem — mark them "describes removed interactive mode (historical)" or trim to the surviving lecture path.

### Phase E — legacy precompute lesson stack (independent track)

In `data_pre_compute_v2/`, unrelated to the interactive-mode removal — can be done before or after Phases A–D.

1. **Edit `pipeline.py` `run()`:** drop the `else` branch (`:382-414`: the `ConceptPlanner` + `example_allocator` path); drop the `concept_plans`-gated stages — per-beat diagrams (`:416-452`) and beat-narration/length/assembly (`:454-544`); drop the helper `_run_per_beat_diagram_stage` (with its `DiagramSpecGenerator` use, **keeping `DiagramQA`**). Collapse `if self.config.enrichment.use_lesson_pipeline:` to run the doc-19 path unconditionally.
2. **Drop imports** at `pipeline.py:32,36,49,64,65` + the inline `example_allocator`/`example_coverage` imports (`:396`, `:490`). Keep the `DiagramQA` import (`:33`); drop `QAResult` if unused after the helper goes.
3. **Delete the legacy-only files** (Group 3 table): `concept_planner.py`, `example_allocator.py`, `diagram_spec_generator.py`, `beat_narration/`, `length_enforcer/`, `script_assembler.py`, `validation/example_coverage.py`.
4. **Clean config + model:** remove `use_lesson_pipeline` + `BeatNarrationConfig`/`LengthEnforcerConfig`/`ScriptAssemblerConfig`/`PerBeatDiagramsConfig` from `config.py` (keep `DiagramQAConfig`); remove `Chapter.concept_plans` + `Chapter.beat_narrations` from `curriculum/models.py`.

**Verify E:** `cd data_pre_compute_v2 && poetry run lecture-pipeline-v2 --help`; run a single-chapter `ingest-book <fixture> -s physics --single-chapter --skip-tts --skip-embeddings --skip-neo4j --output ./out` and confirm it still produces `assembled_chapter_script` via the doc-19 path with no reference to deleted symbols; `poetry run pytest`.

---

## Estimated impact

| Group | Backend files | Frontend files | Risk |
|---|---|---|---|
| Group 1 | ~4 modules + experiments/ + design_agent playground | ~5 screens + diagram-lab + legacy engine cluster | Low — orphans / dev-only |
| Group 2 | ~25 `agent/` + 2 action-tag + worker surgery | ~5 hooks/components + whiteboard scaffolding | Medium — large surface, but verified severable from the active pipelines |
| Group 3 | ~6 precompute modules/dirs + `pipeline.py` surgery + config/model cleanup | — | Medium — dead-within-a-live-pipeline; keep `DiagramQA`; verified that nothing sets `use_lesson_pipeline=False` |

The single biggest deletion is the `agent/` board/teaching subsystem (the bulk of `03-teaching-state-machine.md`). It is also the most-verified-safe: nothing in the three active pipelines imports it. Group 3 is smaller but trickier — it's interleaved into the live `pipeline.py`, so it's a careful surgery rather than a clean file delete, and `DiagramQA` must survive it.

---

## Reading order for the executor

1. This doc, Part C (the catches) and Part D (the runbook).
2. Re-run the §TL;DR safety greps to confirm they're still empty before starting.
3. Execute Phase A → verify → commit; B → verify → commit; C → verify → commit; D.
4. Keep each phase a separate commit so any regression is bisectable and revertable.
