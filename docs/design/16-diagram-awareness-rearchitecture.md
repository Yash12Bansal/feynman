# Diagram-Awareness Re-Architecture: From Patch to Production Teaching Agent

> **Status**: Approved plan (v2 — added Three-Factor Framework + Phase 5 vision perception loop). Sequenced for impact-order execution (~8-10 weeks for Phases 0-5a; Phase 5b is a post-traction latency upgrade).
> **Scope**: IGCSE STEM core — Mathematics 0580, Physics 0625, Chemistry 0620. Biology deferred (different diagram primitives).
> **Supersedes**: tactical fix described in commit `f134180` (which remains shipped as a hardening floor).
> **Related**: `docs/design/14-agent-diagram-awareness.md` (original dictionary design — v0 of this surface); `docs/design/06-board-intelligence-and-latency.md` (broader board-intelligence problem statement).

## Context

The previous tactical patch made annotation tools fail loud when the diagram dictionary didn't resolve a target. That patch shipped (commit `f134180`) and remains valuable, but it doesn't fix the underlying architecture. After re-examining under the right product lens — **not "fix the Aanya demo," but "make a teaching agent that handles ANY STEM doubt with magical precision"** — the current annotation pipeline has structural flaws that no tactical patch can resolve:

- **LLM-as-layout-engine breaks for parametric/computed geometry.** Direct JSON emission works for IGCSE-level simple diagrams but fails for trig-heavy constructions, refraction angles, projectile trajectories, orbital geometry (109.5°, 120°), tangent lines, and anything where exact angles or computed positions matter. As we scale across math + physics + chem, this breakage becomes the norm, not the edge case.
- **Annotation bounds use LLM estimates, not rendered reality.** Frontend measures actual bounds via `getBoundingClientRect()` and reports them to backend (`SpatialSolver`), but `SlideAnnotationLayer.tsx` still reads stale `spec.dictionary[id].bounds`. Highlights land off-element when the LLM's estimate drifts from layout reality.
- **Tool calls fire at start-of-turn, not aligned with TTS playout.** When the agent says "the hypotenuse here in red," the highlight fires ~800ms before the word "hypotenuse" is spoken. Voice-visual desync kills the "teacher pointing while speaking" magic.
- **Vocabulary brittleness.** Agent can only annotate things with a pre-baked role in the dictionary. "The line in red" or "the empty space below the curve" have no path.
- **No perception / correction loop.** The agent emits an instruction, the frontend renders, and the agent never sees what was actually drawn. Mistakes leak through deterministic precision and never get corrected.

This document replaces patch-list thinking with a 5-layer architecture that addresses each structural flaw, sequenced in **impact order** so each phase ships an end-user improvement on its own.

## Three-Factor Evaluation Framework

Every design decision in this plan (and going forward across all features in this project) is evaluated on three factors:

1. **Precision / Accuracy**: does it produce the correct visual/verbal output? For diagrams: pixel-correct geometry, exact angles. For annotations: lands on the right element. For voice: agrees with the visual.
2. **Latency (real-time)**: does it fit a live-teaching pipeline? Hard floor: voice round-trips must be <2s. Visual reactions must be <300ms for mid-sentence sync, <800ms for sentence-boundary sync.
3. **Cost (average per-hour live teaching session)**: at the unit of one student getting one hour of teaching. Total session cost budget ~$5-8/hr (Sonnet + TTS + STT + LiveKit). Any added subsystem must fit within remaining margin headroom (<$1/hr typically).

### Per-phase scorecard

| Phase | Precision | Latency | Cost/hr session |
|---|---|---|---|
| 0: Prompt trim | Neutral. Reduces LLM error rate slightly. | Saves ~50ms per turn (fewer tokens to process). | Saves a few cents/hr. |
| 1: Frontend bounds | **~100% annotation placement** for elements that exist. | <50ms (frontend-local DOM measurement). | $0 (no LLM call). |
| 2: Voice-visual sync | Timing precision only. | Sentence boundary: ~0ms overhead. Word level (Tier B): adds Cartesia plugin work. | $0 (Tier A); negligible (Tier B). |
| 3: Python sandbox | **~100% diagram generation** for parametric/computed cases. | Adds ~100-200ms per diagram (sandbox exec). | Saves on LLM retries; adds GPU/CPU sandbox infra ~$0.05/hr. |
| 4: Action tags | Same as Phase 1 for placement. Wider vocabulary. | Saves tool-call overhead, ~200-400ms per pointing op. | $0 (no extra LLM calls). |
| 5a: Haiku perception loop | **Mistake detection + recovery.** Catches errors that escape Phase 1-4's deterministic floor. | 500-800ms per check (sentence-boundary acceptable). | $0.06/hr (Haiku vision at $0.001 × 60 checks). |
| 5b: VL-JEPA (future) | Same detection + fuzzy-target resolution. | **~142ms per check** (mid-sentence acceptable). | $0.20-0.50/hr amortized (shared GPU). |

Total added cost across phases at full deployment: <$0.50/hr. Total latency added per teaching turn: <300ms. Precision: deterministic floor (Phases 1+3) + perception-loop recovery (Phase 5).

## The 5 Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: Perception          vision watches the board,     │
│  ─────────────                detects mistakes, triggers    │
│                               recovery (Haiku → VL-JEPA)    │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Interaction         <highlight target="N">        │
│  ─────────────                action tags + tool calls      │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Voice-Visual Sync   actions fire when spoken      │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Generation          Python DSL → JSON (sandbox)   │
│  ─────────────                exact trig, parametric, etc.  │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: State / Bounds      live DOM is ground truth      │
│  ─────────────                getBBox() over LLM estimates  │
└─────────────────────────────────────────────────────────────┘
```

Each layer is independently shippable. The user sees an improvement after each.

**Layers 1-4 give a deterministic precision floor** (generation + targeting by construction). **Layer 5 closes the loop** — perception verifies what was actually drawn matches intent, recovers from mistakes the deterministic floor still misses.

A standalone **Phase 0** ships ahead of all layers — a 30-minute prompt-side optimization identified during the Gemini-proposal cross-check.

---

## Phase 0: Prompt-side Context Trim (impact: minor, ~30 min — ships immediately)

**Quick win identified during Gemini-proposal analysis. Independent of all 5 layers; ships first.**

### What

The teaching agent's prompt currently includes the full `current_diagram_dictionary` with all five `ElementMeta` fields: `role`, `semantic`, `position`, `spatial_relations`, `bounds`. For LLM *reasoning* about what's on screen, only `role` + `semantic` (and implicit `id`) are useful. `bounds` is pixel data the LLM never needs; `spatial_relations` and `position` are derivable from the diagram and add prompt noise.

Trimming saves ~50-100 tokens per diagram in the prompt and reduces the LLM's cognitive load when picking annotation targets. Functionally invisible to users; mechanically clean. This is Gemini's "Semantic Map / Legend" idea applied minimally.

### Files

| File | Change |
|---|---|
| `backend/src/feynman/agent/prompts.py` | In `_render_diagram_dictionary_section`, render only `{id, role, semantic}` per element. Drop `bounds`, `position`, `spatial_relations`. |

### Verification

- Existing prompt-rendering tests pass (none assert on dropped fields).
- Manual: print the rendered prompt in a free-form session; dictionary section is trimmed.
- Token-count: existing diagrams show ~50-100 fewer tokens in the prompt section.

### Why this is separate from Phase 1

Phase 1 (Frontend Bounds) changes WHERE bounds come from (live DOM, not dictionary). Phase 0 changes whether the LLM sees bounds AT ALL (it shouldn't, regardless of source). Orthogonal concerns; both ship.

---

## Phase 1: Frontend Bounds Resolution (impact: highest, ~3-5 days)

**Fixes the bug visible today.** Annotations stop landing in the wrong place because we use the live DOM as the truth source.

### Approach

Skip the round-trip through `SpatialSolver` for annotation rendering. The frontend already has:
- Every SVG element stamped with `data-design-element={id}` (in `DesignDiagramContent.tsx`)
- The diagram SVG and annotation overlay in the same React subtree
- `getBBox()` available on every SVG element

So: `SlideAnnotationLayer.tsx` resolves `target_element_id` against the **live DOM**, not the dictionary bounds.

### Files to modify

| File | Change |
|---|---|
| `frontend/src/engine/whiteboard/split/SlideAnnotationLayer.tsx` | Replace `lookupBounds(dictionary, id)` with `resolveLiveBounds(svgRef, id)` that does `svgRef.current.querySelector('[data-design-element="${id}"]').getBBox()`. Falls back to dictionary bounds only if the element isn't in the DOM (rare race during fade-in). |
| `frontend/src/engine/whiteboard/split/SlidePanel.tsx` | Pass `svgRef` (ref to the rendered diagram SVG) down to `SlideAnnotationLayer`. |
| `frontend/src/engine/content/DesignDiagramContent.tsx` | Expose the SVG ref via `forwardRef` so SlidePanel can capture it. |
| `backend/src/feynman/visuals/instructions.py` (or wherever annotation instruction types live) | Extend annotation `target` field to support multi-kind targeting: `{kind: "id" \| "role" \| "color" \| "near_text" \| "data_attr", value: ...}`. Backwards compatible — bare strings still treated as `kind: "id"`. |
| `backend/src/feynman/agent/tools.py` | The 4 annotation tools (`pin_label_near`, `draw_callout`, `bracket`, `highlight_pulse`) emit the new richer target. Keep backend resolver as a sanity check (ensure SOMETHING in the dictionary OR likely DOM match exists), but no longer mandate a dictionary entry. |

### New targeting kinds resolved on the frontend

- `kind: "id"` → `querySelector('[data-design-element="..."]')`
- `kind: "role"` → search dictionary for matching role, then DOM
- `kind: "color"` → `querySelectorAll('[stroke="#ff0000"], [fill="#ff0000"]')`
- `kind: "near_text"` → find `<text>` with substring match, return its parent group / nearest sibling bbox
- `kind: "data_attr"` → arbitrary `data-` attribute query (escape hatch)

### Verification

- Existing 8 tests in `test_tools_annotation.py` continue to pass (they assert backend behavior).
- New frontend Vitest: `SlideAnnotationLayer.test.tsx` — mounts a diagram with known elements, fires a `highlight_pulse` instruction targeting `id`, asserts the overlay positions match `getBBox()` exactly.
- Manual: restart worker, draw a right triangle, ask "highlight the hypotenuse" — annotation lands exactly on `side_c`. Then resize the viewport and re-trigger — annotation stays aligned.

### What this does NOT fix

- Vocabulary mismatch: LLM still has to pick a target. We've widened the target vocabulary (color, near_text), but the LLM still needs to know what to ask for. Layer 4 (action tags + smarter prompting) and Layer 5 (perception-based recovery) address this fully.

---

## Phase 2: Voice-Visual Sync (impact: high, ~2-3 days for approximate, +1-2 weeks for perfect)

**Annotations fire when the word is spoken, not 800ms before.**

### Critical finding from audit

`livekit-agents` does NOT expose per-word playout callbacks. `ctx.wait_for_playout()` blocks until ALL queued audio plays — coarse. The only TTS event surfaced is `conversation_item_added`, which fires AFTER speech completes.

Two implementation tiers — recommend **shipping Tier A first, evaluating need for Tier B later:**

### Tier A: Sentence-boundary sync (2-3 days)

- Extend `SyncMode` enum in `tools.py:233` area: today has `IMMEDIATE` and `ON_PLAYOUT`. Add `AFTER_NEXT_SENTENCE`.
- Annotation tools default to `AFTER_NEXT_SENTENCE` — they wait for the next sentence boundary in TTS output before firing.
- State-changing tools (`draw_design_diagram`, `switch_board`) stay `IMMEDIATE`.
- Implementation: hook `on_speech_committed` (or equivalent in livekit-agents). When a sentence-final punctuation token is committed, drain pending sentence-bounded actions.

### Tier B: Word-level sync (1-2 weeks if/when needed)

- Wrap Cartesia TTS directly via livekit-agents' custom-TTS plugin path. Cartesia returns word timestamps in its streaming API.
- Build a `WordTimingTracker` that maintains a queue of (word, scheduled_time) tuples.
- Annotation tools can specify `sync_to_word="hypotenuse"` — fires at exact word boundary.
- This requires either: (a) modifying the livekit-agents Cartesia plugin, or (b) running our own Cartesia stream in parallel and reconciling.

### Files to modify (Tier A)

| File | Change |
|---|---|
| `backend/src/feynman/agent/tools.py` | Add `AFTER_NEXT_SENTENCE` to `SyncMode`. Annotation tools use it by default. State tools stay `IMMEDIATE`. |
| `backend/src/feynman/livekit/worker.py` | Subscribe to mid-speech text events (or fall back to small text-stream parser that detects `.!?` boundaries). Maintain a sentence-pending action queue per session. Drain on each sentence boundary. |
| `backend/src/feynman/visuals/instructions.py` | Add `sync_mode` to the instruction WS payload so frontend knows whether to play immediately or queue. |
| `frontend/src/livekit/useVisualChannel.ts` | Honor `sync_mode` — if `AFTER_NEXT_SENTENCE`, queue the action and apply on next sentence-end signal from the TTS event stream. |

### Verification

- Unit: mock conversation_item_added with sentence-bounded text, verify queued actions drain.
- Manual: agent says "Here we have a ramp [pause]. The block sits on it [pause]." Highlight on "ramp" fires after "ramp" is spoken, not before.

---

## Phase 3: Python Sandbox / DSL → JSON (impact: structural, ~3-4 weeks)

**Replaces LLM-as-layout-engine for parametric, computed, and constraint-driven diagrams.**

### Why

Direct JSON works for stock topologies (right triangles, simple FBDs). It breaks for:
- Snell's law refraction at specific indices (n₁ sin θ₁ = n₂ sin θ₂)
- Projectile motion with variable angle/velocity (range, max height as parametric functions)
- Tangent lines to circles from external points (requires actual geometry)
- Orbital geometry (sp³ at 109.5°, sp² at 120°, sp at 180° — angles MUST be exact)
- VSEPR molecular geometry (4 bonds + 0 lone pairs ≠ 3 bonds + 1 lone pair)
- Wave superposition with phase

For these, LLM emits coords that look right at low complexity and break at higher complexity. Python computes exactly.

### Architecture

Two-stage call:

```python
# Stage 1: LLM writes Python in our constrained DSL
canvas = Canvas(width=900, height=650)
block = canvas.add_rect(width=100, height=100, center=(450, 325), id="mass_1", role="object")
n_force = canvas.add_vector(
    start=block.top_center, direction=(0, -1), length=150,
    label="N", id="force_N", role="normal_force",
)
gravity = canvas.add_vector(
    start=block.bottom_center, direction=(0, 1), length=150,
    label="mg", id="force_mg", role="gravity",
)
return canvas.export()  # produces existing DiagramSpec JSON
```

```python
# For parametric / computed cases:
import math
theta = 30  # angle of incline
ramp_length = 400
incline_top = (200, 400)
incline_bottom = (
    incline_top[0] + ramp_length * math.cos(math.radians(theta)),
    incline_top[1] + ramp_length * math.sin(math.radians(theta)),
)
canvas.add_line(start=incline_top, end=incline_bottom, id="ramp_surface", role="incline")
# perpendicular to ramp for normal force
canvas.add_vector(
    start=block.center,
    direction=perpendicular_to(incline_top, incline_bottom),
    length=120, label="N", id="force_N", role="normal_force",
)
```

### Library to build

Module: `backend/src/feynman/visuals/canvas_dsl.py` (new). Compiles to existing `DiagramSpec` Pydantic models from `design_agent/backend/schema.py:279` (re-use, do NOT duplicate).

Primitives (STEM-tuned):
- **Shapes**: `add_line`, `add_rect`, `add_circle`, `add_ellipse`, `add_arc`, `add_arrow`, `add_path`, `add_text`, `add_latex`
- **Vectors**: `add_vector(start, direction, length)` — auto-arrow rendering
- **Geometric helpers**: `perpendicular_to(p1, p2)`, `tangent_to(circle, external_point)`, `intersect(line1, line2)`, `midpoint(p1, p2)`, `parallel_at_distance(line, d)`, `polar(center, r, theta)`
- **Anchor points on shapes**: `rect.top_center`, `rect.bottom_left`, `circle.boundary_at_angle(deg)`, `line.midpoint`, `arc.start`, `arc.end`
- **Composites**: `add_right_triangle(legs=(a,b), origin=...)`, `add_free_body_diagram(mass_box, forces=[...])`, `add_ray(from_point, angle, length)`, `add_lens(center, focal_length, type="convex")`, `add_lewis_structure(atoms, bonds)`
- **Annotation pre-anchors**: each primitive returns an object with `id`, `role`, `bounds`. Library auto-populates `dictionary` from these.

Library is opinionated: every primitive auto-registers a dictionary entry. No way to draw an element WITHOUT a role.

### Sandbox

- Use `RestrictedPython` (or `pyodide` server-side via `wasmer-python`) for isolation
- Whitelist: `math`, our `canvas_dsl` module, basic builtins (`range`, `len`, `min`, `max`, `abs`, `round`, list/tuple/dict literals)
- No filesystem, no network, no exec, no eval
- 2-second execution timeout
- LLM gets stderr on failure for retry

### Files

| File | Change |
|---|---|
| `backend/src/feynman/visuals/canvas_dsl.py` | NEW. Library that compiles to `DiagramSpec`. |
| `backend/src/feynman/visuals/sandbox.py` | NEW. Restricted Python execution wrapper. |
| `backend/src/feynman/agent/design_bridge.py` | Add `generate_via_python(prompt)` path. Existing `generate_design_diagram` becomes the fallback / "simple cases" path. |
| `design_agent/backend/prompts.py` | New prompt for Python-DSL mode. Includes library docs (every primitive, every helper). |
| `backend/src/feynman/agent/tools.py:1311` | `draw_design_diagram` chooses between paths based on subject complexity heuristic (or LLM self-selects via a tool param `mode="auto" \| "direct" \| "python"`). |

### Verification

- Library unit tests: each primitive emits valid JSON, anchor math is correct (tangent-to-circle returns point on circle, perpendicular has dot product 0, etc.).
- Sandbox tests: malicious code rejected, timeout enforced, error surfaces cleanly.
- E2E manual: ask agent "show a ramp at 35° with a 5kg block, draw normal force and gravity." Inspect emitted SVG — angles measured with protractor in Figma must match 35° exactly.
- Regression: existing diagrams that worked direct-JSON continue to work via the direct path.

### Honest scope risk

This is the biggest phase. 3-4 weeks is realistic for STEM-core primitives + library docs + sandbox + LLM prompt iteration. The composite helpers (FBD, lens, Lewis structure) are where time concentrates. Acceptable to ship the basic primitives + sandbox first (2 weeks), then composites incrementally as we hit diagram types that need them.

---

## Phase 4: Inline Action Tags (impact: real-time feel, ~2 weeks)

**Lightweight pointing operations stream inline with text. Heavyweight ops stay as tool calls.**

### Hybrid model

- **Tool calls** (validated, with return values): `draw_design_diagram`, `modify_design_diagram`, `switch_board`, `start_doubt_branch`, `resolve_doubt`, `set_lesson_topic`, `advance_concept`.
- **Inline action tags** (frontend-resolved, fail-silent acceptable): `<highlight target="...">`, `<focus on="...">`, `<callout from="..." text="..." />`, `<bracket between="...,..." />`, `<pulse target="..." />`, `<pin label="..." near="..." />`.

### Critical: annotations are SEPARATE from diagram regeneration

Action tags overlay the existing rendered diagram via the live DOM (Phase 1 machinery). They do NOT trigger any LLM round-trip to regenerate the diagram. This is a structural property of the architecture, not a convention:

- Adding a highlight = frontend CSS animation on an existing SVG element. Zero LLM cost. Zero risk of layout drift.
- Actually changing the diagram (add a force vector, erase an element, change a label) = explicit `modify_design_diagram` tool call. LLM in the loop, validated, return value.

Gemini correctly identified this as the "stateless generation bottleneck" risk in the current system. The Phase 1 + Phase 4 split eliminates it: lightweight visual changes never touch the design agent.

The LLM writes:
> "Here you can see <highlight target="force_N"/> the normal force pushing up, and <highlight target="force_mg"/> gravity pulling down."

Action tags are stripped from TTS text and dispatched as visual instructions sync'd to where they appeared in the stream (via Phase 2 sync infra).

### Files

| File | Change |
|---|---|
| `backend/src/feynman/livekit/worker.py` | Tap the LLM text stream BEFORE TTS. Parse for action tags. Strip tags from TTS-bound text. Emit corresponding visual instructions over the `"visuals"` WS channel with `sync_mode=AFTER_NEXT_SENTENCE` (so they fire at the right moment per Phase 2). |
| `backend/src/feynman/agent/prompts.py` | Teach the LLM the action-tag grammar in the system prompt. Show worked examples. Reinforce: state-changing ops use tools, pointing ops use tags. |
| `backend/src/feynman/visuals/instructions.py` | Add `ActionTagInstruction` types (mostly aliases over existing highlight/pulse/callout types). |
| `frontend/src/livekit/useVisualChannel.ts` | Dispatch the new action types. They're resolved on the frontend via Phase 1's live-DOM machinery — so unknown targets fail silently, as designed. |

### Why fail-silent is OK here (and not for tool calls)

For ephemeral pointing operations, a missed highlight is a teaching micro-glitch, not a state corruption. The voice flows on, the lesson continues, the teacher can re-point ("here, this one"). For state-changing operations (creating a doubt branch, drawing a new diagram), silent failure would corrupt session state — those keep tool-call validation. Phase 5 perception loop additionally catches and recovers from these silent misses.

### Verification

- Backend unit: stream parser correctly extracts tags, strips text, emits instructions in stream order.
- Backend unit: malformed tags don't crash the parser, are passed through to TTS as text.
- E2E manual: agent says "look at <highlight target='hypotenuse'/> the long side" — TTS speaks "look at the long side" cleanly, highlight fires synchronized with "long side."
- LLM prompt: confirm agent uses tags appropriately. Mixed-mode prompt may need 2-3 iterations.

---

## Phase 5: Vision-Based Perception Loop (impact: closes the correction loop, ~1-2 weeks for 5a; ~3-4 weeks for 5b)

**Layers 1-4 are deterministic precision by construction. Phase 5 verifies after the fact and recovers from mistakes that escape the deterministic floor.** This is the "Feynman SEES its own mistakes and corrects them" requirement.

### Critical finding from audit

We already have Haiku-based vision infrastructure wired end-to-end:
- `frontend/src/engine/whiteboard/BoardCapture.tsx` captures the slide as a PNG (html2canvas, 512×288, 70% JPEG) and publishes over data channel
- `backend/src/feynman/agent/board_verifier.py` receives captures and calls Claude Haiku to verify layout, parses issues, generates `FixAction`s
- `backend/src/feynman/livekit/worker.py` routes capture responses to the verifier
- Currently used as **one-shot QA per concept** (`_verified_this_concept` flag) and the FixActions are logged but not auto-applied

Phase 5 extends this from one-shot QA into a **continuous perception loop with auto-recovery**.

### Phase 5a: Continuous Haiku Perception Loop (1-2 weeks, ships first)

**Goal**: every diagram and annotation produces a vision-verified record. Mistakes are surfaced back to the agent for in-loop recovery within the same turn.

#### Triggers (expand existing one-shot path)

- After `draw_design_diagram` succeeds: verify layout (today) → ADD: verify diagram matches the prompt intent (e.g., agent said "free body diagram of a block on a ramp" → vision confirms ramp + block + force vectors exist)
- After each annotation tool call (`highlight_pulse`, `pin_label_near`, `draw_callout`, `bracket`): verify the annotation actually landed on a meaningful element. Compare the highlighted region's surrounding context against the agent's verbal claim.
- After every N seconds during teaching (low-frequency drift check, e.g., every 30s): is what's on the board still consistent with the lesson plan?

#### Recovery loop

When verification fails:
1. Vision call returns: `{score: 2/5, issue: "highlight is on the right-angle marker, not the hypotenuse", suggested_target: "side_AB"}`
2. Backend feeds this back to the teaching agent as a tool-result-shaped message (not a user turn — keeps voice flow uninterrupted)
3. Teaching agent retries via Phase 4 action tag with the corrected target

Today: FixActions are logged but not surfaced to the LLM and not auto-applied. Phase 5a wires both.

#### Files to modify

| File | Change |
|---|---|
| `backend/src/feynman/agent/board_verifier.py` | Remove `_verified_this_concept` single-shot guard. Add continuous-mode trigger (every annotation, every modify_design_diagram, periodic drift check). Surface FixActions as inline LLM-feedback messages, not just logs. |
| `backend/src/feynman/agent/tools.py` | All 4 annotation tools spawn a verification task (background asyncio). On failure, feedback flows back to the agent. |
| `backend/src/feynman/livekit/worker.py` | Add periodic drift-check timer (every 30s) that pings the verifier. |
| `backend/src/feynman/agent/prompts.py` | Teach the LLM how to interpret perception-feedback messages and re-attempt. |
| `frontend/src/engine/whiteboard/BoardCapture.tsx` | Capture trigger expanded — fire on every annotation, not just on diagram creation. |

#### Verification

- Unit: mock vision returning low score, verify recovery loop triggers retry with corrected target.
- Manual: ask agent "highlight the hypotenuse" but in a prompt where it gets the role wrong → vision detects miss → agent self-corrects → second highlight is correct.
- Cost: 60 vision checks/hr × $0.001 = $0.06/hr. Under budget.

### Phase 5b: VL-JEPA Self-Hosted (3-4 weeks, post-traction)

**Goal**: drop perception latency from 800ms (Haiku) to ~142ms (VL-JEPA), enabling sub-sentence correction and fuzzy-target resolution by embedding similarity.

#### When to build

After Phase 5a is in production and we observe one or both of:
- Latency ceiling reached: 800ms Haiku is too slow for the "magic" interaction pattern users settle into
- Scale economics: enough concurrent sessions to amortize a dedicated GPU instance (~$1-2/hr fixed cost across 10-20 sessions = $0.10-0.20/session/hr)

#### Architecture

- Dedicated VL-JEPA inference service. Initial: single A10G or L4 instance, FastAPI wrapper around VL-JEPA-Base (1.6B params).
- API: `/embed_visual(image_b64) → vector[1536]`, `/embed_text(query) → vector[1536]`. Optional `/predict(visual, query) → vector[1536]` for prediction tasks.
- Backend calls this service in parallel with (or instead of) Haiku.

#### Applications enabled by 142ms latency

1. **Sub-sentence verification**: encode rendered annotation + encode the agent's just-spoken phrase → cosine similarity. Below threshold → interrupt and re-point.
2. **Fuzzy-target resolution**: agent says `<highlight target="the line in red"/>`. Frontend has no element with role="the line in red". Backend encodes the query + each element's bounding region → picks the highest-similarity match. Solves vocabulary-mismatch beyond the multi-kind targeting in Phase 1.
3. **Continuous drift monitoring**: encode the board every ~1s, compare against expected state vector. Detect "the block moved" or "the diagram got accidentally cleared" type events.
4. **Selective decoding pattern (from VL-JEPA paper)**: most teaching turns produce visually stable states. Only invoke the Haiku/Sonnet decoder when the embedding stream shows significant change. ~2.85× reduction in Haiku calls if we keep Haiku as a fallback for hard-reasoning cases.

#### Files (new)

| File | Change |
|---|---|
| `vision_service/` (new top-level dir) | FastAPI wrapper around VL-JEPA. Dockerized. Deployed separately. |
| `backend/src/feynman/agent/perception.py` (new) | Client to the vision service. Embedding similarity helpers. Abstraction over Haiku + VL-JEPA. |
| `backend/src/feynman/agent/board_verifier.py` | Refactor to call `perception` module. Picks Haiku or VL-JEPA based on latency requirement. |
| `infra/vision_service/` | Deployment config (Docker, Kubernetes manifests, autoscaling rules). |

#### Verification

- Benchmark: VL-JEPA inference latency at p50/p95 < 200ms on target hardware.
- Accuracy: spot-check fuzzy-target resolution against a labeled set of 50 diagrams + 200 "natural language target" descriptions. Should beat the multi-kind targeting fallback (which uses heuristics, not semantic similarity).
- Cost: GPU amortized cost <$0.50/hr/session at expected concurrent load.

### Honest scope risk

Phase 5b is real infra work: model serving, GPU autoscaling, fallback paths, cost monitoring. Don't conflate "Meta released the weights" with "easy to deploy." Plan 3-4 weeks; expect 5-6 with infra rough edges.

5a is much smaller because the infrastructure exists. The risk there is prompt-engineering on the perception feedback (LLM has to interpret "score: 2/5, issue: ..." and re-attempt correctly without going into spiral).

---

## What this plan deliberately does NOT do

- **Demo-specific hacks.** No pre-baked Aanya annotation library, no hardcoding around the 7-minute script. The product fix is the demo fix.
- **Bio-specific diagram primitives.** Cell structures, ecosystems, anatomy. Add later when we expand subject scope.
- **Modify the existing typed JSON DSL schema.** The Python DSL compiles to the EXISTING `DiagramSpec` — frontend rendering stays untouched.
- **Modify `BoardManager` / `TeachingContext`.** State management is sound; we're upgrading the layers that USE it, not the state itself.
- **Touch curriculum (Neo4j) loading.** Orthogonal. Free-form mode remains the default while this work happens.

## Critical files for context

- **Annotation rendering**: `frontend/src/engine/whiteboard/split/SlideAnnotationLayer.tsx:52-64` (current `lookupBounds`)
- **Annotation publish**: `backend/src/feynman/agent/tools.py:1311` (`draw_design_diagram`), 4 annotation tools at `pin_label_near` / `draw_callout` / `bracket` / `highlight_pulse`
- **Bounds reporting infrastructure**: `backend/src/feynman/agent/scene_graph.py` (`SpatialSolver`, `BoundsReportPayload`), `worker.py:331-342` (receives bounds)
- **DiagramSpec schema (reused as Python DSL emit target)**: `design_agent/backend/schema.py:233-289`
- **WS message dispatch**: `frontend/src/livekit/useVisualChannel.ts:54-111` (`onMessage`)
- **TTS sync primitive**: `backend/src/feynman/agent/tools.py:233` (`ctx.wait_for_playout()`)
- **Vision infrastructure (extends in Phase 5)**: `backend/src/feynman/agent/board_verifier.py` (Haiku-vision one-shot QA today), `frontend/src/engine/whiteboard/BoardCapture.tsx` (html2canvas → base64 PNG → data channel), `worker.py` capture-response handler
- **Existing test surfaces to keep green**: `backend/tests/unit/test_tools_annotation.py`, `test_diagram_dictionary.py`

## Sequencing & shipping cadence

| Phase | Effort | Ships | User-visible win |
|---|---|---|---|
| 0: Prompt trim | 30 min | Day 1 | Cleaner LLM context, ~50-100 tokens saved per diagram. |
| 1: Frontend Bounds | 3-5 days | Week 1 | Annotations stop landing in wrong spots. Color/near-text targeting available. |
| 2: Voice-Visual Sync (Tier A) | 2-3 days | Week 2 | Annotations fire at the right moment, not 800ms early. |
| 3a: Python Sandbox (basic primitives) | 2 weeks | Week 4 | Parametric/trig-correct diagrams. Composite helpers added incrementally. |
| 3b: Python Sandbox (composites) | 1-2 weeks | Week 5-6 | FBDs, lens diagrams, Lewis structures use library shortcuts. |
| 4: Action Tags | 1-2 weeks | Week 7-8 | Streaming pointing operations sync with spoken word. Hybrid with tool calls. |
| 5a: Haiku Perception Loop | 1-2 weeks | Week 9-10 | Feynman SEES its mistakes and recovers in-loop. ~$0.06/hr added cost. |
| 5b: VL-JEPA self-hosted | 3-4 weeks | Post-traction | Sub-sentence correction (142ms). Fuzzy-target resolution by embedding similarity. |

Total: ~8-10 weeks for Phases 0-5a (the "feature-complete" architecture). Phase 5b is a latency/scale upgrade, build when traction warrants the GPU infra.

## Risks

| Risk | Mitigation |
|---|---|
| Phase 3 sandbox security holes | RestrictedPython + whitelist + timeout + no network/FS. Treat sandbox as a security boundary, not just a correctness one. |
| LLM Python code hallucinations (calling non-existent helpers) | Tight error feedback in retry loop. Library docs in system prompt with worked examples per primitive. |
| Phase 4 livekit-agents may not expose token-stream cleanly | Acceptable fallback: chunk-level tag extraction (parse each LLM response chunk before forwarding to TTS). Even if not perfectly streaming, the action-tag UX still wins. |
| Phase 2 Tier A insufficient for "magical" sync | Re-evaluate need for Tier B (word-level) after Phase 4 ships. May discover sentence-boundary is good enough in practice. |
| Phase 3 scope creep into bio / advanced subjects | Cap library at STEM core. Bio additions go in a separate `bio_dsl.py` later. |
| Backward compat: existing direct-JSON diagrams break | Keep both paths. Python path is opt-in for complex cases via tool param. Tests for existing diagrams stay green. |
| Phase 5a perception-feedback creates retry spirals (LLM tries, vision flags, LLM tries again, infinite loop) | Hard cap on retries per annotation (e.g., 2 attempts). After cap, surface as a soft-feedback to the user ("let me show you a different way") and move on. |
| Phase 5a vision call adds 800ms latency on hot path | Vision runs as background asyncio task, not in the request flow. Voice continues; correction surfaces at next sentence boundary via Phase 2 sync infra. |
| Phase 5b GPU infra costs eat into margins at low concurrent load | Don't ship 5b until concurrent-session metrics justify amortization. Until then, Haiku is the answer. |
| Phase 5 false-positives (vision says "wrong" when annotation was actually fine) | Threshold tuning. Start conservative (only act on score ≤ 2/5). Log all flag decisions; adjust thresholds based on labeled data. |

## Verification across phases

```bash
cd /Users/yashbansal/proj/feynman/backend

# After each phase
uv run pytest -x -v tests/unit/test_tools_annotation.py tests/unit/test_diagram_dictionary.py
uv run pytest -x -v tests/

# Frontend
cd /Users/yashbansal/proj/feynman/frontend
pnpm test
pnpm lint

# E2E per phase
make dev  # backend + frontend
make dev-worker  # separate terminal
# Use http://localhost:5173 with USE_NEO4J_CURRICULUM=false for free-form testing
```

End-to-end product validation (after each phase):

- **After Phase 0**: rendered prompt shows trimmed dictionary section; agent behavior unchanged; token-count reduced.
- **After Phase 1**: free-form mode, ask agent to draw and annotate ANY diagram on a STEM topic. Annotations land exactly. No silent failures.
- **After Phase 2**: same as Phase 1 but observe voice-visual timing. Annotations should fire on the relevant word, not before.
- **After Phase 3**: ask agent to draw "Snell's law refraction with n1=1.0, n2=1.5, angle of incidence 47°." Measure refracted-ray angle in the rendered SVG — must be ~30.7°. Ask for "VSEPR for methane" — bond angles must be 109.5°.
- **After Phase 4**: agent's responses contain inline `<highlight>` tags, voice plays cleanly without speaking tag syntax, highlights fire mid-sentence.
- **After Phase 5a**: deliberately give the agent a tricky annotation target (something not obvious from the role dictionary). Vision verifier catches the mis-target; agent receives feedback; second attempt lands correctly. Check audit log to confirm the recovery happened automatically, not via user re-prompting.
- **After Phase 5b**: free-form question "highlight the line going to the upper right" with no matching role. VL-JEPA-based fuzzy resolution finds the correct element via embedding similarity. Latency end-to-end under 300ms.

---

## Appendix: Cross-Check Against Gemini's Proposed Architecture

For traceability. A separate Gemini chat suggested a 3-phase "Code-to-State" pipeline. Here's how each part of Gemini's proposal maps to this plan, plus what Gemini's proposal didn't address but this plan does.

### Gemini's proposals → Plan coverage

| Gemini Phase | Core idea | Covered by | Notes |
|---|---|---|---|
| **Phase 1: Python Sandbox** | LLM writes Python in custom DSL; backend executes; emits JSON | **Plan Phase 3** | Direct match. Plan adds: cache by code hash, retry-on-stderr loop, escape hatch for direct JSON for trivial diagrams. |
| **Phase 2: Semantic Map / Trim Context** | LLM sees only `{id: semantic}`, not coords | **Plan Phase 0** | Added after Gemini cross-check (was missing in v1 of this plan). Phase 0 explicitly trims prompt to `{id, role, semantic}` only. |
| **Phase 3: Inline Action Tags** | `<action>` tags streamed inline; frontend parses | **Plan Phase 4** | Direct match. Plan adds: hybrid model (tool calls for state changes, tags for ephemeral pointing); explicit fail-silent reasoning; sync via Phase 2 infra. |

### What Gemini's proposal missed (additions in this plan)

| Gap in Gemini's proposal | Addressed by | Why it matters |
|---|---|---|
| **Post-render bounds drift** | Plan Phase 1 | LLM-estimated bounds (which Gemini's architecture also inherits — Python sandbox computes bounds at generation time, not render time) drift from rendered reality for text metrics, arc bbox, transformed groups. Live DOM via `getBBox()` is the only true source. Without this, even Gemini's perfect architecture has misaligned annotations. |
| **Vocabulary mismatch beyond known roles** | Plan Phase 1 multi-kind targeting (`id`, `role`, `color`, `near_text`, `data_attr`) | The LLM thinks "the line in red" but Gemini's "Legend" only has role names. New `color` and `near_text` kinds widen the expressive vocabulary without requiring exhaustive aliases. |
| **Tag validation / no error path** | Plan Phase 4 hybrid model + explicit fail-silent reasoning | Gemini's pure action-tag model has NO error path for bogus `target`. Plan keeps tool calls (validated, with return) for state changes; tags fail-silent only for cheap pointing where re-pointing is acceptable. |
| **Voice-visual sync mechanism (livekit-agents reality)** | Plan Phase 2 (Tier A sentence-boundary, Tier B word-level via Cartesia timings) | Gemini's "frontend executes as text streams" assumes free token-level streaming with per-word callbacks. Audit confirmed livekit-agents does NOT expose per-word callbacks. Plan explicitly designs sync tier infrastructure: Tier A is achievable now; Tier B requires SDK extension. |
| **State-change vs pointing distinction** | Plan Phase 4 (hybrid: tools for state, tags for pointing) | Gemini lumps all interactions into action tags. Plan keeps validated tool calls for `draw_diagram`, `switch_board`, `start_doubt_branch`, `resolve_doubt` — operations where silent failure corrupts session state. |
| **Bounds reporting infrastructure already half-wired** | Plan Phase 1 (audit finding) | Backend's `SpatialSolver` and `BoundsReportPayload` exist and are populated by the frontend but unused by annotation rendering. Plan formalizes the consumption path: don't round-trip bounds through backend; just use the live DOM directly. |
| **Backward compat with existing direct-JSON path** | Plan Phase 3 (escape hatch via tool param `mode="auto" \| "direct" \| "python"`) | Gemini implies wholesale replacement of JSON generation. Plan keeps direct JSON as fast path for trivial diagrams; Python sandbox is opt-in. Migration is gradual; existing diagrams that work today don't regress. |
| **Stateless regeneration risk** | Plan Phase 1 + Phase 4 (annotations overlay; never trigger regeneration) | Gemini correctly identifies this as a problem in current system. Plan's architecture structurally prevents it: action tags + Phase 1 live-DOM resolution mean lightweight pointing never touches the design agent. Diagram modification is a separate, explicit `modify_design_diagram` tool call. |

### Where this plan deliberately differs from Gemini

| Gemini suggested | This plan instead | Why |
|---|---|---|
| Pure inline action tags for ALL interactions | Hybrid: tool calls (state) + action tags (pointing) | Validation matters for state-changing ops; silent failure is unacceptable for `draw_diagram`, `switch_board`, etc. Acceptable trade for cheap pointing. |
| LLM writes Python exclusively | Two paths: Python for complex/parametric; direct JSON for simple cases | Most stock diagrams (right triangle, simple FBD, ramp+block) don't need a sandbox; direct JSON is faster and cheaper. Sandbox is opt-in via tool param. |
| (Implicit) Single LLM-trip generates everything | Generation (LLM) → frontend renders → annotations resolve against rendered DOM | Truth source for annotation positioning is the rendered DOM, not the LLM. Decouples generation accuracy from interaction accuracy — both can be wrong independently and recover independently. |

### What both Gemini and this plan agree on

- LLM-as-pure-layout-engine breaks for parametric/precision work. Python sandbox is the right floor.
- Token cost of dragging the full dictionary through every turn is unnecessary. Lightweight legend wins.
- Voice-visual sync at the streaming level is the right interaction model for a teaching agent. Tool-calls at start-of-turn miss the mark.
- The board should be a "first-class teaching tool" (per project CLAUDE.md), not a display surface that gets regenerated wholesale on each interaction.

### Beyond Gemini: Vision-based perception loop (Phase 5)

Gemini's 3-phase proposal achieves correctness *by construction* (Python computes accurately, action tags target accurately). It has no perception loop — the agent never verifies what was actually drawn matches intent. For a teaching agent that needs to handle ANY STEM doubt, deterministic precision floors leak (LLM picks wrong target despite valid options; sandbox produces valid Python that draws the wrong concept; user resizes the viewport and bounds drift).

VL-JEPA research (Chen et al., Meta FAIR, Dec 2025) crystallized that **vision can be added to the pipeline at negligible cost and real-time latency**:
- 1.6B params, 142ms inference per visual-query embedding
- Selective decoding pattern (only decode when embedding stream changes significantly) reduces compute by 2.85×
- Beats CLIP/SigLIP2/PE-Core on retrieval; matches generative VLMs on VQA with half the trainable params
- Native support for embedding-similarity tasks (perfect for "encode question + encode diagram regions → cosine match")

Phase 5 of this plan adds the perception loop in two tiers: Phase 5a uses the existing Haiku-vision infrastructure (`BoardVerifier`) made continuous and recovery-aware (1-2 weeks, $0.06/hr added cost). Phase 5b is the VL-JEPA upgrade once traction justifies the GPU infra investment.

This is genuinely outside Gemini's proposal — Gemini focused on getting generation/interaction RIGHT, not on detecting/recovering from mistakes that leak through.
