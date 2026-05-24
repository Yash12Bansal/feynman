# Design Doc 18 — Attention-Direction Redesign: Spotlight + Sequential Reveal

**Status**: Design proposed, awaiting Yash review.
**Date**: 2026-05-23
**Author**: co-founder pair (Yash + Claude)
**Supersedes (partial)**: doc 17 §6 (annotation system as currently spec'd), the unused `render_data.animations` placeholder, the `manim/3b1b` track in plan `jolly-knitting-sprout.md`.

---

## 1. The problem (one paragraph)

Once the board fills up with annotations during a lecture, the student doesn't know what to look at. The teaching agent is talking, the board has 4 PINs + a CALLOUT + a BRACKET + recent HIGHLIGHTs fading, and there's **no visual signal** for "this is the thing being discussed RIGHT NOW." That's a broken teaching experience — the entire point of pointing-while-teaching is to guide attention. Today the system POINTS A LOT (5 annotation types, 4 policies, sophisticated spatial dedup), but it never **DIRECTS** attention to a single focal point.

A real teacher uses ONE pointer. They tap one part of the diagram, talk about it, then move the tap. The student's eyes follow. Our system gives the LLM 5 ways to annotate and accumulates the results until the slide is a cluttered mess. The fix is to invert the design: **give the LLM ONE primitive — "focus on this element right now" — and let the renderer turn that into spotlight, sequential reveal, optional label, and de-emphasis of everything else.**

---

## 2. What's actually broken — code-grounded

Confirmed by exploration (see `Section 7 — System inventory` for line-level references):

### 2.1. Too many annotation primitives with overlapping semantics

The LLM is offered **5 marker types** for "point at the board":

| Marker    | Persistent?        | Visual                         | Frontend component          | Spatial fallback          |
| --------- | ------------------ | ------------------------------ | --------------------------- | ------------------------- |
| PIN       | yes                | text label + connector line    | `<PinLabel>` (84 LOC)       | 8 positions               |
| CALLOUT   | yes                | speech bubble + tail           | `<Callout>` (98 LOC)        | 6 directions              |
| BRACKET   | yes                | curly brace spanning two roles | `<Bracket>` (82 LOC)        | none (drops on collision) |
| HIGHLIGHT | transient (1500ms) | glow overlay                   | `<HighlightPulse>` (36 LOC) | none                      |
| PULSE     | transient (800ms)  | scale pulse                    | `<HighlightPulse>` (36 LOC) | none                      |

Each has its own fragment dataclass (5 in `tts/chunker.py`), its own handler in the walker (4 distinct `_handle_*` methods, 154 LOC combined), its own policy gates (cooldown, budget, dedup), its own frontend component (4 React components, ~300 LOC combined). The semantic overlap is huge: **PIN ≈ CALLOUT ≈ HIGHLIGHT-with-label**, and **PULSE ≈ HIGHLIGHT-with-shorter-duration**.

The LLM has to choose among them with essentially zero guidance:

> "Persistent (drawn once, stay until next diagram or CLEAR_ANNOTATIONS): PIN / CALLOUT / BRACKET. Transient (fade after duration_ms): HIGHLIGHT / PULSE." — `beat_narration/prompts.py:85-106`

There's **no rule** for "when to PIN vs. CALLOUT vs. HIGHLIGHT". It's pure LLM judgment. Result: the LLM picks whichever it feels like, often multiple per beat.

### 2.2. Persistent annotations accumulate indefinitely

PIN/CALLOUT/BRACKET are explicitly persistent: "drawn once, stay until next diagram or CLEAR_ANNOTATIONS" — `beat_narration/prompts.py:90`. The walker enforces `MAX_PERSISTENT_PER_DIAGRAM = 4` (`policies/annotations.py:18`). So the slide can carry **4 simultaneous persistent annotations** plus whatever transients are alive in the 30-second window.

When the LLM emits a 6th PIN, the walker silently downgrades it to PULSE (`walker.py:601, _downgrade_to_pulse:784-807`). This is a band-aid: the underlying problem is the LLM shouldn't be emitting 6 PINs in the first place. The downgrade logic exists because the LLM doesn't know to stop.

**The "board full of annotations, student lost" failure mode is BUILT INTO THE DESIGN.** The system allows 4 persistent + 3-per-30s transient annotations, all visible at once, with no concept of "current focus."

### 2.3. No "active element" state on the frontend

`SlideAnnotationLayer.tsx:257-288` renders all annotations as **independent sibling SVG overlays** on top of the diagram. There's no "which one is current" state. Z-index is implicit via SVG render order (newest on top), and there's no opacity/dimming logic to de-emphasize stale annotations. Every annotation looks equally important until it's cleared.

> "Annotations are anchored to the current diagram" — comment at line 28
> "No explicit hide/clear logic; occupancy is backend-only" — explorer's words

Annotations are static decoration once placed. They aren't "the thing the speaker is talking about RIGHT NOW" — they're "things the speaker has talked about at some point."

### 2.4. Sophisticated spatial dedup for a problem that shouldn't exist

`geometry.py` has 424 LOC of label-rect estimation, 8-position PIN fallback, 6-direction CALLOUT fallback, occupancy tracking, overlap checks. This is engineering effort spent making a crowded slide LESS crowded. If the design said "max 1 annotation visible at a time," this code mostly disappears.

The complexity is real:

- `resolve_pin_position()` tries 8 positions, complexity O(8 × occupancy.len)
- `resolve_callout_direction()` tries 6 directions, complexity O(6 × occupancy.len)
- BRACKET has no fallback because spanning two elements is too constrained — it just drops on collision

**This is an entire problem space we shouldn't be in.**

### 2.5. The `render_data.animations` field exists but is never used

Frontend types declare it (`frontend/src/diagram-lab/types.ts:126`), backend never populates it, no component reads it. It's dead code. Multiple system audits mention it as "future GSAP animations." It's been there long enough to be vestigial.

### 2.6. Walker policies enforce constraints the LLM should be respecting natively

Four policy constants do crowd control:

```python
COOLDOWN_SAME_ROLE_MS = 6_000              # don't re-annotate same role within 6s
MAX_TRANSIENTS_PER_DIAGRAM_30S = 3         # max 3 HIGHLIGHTs/PULSEs per 30s
TRANSIENT_WINDOW_MS = 30_000               # rolling window
MAX_PERSISTENT_PER_DIAGRAM = 4             # max 4 PINs/CALLOUTs/BRACKETs per diagram
```

Plus `_downgrade_to_pulse` for duplicate-PIN cleanup, `_evict_old_transients` for window rotation, `_allow_transient` for cooldown + budget gating. Defensive engineering against an LLM that over-emits.

The cleaner fix: **constrain the LLM's primitive count down to 1, and the over-emission problem disappears.** Walker policies become trivial or unnecessary.

### 2.7. Concept-style beats sometimes ship without diagrams

From the chapter-47 ingest:

- §47.1 (Principle of Relativity) had **0 diagrams** across 9 beats — the planner picked `draw_scene` for the hook and `modify_design_diagram` (with no prior diagram) for the explain. Result: 3 minutes of audio with a blank "loading" slide.
- §47.4 (Dynamics at Large Velocity) had **0 diagrams** in run 2 (had one in run 1 — LLM nondeterminism).

Per Yash's calibration:

> "concept clarity without text and visuals is bad. it is fine if agent is explaining equations, questions, derivations but concept clarity without text and visuals is bad"

The beat-type taxonomy splits naturally:

| Beat type          | Concept-style (must have diagram) | Mechanic-style (text-only OK) |
| ------------------ | --------------------------------- | ----------------------------- |
| `hook`             | ✓                                 |                               |
| `big_picture`      | ✓                                 |                               |
| `first_principles` | ✓                                 |                               |
| `bridge`           | ✓                                 |                               |
| `visual_build`     | ✓                                 |                               |
| `misconception`    | ✓                                 |                               |
| `explain`          | ✓ (default)                       | (acceptable if pure mechanic) |
| `derive`           |                                   | ✓                             |
| `example`          |                                   | ✓                             |
| `ask`              |                                   | ✓                             |
| `summarize`        |                                   | ✓                             |
| `transition`       |                                   | ✓                             |

The kernel's `ConceptPlanner` currently picks `visual.tool` per beat with no constraint that concept-style beats produce a renderable diagram. Adding a hard rule fixes the §47.1 dead-slide gap structurally.

---

## 3. What we're cutting

**Markers** (the LLM-facing surface):

- DEPRECATE: `PIN`, `CALLOUT`, `BRACKET`, `HIGHLIGHT`, `PULSE`
- Tolerate them in the chunker for one cycle (back-compat for any in-flight content), then remove.
- INTRODUCE: `FOCUS`, `UNFOCUS` (2 markers, see §4).
- KEEP: `CLEAR_ANNOTATIONS` (renamed to `RESET_FOCUS` for clarity), `SHOW_DIAGRAM`, all WRITE\_\* notebook markers, `PAUSE`, `SECTION`, `NEW_PAGE`, `STRIKE`.

**Walker policy stack**:

- DELETE: `COOLDOWN_SAME_ROLE_MS`, `MAX_TRANSIENTS_PER_DIAGRAM_30S`, `TRANSIENT_WINDOW_MS`, `MAX_PERSISTENT_PER_DIAGRAM` constants and their gating logic.
- DELETE: `_downgrade_to_pulse`, `_evict_old_transients`, `_allow_transient`.
- DELETE: `_handle_pin`, `_handle_callout`, `_handle_bracket`, `_handle_transient` (~154 LOC).
- ADD: `_handle_focus`, `_handle_unfocus` (~40 LOC combined estimated).

**Frontend components**:

- DELETE: `<PinLabel>`, `<Callout>`, `<Bracket>`, `<HighlightPulse>` (~300 LOC combined).
- ADD: `<Spotlight>` (single component, ~100 LOC estimated).
- UPDATE: `<SlideAnnotationLayer>` — render at most one `<Spotlight>` at a time + dim non-focused elements on the SVG diagram itself.

**Geometry helpers**:

- DELETE: `resolve_pin_position`, `resolve_callout_direction`, `pin_label_rect`, `callout_bubble_rect`, `bracket_label_rect`, the 8-position + 6-direction fallback tables (~300 LOC of geometry.py).
- KEEP: the basic `Rect` type and overlap check (used by LayoutPlanner separately).

**Schema**:

- DELETE: unused `render_data.animations` field declaration.

**Net code removed**: ~700 LOC across backend + frontend.
**Net code added**: ~200 LOC (spotlight component + 2 new handlers + LLM prompt update).
**Net delta**: **−500 LOC** with strictly better behavior.

---

## 4. The chosen approach — Spotlight + Sequential Reveal + Optional Inline Label

### 4.1. Mental model

A real teacher pointing at a board does three things:

1. **Their pointer is on ONE thing at a time.** When it moves, attention moves.
2. **They reveal complexity gradually.** A diagram builds up element-by-element matched to what they're saying. Students aren't staring at a fully-drawn 30-element diagram while the teacher is talking about element 3.
3. **Sometimes they write a short word next to what they're pointing at.** Not a paragraph. Not five labels. ONE word, when it helps anchor.

Our redesign maps these directly:

| Teacher behavior                 | System primitive                                                                                               |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Point at element X               | `<<FOCUS:role>>` — spotlight on role, dim everything else                                                      |
| Move pointer to element Y        | next `<<FOCUS:role>>` automatically replaces previous                                                          |
| Stop pointing                    | `<<UNFOCUS>>` (rarely needed; next SHOW_DIAGRAM or FOCUS implicitly releases)                                  |
| Reveal element as it's mentioned | Implicit: an element not yet FOCUSed appears at low opacity. First FOCUS on it animates it in fully.           |
| Optional short label             | `<<FOCUS:role                                                                                                  | text=2-3 words>>` — text passes through as a tiny inline label next to the focused element. Replaces previous focus label on next FOCUS. |
| Re-mention an element            | `<<FOCUS:role>>` again — brief PULSE-like attention flash on re-focus, even if it's already the active element |
| Reset everything                 | `<<RESET_FOCUS>>` — wipe spotlight state, return all elements to baseline opacity                              |

That's the whole API. **One concept**: at any moment, there is either zero or one focused element. Everything else is de-emphasized.

### 4.2. The visual treatment

**Three visual states** per diagram element:

| State                                        | Opacity                                                                                   | Stroke weight              | Color       | Behavior                                                      |
| -------------------------------------------- | ----------------------------------------------------------------------------------------- | -------------------------- | ----------- | ------------------------------------------------------------- |
| **Pre-reveal** (not yet focused)             | 0.0 (hidden) for "build-up" diagrams, OR 0.3 (ghosted) for "overview" diagrams — see §4.3 | normal                     | desaturated | Invisible/ghosted until first FOCUS                           |
| **Active** (currently focused)               | 1.0                                                                                       | normal or slightly thicker | full color  | Sharp, attention-grabbing. Optional small label nearby.       |
| **Dimmed** (previously focused, not current) | 0.4                                                                                       | normal                     | full color  | Visible but de-emphasized. Student knows it's been discussed. |

**Spotlight effect** is achieved by manipulating opacity on the SVG diagram's elements directly via their `id` (which the design_agent already assigns and the dictionary already knows). Not a separate overlay — direct DOM property mutation. **No accumulating overlay components.**

**Inline label** (optional `|text=...` on FOCUS) renders as a small text node attached to the focused element. Replaces any previous label on next FOCUS. At most ONE label visible at any time.

### 4.3. Two diagram presentation modes

The DiagramSpec gets a new `presentation_mode` field:

- **`build_up`** (default for concept-style beats like `first_principles`, `visual_build`): elements start invisible (opacity 0). First FOCUS reveals each. Mimics a teacher drawing as they talk.
- **`overview`** (default for `explain`, `derive`, `example`): all elements visible from the start at slightly reduced opacity. FOCUS still highlights the active one. Mimics a teacher pointing at a pre-drawn reference.

The LLM (or the DiagramSpec generator) picks the mode based on beat type. Build-up forces sequential reveal, which naturally limits clutter and matches narration tempo. Overview is for diagrams that need to show structure first.

### 4.4. Why this is the right answer

**Alternative approaches I considered**:

| Approach                                                                    | Pro                                                        | Con                                                                                                     | Verdict                                                                    |
| --------------------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Keep PIN/CALLOUT/BRACKET/HIGHLIGHT/PULSE, just add ATTENTION priority field | Backwards compatible                                       | Doesn't solve the LLM-over-emits-anyway problem; complexity stays                                       | NO                                                                         |
| Spotlight only (no inline label)                                            | Simplest possible                                          | Loses the "label next to the focus" affordance that's pedagogically useful when introducing terminology | NO                                                                         |
| Spotlight + multiple persistent labels (1 per element ever focused)         | Rich annotation memory                                     | Recreates the "board fills up" problem                                                                  | NO                                                                         |
| Spotlight + single inline label (CHOSEN)                                    | One thing to look at; one label at most; sequential reveal | Loses the "see all annotations at once" mode                                                            | YES — that mode wasn't actually used pedagogically; it was just complexity |
| Cursor-only (animated dot that hovers over active element)                  | Mimics laser pointer literally                             | No persistent context for student who looks away briefly                                                | NO — too transient                                                         |
| Build-up animation library (3b1b-style)                                     | Beautiful animations                                       | Doesn't address attention direction; orthogonal concern; adds complexity                                | DEFER until after spotlight ships                                          |

**Spotlight + sequential reveal + single inline label** wins because:

1. **One thing for the LLM to control**: "what's the focus right now?" Replaces 5 marker decisions.
2. **One thing for the student's eye to track**: "where's the bright element?" Replaces 6+ annotations to triage.
3. **Self-limiting clutter**: there's no annotation that accumulates. Even after 5 minutes of talking, the slide shows only the active element prominently.
4. **Naturally matches teacher behavior**: this IS how human teachers point.
5. **Strictly simpler than today**: −500 LOC, fewer policies, fewer components, fewer LLM decisions.

### 4.5. What about the "I want to see everything that's been discussed" use case?

It exists pedagogically — sometimes you want a recap view. But that's a TOPIC-end or BEAT-end concept, not a mid-beat concept. We can address it later with an explicit `<<RECAP>>` marker that brings all previously-focused elements back to full opacity briefly. Phase B work.

### 4.6. What about decorative annotations (e.g., a curly brace labeling "the legs of the triangle")?

The BRACKET marker today serves this. In the new model, BRACKET-equivalent functionality is built INTO THE DIAGRAM itself: the design_agent generates the bracket as an SVG element with a role like `legs_bracket`, dictionary-addressable. FOCUS on `legs_bracket` makes it appear (in build-up mode) or highlights it (in overview mode). **This pushes structural annotations from overlay-time to author-time**, where they belong. A pre-baked bracket is always positioned correctly relative to the elements it spans, with no spatial-dedup gymnastics.

---

## 5. Concept-beats mandatory-diagram rule

Per Yash's calibration in §2.7:

### 5.1. Rule

For these beat types, the kernel's `ConceptPlanner` MUST emit `visual.tool == "draw_design_diagram"` (or `"modify_design_diagram"` if a prior diagram exists in the same concept_plan):

- `hook`
- `big_picture`
- `first_principles`
- `bridge`
- `visual_build`
- `misconception`
- `explain` (default; overridable to text-only IF the explain is pure mechanic with no visual concept)

For these beat types, text-only tools are acceptable (and often preferred):

- `derive` — typically `write_equation` + `write_step`
- `example` — typically `write_step` + `write_answer`
- `ask` — typically `write_text` (a question)
- `summarize` — typically `write_key_point`
- `transition` — typically `write_text` or just narration

### 5.2. Enforcement

**Soft enforcement at the kernel prompt** (`PLANNING_SYSTEM_PROMPT` updated): "For concept-style beats (hook, big_picture, first_principles, bridge, visual_build, misconception), `visual.tool` MUST be `draw_design_diagram` or `modify_design_diagram` (when a prior diagram exists in this concept_plan). Free-form tools like `draw_scene` or `draw_diagram` are NOT supported by the precompute pipeline and result in dead slide-time."

**Hard validation at the pipeline boundary** (post-planning, pre-diagram-generation): walk every chapter's `concept_plans`; for each concept-style beat with `visual.tool` outside `{draw_design_diagram, modify_design_diagram}`, **rewrite the tool to `draw_design_diagram`** (the brief becomes a default `"Draw a diagram appropriate to: {speech_guidance}"`). Log a warning. Pipeline never silently produces a dead-slide concept beat.

This is the same `allowed_visual_tools` mechanism from track A1 of the prior plan, plus a beat-type-aware default fallback when the LLM picks a forbidden tool.

### 5.3. Verification post-fix

After re-ingesting chapter 47:

- `out/extraction_phase4e_vol2_ch47.json` chapter manifest → count `show_diagram` events per topic. Expect ≥1 per topic for §47.1, §47.2, §47.3, §47.5, §47.6, §47.7. §47.4 too.
- §47.1's manifest should now have a `show_diagram` event somewhere in its block (currently 0).
- Frontend playback: §47.1 slide should never go blank ("loading" forever) again.

---

## 6. Step-by-step implementation plan

Six steps. Each ends with a verifiable bar. Total estimated effort: **4-5 days of focused work** + 2 chapter-47 re-ingest cycles (~$6-8 in API spend).

### Step 1 — Backend: chunker + walker simplification

**Files (modify)**:

- `data_pre_compute_v2/src/lecture_pipeline_v2/tts/chunker.py`:
  - Add `FOCUS`, `UNFOCUS`, `RESET_FOCUS` to `_MARKER_RE` (regex line 52-57).
  - Add `FocusFragment` (`role`, `text?`, `diagram_id`) and `UnfocusFragment` (`diagram_id`) dataclasses.
  - Add `ResetFocusFragment` (rename of `ClearAnnotationsFragment`; keep both names as aliases for one cycle for back-compat).
  - Keep `PinFragment`, `CalloutFragment`, `BracketFragment`, `HighlightFragment`, `PulseFragment` parsing for back-compat. Add deprecation log per parse.
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/walker.py`:
  - Add `_handle_focus(frag)` and `_handle_unfocus(frag)` handlers. ~20 LOC each.
  - DELETE: `_handle_pin`, `_handle_callout`, `_handle_bracket`, `_handle_transient`, `_downgrade_to_pulse`, `_evict_old_transients`, `_allow_transient`. Total deletion: ~200 LOC.
  - Update fragment dispatch (line 264-266 region) — old 5 handlers collapse to 2.
  - Update `_active` state struct: drop `persistent: dict`, drop `transient_history: list`, add `focus_role: str | None`.
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/policies/annotations.py`:
  - DELETE the whole file (constants are gone). Update `policies/__init__.py` accordingly.
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/manifest_composer/geometry.py`:
  - DELETE `resolve_pin_position`, `resolve_callout_direction`, `pin_label_rect`, `callout_bubble_rect`, `bracket_label_rect`, `PIN_FALLBACK_POSITIONS`, `CALLOUT_FALLBACK_DIRECTIONS`. ~300 LOC.
  - KEEP `Rect`, basic overlap helper (used by LayoutPlanner).
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py`:
  - Add `FocusEvent`, `UnfocusEvent` to `ManifestEvent` discriminated union.
  - Keep `PinEvent`, `CalloutEvent`, `BracketEvent`, `HighlightEvent`, `PulseEvent` for back-compat read-only (writer never emits new ones).
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/media/audio_pipeline.py`:
  - In `_render_fragments`: add FocusFragment → FocusEvent mapping. Keep old fragment-to-event mappings as no-op fallthrough.

**Tests (update)**:

- `tests/test_manifest_composer.py` (15 tests today, ~10 fail under this change because they assert on PIN/CALLOUT/etc. behavior).
  - Rewrite as `test_manifest_composer_focus.py`:
    - `test_focus_emits_event`
    - `test_focus_replaces_previous_focus`
    - `test_unfocus_clears_focus`
    - `test_reset_focus_clears_all_state`
    - `test_focus_unknown_role_drops`
    - `test_focus_no_active_diagram_drops`
    - `test_legacy_pin_marker_parses_but_emits_no_event` (back-compat)
- `tests/test_phase2_integration.py` — adapt the fixture script to use FOCUS instead of PIN/CALLOUT/etc.

**Bar**:

- v2 test suite still green
- Walker LOC down from ~849 to ~650 (delete 200, add 40)
- Chunker parses FOCUS markers correctly
- Composer report shape unchanged (event counts shift)

### Step 2 — Backend: LLM prompt simplification

**Files (modify)**:

- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/beat_narration/prompts.py`:
  - REPLACE the "## Diagram annotations" section (lines 85-106) with a much shorter "## Pointing at the diagram" section that documents ONLY `FOCUS`, `UNFOCUS`, `RESET_FOCUS`. Concrete examples included.
  - Update Rule 4 (line 126-127) — sentence-boundary placement still applies but only for FOCUS.
  - Add explicit emission guidance: "Emit `<<FOCUS:role>>` at the start of the sentence in which you introduce or discuss `role`. Do not emit more than one FOCUS per sentence. Do not re-FOCUS the same role twice in a row."
- `feynman_teaching_kernel/src/feynman_teaching_kernel/prompts.py` (`PLANNING_SYSTEM_PROMPT`):
  - Add the §5.1 mandatory-diagram rule: concept-style beats MUST use `draw_design_diagram` or `modify_design_diagram`; list the beat types explicitly.
  - Add the §5.2 enforcement note: "Free-form tools like `draw_scene`/`draw_diagram` are not supported by precompute and result in dead slide-time."

**Files (new)**:

- None — prompt edits only.

**Bar**:

- Kernel tests still 8/8 green (no model/schema changes, just prompt text)
- Backend tests still 1175/19 baseline

### Step 3 — Backend: pipeline enforcement for concept beats

**Files (modify)**:

- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/lecture_plan/concept_planner.py`:
  - Pass `allowed_visual_tools=["draw_design_diagram", "modify_design_diagram", "write_section", "write_equation", "write_step", "write_key_point", "write_text", "write_answer"]` to the kernel call.
  - After kernel returns the `ConceptTeachingPlan`, walk the `beats[]`. For any beat with `beat_type in {hook, big_picture, first_principles, bridge, visual_build, misconception}` AND `visual.tool not in {draw_design_diagram, modify_design_diagram}`:
    - Rewrite `visual.tool = "draw_design_diagram"`.
    - Set `visual.brief = f"Concept diagram for: {beat.speech_guidance}"` if brief is empty.
    - Log a warning: `"concept_beat_tool_fallback: {beat_type} had {original_tool}, rewrote to draw_design_diagram"`.
- `feynman_teaching_kernel/src/feynman_teaching_kernel/planner.py`:
  - Add `allowed_visual_tools: list[str] | None = None` kwarg to `plan_concept`. When non-None, inject the list into the system prompt as constraint guidance. When None (live agent default), behavior unchanged.

**Tests**:

- `feynman_teaching_kernel/tests/test_models.py`:
  - `test_plan_concept_respects_allowed_visual_tools` (mock LLM emits a forbidden tool; confirm caller's expected behavior — likely a "still emit but warn" rather than reject, since kernel can't easily reject after-the-fact validation)
- `data_pre_compute_v2/tests/test_concept_planner.py`:
  - `test_concept_beats_rewritten_to_draw_design_diagram_when_planner_chose_draw_scene`
  - `test_mechanic_beats_left_alone`

**Bar**:

- Concept-style beats always have `visual.tool in {draw_design_diagram, modify_design_diagram}` after this stage
- §47.1 ingest produces ≥1 show_diagram event (canonical bar for "no more dead slides")

### Step 4 — Backend: DiagramSpec adds `presentation_mode`

**Files (modify)**:

- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py`:
  - Add `presentation_mode: Literal["build_up", "overview"] = "overview"` to the `Diagram.render_data` (or wherever DiagramSpec is modeled).
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagram_spec_generator.py` (Phase 4c per-beat):
  - In the prompt, instruct the LLM to set `presentation_mode = "build_up"` when the linked beat_type is in `{hook, big_picture, first_principles, visual_build, misconception}`, and `"overview"` otherwise.
- `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagrams.py` (Phase 1 per-topic):
  - Default `presentation_mode = "overview"` (per-topic diagrams aren't tied to a single beat).

**Bar**:

- Diagram JSON includes `presentation_mode`
- Build-up mode propagates to `show_diagram` event in manifest (frontend reads it)

### Step 5 — Frontend: spotlight rendering

**Files (delete)**:

- `frontend/src/engine/whiteboard/split/SlideAnnotationLayer.tsx` — DELETE the 4 sub-components (`PinLabel`, `Callout`, `Bracket`, `HighlightPulse`). Replace with a single `<Spotlight>` component (~100 LOC).

**Files (new)**:

- `frontend/src/engine/whiteboard/split/Spotlight.tsx` (~100 LOC):
  - Props: `focusedRole: string | null`, `inlineLabelText: string | null`, `dictionary`, `viewBox`, `stageRef`.
  - Implementation: resolves `focusedRole` → SVG element via dictionary + live DOM lookup (reuse existing `useResolvedBounds()`). Renders ONE small text label near the element if `inlineLabelText` provided. No persistent overlay accumulation.
  - Subtle visual: small caret + 2-3 word label, sized to match Phase 3 typography.

**Files (modify)**:

- `frontend/src/engine/whiteboard/split/SplitBoard.tsx` (or wherever the diagram SVG is rendered):
  - Maintain `focusedRole` state at the SplitBoard level. Updates on FocusEvent.
  - When the diagram renders, apply opacity based on element state:
    - `presentation_mode === "build_up"`: pre-reveal opacity = 0; revealed (i.e., has been focused at least once) opacity = 0.4; currently-focused opacity = 1.0.
    - `presentation_mode === "overview"`: all elements opacity 0.5 (baseline) → 1.0 when focused → 0.4 (dimmed) after focus moves on.
  - Use CSS transitions on `opacity` (200-300ms ease) — no new animation engine needed.
- `frontend/src/screens/LecturePreviewScreen.tsx`:
  - Handle new event types: `focus`, `unfocus`, `reset_focus`. Each updates the SplitBoard's `focusedRole` + `revealedRoles` state.
  - Drop the `pin`/`callout`/`bracket`/`highlight`/`pulse` handlers (or treat as no-op for back-compat).
- `frontend/src/screens/LecturePreviewScreen.tsx` empty-slide state:
  - When no SHOW_DIAGRAM has fired for the current topic, render section title + soft "· · ·" placeholder (matches design doc 17 Q16). NOT "loading".

**Tests** (if Vitest exists):

- Component test: `Spotlight.test.tsx` — renders only when focusedRole is non-null; renders label only when inlineLabelText is non-null.
- Component test: `SplitBoard.test.tsx` — opacity changes correctly across focus state transitions.

**Bar**:

- TypeScript check clean
- Manual test: load `:5174/#/lecture-preview` with the existing chapter-47 extraction → confirm rendering works (legacy PIN/CALLOUT events become no-ops; should not crash)

### Step 6 — Validation: re-ingest chapter 47

**Procedure**:

```bash
cd /Users/yashbansal/proj/feynman/data_pre_compute_v2
set -a; source /Users/yashbansal/proj/feynman/.env; set +a
poetry run python -m lecture_pipeline_v2.cli ingest-book \
  "/Users/yashbansal/Downloads/hc verma v2.pdf" \
  --subject physics --chapter "relativity" \
  --force --skip-questions --skip-prereqs \
  --output out_phase4e_vol2_ch47_attention/ --verbose
mv out_phase4e_vol2_ch47_attention/extraction.json out/extraction_phase4e_vol2_ch47_attention.json
```

**Bar**:

- `manifest.events` distribution: `focus` count >0, `pin/callout/bracket/highlight/pulse` counts all 0
- `§47.1` block has ≥1 SHOW_DIAGRAM event (concept-beat enforcement worked)
- Total Anthropic spend ≤ $4
- Yash watches end-to-end and confirms:
  - [ ] Slide never shows >1 element prominently at a time
  - [ ] §47.1 has a diagram, focus moves through its elements as narration progresses
  - [ ] Twin Paradox + Light Clock animations feel coherent (build-up mode)
  - [ ] Energy-Momentum Triangle uses overview mode and focus highlights each leg sequentially
  - [ ] At no point does the slide become a cluttered overlay-soup

---

## 7. System inventory (line references for implementers)

| Component                      | File                                | Key lines |
| ------------------------------ | ----------------------------------- | --------- |
| Marker regex                   | `tts/chunker.py`                    | 52-57     |
| Annotation fragments           | `tts/chunker.py`                    | 177-231   |
| Walker dispatch                | `manifest_composer/walker.py`       | 264-266   |
| `_handle_pin`                  | `manifest_composer/walker.py`       | 588-634   |
| `_handle_callout`              | `manifest_composer/walker.py`       | 636-676   |
| `_handle_bracket`              | `manifest_composer/walker.py`       | 678-725   |
| `_handle_transient`            | `manifest_composer/walker.py`       | 731-748   |
| `_downgrade_to_pulse`          | `manifest_composer/walker.py`       | 784-807   |
| `_allow_transient`             | `manifest_composer/walker.py`       | 750-765   |
| Policy constants               | `policies/annotations.py`           | 14-25     |
| `resolve_pin_position`         | `manifest_composer/geometry.py`     | 362-389   |
| `resolve_callout_direction`    | `manifest_composer/geometry.py`     | 404-424   |
| LLM annotation guidance        | `beat_narration/prompts.py`         | 85-106    |
| Annotation rules               | `beat_narration/prompts.py`         | 122-127   |
| Active-diagram resolver        | `beat_narration/writer.py`          | 380-398   |
| Role vocab extraction          | `beat_narration/prompts.py`         | 147-158   |
| Frontend annotation switch     | `SlideAnnotationLayer.tsx`          | 297-308   |
| `<PinLabel>`                   | `SlideAnnotationLayer.tsx`          | 360-444   |
| `<Callout>`                    | `SlideAnnotationLayer.tsx`          | 448-546   |
| `<Bracket>`                    | `SlideAnnotationLayer.tsx`          | 573-655   |
| `<HighlightPulse>`             | `SlideAnnotationLayer.tsx`          | 659-695   |
| `<SlideAnnotationLayer>` shell | `SlideAnnotationLayer.tsx`          | 257-288   |
| Unused `animations` field      | `frontend/src/diagram-lab/types.ts` | 126       |

---

## 8. Risks + non-goals

### 8.1. Risks

| Risk                                                                                                   | Mitigation                                                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Spotlight feels less "rich" than current multi-annotation system                                       | Single visual primitive done well > five primitives all mediocre. Watch the re-ingest playback before declaring. If too sparse, add the optional inline label as a stronger default.                                                                          |
| Build-up mode hides too much, students get lost                                                        | Default to `overview` mode; opt-in `build_up` only for genuinely concept-introduction beats (hook, first_principles).                                                                                                                                         |
| Existing PIN/CALLOUT/BRACKET emissions in any in-flight content break                                  | One-cycle back-compat: chunker parses old markers + walker silently drops them (no event emitted). After one verified cycle, remove parsers entirely.                                                                                                         |
| Kernel changes leak into live agent tool selection                                                     | `allowed_visual_tools` defaults to None (= no constraint), so live agent behavior is unchanged unless caller explicitly passes the constraint. Backend test suite is the gate (1175/19 baseline).                                                             |
| Concept-beat fallback rewrite changes the meaning of a beat                                            | The fallback is just at the tool level — `speech_guidance` is unchanged, so the LLM's narration of the beat stays the same. The diagram is freshly generated by Phase 4c per-beat generator using the updated tool.                                           |
| `presentation_mode` field breaks existing diagram consumers                                            | Default value (`"overview"`) means old consumers can ignore the field; new field is opt-in for frontend logic.                                                                                                                                                |
| LLM under-emits FOCUS (no annotations at all)                                                          | The prompt explicitly requests "emit FOCUS at the start of each sentence that introduces or discusses a role." DiagramQA prompt should add: "diagrams without sequential FOCUS coverage on most key elements are weak." Re-ingest will surface this; iterate. |
| Frontend spotlight transitions feel janky                                                              | CSS opacity transitions are dirt-simple and look fine. If they don't, upgrade to `framer-motion` for opacity tweens. Low risk.                                                                                                                                |
| The 5 deleted annotation event types still exist in the manifest schema and break downstream consumers | Pydantic discriminated union keeps old types as readable (back-compat); writer just stops emitting them. Old manifests load cleanly.                                                                                                                          |

### 8.2. What this design does NOT do

- **Does not introduce manim or any new animation framework.** Spotlight transitions are CSS opacity changes on existing SVG elements. No new dependencies.
- **Does not change the chunker's note-taking markers** (`WRITE_EQUATION`, `WRITE_STEP`, `WRITE_KEY`, etc.) — those work fine and aren't part of the attention-direction problem.
- **Does not change Phase 3 layout intelligence** — LayoutPlanner, MeasurementService, page breaks stay as-is. Spotlight is orthogonal to pagination.
- **Does not address the diagram quality issue separately** (e.g., the text-stuffed diary diagram). That's a DiagramSpec prompt issue, handled in track A2/A3 of the broader plan, not this doc.
- **Does not address per-stage LLM routing.** That's track B of the broader plan, orthogonal to this doc.
- **Does not change the live (real-time) agent's annotation system.** The live agent has its own action-tag dispatcher; this doc is precompute-only. Live agent can adopt the same model later if it lands well in precompute. The kernel `allowed_visual_tools` kwarg defaults to None for live, so live behavior unchanged.
- **Does not promise a recap/timeline view of all previously-focused elements.** That's a future addition (`<<RECAP>>` marker) once spotlight ships and stabilizes.
- **Does not delete the `render_data.animations` field on its own** — it's unused so removal is safe but cosmetic. Bundle with general schema cleanup later if desired.

---

## 9. Cost summary

| Bucket                   | Cost                  | Notes                                                                                                             |
| ------------------------ | --------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Engineering              | ~4-5 days focused     | Steps 1-5 above. Backend ~2 days, frontend ~1.5 days, tests ~1 day, prompt iteration ~0.5 day                     |
| Re-ingest validation     | ~$6-8 Anthropic spend | 2 chapter-47 re-ingests during iteration (~$3-4 each)                                                             |
| Risk to existing systems | Low                   | Back-compat parsing for old markers; live agent isolated via kwarg default; backend tests gate kernel changes     |
| Visible payoff           | High                  | The "board full, student lost" problem disappears structurally — there's no way for the slide to become cluttered |
| LOC delta                | **−500 LOC**          | ~700 deleted, ~200 added                                                                                          |

---

## 10. Decision points for Yash

Before implementation starts, please confirm:

1. **Approve the spotlight + sequential reveal + single inline label approach?** (vs. spotlight-only, vs. keeping old system with new "priority" field — see §4.4 alternatives)
2. **Default presentation mode** — `overview` for everything (less risk of hidden content) or `build_up` for concept-style beats (more pedagogically natural but riskier)?
3. **Back-compat retention period** — one cycle (1 week, fast removal) or three cycles (1 month, conservative)?
4. **Concept-beat list** — does §5.1's beat-type split match your mental model? Particularly: should `explain` default-have-diagram or default-text-only?
5. **Live agent impact** — confirm we're scoping kernel changes to NOT affect live agent (kwarg defaults preserve behavior), OR do you want the spotlight model carried into live too (out-of-scope for this doc but worth flagging)?

Once approved, implementation proceeds per §6 step-by-step. Each step's bar must pass before the next starts. Yash watches the chapter-47 re-ingest playback before declaring done.

---
