# Pre-Compute Lecture Pipeline v2 — Overhaul

**Doc ID**: `17`
**Status**: design complete, implementation pending
**Author**: Yash + Claude (Opus 4.7 1M)
**Scope**: `data_pre_compute_v2/` + targeted frontend additions to `SplitBoard`
**Owns**: lecture-generation phases (planning, narration, diagrams, layout, annotations, pagination)
**Does NOT touch**: real-time agent (`backend/src/feynman/agent/`) is read-only here, but Phase 4 extracts shared planning code into a kernel both sides consume.

---

## 0. Why this exists

The v2 pipeline produces lectures that are coverage-correct but un-engaging:

- The board goes inert after a diagram appears — voice keeps talking, board stays static.
- Narration is textbook paraphrase, not a teacher leading from a hook.
- Length inflates with no budget; "topics" just march in TOC order with no arc.
- The current `enrichment/diagrams.py` prompt is a frozen-in-time fork of the real `design_agent`'s prompt — wrong colors (light/white vs dark SplitBoard), no semantic dictionary, no role-based addressing.
- Layout is unmeasured: text can overflow, page-turns rely on LLM judgment, slide swaps don't coordinate with text region.

This doc consolidates four design conversations (engagement redesign, dynamic board referencing, board-fullness handling, layout intelligence) into ONE coordinated overhaul.

**Bar**: a precomputed lecture should feel like a great human teacher thinking out loud at a board — hook then big picture then first principles then core; board always doing meaningful work; pointing/annotating sparingly at the moment things matter; pages turning deterministically when content demands.

---

## 1. Scope decision (locked)

**Full 4-phase rollout**, ~6–8 weeks single-developer, sequential phases.

Decided against the 3-week critical-path subset because Yash explicitly said "we are going to do everything in different sessions today only without missing even single details" — full quality, not partial.

Phases (sequential, each ships independently with visible improvement):

| Phase | Name                             | Duration   | Ships                                                                                 |
| ----- | -------------------------------- | ---------- | ------------------------------------------------------------------------------------- |
| **1** | Diagram dictionary fix           | ~1 day     | Dark/neon dark-mode diagrams with `dictionary` field; role-based addressing           |
| **2** | Dynamic board referencing        | ~1 week    | Highlights, pulses, pins, callouts, brackets, clear-annotations                       |
| **3** | Layout + pagination intelligence | ~2 weeks   | Page geometry, measurement, occupancy, deterministic page-breaks with carry-forward   |
| **4** | Engagement redesign              | ~3–4 weeks | Chapter arc planner, concept beats, per-beat narration, length enforcement, DiagramQA |

Each phase has its own `## Phase N` section below with file-level detail.

---

## 2. Architectural shape after all phases land

```
PDF
  → pdf parse + anchors                     (unchanged)
  → BookSkeleton                            (unchanged)
  → Topic extraction                        (unchanged, our_understanding is FACT SOURCE only)
  → Enrichment (questions)                  (unchanged for questions)
  → PREREQ linking                          (unchanged)
  → Validation gate                         (unchanged)
  ────────────────────────────────────────
  → ChapterLecturePlan         [Phase 4]    NEW: chapter arc, concept clusters, length budget
  → ConceptTeachingPlan (per)  [Phase 4]    NEW: Feynman beats — hook → big_picture → first_principles → derive
  → DiagramSpec per beat       [Phase 1,4]  NEW: design_agent in-process, with dictionary
  → DiagramQA                  [Phase 4]    NEW: vision-LLM spot-check of diagram vs claim
  → BeatNarration per beat     [Phase 4]    NEW: small per-beat LLM calls with annotation markers
  → LengthEnforcer             [Phase 4]    NEW: deterministic trim to budget
  → ScriptAssembler            [Phase 4]    NEW: stitch beats into chapter narration string
  ────────────────────────────────────────
  → ManifestComposer           [Phase 2,3]  NEW: ONE walker that owns annotations + layout
     ├ annotation policies     [Phase 2]    one-shot, cooldown, spatial dedup, clear semantics
     ├ layout policies         [Phase 3]    measurement, occupancy, overflow, page-break, carry-forward
     └ look-ahead              [Phase 3]    references determine slide carry-forward decisions
  ────────────────────────────────────────
  → TTS + audio + manifest events           (extended event vocabulary)
  → Diagram fallback PNG                    (unchanged)
  → Embeddings                              (unchanged)
  → Neo4j ingest                            (extended schema, see §11)
  ────────────────────────────────────────
  → preview_server + SplitBoard             (extended with new event handlers + placement honoring)
```

---

## 3. Cross-cutting decisions (apply to all phases)

These are the foundational decisions baked into every phase. Locked in.

### 3.1 The book is coverage + guardrails, never script

- `Topic.our_understanding` is FACT SOURCE — referenced for content correctness, never copied into spoken narration.
- A post-check enforces this: no narration sentence may have ≥80% character-overlap with any `our_understanding` sentence. Violations trigger regeneration of that beat.
- `BookSkeleton.chapters[i].key_concepts` + numbered section anchors form the `coverage_checklist`. Every checklist item must be referenced by ≥1 beat. Missing → re-call planner with required-coverage hints.

### 3.2 One unified composer, not multiple engines

- `ManifestComposer` owns both annotation policy and layout/pagination policy.
- Single walking loop through the fragment stream. Annotation injections, page-break injections, and clear injections all share the same insertion primitive.
- Module location: `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/`

### 3.3 Shared kernel with the real-time agent

- The `ConceptTeachingPlan` / `TeachingBeat` / `VisualBeatAction` Pydantic models + planning system prompts move from `backend/src/feynman/agent/concept_planner.py` into a shared package `feynman_teaching_kernel/`.
- Both the real-time agent and the pre-compute pipeline import the same kernel — kills drift between live teaching and recorded teaching.
- Kernel includes the EXTENDED beat vocabulary: `hook`, `big_picture`, `first_principles`, `derive`, `visual_build`, `explain`, `ask`, `misconception`, `example`, `summarize`, `transition`.

### 3.4 Role-based addressing everywhere

- Every annotation, every reference, every modification targets a **role** (e.g., `hypotenuse`, `weight`, `applied_force`), not a raw SVG element id.
- Role → element_id resolution happens at compose time (pipeline) using each diagram's `dictionary`.
- Page-coordinate bounds for every role are stamped onto `ShowDiagramEvent.slide_element_bounds` so the frontend doesn't re-resolve.

### 3.5 Hard rule: no padding

- Length budgeting is mandatory. Density of insight per minute is the explicit target.
- `LengthEnforcer` cuts deterministically; structural beats (`hook`, `big_picture`, `first_principles`, `ask`, `misconception`) are non-deletable.

### 3.6 Pre-compute latency tolerance

- Spend the time. Diagram generation can take 30–60s with retries. Vision QA can take 10s/diagram. Measurement is one-time per content hash.
- Cache aggressively (content-hashed). Idempotency snapshot already exists; extend it for new artifact types.

---

## 4. Open questions — locked-in defaults

All my recommended defaults from the design conversations are now locked as design decisions. Recorded here so future sessions know which were locked vs which were left explicit.

| #   | Question                               | Locked default                                                                         | Notes / can change                                |
| --- | -------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Q1  | Default chapter length budget          | **15 min** (configurable; salience-weighted 8–20 min per concept)                      | tune after Phase 4 ingestion                      |
| Q2  | Where does shared kernel live          | Extract `concept_planner.py` into new top-level package `feynman_teaching_kernel/`     | clean separation                                  |
| Q3  | Diagram engine call style              | **In-process** (import design_agent module, not HTTP)                                  | simpler ops                                       |
| Q4  | DiagramQA vision model                 | **Claude vision (Sonnet)**                                                             | reasonable cost; switch to Haiku if budget tight  |
| Q5  | Beat-narration parallelism             | 5 in flight per chapter                                                                | matches existing diagram concurrency              |
| Q6  | Old `enrichment/diagrams.py`           | **Deprecate** after Phase 4 lands                                                      | run both side-by-side for one chapter pre-cutover |
| Q7  | Coverage strictness                    | Re-call planner once on missing coverage, then `needs_review` flag                     | non-blocking                                      |
| Q8  | Standalone narrations                  | **Drop in v0**; standalone playback uses chapter narration from relevant `TOPIC_START` | halves audio work                                 |
| Q9  | Marker dedup downgrade                 | Repeated PIN → emit PULSE (transient) instead                                          | honors intent without overlap                     |
| Q10 | Annotation budget across carry-forward | **Persist** (don't reset on page break that keeps the same diagram)                    | prevents gaming the cap                           |
| Q11 | BRACKET shares persistent budget       | **Yes** (combined ≤4 per diagram)                                                      | "sticker book" prevention                         |
| Q12 | Lead vs follow on annotation timing    | **Lead** (eye-then-voice; markers at sentence boundary BEFORE the sentence)            | dominant teacher pattern                          |
| Q13 | Page viewport defaults                 | 1600×900; slide 900×800; notebook 600×800; gap 100px                                   | read from actual SplitBoard CSS if mismatched     |
| Q14 | Measurement backend                    | **Playwright in-process**                                                              | well-cached; well-understood                      |
| Q15 | Look-ahead window                      | **20s of audio** for slide carry-forward decisions                                     | tune after Phase 3 ingestion                      |
| Q16 | `slide_action=release` aesthetics      | **Soft placeholder** ("· · ·")                                                         | clear "no active diagram" signal                  |
| Q17 | `<<NEW_PAGE>>` writer markers          | **Keep** alongside composer auto-insertion                                             | pedagogical intent matters                        |
| Q18 | `PageSummary` diagnostic               | **Yes**, persist on Chapter                                                            | cheap, useful for debugging                       |
| Q19 | Topic boundaries vs page boundaries    | Not 1-1; topics share pages when content allows                                        | density over rigid breaks                         |
| Q20 | Measurement cache persistence          | Across pipeline runs, in `artifacts/measurement_cache/`, idempotent                    | survives `--force`                                |

---

## 5. Phase 1 — Diagram dictionary fix

**Goal**: replace the stale v1 diagram prompt with the canonical `design_agent` prompt. Every Diagram gains a populated `dictionary` and dark-mode neon palette.

### 5.1 Files touched

- **MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagrams.py`
  - Replace `DIAGRAM_SYSTEM_PROMPT` (lines 26–92) entirely.
  - Two options for the new prompt source (pick at implementation time):
    - **Option A (recommended)**: `import` from `design_agent.backend.prompts` if Python path allows; fall back to verbatim copy.
    - **Option B**: copy `design_agent/backend/prompts.py:SYSTEM_PROMPT` verbatim into `enrichment/diagrams.py` with a `# DO NOT EDIT — synced from design_agent on YYYY-MM-DD` header. Use this if import isn't clean.
  - Update `_build_user_prompt(...)` to ensure the user message asks for the dictionary (the new system prompt already requires it).
- **MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/validation/render_test.py`
  - Add an assertion: after rendering, if `render_data` lacks a non-empty `dictionary`, mark diagram `needs_review` but don't drop (graceful for any legacy specs).
- **OPTIONAL** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/validation/structural.py`
  - Add a check: every `Diagram.render_data` should have `dictionary` with ≥1 role-tagged element. Warn (not error) when missing.

### 5.2 What changes in generated output

- `Diagram.render_data` now contains a top-level `dictionary` field mapping element_id → `{role, semantic, position, spatial_relations, bounds}`.
- `Diagram.render_data.backgroundColor` becomes `"transparent"` (was `"#ffffff"`).
- Element strokes use the neon dark palette: light ink `#e8e8ee`, cyan `#7fd4ff`, green `#9effc9`, pink `#ff7a8a`, muted `rgba(232,232,238,0.55)`.
- All shapes outlined (`fill: "none"`), per design_agent's "diagram not slide" rule.
- Per-element bounds are now knowable from `dictionary[id].bounds`.

### 5.3 Frontend impact

- **None.** The SplitBoard already renders DiagramSpecs with arbitrary backgrounds and any colors. Existing chapter 5 PNG fallbacks may look wrong against the dark slide; re-render after re-generation.

### 5.4 Acceptance criteria

- Re-ingest chapter 5 with `--force --skip-questions --skip-tts`.
- In `out/extraction.json`: every Diagram has `render_data.dictionary` with ≥3 role entries (most diagrams have 5–10).
- Slide-side: playback shows dark-board neon diagrams (no white cards).
- `enrichment/diagrams.py` line count for the prompt section roughly matches `design_agent/backend/prompts.py` (i.e., we got the full prompt, not a truncated copy).

### 5.5 Risks

- Low. Single file change.
- Edge: the design_agent prompt mentions `parameters` and `animations` arrays — verify the v2 SVG renderer handles them or strip them. Quick check on `frontend/src/engine/whiteboard/split/SplitBoard.tsx` rendering path.

### 5.6 Estimated effort

- ~0.5 day, including re-ingesting chapter 5 to validate visually.

---

## 6. Phase 2 — Dynamic board referencing (annotations)

**Goal**: while a diagram is on the slide, the lecture can highlight, pulse, pin, callout, and bracket specific parts of it at narration-aligned moments. Persistent vs transient is distinguished. Repeats are prevented. Anti-overlap geometry is enforced.

### 6.1 Files touched

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/lecture_script/script_writer.py`

- Extend `SCRIPT_SYSTEM_PROMPT` (lines 63–201) with:
  - The 5 new markers (PIN, CALLOUT, BRACKET, HIGHLIGHT, PULSE) — full grammar.
  - The `CLEAR_ANNOTATIONS` marker — wipes annotation overlay on current diagram.
  - The hard rules: one-shot for persistent, sparing, place at sentence boundaries, budget ≤4 persistent per diagram, cooldown for transient.
- Extend `_build_user_prompt(...)` to list available ROLES per diagram (read from `Diagram.render_data.dictionary`).

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/tts/chunker.py`

- Extend `_MARKER_RE` (line 34) to recognize: `HIGHLIGHT`, `PULSE`, `PIN`, `CALLOUT`, `BRACKET`, `CLEAR_ANNOTATIONS`.
- Add 6 new fragment dataclasses: `HighlightFragment`, `PulseFragment`, `PinFragment`, `CalloutFragment`, `BracketFragment`, `ClearAnnotationsFragment`.
- Extend `_build_fragment(...)` (line 202) with 6 new branches.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py`

- Add 6 new event types as Pydantic BaseModels:
  - `HighlightEvent { type, diagram_id, target_role, target_element_id?, duration_ms, color_token? }`
  - `PulseEvent { type, diagram_id, target_role, target_element_id?, duration_ms, color_token? }`
  - `PinEvent { type, diagram_id, target_role, target_element_id?, annotation_id, text, position }`
  - `CalloutEvent { type, diagram_id, target_role, target_element_id?, annotation_id, text, direction }`
  - `BracketEvent { type, diagram_id, target_role_a, target_role_b, target_element_id_a?, target_element_id_b?, annotation_id, label, side }`
  - `ClearAnnotationsEvent { type, diagram_id }`
- Extend the `ManifestEvent` discriminated union (line 106) with the 6 new types.

**NEW MODULE** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/`

- `__init__.py` — exports `ManifestComposer`.
- `policies/annotations.py` — annotation policy rules (one-shot, cooldown, spatial dedup, downgrade).
- `policies/notebook.py` — handles writer `<<NEW_PAGE>>` markers (deterministic page-cap added in Phase 3).
- `geometry.py` — `Rect` type (reuse from `spatial_solver.py` if importable cleanly; otherwise local copy).
- `walker.py` — the single stream walker that holds state and applies policies.
- `composer.py` — public entry point: `compose(fragments, diagrams_by_id, audio_durations_estimator) -> list[ManifestEvent]`.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/media/audio_pipeline.py`

- In `_do_build_for_chapter` (line 143): between `split_script(...)` (line 163) and `_render_fragments(...)` (line 164), invoke `ManifestComposer.compose(...)`.
- Extend `_render_fragments` (line 195) with 6 new fragment→event branches.

**MODIFY FRONTEND** `frontend/src/screens/LecturePreviewScreen.tsx`

- Add 6 event handler branches in the manifest event walker (analogous to existing `write_equation`, `show_diagram` cases).
- Each routes to the existing SplitBoard annotation primitive used by the real-time agent.

**MODIFY FRONTEND** `frontend/src/engine/whiteboard/split/SplitBoard.tsx` (or wherever annotation overlay lives)

- Confirm the annotation overlay layer reads `diagram_id` and resolves roles via the active slide's `dictionary`. Wire up the 6 new event types to existing animation primitives.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/ingestion/cypher_generator.py`

- Manifest JSON blobs serialize new event types automatically (Pydantic discriminator does this). No Cypher schema change beyond ensuring `chapter_manifest` and `standalone_manifest` properties accept the bigger JSON.

### 6.2 The 5 new markers — VERBATIM grammar

```
Persistent (drawn once, stays until diagram changes):
  <<PIN role|text|position=above|id=pin-1>>
  <<CALLOUT role|text|direction=up-right|id=callout-1>>
  <<BRACKET role_a,role_b|label|side=above|id=brk-1>>

Transient (appears, fades):
  <<HIGHLIGHT role|duration=1500>>
  <<PULSE role|duration=800>>

Overlay reset:
  <<CLEAR_ANNOTATIONS>>
```

- `role` references a role from the diagram's `dictionary`.
- `text`/`label` content is mandatory; everything after `|` is attributes.
- `position` for PIN: `above | below | left | right` (default `above`).
- `direction` for CALLOUT: `up-right | up-left | down-right | down-left | right | left | up | down` (default `up-right`).
- `side` for BRACKET: `above | below` (default `above`).
- `id` is optional; auto-generated if missing. Required only if a later marker would reference it.
- `duration` for HIGHLIGHT/PULSE is in milliseconds; defaults `1500` and `800`.

### 6.3 The composer policy rules (locked-in)

State held per chapter:

```
per_diagram:
  persistent_annotations: dict[(role, action_type), AnnotationRecord]
  spatial_occupancy: list[Rect]    # bounds of placed labels + element bounds
  last_transient_ms: dict[role, int]
  transient_window: deque[(ms, role)]    # rolling 30s
  persistent_count: int

global:
  cumulative_audio_ms: int           # advances per TextFragment estimated/actual duration
  active_diagram_id: str | None
```

Per-fragment decisions:

- `ShowDiagramFragment`: reset all per-diagram state for new `diagram_id`; set `active_diagram_id`. Emit `ShowDiagramEvent`.
- `ClearAnnotationsFragment`: wipe `persistent_annotations[diagram_id]`, reset `spatial_occupancy[diagram_id]`, reset `persistent_count`. Emit `ClearAnnotationsEvent`.
- `PinFragment(role=R)` / `CalloutFragment` / `BracketFragment`:
  1. Validate role exists in `active_diagram.dictionary`. If not, drop with log `role_unknown`.
  2. If `(role, action_type)` already in `persistent_annotations`: drop, downgrade to `PulseEvent` if not in transient cooldown.
  3. If `persistent_count >= 4`: drop, log `persistent_budget_exceeded`. Consider emitting `ClearAnnotationsEvent` auto-injection if conditions match.
  4. Compute label position via `_resolve_position` (tries requested position, then fallback order: `above → right → below → left → above-right → above-left → below-right → below-left`). For each candidate, check overlap against `spatial_occupancy`. If all 8 fail: drop.
  5. Emit event with resolved position; record annotation_id; add label rect to `spatial_occupancy`; increment `persistent_count`.
- `HighlightFragment` / `PulseFragment`:
  1. Validate role.
  2. Check `last_transient_ms[(diagram, role)]` — if `cumulative_audio_ms - last < 6000`: drop, log `transient_cooldown`.
  3. Check `transient_window` for `diagram_id` — if length ≥ 3 within 30s rolling: drop, log `transient_rate_limit`.
  4. Emit; update `last_transient_ms`; append to `transient_window`.
- `TextFragment`: estimate duration via `len(text) / WPM_CHARS_PER_MS` (default `~12 chars/sec = 83ms/char` for Kokoro), increment `cumulative_audio_ms`. No event yet — audio_pipeline emits `AudioEvent` after TTS.

Defaults exposed in `policies.py`:

```python
COOLDOWN_SAME_ROLE_MS = 6000
MAX_TRANSIENTS_PER_DIAGRAM_30S = 3
MAX_PERSISTENT_PER_DIAGRAM = 4
TRANSIENT_WINDOW_MS = 30000
LABEL_PADDING_PX = 8
POSITION_FALLBACK_ORDER = ["above", "right", "below", "left", "above-right", "above-left", "below-right", "below-left"]
DROP_LOG_LEVEL = logging.WARNING
```

### 6.4 Acceptance criteria

- Re-ingest chapter 5 with `--force --skip-questions`.
- Inspect `chapters[0].chapter_manifest.events` in `extraction.json`: should show interleaved AudioEvent + new annotation events.
- For at least one diagram in the chapter: 2–4 PinEvents, 0–2 BracketEvents, multiple PulseEvents — no duplicate (diagram, role, PIN) pairs.
- Playback at `http://localhost:5173/#/lecture-preview`: pins land at the right narration moments and stay; pulses fire on re-mentions; cross-fade clears annotations; no visible overlap between pin labels.
- Composer log shows expected drop counts (some `transient_cooldown`, some `role_unknown` if the writer hallucinated; flag if `persistent_budget_exceeded` is common — indicates the writer is over-pinning).

### 6.5 Risks

- The script writer LLM may hallucinate roles. Mitigation: prompt lists the role vocabulary per diagram; composer drops unknowns gracefully.
- Spatial dedup edge cases (curved BRACKETs near canvas edges). Mitigation: start with greedy 8-position fallback; can upgrade to proper layout solver later.
- Frontend overlay GC on cross-fade — verify it actually clears.

### 6.6 Estimated effort

- ~5–7 days. Roughly: 1 day prompt work, 1 day chunker + models, 2 days composer (policies + geometry), 1 day frontend wiring, 1 day end-to-end validation + tuning.

---

## 7. Phase 3 — Layout + pagination intelligence

**Goal**: deterministic page management. Every text block measured, every diagram placed in known coords, every page break triggered by measured overflow or new-diagram conflict, with diagram-carry-forward decided by reference look-ahead.

### 7.1 Files touched

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/config.py`

- Add `LayoutConfig` Pydantic model with the full §7.3 schema.
- Add `PipelineConfig.layout: LayoutConfig`.

**MODIFY** `data_pre_compute_v2/config.yaml`

- Add `layout:` block with defaults from §7.3.

**NEW** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/measurement.py`

- Headless-browser measurement service (Playwright).
- `MeasurementService.start()` — launches Chromium with a measurement page loaded.
- `MeasurementService.measure(type, content, attrs, width_px) -> {width, height}` — calls into the page via `page.evaluate(...)`.
- Cache on disk in `artifacts/measurement_cache/`, keyed by `sha256(type, content, attrs, width)`.

**NEW** `data_pre_compute_v2/tools/measurement_page.html`

- Static HTML that loads the SplitBoard CSS + KaTeX + exposes `window.measureBlock({type, content, attrs, width})` returning bounding-rect dimensions.

**NEW** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/policies/layout.py`

- `LayoutPlanner` class — implements the per-page state model from §7.4.
- Methods: `place_text(fragment) -> (placed_event, was_break)`, `place_diagram(fragment) -> (placed_event, was_break)`, `decide_slide_action(lookahead_fragments) -> "keep" | "swap" | "release"`.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/walker.py`

- Integrate `LayoutPlanner` alongside annotation policies.
- Single walking loop applies both families of policies.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py`

- Add `Placement` Pydantic model: `{ page_index: int, rect: Rect, measured: bool }`.
- Extend each notebook event (`WriteEquationEvent`, `WriteStepEvent`, etc.) with `placement: Placement | None`.
- Extend `ShowDiagramEvent` with `placement: Placement | None` and `slide_element_bounds: dict[str, Rect]` (role → page-coord bounds).
- Add `PageBreakEvent`: `{ type, new_page_index, slide_action: "keep"|"swap"|"release", next_diagram_id: str | None, notebook_carry_forward_ids: list[str], reason: str }`. Promote `NewPageEvent` to be a subset (or alias) — `NewPageEvent` becomes deprecated but tolerated; preferred is `PageBreakEvent`.
- Add `PageSummary`: `{ page_index, topic_id, slide_diagram_id, notebook_block_count, notebook_height_used_px, notebook_height_total_px, annotations_count }`.
- Extend `Chapter` model with `pages: list[PageSummary]`.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/ingestion/cypher_generator.py`

- Handle the new placement fields in event serialization. Add `pages` property on Chapter Cypher.

**MODIFY FRONTEND** `frontend/src/screens/LecturePreviewScreen.tsx`

- Honor `placement.rect` for absolute positioning (replace flow layout with absolute coords).
- Handle `PageBreakEvent.slide_action`:
  - `keep`: animate notebook page-flip; slide unchanged; annotations carry forward.
  - `swap`: animate both — notebook page-flip + slide cross-fade to `next_diagram_id`; annotation overlay clears.
  - `release`: animate notebook page-flip; slide fades to soft placeholder ("· · ·" centered in slide region).

**MODIFY FRONTEND** `frontend/src/engine/whiteboard/split/SplitBoard.tsx`

- Confirm page geometry matches `LayoutConfig` defaults. Add an absolute-positioning mode for events that include `placement.rect`.

### 7.2 The measurement page contract (`measurement_page.html`)

```html
<!DOCTYPE html>
<html>
  <head>
    <link rel="stylesheet" href="/path/to/SplitBoard.css" />
    <link
      rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/katex@0.16.x/dist/katex.min.css"
    />
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.x/dist/katex.min.js"></script>
  </head>
  <body>
    <div id="root"></div>
    <script>
      window.measureBlock = ({ type, content, attrs, width }) => {
        const host = document.createElement("div");
        host.style.position = "absolute";
        host.style.visibility = "hidden";
        host.style.width = `${width}px`;
        host.className = `notebook-block notebook-block--${type.toLowerCase()}`;
        // Render content per type — equation uses KaTeX, others are plain text
        if (type === "EQUATION") {
          katex.render(content, host, { throwOnError: false });
        } else if (type === "SECTION") {
          host.innerHTML = `<h3 class="notebook-section">${escapeHtml(content)}</h3>`;
        } else if (type === "KEY") {
          host.innerHTML = `<div class="notebook-key">${escapeHtml(content)}</div>`;
        } else if (type === "STEP") {
          const indent = attrs.indent || 0;
          host.innerHTML = `<div class="notebook-step" style="padding-left:${indent * 24}px">${escapeHtml(content)}</div>`;
        } else if (type === "ANSWER") {
          host.innerHTML = `<div class="notebook-answer">${escapeHtml(content)}</div>`;
        } else if (type === "TEXT") {
          host.innerHTML = `<div class="notebook-text">${escapeHtml(content)}</div>`;
        }
        document.body.appendChild(host);
        const rect = host.getBoundingClientRect();
        const dims = { width: rect.width, height: rect.height };
        document.body.removeChild(host);
        return dims;
      };
    </script>
  </body>
</html>
```

### 7.3 LayoutConfig defaults

```yaml
layout:
  viewport: { width: 1600, height: 900 }
  slide:
    x: 30
    y: 50
    width: 900
    height: 800
    padding: 20
  notebook:
    x: 970
    y: 50
    width: 600
    height: 800
    padding: 30
  block_spacing_px: 12
  block_default_widths:
    SECTION: 540
    EQUATION: 540
    STEP: 520
    KEY: 540
    TEXT: 540
    ANSWER: 540
  diagram:
    max_scale: 1.0
    fit: "contain"
  measurement:
    mode: "headless_browser"
    cache_dir: "./artifacts/measurement_cache"
    page_path: "./tools/measurement_page.html"
  pagination:
    lookahead_seconds: 20.0
    overflow_safety_margin_px: 8.0
```

### 7.4 PageState walker (per chapter)

```python
class PageState:
    page_index: int
    slide: SlideState              # diagram_id, placed_rect, element_bounds, annotations
    notebook: NotebookState        # blocks, cursor_y, available_height
    audio_time_ms: float           # cumulative at this point in stream
    topic_id: str
```

Per-fragment decisions:

- **Text/equation fragment**: measure block → required_vertical = `block.height + block_spacing_px`. If `notebook.cursor_y + required_vertical > notebook.y + notebook.height - notebook.padding`: **trigger page break** (text overflow). Else place at `(notebook.x + notebook.padding, cursor_y, ...)` and advance `cursor_y`.
- **Diagram fragment** (`<<SHOW_DIAGRAM:id>>`):
  - If `slide.diagram_id is None`: compute scale + bounds + per-role element bounds, set state. Emit `ShowDiagramEvent` with `slide_element_bounds`.
  - If matches current: no-op.
  - If different: **trigger page break** (new-diagram conflict). Open new page with the new diagram.
- **Explicit `<<NEW_PAGE>>` from writer**: trigger page break with `reason="writer_marker"`.

### 7.5 Page-break procedure (coupling Option C)

When any trigger fires:

1. **Decide slide_action** via `decide_slide_action(lookahead_fragments)`:
   - Scan forward up to `lookahead_seconds` of audio time (sum of estimated TextFragment durations).
   - Collect any reference fragments (PIN/PULSE/HIGHLIGHT/CALLOUT/BRACKET) whose target role is in current diagram's `dictionary`.
   - Stop at first `<<SHOW_DIAGRAM>>` (marks end of current diagram's relevance) or at window end.
   - If trigger is "new_diagram" → `slide_action = "swap"`, `next_diagram_id = new_id`.
   - If trigger is "text_overflow" AND references exist OR no upcoming ShowDiagram → `slide_action = "keep"`.
   - If trigger is "text_overflow" AND no references AND no upcoming ShowDiagram → `slide_action = "release"`.
   - If trigger is "writer_marker" → `slide_action = "swap"` if next ShowDiagram is within window, else `"keep"`.
2. **Emit `PageBreakEvent`** with the resolved `slide_action`, `next_diagram_id`, `reason`, and `notebook_carry_forward_ids` (auto-select: the last `<<WRITE_ANSWER>>` or `<<WRITE_KEY>>` block if it exists and isn't superseded; otherwise empty).
3. **Open new PageState** (`page_index += 1`).
4. If `slide_action == "keep"`: carry slide state forward (diagram_id, placed_rect, element_bounds). Annotation state persists.
5. If `slide_action == "swap"`: emit `ShowDiagramEvent` for `next_diagram_id` on new page; reset annotation state.
6. If `slide_action == "release"`: set `slide.diagram_id = None`. Slide will hold soft placeholder until next ShowDiagram.
7. Place the deferred fragment on the new page (the one that triggered the break, if any).

### 7.6 Acceptance criteria

- Re-ingest chapter 5.
- `chapters[0].pages` in extraction.json shows 4–8 pages with `notebook_height_used_px` between 60–95% of `notebook_height_total_px` (no under-30% pages, no >100% overflows).
- All notebook events have `placement.rect` with `measured=true`.
- All `ShowDiagramEvent`s have `slide_element_bounds` populated.
- `PageBreakEvent.reason` distribution shows: some `text_overflow`, some `new_diagram`, some `writer_marker` — proves all three triggers fire.
- Playback: no notebook entry visually clips at page bottom; page transitions smooth; annotations correctly carry forward on `slide_action="keep"`.
- Measurement cache populated; second `--force` run reuses cached measurements (verify by timing).

### 7.7 Risks

- Playwright integration depth — font matching, CSS loading order, headless quirks. Mitigation: build measurement service early in the phase; verify against eyeballed dimensions on 10 sample blocks.
- Look-ahead window tuning — too short over-swaps slides, too long over-carries. Calibrate against real chapter behavior.
- Frontend reflow from CSS layout → absolute positioning. May need to keep CSS as a fallback for un-measured blocks.

### 7.8 Estimated effort

- ~10–14 days. Roughly: 3 days measurement service, 4 days LayoutPlanner + page-break logic, 2 days frontend placement-honoring, 2 days end-to-end validation + tuning, 1–2 days schema migration + Cypher updates.

---

## 8. Phase 4 — Engagement redesign

**Goal**: replace the monolithic `ScriptWriter` with a chapter-arc planner → per-concept beat planner → per-beat narration writer → length enforcer. Diagrams generated per-beat via the shared kernel + design_agent + vision QA. Every lecture opens with a hook and flows through Feynman-style beats.

### 8.1 Files touched

**NEW PACKAGE** `feynman_teaching_kernel/` (top-level, importable by both backend and pipeline)

- Repository location: TBD — propose `/Users/yashbansal/proj/feynman/feynman_teaching_kernel/` as a sibling to `backend/` and `data_pre_compute_v2/`, with `pyproject.toml` declaring it as a local package.
- Both `backend/src/feynman/agent/` and `data_pre_compute_v2/src/lecture_pipeline_v2/` add it as a dependency.
- Contains:
  - `models.py` — `ConceptTeachingPlan`, `TeachingBeat`, `VisualBeatAction`, `ChecklistItem` (moved from `backend/src/feynman/agent/concept_planner.py` and `doubt_orchestrator.py`).
  - `prompts.py` — `PLANNING_SYSTEM_PROMPT` (the full prompt from `concept_planner.py:182-339`), extended with hook/big_picture/first_principles requirements.
  - `planner.py` — `plan_concept()` async function (moved from `concept_planner.py`).
  - `format.py` — `format_plan_for_prompt()` (moved).
  - `style_guide.py` — banned-opener regex list, sentence-style validators.

**MODIFY** `backend/src/feynman/agent/concept_planner.py`

- Replace local models + prompts with `from feynman_teaching_kernel import …`.
- Keep doubt-specific planning (`plan_doubt`) in this file or move to kernel — decide at implementation time.

**MODIFY** `backend/src/feynman/agent/prompts.py`

- Update imports: `from feynman_teaching_kernel.format import format_plan_for_prompt` (was local).

**NEW** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/lecture_plan/`

- `__init__.py`
- `models.py` — `ChapterLecturePlan` Pydantic model.
- `prompts.py` — `CHAPTER_PLANNER_SYSTEM_PROMPT`.
- `chapter_planner.py` — `ChapterLecturePlanner.plan(chapter, topics, skeleton) -> ChapterLecturePlan`.

**NEW** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/beat_narration/`

- `__init__.py`
- `prompts.py` — `BEAT_NARRATION_SYSTEM_PROMPT` (one prompt that knows annotation grammar).
- `writer.py` — `BeatNarrationWriter.write(beat, concept_plan, diagram_dictionary, target_seconds) -> BeatNarration`.
- `models.py` — `BeatNarration { text, audio_targets, beat_id }`.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagrams.py`

- Refactor `DiagramGenerator` → `DiagramSpecGenerator`. Accept a `VisualBeatAction` instead of a `Topic`. Generate per-beat, not per-topic.
- Support `mode="auto" | "direct" | "python"` for design_agent path selection. Default `auto` (heuristic based on geometric keywords in beat description).
- Temperature `0.1` (was `0.3`). Retries up to 2 on validation failure.

**NEW** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagram_qa.py`

- `DiagramQA.verify(spec, claim) -> {passed, score, issue, suggestion}`.
- Implementation: render spec to PNG (existing `DiagramFallbackRenderer`) → call Claude Sonnet with vision attachment + scoring rubric → parse.
- On `score < 3`: re-call `DiagramSpecGenerator` with corrective hint. Max 2 retries.

**NEW** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/length_enforcer/`

- `__init__.py`
- `enforcer.py` — `LengthEnforcer.trim(chapter_plan, beat_narrations, audio_durations) -> trimmed_beats`.
- Algorithm in §8.4.

**NEW** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/script_assembler.py`

- Stitches per-beat `BeatNarration.text` into one narration string per topic in the format `tts/chunker.py` expects.
- Inserts `<<TOPIC_START:id>>` at concept-cluster boundaries.
- Inserts `<<BEAT_START:type|id>>` and `<<BEAT_END:id>>` for observability (composer can use these later for telemetry).

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/pipeline.py`

- Insert new phases 7a (chapter plan), 7b (concept plans), 7c (diagram per beat), 7d (diagram QA), 7e (beat narration), 7f (length enforcer), 8 (script assembler) before existing Phase 9 (TTS).
- Remove old `ScriptWriter.write_for_all` call; replace with new flow.
- Phase order: same as §2 architecture diagram.

**DEPRECATE** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/lecture_script/script_writer.py`

- Keep file for backward compatibility during transition; route around it after Phase 4 lands.
- Delete after one chapter has been fully validated through the new path.

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py`

- Add to `Chapter`: `lecture_plan: ChapterLecturePlan | None`, `concept_plans: list[ConceptTeachingPlan]`, `length_budget_minutes: float`.
- Add to `Topic`: `coverage_anchor_ids: list[str]` (derived from section anchors + key concepts touched by this topic).

**MODIFY** `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/ingestion/cypher_generator.py`

- Serialize the new ChapterLecturePlan + ConceptTeachingPlan fields onto Chapter/Topic nodes.

### 8.2 ChapterLecturePlan model

```python
class ConceptCluster(BaseModel):
    cluster_id: str
    concept_title: str
    covers_topic_ids: list[str]                    # which Topic(s) this cluster covers
    coverage_anchor_ids: list[str]                 # section numbers + key_concepts
    target_minutes: float
    board_pattern: Literal["concept_intro", "derivation", "comparison", "problem_solving", "single_focus", "free_form"]
    salience_weight: float = 1.0

class ChapterLecturePlan(BaseModel):
    chapter_id: str
    chapter_arc: str                               # 2-3 sentences — the chapter as a story
    concept_sequence: list[ConceptCluster]         # may MERGE / SPLIT / DROP from raw topic order
    length_budget_minutes: float
    coverage_checklist: list[str]                  # every anchor + key_concept that MUST be referenced
    rationale: str                                 # brief — why this clustering, what's emphasized
```

### 8.3 Concept planner prompt extension

The shared `PLANNING_SYSTEM_PROMPT` (in `feynman_teaching_kernel`) gets one critical addition near the top:

```
## Arc requirements (NON-NEGOTIABLE)

Every concept MUST open with these four beats, IN ORDER, BEFORE any
derive/explain/visual_build beats descend into the core mechanics:

  1. hook (~10-15s) — a question, paradox, surprising fact, or relatable analogy
     that makes the student CARE. Never open with a definition. Never open with
     "in this section we look at...". Lead with curiosity.

  2. big_picture (~20-30s) — place this idea in a larger landscape. Where does
     this concept sit in the world / in science / in everyday life? Why does it
     matter beyond passing the exam?

  3. first_principles (~30-60s) — build intuition from the ground up using the
     core_analogy. NOT the formal definition yet — the mental model the formula
     will later confirm.

  4. (then any of: derive, explain, visual_build, ask, misconception, example,
     summarize, transition)

The first three beats are STRUCTURAL — the LengthEnforcer cannot delete them.
```

The Pydantic validator on `ConceptTeachingPlan.beats` enforces this at parse time: must contain `hook` followed by `big_picture` followed by `first_principles` as the first three beats.

### 8.4 LengthEnforcer algorithm

```python
def trim(chapter_plan: ChapterLecturePlan, beat_narrations: list[BeatNarration]) -> list[BeatNarration]:
    estimated_total_s = sum(estimate_seconds(b.text) for b in beat_narrations)
    budget_s = chapter_plan.length_budget_minutes * 60
    if estimated_total_s <= budget_s * 1.1:
        return beat_narrations  # within 10% of budget — accept

    # Pass 1: drop low-priority beats
    candidates_to_drop = (
        [b for b in beat_narrations if b.beat_type == "summarize"]
        + [b for b in beat_narrations[1:] if b.beat_type == "example"]  # keep first example
    )
    for b in candidates_to_drop:
        beat_narrations.remove(b)
        if estimated_total_s := recompute() <= budget_s * 1.1:
            return beat_narrations

    # Pass 2: merge adjacent explain/derive beats
    # ... (deterministic merging by concatenating speech with smooth connector)

    # Pass 3: re-call BeatNarrationWriter on longest remaining beat with 25% tighter target
    longest = max(beat_narrations, key=lambda b: estimate_seconds(b.text))
    if longest.beat_type not in {"hook", "big_picture", "first_principles", "ask", "misconception"}:
        new_text = beat_narration_writer.rewrite(longest, target_seconds=longest.target_duration_seconds * 0.75)
        longest.text = new_text

    # Hard ceiling check
    if estimated_total_s := recompute() > budget_s * 1.3:
        log.warning("LengthOverflow", chapter=chapter_plan.chapter_id, over_pct=...)
        # Don't abort — flag chapter needs_review
    return beat_narrations
```

Non-deletable beat types: `hook`, `big_picture`, `first_principles`, `ask`, `misconception`.
Deletable in order: `summarize` → secondary `example` → adjacent `explain`/`derive` merge.

### 8.5 BeatNarrationWriter prompt structure

```
System prompt:
"You write one teaching beat for a precomputed lecture. The student is ~14 years old.
This beat has type {beat_type} and a target duration of {target_seconds}s.
Write a spoken-narration string that:
  - Speaks like an excellent teacher (warm, clear, intellectually honest).
  - Does NOT paraphrase the textbook content.
  - Embeds inline markers from this vocabulary:
    [annotation grammar from Phase 2 — full role list of available diagrams provided]
    [SHOW_DIAGRAM if this beat introduces a new visual]
    [WRITE_EQUATION / WRITE_STEP / WRITE_KEY / WRITE_TEXT / WRITE_ANSWER / WRITE_SECTION as needed]
    [PAUSE for emphasis]
  - Places markers at sentence boundaries.
  - Targets exactly ~{target_words} words (= target_seconds * 2.5 WPS).
  - Hook beats: provocative question / paradox / analogy. NEVER definition.
  - Big_picture: where does this idea live in the larger landscape.
  - First_principles: intuition from the ground up using {core_analogy}.
  - Derive/explain: stay tight to the beat's speech_guidance.
  - Output: ONE narration string. No JSON wrapper. No commentary."

User prompt: {beat.speech_guidance} + {visual context} + {role vocabulary} + {fact source from our_understanding}
```

### 8.6 Acceptance criteria

- Re-ingest chapter 5 with full Phase 4 path.
- `out/extraction.json` shows `chapters[0].lecture_plan` populated with chapter_arc + concept_sequence (likely 5–7 clusters, possibly merged from 7 raw sections).
- Every cluster's first three beats are `hook`, `big_picture`, `first_principles` (validator passes).
- Total chapter audio duration within 110% of `length_budget_minutes`.
- No narration sentence has ≥80% character-overlap with `Topic.our_understanding` sentences (coverage check passes).
- DiagramQA flagged ≤10% of diagrams for regeneration; final accepted diagrams all score ≥3/5.
- Playback: lecture opens with a HOOK not a definition. Beats flow correctly. Voice + board are coordinated (annotations from Phase 2 fire). No dead board >8s.

### 8.7 Risks

- Highest risk phase. Many moving parts.
- Prompt iteration cycle dominates. Expect 3–4 cycles of "watch lecture → refine prompt → re-ingest → watch again" before quality lands.
- Cost: per-chapter LLM spend goes from ~$0.30 (current) to ~$3–5 (Phase 4 full). Configure model choice at concept-planner / beat-narration level — start with Sonnet, downgrade to Haiku for narration if quality holds.
- Shared kernel extraction touches the real-time agent — must not break it. Run real-time agent tests after kernel extraction.

### 8.8 Estimated effort

- ~20–28 days. Rough split: 3 days kernel extraction + real-time agent re-validation, 4 days ChapterLecturePlanner + ConceptPlanner integration, 3 days DiagramSpecGenerator refactor + per-beat generation, 4 days DiagramQA (vision integration + prompt tuning), 5 days BeatNarrationWriter (prompt + integration), 3 days LengthEnforcer + ScriptAssembler, 4–6 days end-to-end validation cycles.

---

## 9. The unified ManifestComposer (cross-cutting)

Single module at `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/`.

```
manifest_composer/
├── __init__.py                  # public API: compose(fragments, diagrams, config) -> list[ManifestEvent]
├── walker.py                    # the single fragment walker, holds combined state
├── geometry.py                  # Rect, overlap check, position resolver
├── measurement.py               # Phase 3: Playwright service + cache
├── policies/
│   ├── annotations.py           # Phase 2: one-shot, cooldown, spatial dedup
│   ├── layout.py                # Phase 3: occupancy, overflow detection, page-break decisions
│   └── notebook.py              # writer NEW_PAGE handling
└── tests/
    ├── test_annotations.py
    ├── test_layout.py
    └── test_walker_integration.py
```

The walker walks fragments once. For each fragment, it dispatches to the relevant policy module and applies the result. State (`per_diagram`, `current_page`, `cumulative_audio_ms`) is held in the walker.

Invocation point: `media/audio_pipeline.py:_do_build_for_chapter`, between `split_script(...)` and `_render_fragments(...)`.

```python
# Pseudocode
fragments = split_script(narration_text)
composed = ManifestComposer(config.layout).compose(
    fragments=fragments,
    diagrams_by_id=diagrams_by_id,
    audio_estimator=estimate_audio_duration,
)
# composed is list[ManifestEvent], including the new annotation events, PageBreakEvents,
# and placement metadata on every event.
events = await audio_pipeline._render_audio(composed)
```

---

## 10. Cost model (per chapter, Phase 4 full)

| Stage                 | Calls                       | Tokens (avg)                        | Sonnet cost        | Notes                     |
| --------------------- | --------------------------- | ----------------------------------- | ------------------ | ------------------------- |
| BookSkeleton          | 1/book                      | ~5k in / ~2k out                    | ~$0.02             | amortized across chapters |
| Topic extraction      | 7 (one per section)         | ~3k in / ~1k out each               | ~$0.15             | unchanged                 |
| ChapterLecturePlanner | 1/chapter                   | ~6k in / ~3k out                    | ~$0.04             | new                       |
| ConceptPlanner        | 5–7/chapter                 | ~4k in / ~2k out each               | ~$0.15             | shared kernel call        |
| DiagramSpecGenerator  | 8–15/chapter                | ~5k in / ~4k out each               | ~$0.35             | replaces enrichment       |
| DiagramQA             | 8–15/chapter                | ~3k in (with image) / ~500 out each | ~$0.25             | Claude vision             |
| BeatNarrationWriter   | 25–40/chapter               | ~3k in / ~1.5k out each             | ~$0.50             | new, per-beat             |
| QuestionGenerator     | 5–7/chapter                 | ~2k in / ~2k out each               | ~$0.20             | unchanged                 |
| **Subtotal LLM**      |                             |                                     | **~$1.70/chapter** |                           |
| Kokoro TTS            | local                       | 0                                   | $0                 | unchanged                 |
| Embeddings            | local sentence-transformers | 0                                   | $0                 | unchanged                 |
| **TOTAL per chapter** |                             |                                     | **~$1.70**         | Opus path: ~$8–12         |

For full IGCSE Maths 0580 (~25 chapters): ~$40 one-time at Sonnet rates. Acceptable.

---

## 11. Neo4j schema migrations

Combined across all phases. List of new properties/labels:

**Diagram**:

- Inside `render_data` (JSON blob): `dictionary` field per spec.
- No new top-level Neo4j properties (render_data is one JSON property).

**Topic**:

- `coverage_anchor_ids: list[str]`

**Chapter**:

- `lecture_plan: str` (serialized ChapterLecturePlan JSON)
- `concept_plans: str` (serialized list[ConceptTeachingPlan] JSON)
- `length_budget_minutes: float`
- `pages: str` (serialized list[PageSummary] JSON)

**Manifest events** (inside `chapter_manifest` / `standalone_manifest` JSON):

- New event types: HighlightEvent, PulseEvent, PinEvent, CalloutEvent, BracketEvent, ClearAnnotationsEvent, PageBreakEvent
- New properties on existing events: `placement`, `slide_element_bounds`

No new Neo4j labels needed. All extensions ride existing nodes via JSON properties.

**Backward compatibility**: existing extractions (chapter 5 fixture) won't have these fields. The pipeline should treat absent fields as defaults (no annotations, default placement). Re-ingest from PDF to get full schema.

---

## 12. How to validate after each phase (executable)

### After Phase 1

```bash
cd data_pre_compute_v2
poetry run lecture-pipeline-v2 ingest-book "$PDF_PATH" --subject physics --chapters 5 \
  --force --skip-questions --skip-tts --output ./out --verbose
poetry run lecture-pipeline-v2 query \
  "MATCH (d:Diagram) RETURN d.diagram_id, d.render_data LIMIT 3"
# Verify: render_data JSON has top-level `dictionary` field
```

### After Phase 2

```bash
# Full re-ingest with audio
poetry run lecture-pipeline-v2 ingest-book "$PDF_PATH" --subject physics --chapters 5 \
  --force --skip-questions --output ./out --verbose

# Inspect annotation events
python -c "
import json
d = json.load(open('out/extraction.json'))
events = d['chapters'][0]['chapter_manifest']['events']
ann_events = [e for e in events if e['type'] in ['pin','callout','bracket','highlight','pulse']]
print(f'Annotation events: {len(ann_events)}')
print('Sample:', ann_events[:3])
"

# Launch playback
poetry run python tools/preview_server.py &
cd ../frontend && pnpm dev
# Open http://localhost:5173/#/lecture-preview → play
```

### After Phase 3

```bash
# Same ingest as Phase 2
# Inspect pagination
python -c "
import json
d = json.load(open('out/extraction.json'))
pages = d['chapters'][0]['pages']
print(f'Total pages: {len(pages)}')
for p in pages:
    pct = p['notebook_height_used_px'] / p['notebook_height_total_px'] * 100
    print(f'  Page {p[\"page_index\"]}: {p[\"notebook_block_count\"]} blocks, {pct:.0f}% used, slide={p[\"slide_diagram_id\"]}')
"
# Verify: all blocks have placement.measured=true; pages 60-95% used; no overflow
```

### After Phase 4

```bash
# Full new path
poetry run lecture-pipeline-v2 ingest-book "$PDF_PATH" --subject physics --chapters 5 \
  --force --output ./out --verbose
# Wait ~30-40 min (Phase 4 is the slowest)

# Inspect engagement structure
python -c "
import json
d = json.load(open('out/extraction.json'))
plan = d['chapters'][0]['lecture_plan']
print(f'Chapter arc: {plan[\"chapter_arc\"]}')
print(f'Clusters: {len(plan[\"concept_sequence\"])}')
print(f'Budget: {plan[\"length_budget_minutes\"]} min')
for cp in d['chapters'][0]['concept_plans']:
    beats = cp['beats']
    first_three = [b['beat_type'] for b in beats[:3]]
    print(f'  {cp[\"concept_title\"]}: first 3 beats = {first_three}')
    assert first_three == ['hook', 'big_picture', 'first_principles']
"

# Watch the lecture end-to-end
afplay /tmp/stitched.mp3  # via tools/stitch_chapter_audio.py
# Then full playback in browser; rate against the engagement bar
```

---

## 13. Cutover plan (chapter 5 fixture)

To avoid risk, run old + new in parallel for one chapter before deprecating:

1. **Keep** `out/extraction.json` as the current fixture (Phase 0 baseline).
2. **After Phase 1**: re-ingest chapter 5 → save as `out/extraction_phase1.json`. Compare diagram quality side-by-side in browser. If acceptable → make it the new baseline.
3. **After Phase 2**: re-ingest → `out/extraction_phase2.json`. Confirm annotations appear, slide is alive. Make new baseline.
4. **After Phase 3**: re-ingest → `out/extraction_phase3.json`. Confirm no text overflow, page transitions clean. Make new baseline.
5. **After Phase 4**: re-ingest → `out/extraction_phase4.json`. Confirm hook, beats, length. Compare to old extraction.json (Phase 0) side-by-side — should be obviously more engaging. If not, iterate before committing.
6. **Cutover**: replace `out/extraction.json` with Phase 4 version. Commit. Delete deprecated `script_writer.py` and `enrichment/diagrams.py` (after one week of stability).

---

## 14. Things explicitly OUT of scope for this overhaul

- Real-time agent changes beyond the kernel extraction (we're not touching how live teaching works).
- Notebook panel cross-fading (just page-flip animation; no fancy transitions).
- Doubt branches in the precomputed lecture (the lecture is linear; doubt is real-time only).
- Modify_design_diagram in pre-compute (today's pipeline generates diagrams atomic; incremental builds are for the real-time agent).
- Forced-alignment of TTS for sub-word marker timing (sentence-boundary is enough for v0; future upgrade).
- Multi-language support (English only).
- Cost optimization beyond model choice (model defaults locked in §10).
- Doubt-branch likely-doubts library precomputation (separate feature, Aanya demo specific).

---

## 15. Files NOT touched (read-only across all phases)

For session-start clarity — these exist but we don't modify:

- `backend/src/feynman/livekit/` — entire LiveKit integration
- `backend/src/feynman/session/`, `backend/src/feynman/redis/`, `backend/src/feynman/db/`
- `backend/src/feynman/knowledge/`
- `backend/src/feynman/visuals/` (old visual system; superseded by design_agent)
- `data_pre_compute/` (v1; kept as reference)
- `frontend/src/screens/ClassroomScreen.tsx`, `DevHarness.tsx`, `WaitingScreen.tsx`
- `frontend/src/screens/SplitBoardPrototype.tsx` (prototype, not production path)
- `contracts/` (no schema changes affect this dir; manifest events are internal)
- `docker-compose.yml`, `Makefile`, root `pyproject.toml` (config only)
- Real-time agent's `concept_planner.py:plan_doubt` — keep as-is unless it conflicts with kernel extraction
- `design_agent/backend/agent.py` — read-only; we use it via import (in-process)

---

## 16. Master file inventory

For session-start verification — these are ALL the files the overhaul will touch.

**NEW FILES** (~20 new files)

- `feynman_teaching_kernel/` (5 files: models.py, prompts.py, planner.py, format.py, style_guide.py)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/lecture_plan/` (3 files: models.py, prompts.py, chapter_planner.py)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/beat_narration/` (3 files: prompts.py, writer.py, models.py)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/` (7 files: walker.py, geometry.py, measurement.py, policies/annotations.py, policies/layout.py, policies/notebook.py, composer.py)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/length_enforcer/` (1 file: enforcer.py)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagram_qa.py`
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/script_assembler.py`
- `data_pre_compute_v2/tools/measurement_page.html`

**MODIFIED FILES** (~12 modified files)

- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagrams.py` (Phase 1 prompt; Phase 4 refactor to per-beat)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/validation/render_test.py` (Phase 1 dictionary check)
- `data_pre_compute_v2/src/lecture_pipeline_v2/tts/chunker.py` (Phase 2 marker grammar)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py` (Phase 2 events; Phase 3 placement; Phase 4 plans)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/lecture_script/script_writer.py` (Phase 2 marker extensions; Phase 4 deprecation)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/media/audio_pipeline.py` (composer integration, new event types)
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/ingestion/cypher_generator.py` (new fields)
- `data_pre_compute_v2/src/lecture_pipeline_v2/config.py` (Phase 3 LayoutConfig)
- `data_pre_compute_v2/config.yaml` (Phase 3 layout block)
- `data_pre_compute_v2/src/lecture_pipeline_v2/pipeline.py` (Phase 4 new phases inserted)
- `backend/src/feynman/agent/concept_planner.py` (Phase 4 kernel imports)
- `backend/src/feynman/agent/prompts.py` (Phase 4 kernel imports)
- `frontend/src/screens/LecturePreviewScreen.tsx` (Phase 2 event handlers; Phase 3 placement honoring)
- `frontend/src/engine/whiteboard/split/SplitBoard.tsx` (Phase 2 annotation overlay; Phase 3 absolute positioning)

---

## 17. Session protocol — how to pick up this work in a fresh session

At the start of EVERY new session for this overhaul:

1. Read this doc end-to-end (canonical source of truth).
2. Read the active feature state file at:
   `~/.claude/projects/-Users-yashbansal-proj-feynman/memory/active-features/precompute-lecture-overhaul.md`
   (Current State section tells you what's done and what's next.)
3. Read `MEMORY.md` for context on Yash's preferences, product philosophy, evaluation lens.
4. Read the project `CLAUDE.md` files for module conventions.
5. Confirm which phase the session is targeting.
6. Read the relevant `Phase N` section in this doc.
7. Read the files in §16 that the target phase touches.
8. Begin implementation per the phase's file-level plan.

After EVERY phase completion:

- Update the state file's `Current State` section.
- Log any decisions that came up mid-implementation in the state file's `Design Decisions` section.
- Commit to git with message format: `phase N: <short description>` (e.g., `phase 1: replace diagram prompt with design_agent's dark-mode dictionary prompt`).
- Run the §12 validation for that phase.
- Tell Yash what shipped and what's next.

---

**End of master design doc.**
