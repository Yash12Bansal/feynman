# 11 — Precompute Lecture Playback: End-to-End Control Flow

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28 (every cited line read in full this pass)

> Companion deep-dive to `09-end-to-end-trace.md` (high-level) and `01-precompute-pipeline.md` (how the manifest is produced). This doc traces the *runtime* of precompute teaching — what fires, in what order, from clicking a chapter to the lecture playing in sync — and ends with a verified known-issues list. For the doubt path on top of this, see `12-ask-feynman-flow.md`.

## TL;DR

A precomputed lecture is a **manifest** — an ordered array of events — produced offline (doc 01) and stored on the `Chapter` node in Neo4j. At runtime:

1. The frontend fetches the manifest from `preview_server.py` (`:8080`), which reads Neo4j and embeds diagram specs + topic metadata inline.
2. `useExtractionPlayback` walks the event array **sequentially**. Audio events block on `<audio>.ended`; every other event applies its state change synchronously and the loop advances immediately.
3. The result renders through `SplitBoard` → `SlidePanel` (left, one diagram) + `Notebook` (right, sequential writing).

**The sync model is the single most important thing to understand: there is no timeline, no timestamps, no scheduler. Audio fragments are the clock.** Visual events are interleaved *between* audio fragments in the manifest; they fire the instant the preceding fragment's audio ends. "In sync" means "the precompute pipeline ordered the events correctly," not "the player schedules them against a clock."

```
Browser                         preview_server (:8080)            Neo4j
   │  GET /lecture-api/chapters        │                            │
   │ ─────────────────────────────────▶│  MATCH (c:Chapter) ───────▶│
   │ ◀───────────────────────────────  │ ◀──────────────────────────│
   │  [pick chapter → ?lecture=<id>]   │                            │
   │                                   │                            │
   │  GET /lecture-api/chapter/{id}    │                            │
   │ ─────────────────────────────────▶│  manifest + diagrams +     │
   │                                   │  topics + board_snapshots ─▶│
   │ ◀── ChapterPayload ────────────── │ ◀──────────────────────────│
   │                                                                │
   │  useExtractionPlayback.play():                                 │
   │    for ev in events:                                           │
   │      audio  → play mp3, await ended  (BLOCKS — the clock)      │
   │      visual → apply state synchronously (instant)             │
   │      page   → 200ms turn animation, await                     │
   │                                                                │
   │  SplitBoard ⟵ slide/notebook state                            │
```

---

## 1. Entry — picking a chapter to `LectureViewer` mounting

| Step | File:line | What happens |
|---|---|---|
| List chapters | `frontend/src/screens/LectureHomeScreen.tsx:32` | `fetch("/lecture-api/chapters")` on mount → `ChapterListEntry[]` (`{id, title, idx, has_manifest}`). |
| Pick a chapter | `LectureHomeScreen.tsx:96` | Click sets `window.location.search = "?lecture=<chapter_id>"` (hard navigation). |
| Route | `frontend/src/App.tsx` (`useLectureChapterParam`) | On reload, `MainEntry` reads `?lecture=` → renders `<MainApp lectureChapterId=...>`. |
| Session | `App.tsx` (`MainApp` effect) | `startSession({ lecture_chapter_id })` → `POST /api/sessions` → token + room. Status `connecting → connected`. |
| Mount viewer | `frontend/src/screens/ClassroomScreen.tsx:22` | `if (lectureChapterId) return <LectureViewer chapterId={lectureChapterId} />;` |

The `?lecture=` param is the only thing that distinguishes precompute teaching from the (parked) interactive path. `ClassroomScreen.tsx:22` is the fork: param present → `LectureViewer`; absent → `LiveAgentClassroom` (the legacy live path — see `13-redundant-code-audit.md`).

The Vite dev proxy (`frontend/vite.config.ts`) maps `/lecture-api` and `/lecture-artifacts` → `http://127.0.0.1:8080` (the preview server), and `/api` → `http://localhost:8000` (FastAPI). So the lecture content path never touches FastAPI — it's preview_server + Neo4j + static files.

---

## 2. The manifest fetch — `preview_server.py`

`LectureViewer.tsx:109` fetches `GET /lecture-api/chapter/{chapterId}`, served by `chapter_data()` at `data_pre_compute_v2/tools/preview_server.py:81`.

What that handler does (verified `preview_server.py:81-174`):

1. `MATCH (c:Chapter {chapter_id})` → pull `title`, `chapter_index`, `chapter_manifest` (JSON string), `board_snapshots` (JSON string) (`:88-94`).
2. `404` if chapter not found (`:97`); `409` if `chapter_manifest` is null — "TTS not run" (`:101`).
3. Parse the manifest JSON; `events = manifest["events"]` (`:102-105`).
4. **Diagrams are fetched in a second query and embedded inline** (`:113-138`): collect all `diagram_id`s from `show_diagram` events, `MATCH (d:Diagram) WHERE d.diagram_id IN $ids`, and for each emit `{url: rewrite_url(fallback), description, spec: json.loads(render_data)}`. The full SVG spec (the `DesignDiagramSpec`) is shipped inline — the frontend never makes a second request per diagram.
5. **Topics** similarly fetched and embedded (`:140-155`): `{name, section}` keyed by `topic_id`.
6. **URL rewriting** (`rewrite_url`, `:41-54`): `file://./artifacts/...` → `/lecture-artifacts/...`. Applied to audio event URLs (`:159-164`) and diagram fallback URLs (`:135`). The inline SVG specs need no rewriting (they're self-contained vector data).

The response shape is `ChapterPayload` (mirrored in `useExtractionPlayback.ts:239-249`):

```ts
interface ChapterPayload {
  chapter_id: string;
  title: string;
  chapter_index: number | null;
  events: ManifestEvent[];                          // the ordered timeline
  diagrams: Record<string, DiagramEntry>;           // {url, description, spec} keyed by diagram_id
  topics: Record<string, TopicEntry>;               // {name, section} keyed by topic_id
  board_snapshots?: readonly BoardSnapshot[];        // one per closed page (feat/unify_boardstate)
}
```

`LectureViewer.tsx:114` casts the JSON directly to `ChapterPayload` with **no runtime validation** (see Known Issue #8).

---

## 3. The playback engine — `useExtractionPlayback.ts`

`LectureViewer.tsx:118-129` calls `useExtractionPlayback({ chapter, autoStart: true })`. The hook is headless: the viewer supplies an `<audio ref={setAudioElement}>` (`LectureViewer.tsx:321`) and reads `slide`/`notebook` to render. No player chrome — the student watches, they don't operate a player.

### The play loop (the heart) — `:797-845`

```ts
const play = useCallback(async () => {
  if (!chapter) return;
  if (loopRef.current) return;                       // already playing
  if (status === "finished" || cursorRef.current >= chapter.events.length) return;
  abortRef.current = false;
  if (slideSnapshotRef.current !== null) {           // restore pre-doubt slide (Phase 6)
    setSlide(slideSnapshotRef.current);
    slideSnapshotRef.current = null;
  }
  setStatus("playing");
  const loop = (async () => {
    while (cursorRef.current < chapter.events.length && !abortRef.current) {
      const i = cursorRef.current;
      const ev = chapter.events[i];
      onEventRef.current?.(ev, i);
      const completed = await runEvent(ev, chapter);   // ← awaits per event
      if (!completed) {                                // paused mid-event
        if (ev.type === "audio") {
          audioIdxRef.current = Math.max(0, audioIdxRef.current - 1);   // rewind audio
          setAudioProgress({ current: audioIdxRef.current, total: totalAudios });
        } else {
          cursorRef.current = i + 1;                   // ← advances past non-audio event
          setCursorState(cursorRef.current);
        }
        return;
      }
      cursorRef.current = i + 1;
      setCursorState(cursorRef.current);
    }
    if (!abortRef.current && cursorRef.current >= chapter.events.length) {
      setStatus("finished");
      onCompleteRef.current?.();
    }
  })();
  loopRef.current = loop;
  try { await loop; } finally { loopRef.current = null; }
}, [chapter, runEvent, status, totalAudios]);
```

### `runEvent` — which events block, which don't (`:728-795`)

```ts
const runEvent = async (ev, c): Promise<boolean> => {
  switch (ev.type) {
    case "audio":                                       // BLOCKS on <audio>.ended
      audioIdxRef.current += 1; setAudioProgress(...);
      const c2 = makeCancelableAudio(audio, ev.url);
      currentCancelableRef.current = c2;
      await c2.promise;                                 // ← the clock tick
      return !abortRef.current;
    case "pause":                                       // BLOCKS on setTimeout
      await makeCancelableSleep(ev.duration_ms).promise;
      return !abortRef.current;
    case "new_page":                                    // BLOCKS 200ms then clears page
    case "page_break":                                  // BLOCKS 200ms then turns page
      setPageTurning(true);
      await makeCancelableSleep(PAGE_TURN_MS / 2).promise;   // PAGE_TURN_MS = 400
      if (abortRef.current) { setPageTurning(false); return false; }
      setNotebookEntries([]); setPageNum(n => n + 1); advanceSnapshot(c);
      // page_break also mutates slide on slide_action swap/release
      setPageTurning(false);
      return true;
    default:                                            // ALL visual events
      applySyncEvent(ev, c);                            // synchronous, instant
      return true;
  }
};
```

This is the definitive answer to "how does it stay in sync":

- **`audio` is the only real clock.** `makeCancelableAudio` (`:306-335`) sets `audio.src`, calls `audio.play()`, resolves the promise on the `ended` event. The loop is parked on `await c2.promise` for the full audio duration.
- **Everything visual is instant.** `show_diagram`, `focus`, `trace`, `write_equation`, etc. all go through `applySyncEvent` (`:541-713`), set React state, and return `true` immediately. The loop advances to the next event in the same tick.
- **Sync = ordering.** A `focus` event placed in the manifest *after* audio fragment A and *before* audio fragment B fires precisely at the A→B boundary. The precompute pipeline (doc 01, `tts/chunker.py` + `audio_pipeline.py`) achieves "draw this as I say it" by splitting narration into fragments and interleaving visual events at fragment seams. **Sync granularity = audio fragment boundary.** There is no sub-fragment timing — if the pipeline wants a highlight to land mid-sentence, it must split the sentence into two audio fragments.

### Pause semantics — `:847-856`

```ts
const pause = () => {
  if (!loopRef.current) return;
  slideSnapshotRef.current = slide;        // snapshot for post-doubt restore
  abortRef.current = true;
  currentCancelableRef.current?.cancel();  // halts in-flight audio/sleep
  setStatus("paused");
};
```

`cancel()` on the cancelable pauses the `<audio>` and resolves its promise, so the awaiting loop unblocks, sees `!completed`, and returns. For audio, the cursor is *not* advanced and `audioIdxRef` is rewound by one (`:819-820`) so resume re-plays the interrupted fragment from the top — this is the "lecture pauses for a doubt, resumes from where we left off" behavior that `12-ask-feynman-flow.md` depends on.

### Auto-start + reset

- Auto-start: `:966-969` fires `play()` once when `chapter` loads and `status === "idle"`.
- Chapter-change reset: `:425-443` aborts the loop, resets cursor/audio/snapshot/notebook/slide. This is the cleanup when you switch chapters.

---

## 4. Event coverage — what the pipeline emits vs. what the player handles

Precompute emits 25 `ManifestEvent` types (`data_pre_compute_v2/.../curriculum/models.py`, discriminated union ~`:365`). The frontend mirrors them (`useExtractionPlayback.ts:67-207`) and handles them across `runEvent` (async) + `applySyncEvent` (sync).

| Event | Handled where (`useExtractionPlayback.ts`) | Notes |
|---|---|---|
| `audio` | `runEvent:731` | Blocking; the clock. |
| `pause` | `runEvent:745` | Blocking sleep. |
| `new_page` | `runEvent:752` | Blocking 200ms; clears notebook, `pageNum++`, advances snapshot. |
| `page_break` | `runEvent:768` | Like new_page + `slide_action` (keep/swap/release). |
| `topic_start` | `applySyncEvent:544` | Sets topic label; **sets slide to `{status:"loading"}`** (`:564`). |
| `show_diagram` | `applySyncEvent:567` | Mounts `DrawDesignDiagramInstruction` from `chapter.diagrams[id].spec`. |
| `write_section` | `:593` | → `SectionEntry`. |
| `write_equation` | `:602` | → `EquationEntry` (`alignGroup`, `boxed`). |
| `write_step` | `:613` | → `StepEntry` (indent clamped 0–3, `:357`). |
| `write_text` | `:623` | → `TextEntry`. |
| `write_key_point` | `:632` | → `KeyPointEntry`. |
| `write_answer` | `:641` | → `AnswerEntry`. |
| `strikethrough` | `:650` | Marks matching entry `struck: true`. |
| `focus` | `:660` | Sets `focusedElementId` / `focusedRole` / `inlineLabelText`. |
| `unfocus` / `clear_annotations` | `:668-671` | `resetSlideFocus()` — clears focus + all annotation arrays. |
| `trace` | `:673` | Appends to `slide.traces`. |
| `mark_point` | `:677` | Appends to `slide.markPoints`. |
| `point_at` | `:681` | Appends to `slide.pointers`. |
| `write_margin` | `:685` | Appends to `slide.marginNotes`. |
| `pin` / `callout` / `bracket` / `highlight` / `pulse` | `:690-695` | **Dropped silently** — legacy back-compat; the writer no longer emits them. Benign. |

No actively-emitted event type is unhandled. The five legacy types are intentionally dropped. Unknown *future* types would fall through silently (Known Issue #8).

---

## 5. Rendering — state to pixels

`LectureViewer.tsx:315` renders `<SplitBoard slide={slide} notebook={notebook} mode="split" notebookTitle={chapter.title}/>`.

`SplitBoard.tsx:37` is a thin CSS-driven composition: `<SlidePanel state={slide}/>` + `<Notebook state={notebook}/>`. Mode (`split`/`slide_full`/`notebook_full`) and `viewport` (`responsive`/`preview`) are pure data-attributes; transitions are CSS. The `preview` viewport pins the board to fixed 1600×900 to match the precompute layout pipeline's measured placements byte-for-byte (`SplitBoard.tsx:18-24`); `LectureViewer` uses the default `responsive`.

### Slide — `SlidePanel.tsx`

- One slide at a time. `status === "loading"` → `DraftingLoader` ("Sketching…", `:87-93`). `status === "ready" && liveInstruction` → `InstructionSwitch` renders the diagram (`:94-100`). Note: this is `whiteboard/InstructionSwitch` (`SlidePanel.tsx:12`), not the legacy `engine/InstructionSwitch`.
- A `show_diagram` for a `draw_design_diagram` becomes `designDiagram` (`:57-60`), routed to `whiteboard/content/DesignDiagramContent` (renders SVG primitives + parameter sliders + KaTeX overlay; the live mirror of `design_agent`'s renderer).
- **Spotlight overlay** (`SlideAnnotationLayer`) mounts whenever the design spec carries a `dictionary` (`SlidePanel.tsx:64-65`), even before anything is focused, so focus transitions are clean. It consumes `focusedElementId/focusedRole/inlineLabelText` + `traces/markPoints/pointers/marginNotes` + `presentationMode` (`:102-116`). It resolves element bounds by querying the live DOM (`[data-design-element]` under `stageRef`) with a fallback to the spec's dictionary bounds.
- `presentationMode` is `build_up` (elements revealed as focused) or `overview` (all visible, spotlight additive), chosen at `SlidePanel.tsx:69-70`.

### Notebook — `Notebook.tsx`

- A vertical stack of `NotebookEntryView` over `page.entries` (`:112-123`). **Only the current page renders** — `useExtractionPlayback` clears `notebookEntries` on each page turn (`:762`, `:778`), so prior pages are gone from state.
- Equations sharing an `alignGroup` get a shared `=` column: each entry reports its `=` offset post-render (`handleEqualsOffset`, `:69`), the max is computed, and laggards are nudged via a per-entry CSS var (`alignOffsets`, `:92-110`).
- Page-turn animation: detected during render when `page.pageNum` changes (`:40-42`), flashes `.sb-notebook-turning` for 450ms (`:43-53`).

---

## 6. Board-snapshot tracking (the bridge to Ask Feynman)

`feat/unify_boardstate` attaches `Chapter.board_snapshots` — one `BoardSnapshot` per *closed page*, computed by the precompute composer (doc 01 §10). At runtime:

- `currentSnapshot` state starts `null` (`:377`).
- `advanceSnapshot(c)` (`:717-724`) consumes the next snapshot (1:1 with page closes) and is called **only** in `new_page` (`:764`) and `page_break` (`:785`).

So `currentSnapshot` always reflects the **last closed page**, never the live in-progress page. `LectureViewer.tsx:275` ships it as `board_snapshot` in the `doubt_intent` payload, and the worker's resolution planner formats it into the LLM prompt (`12-ask-feynman-flow.md` §5). This is the "what's on the board" contract — but it is page-stale (Known Issue #3), which matters most for the doubt path.

---

## 7. Known issues / out-of-sync (verified against full reads)

Each re-verified against the current source this pass. Severity is my engineering judgment, not a product call.

| # | Issue | Evidence | Severity | Notes |
|---|---|---|---|---|
| 1 | **Silent `show_diagram` lookup failure** | `useExtractionPlayback.ts:568-569`: `const d = c.diagrams[ev.diagram_id]; if (!d || !d.spec) return;` | **HIGH** | No log, no fallback, no placeholder. Because the preceding `topic_start` set the slide to `{status:"loading"}` (`:564`), a missing/spec-less diagram leaves the slide **stuck on the DraftingLoader forever** while audio keeps playing. Most user-visible failure mode. Fix: log + render a "missing diagram" placeholder. |
| 2 | **Non-audio pause skips the event on resume** | `:817-829` — on abort, audio rewinds (`:819-820`) but the `else` branch advances `cursorRef = i+1` (`:826`) | **MEDIUM** | If `pause()` lands during the ~200ms page-turn sleep of a `new_page`/`page_break`, that event returns `false` *before* its effects (`setNotebookEntries([])`, `pageNum++`, `advanceSnapshot`) run (`:758-760`, `:774-776`), yet the cursor advances past it. On resume the page never turns: notebook keeps appending to the stale page and the snapshot cursor desyncs. Narrow window, real. Fix: rewind non-audio pausable events too (don't advance cursor on abort). |
| 3 | **`board_snapshot` is page-stale** | `currentSnapshot` only updates via `advanceSnapshot` in `new_page`/`page_break` (`:764`, `:785`); starts `null` on page 0 | **MEDIUM** | The snapshot sent to the doubt resolver reflects the last *closed* page, not the current visual state. A doubt asked mid-page (or before the first page closes) sends stale/null board context. The planner still works (it has chapter context) but loses precision. See `12` §5. Fix would require a live snapshot at doubt-intent time. |
| 4 | **Snapshot index out-of-bounds → stale snapshot** | `:721`: `if (idx >= snaps.length) return;` | **LOW** | If `board_snapshots` is shorter than the page count (e.g. chapter ingested before snapshots existed, or composer emitted fewer), later page closes silently keep the old `currentSnapshot`. Graceful but undiagnosable. Fix: warn when a page closes with no available snapshot. |
| 5 | **Audio not stopped on unmount** | `LectureViewer.tsx:321` `<audio ref={setAudioElement}>`; no unmount cleanup pauses it | **LOW** | `cancel()` (which calls `audio.pause()`) only fires via `pause()`/`reset`/`restart`/`seek`. On navigating away mid-playback, nothing pauses the detached `<audio>`; browsers may keep it playing until GC. UX leak. Fix: `useEffect` cleanup that pauses + clears `src`. |
| 6 | **`page_break slide_action:"swap"` ignores `next_diagram_id`** | `:780-781`: swap → `setSlide({status:"loading"})`; `ev.next_diagram_id` (type `:123`) never read | **LOW** | The "swap" branch only sets a loading state and relies on a *following* `show_diagram` event to actually mount the new diagram. The `next_diagram_id` field is dead, and the coupling is implicit — a malformed manifest (swap with no following show_diagram) leaves the slide stuck loading. Fix: load `next_diagram_id` directly, or assert the following show_diagram. |
| 7 | **No runtime validation of `ChapterPayload`** | `LectureViewer.tsx:114` casts `data` directly | **LOW** | Future/renamed event or field shapes pass the cast and then no-op (unknown event types fall through `applySyncEvent`'s switch and `runEvent`'s `default → applySyncEvent` which also no-ops). Silent drops, no console signal. Fix: validate or at least `console.warn` on unknown `type`. |
| 8 | **Stale worker docstring** | `backend/.../livekit/worker.py:540-546` calls the classifier a "Phase 3 stub" and says Phase 4/5 are future | **INFO** | The code already runs the full classify→plan→match→deliver chain. Docstring rot only — no behavior impact. Fix: update the docstring. |
| 9 | **`SlideState.annotations` legacy field** | `split/types.ts` (Phase-2 field, deprecated for `focusedRole`) | **INFO** | Never written by the playback hook, never read by `SlidePanel`. Dead field kept "one back-compat cycle." Remove on next type cleanup. |

**What is working correctly** (verified, to avoid alarm): the entry/route flow; the preview_server contract incl. URL rewriting and inline diagram/topic embedding; sequential audio playback with cancelable pause + audio rewind; all 20 active event types handled; notebook pagination (current-page-only, align-group `=` columns, page-turn animation); annotation overlays (focus/trace/mark_point/point_at/write_margin); board-snapshot 1:1 page indexing.

---

## 8. Reading order for a new engineer

1. This doc, then `useExtractionPlayback.ts` top-to-bottom (the playback loop `:797`, `runEvent` `:728`, `applySyncEvent` `:541`).
2. `preview_server.py` — the manifest contract.
3. `LectureViewer.tsx` — the host (ignore the doubt parts; those are doc 12).
4. `SplitBoard.tsx` → `SlidePanel.tsx` → `Notebook.tsx` → `whiteboard/content/DesignDiagramContent.tsx`.
5. Cross-reference `01-precompute-pipeline.md` §6 to see how the manifest events were authored (chunker + audio_pipeline), and `07-contracts-and-protocols.md` §7 for the `ManifestEvent` union.
