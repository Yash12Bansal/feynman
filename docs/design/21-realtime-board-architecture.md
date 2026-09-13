# Design Doc 21 — The Real-Time Board: Ops, a Geometry/Math Kernel, and the Streaming Teacher Loop

**Status:** Proposal. Written 2026-09-13 in response to Yash's question: how do we make Feynman draw and write in real time, with accuracy, starting with maths and physics.
**Scope:** Maths + Physics (IGCSE first, JEE-level later). Any subject eventually, but the kernel is designed for these two.
**Keeps intact:** doc 10 (split board), doc 16 Phase 1 (live DOM is ground truth for bounds), doc 19 (plan-first lecture pipeline, single spotlight), strategy 02 (cost plan).
**Changes:** the *unit of visual work*, the *division of labour* between the LLM and deterministic code, and *where voice/visual sync happens*.

---

## 0 · The one idea

A teacher at a board does not produce "a diagram". A teacher emits a stream of small board operations, about one per second, interleaved with speech: draw this line, label it *c*, write the next equation line, point at the angle, erase the wrong step. A diagram is what twenty to forty of those ops accumulate into.

Today the unit of work is the **DiagramSpec**: 2K to 3K output tokens of JSON authored from scratch by Sonnet. It cannot appear before it is complete. Doc 07 measured 43 to 51 seconds per spec in a live session; the best case is 5 to 15 seconds. That is the latency problem, and it is a **granularity** problem, not a model-speed problem.

Accuracy is a **division-of-labour** problem. Every benchmark on LLM-drawn figures (see §7) says the same thing: language models are excellent at *specifying* a figure and unreliable at *computing* it (angles, intersections, tangents, arrowheads, label placement). So the LLM must never compute geometry and never assert an algebra step unchecked. Deterministic code does that.

So:

1. **Ops, not documents.** The board's wire format becomes a small typed op vocabulary. Each op is 20 to 60 tokens and renders in well under a second. The LLM streams ops inline with its speech.
2. **Accuracy by construction, not by validation.** Geometry is computed by a constraint kernel from semantic instructions ("normal force perpendicular to the ramp at the block"). Algebra written to the notebook is verified by a CAS before it is drawn. Physics conventions live in parametric templates, encoded once.
3. **Sync at the word, scheduled by the worker.** Ops carry an anchor word; the worker fires them at the TTS word timestamp using its own audio clock. No dependency on LiveKit playout callbacks (the reason doc 16 deferred word-level sync).
4. **The split board stays.** Slide left, notebook right, no 2D layout by the LLM (docs 09 and 10 settled this and I am not reopening it). What changes is that the slide becomes a *persistent, mutable* figure that ops add to and modify across beats, instead of an atomic image that gets swapped.

---

## 1 · Where the repo actually is (facts this design is built on)

| Fact | Evidence | Consequence |
|---|---|---|
| The live interactive teacher (state machine, ~40 tools, anticipation, design_bridge) was deleted on 2026-05-31. Live = Ask Feynman only; lessons are precomputed manifests. | commit `bfb4931`, `docs/engineering/13` | We are designing the *next* live loop, not patching the old one. Good: no legacy 2D-layout code to fight. |
| The precomputed manifest is already an op stream in all but name: 28 event types (`show_diagram`, `write_equation`, `focus`, `trace`, `reveal_step`, `set_parameter`, `animate_parameter`, `new_page`, ...) driven by `cumulative_audio_ms`. | `data_pre_compute_v2/.../tts/chunker.py`, `useExtractionPlayback.ts` | The live loop should emit *the same* ops. One renderer for lecture playback, doubts, and live teaching. |
| The doubt path already interleaves board events with speech at phrase level, worker-side: `<<FOCUS>>` / `<<TRACE>>` markers split narration into fragments; each text fragment is a separate TTS call. | `agent/doubt_resolution/narration_markers.py`, `livekit/doubt_delivery.py:deliver_resolution` | Right mechanism, wrong clock. Per-fragment TTS breaks prosody and adds a TTFA per fragment. Word timestamps fix both. |
| A geometric DSL with exact helpers exists: `polar`, `perpendicular_to`, `parallel_at_distance`, `intersect`, `tangent_to`, plus composites `add_right_triangle`, `add_free_body_diagram`, `add_ray`, `add_lens`, `add_lewis_structure`, each auto-registering dictionary roles. | `backend/src/feynman/visuals/canvas_dsl.py` (1,597 LOC), `sandbox.py` | This is the seed of the geometry kernel. It has had no runtime consumer since `design_bridge.py` was deleted; only tests import it. |
| Seven zero-LLM frontend templates (`right-triangle-trig`, `lens-ray-diagram`, `dc-circuit-series`, `unit-circle-sine`, `projectile-motion`, `vector-addition-2d`, `circuit-parallel`) render in under a frame, with roles and params; the doubt planner can pick them. | `frontend/src/engine/whiteboard/diagram-templates/`, `doubt_resolution/diagram_templates.py` | The template path is proven. It needs 10x the coverage and build-up stages. |
| A legacy deterministic component library (circuits, optics, geometry, chemistry, free-body, inclined plane, spring) is still compiled into the bundle via `InstructionSwitch`. | `frontend/src/engine/whiteboard/scene/components/**`, doc 13 | Mine it for templates rather than rebuild. |
| Staged reveal (`presentation_mode: build_up`, `defaultReveal.ts`), stroke-dash animation for traces and strikethroughs, Hershey single-stroke handwriting with GSAP, rough.js, perfect-freehand, KaTeX, and the notebook with `=` alignment all exist. Design-diagram elements themselves fade in per element; they do not stroke-animate. | `DesignDiagramContent.tsx`, `TraceOverlay.tsx`, `HandwrittenTextContent.tsx`, `NotebookEntry.tsx`, `package.json` | The "hand" is mostly built. It is fed too coarsely, and constructed elements need a real draw-on animation (Phase 2). |
| Annotation targets resolve against the live DOM (`data-design-element` + `getBBox`), not LLM-estimated bounds. | doc 16 Phase 1, `SlideAnnotationLayer.tsx`, `resolveTarget.ts` | Keep. Ops target entity ids; the renderer finds pixels. |
| The focus *dimming* overlay and the `point_at` arrow were cut at `04cec94` (the SVG mask hole misresolved and greyed the whole diagram; pointers landed at wrong positions). `focus` survives only as a glow-and-lift class on the element; precompute still emits `point_at`, which the frontend no-ops. | `SlideAnnotationLayer.tsx:5-8`, `DesignDiagramContent.tsx:293-306`, git log | Half of doc 18's attention primitive is inert. Restore it with per-element opacity, not a mask, in Phase 0. |
| Cartesia Sonic-3 exposes word timestamps (`add_timestamps`); livekit-agents' Cartesia plugin supports `use_tts_aligned_transcript`. The old worker already set that flag. | LiveKit docs, `docs/engineering/04` | Word-level sync is available today; what was missing is *who* schedules the op. |
| No streaming LLM call exists on the live path. Classify (Haiku) then plan (Sonnet 4, forced tool, 4K tokens) run serially and block, covered by a spoken one-line acknowledgement; a doubt diagram is one non-streaming 8K-token Sonnet 4 call. | `worker.py:154-170`, `resolution_planner.py`, `diagram_generator.py` | The streaming teacher loop replaces "plan fully, then deliver" with "plan a skeleton, then stream speech and ops". |
| `contracts/visuals.schema.json` is the stale *live-teaching* vocabulary (25 instruction types that still carry `zone`, `position_x/y`, `placement`), while the manifest and doubt vocabulary (`ManifestEvent` / `BoardEvent`) is not in `contracts/` at all and is kept in sync by convention. | `contracts/visuals.schema.json`, `useExtractionPlayback.ts:85-256`, `board_events.py:1-13` | Phase 1 replaces both with one `board-ops.schema.json`. |
| 760 precomputed diagram artifacts and 139 generated specs exist; median spec is ~5.6 KB JSON. | `data_pre_compute_v2/artifacts/diagrams`, `design_agent/generated` | Retrieval corpus for the "hands". |

---

## 2 · Target architecture

```
                         ┌────────────────────────────────────────────────────┐
  Student voice  ──STT──▶│  TEACHER (Sonnet 5 / Opus 5, one streaming turn)   │
                         │  speech tokens  +  inline ops  +  figure requests   │
                         │  sees: lesson plan, board state (≤300 tok), history │
                         └──────┬───────────────────────┬─────────────────────┘
                                │ text (sentences)      │ ops (parsed as tags close)
                                ▼                       ▼
                     ┌──────────────────┐     ┌──────────────────────────────┐
                     │ TTS (Cartesia)   │     │ OP SCHEDULER (worker)         │
                     │ word timestamps  │────▶│ anchor word → audio ms →      │
                     │ audio frames     │     │ dispatch at that frame        │
                     └────────┬─────────┘     └──────────────┬───────────────┘
                              │ WebRTC audio                 │ data channel "board"
                              ▼                              ▼
                     ┌────────────────────────────────────────────────────────┐
                     │  BOARD RUNTIME (frontend)                              │
                     │  entity scene (slide) + notebook lines + figure history│
                     │  geometry kernel (TS) · KaTeX · stroke/handwriting     │
                     │  sim engine · state serializer → back to worker        │
                     └────────────────────────────────────────────────────────┘
                                ▲
       ┌────────────────────────┴───────────────────────────────┐
       │  HANDS (async, ahead of the teacher)                    │
       │  visual intent → template | retrieval | generated ops   │
       │  Haiku 4.5 writes compact DSL; kernel computes; QA      │
       │  fed by the beat plan (anticipation), never on hot path │
       └─────────────────────────────────────────────────────────┘
       ┌─────────────────────────────────────────────────────────┐
       │  MATH SERVICE (SymPy + Pint)                            │
       │  verify each notebook step · solve · units · LaTeX      │
       └─────────────────────────────────────────────────────────┘
```

### 2.1 Board Runtime (deterministic, shared contract)

**Slide = an entity scene, not an image.** Entities: `point`, `segment`, `vector`, `angle`, `arc`, `circle`, `curve`, `body` (block, ball, lens, resistor...), `label`, `latex`, `group`, `param`. Every entity gets a **semantic id at creation** (`hypotenuse`, `F_normal`, `ray_1`). The dictionary concept from doc 14 becomes the primary key instead of a post-hoc annotation. Relations are recorded (`on`, `from`, `to`, `perpendicular_to`, `at_angle`), because they are what the teacher talks about.

**Notebook = unchanged model** (kinds `section | equation | step | text | key_point | answer`, `align_group`, `indent`, `strikethrough`, `boxed`, `new_page(carry)`), plus two fields: `verified: bool | null` (CAS result) and an optional inline mini-figure slot (a sparkline-sized graph or number line, which `RoughGraphContent` already renders inside the notebook).

**Figure history.** Every figure that has been on the slide is kept with a thumbnail. `figure.recall(id)` brings it back in one op (~10 tokens). This is how "remember the triangle from before?" costs nothing. Doc 10's rejection of side-by-side stays; sequence, don't tile.

**The op vocabulary (v1, about 28 ops).** Placement is always relational or template-driven. The LLM never emits a pixel (doc 09's lesson).

| Group | Ops | Notes |
|---|---|---|
| Figure | `figure.template(id, params, build="staged"\|"whole")`, `figure.recall(id)`, `figure.request(brief)`, `figure.clear()` | `request` is async: the hands fulfil it; the teacher references it later by id. |
| Construct | `draw.point(id, at=<rel>)`, `draw.segment(id, from, to)`, `draw.vector(id, at, dir, mag, label)`, `draw.angle(id, at, from, to)`, `draw.arc`, `draw.circle(id, center, through\|r)`, `draw.curve(id, expr, domain)`, `draw.body(id, kind, at)`, `draw.mark(id, at, kind)` | `<rel>` is a construction: `midpoint(A,B)`, `on(seg, t=0.6)`, `intersect(l1,l2)`, `perp_from(P, seg)`, `polar(O, r, θ)`, `foot(P, seg)`. The kernel resolves it. |
| Annotate | `label(target, text, side)`, `focus(target)`, `unfocus()`, `trace(target)`, `point_at(target)`, `margin(target, text)`, `reveal(step)`, `erase(target)` | These are the doc 19 §12 primitives. `focus` must be re-shipped (see §6 Phase 0). |
| Morph | `param.set(name, v)`, `param.animate(name, to, ms)`, `sim.run(kind, params)`, `sim.pause()` | Parametric change is a 15-token op. Physics simulations are first-class. |
| Notebook | `write.section`, `write.eq(latex, group, boxed)`, `write.step(text, indent)`, `write.text`, `write.key`, `write.answer`, `strike(id)`, `page.new(carry)` | `write.eq` passes through CAS verification before it is drawn (see 2.2). |
| Control | `pause(ms)`, `mode(split\|slide_full\|notebook_full)` | Mode switches at most once per concept (doc 10). |

Wire format: one JSON schema, `contracts/board-ops.schema.json`, with `{op, args, at: {word_index | ms | "now"}, id}`. The precompute manifest becomes a recorded op stream with `at.ms`. `board_events.py` and the 28 manifest event types map almost one-to-one; this is a rename and a merge, not a rewrite.

**Board state serializer (the LLM's eyes).** ≤300 tokens, regenerated per turn: active figure id and title; entity list as `id (kind): semantic`; current focus; last 8 notebook lines with ids; page number; figure-history ids. This replaces the deleted ASCII snapshot with something the model is actually good at reading (a list of named things), which is what doc 09 concluded LLMs can handle.

### 2.2 Geometry and math kernel (accuracy by construction)

**Geometry kernel.** Take the helpers in `canvas_dsl.py` and make them the *runtime*, not a generation-time convenience: `polar`, `perpendicular_to`, `parallel_at_distance`, `intersect`, `tangent_to`, plus `foot`, `reflect`, `project`, `angle_at`, `circle_through`, `arc_between`, `fit_to_viewbox` (auto-scale a construction to the slide so the LLM never chooses coordinates or sizes), and a label placer (outside normal of a segment, nudged away from other labels, using the live `getBBox` from doc 16 Phase 1). Port it to TypeScript (about 600 LOC) so morphs and sliders are exact on the client, and keep the Python copy for precompute and the sandbox. A shared fixture suite runs both.

*Alternative worth a two-day spike:* **JSXGraph** (MIT/LGPL) is a constraint-based construction engine built for maths education: dependent points, intersections, sliders, function graphs, and it re-solves on parameter change. It is essentially this kernel plus a renderer. Risks: its rendering is its own SVG, not our rough/stroke-reveal look; integration means using it as the *solver* and drawing with our renderer, or theming it. Decide after the spike.

**Figure templates (the fast path).** A template is a parametric construction with declared roles, build-up stages, and domain conventions baked in. The physics rules that LLMs get wrong at 2 a.m. are encoded once:

- Free body: weight always down from the centre of mass; normal perpendicular to the contact surface; friction along the surface opposing relative motion; tension along the string.
- Optics: the three principal rays for a thin lens; image location from the lens equation, not from guessing.
- Circuits: series and parallel from a netlist; current arrows consistent; meters placed correctly.
- Geometry: right-angle marks, congruence ticks, angle arcs from the actual angle.
- Kinematics: trajectory from the equations; velocity components at any `t`.

Target coverage: about 60 templates covers most of IGCSE 0580 + 0625 teaching visuals; about 150 covers JEE-level maths and physics. Seed from the 7 frontend templates, the 5 `canvas_dsl` composites, and the legacy `scene/components` library (circuits, optics, geometry, chemistry). Each template costs about 30 tokens to invoke and renders in under 100 ms, exactly.

**Retrieval (the second path).** Index the 760 precomputed diagrams and every generated spec by concept id and by embedding of the visual intent. A hit is a 50 ms fetch. Strategy 02's cross-session Redis cache becomes this index.

**Draw-on animation for constructed elements.** Every op that adds a stroke (segment, arc, circle, curve, vector, handwriting) animates by path length with the existing dash technique used by `TraceOverlay` and the Hershey text, paced to the op's duration. Design-diagram elements only fade today; a figure that draws itself while the teacher talks is the difference between a display and a hand.

**Generation (the third path, never on the hot path).** For novel figures the hands write a **compact line DSL**, not JSON:

```
tmpl ramp angle=30 length=6
body block on=ramp t=0.55 w=1.2
vec W  at=block dir=down mag=2 label="W = mg"
vec N  at=block dir=perp(ramp) mag=1.7 label="N"
vec f  at=block dir=along(ramp,up) mag=1 label="f"
angle theta at=ramp.base from=ground to=ramp
```

Six lines, about 90 tokens, exact geometry. Each line is a complete op that executes as it arrives, so the first stroke appears about one second after the request and a 30-element figure streams in over a few seconds while the teacher is still talking about the previous beat. The JSON DiagramSpec survives only as a *storage* and *interchange* format the DSL compiles to.

**Math engine.** A small SymPy service (in the worker process, async via a thread pool) with three calls:

- `verify(prev_latex, next_latex, context) -> {ok, reason}`: equivalence (`simplify(lhs - rhs) == 0`), or a named transformation (expand, factor, substitute, divide both sides), or numeric spot-check at random points when symbolic fails. Wrong steps are **never drawn**. The op returns an error to the teacher, which re-derives. This is doc 03's "never show an unvalidated thing", applied to algebra, at ~10 ms instead of a Haiku call.
- `units(expr)` with Pint for dimensional consistency on physics equations.
- `solve / simplify / latex` for the teacher to ask for a result rather than compute it in its head.

**Physics simulation.** `sim.projectile`, `sim.pendulum`, `sim.spring`, `sim.collision_1d`, `sim.circuit_dc` with a deterministic fixed-step integrator (or matter.js for contact-heavy cases). Parameterised, pausable, scrubbable. "Let's actually watch it" is the single strongest physics-teaching move a board can make, and it is cheap once the figure is an entity scene.

### 2.3 The streaming teacher loop

**One turn, two channels, one stream.** The teacher model's output is speech with inline ops:

```
Let's put the ladder against the wall. <op>figure.template("right-triangle-trig",{theta:60,hyp:10},build="staged")</op>
The ladder is the <op at="hypotenuse">focus("hypotenuse")</op>hypotenuse, ten metres.
The question is how high it reaches, so we want the <op at="opposite">focus("opposite")</op>opposite side.
Sine is opposite over hypotenuse: <op>write.eq("\\sin 60^\\circ = \\frac{h}{10}", group="g1")</op>
so <op>write.eq("h = 10 \\sin 60^\\circ", group="g1")</op> and <op>write.eq("h \\approx 8.66\\,\\text{m}", group="g1", boxed=true)</op>
```

The `<op>` tag is the existing action-tag idea (deleted with the old worker) widened to the full vocabulary. The parser fires an op the moment its closing tag arrives; the text between tags goes to TTS sentence by sentence. On Anthropic models, the same can be done with fine-grained tool streaming (`eager_input_streaming: true`) if you prefer tool calls to tags; tags are cheaper in tokens and simpler to interleave, tool calls are validated by schema. Use tags for annotate/morph/notebook ops (fail-silent is fine, per doc 16 Phase 4) and strict tools for figure requests and anything that changes state irreversibly.

**Three sync tiers.**

1. *Draw-then-say* (default, most ops): the op fires when parsed, which is naturally 200 to 600 ms before the words are spoken because TTS trails the token stream. This is doc 02's "90% case".
2. *Word-anchored* (`at="word"`): the worker already owns the audio clock. It pushes every frame through `AudioSource.capture_frame`, so it knows to the millisecond how much audio has been played out (minus a fixed jitter-buffer offset, measured once). Cartesia returns word timestamps for the synthesized sentence; the scheduler dispatches the op when the anchor word's timestamp is reached. Accuracy about ±150 ms. This removes the reason doc 16 deferred Tier B, and it also lets you synthesise whole sentences again instead of one TTS call per fragment, which fixes the prosody breaks and the extra TTFA per fragment in today's `deliver_resolution`.
3. *Precomputed* (`at.ms`): exact, as today.

**Anticipation, properly fed.** The plan (kernel `ConceptTeachingPlan` today; doc 19's `DiagramRequirement` with `required_elements`) names each beat's visual intent. Before beat *n* starts speaking, the hands resolve beat *n+1*'s intent to `template | retrieved | generated` and the result is already in the runtime's figure store. `figure.request` from the teacher mid-flow is the exception path, not the norm. The old anticipation engine failed because it matched prompts by Jaccard (doc 07); match by plan slot id, which is what doc 07 recommended.

**Model roles and settings.**

| Role | Model | Why |
|---|---|---|
| Teacher | `claude-sonnet-5` by default; `claude-opus-5` with fast mode for premium tiers | Streaming, prompt-cached system + template catalogue + lesson plan; effort `low`/`medium` for turn latency. On Opus 5 the board state goes in as a mid-conversation system message so the cached prefix survives every turn. |
| Hands | `claude-haiku-4-5` (about 90 tok/s, $1/$5) | Writes compact DSL from a visual intent + template catalogue; the kernel computes; a deterministic QA pass (element count, overlap, required elements) gates it. Later: a fine-tuned open model on vLLM per strategy 03, at 200+ tok/s. |
| Planner | `claude-sonnet-5`, structured outputs | Async, per concept, ahead of time. Unchanged from the kernel. |
| Judge | offline only | Doc 19's quality gate. Never in the live loop. |

**Speech-to-speech models: not yet, and here is the reason.** GPT-realtime and Gemini Live give ~200 to 300 ms first-audio latency and excellent turn-taking, but their function-calling accuracy is around 66% on OpenAI's own benchmark, and they cannot interleave dozens of precise ops inside an utterance. A tutor that mis-fires a third of its board actions is worse than one that answers 800 ms later. Keep the cascade (Deepgram → text LLM → Cartesia), shave it (Deepgram Flux or LiveKit's turn detector for end-of-turn, streaming everywhere, prompt cache at 90%+), and revisit S2S for the *student-teaches* mode (doc 20) where the AI mostly listens.

---

## 3 · Budgets this design meets

| Event | Today | Target | How |
|---|---|---|---|
| Annotation (focus/trace/point) lands | inert on frontend (`04cec94`); when it worked, ~800 ms | ≤ 300 ms, ±150 ms to the spoken word | inline op + word-anchored dispatch |
| Notebook line appears | precomputed only | ≤ 400 ms after the teacher decides, paced to speech | inline `write.*`, handwriting reveal |
| Template figure | < 1 frame (7 templates) | < 100 ms (60 → 150 templates) | kernel + template library |
| Retrieved figure | n/a live | ~50 ms | concept + embedding index |
| Novel figure, first stroke | 5 to 15 s (43 to 51 s measured) | ~1 s, complete in 4 to 8 s, hidden behind narration; 0 s when anticipated | compact DSL streamed op-by-op by Haiku; plan-slot anticipation |
| Algebra step correctness | unchecked | 100% of drawn steps verified | SymPy `verify` before `write.eq` |
| Geometry correctness | LLM-computed | exact by construction | kernel resolves all placement |
| Voice round trip | 1.5 to 3 s | 1.0 to 1.8 s | streaming, turn detector, cached prompt |
| Cost delta | – | +20 to 30% teacher output tokens; hands ~$0.004/figure | ops are short; generation is rare |

---

## 4 · What this deliberately does not do

- **No 2D layout intelligence.** Docs 06 and 09 built it and doc 10 deleted it. The slide is one figure, auto-fitted; the notebook is a column. Ops are relational; the renderer places.
- **No full DiagramSpec generation on the hot path.** It becomes a storage format and a precompute output.
- **No vision model in the loop per op.** Doc 14's argument holds: the structure is known at creation time. Vision (Haiku or later VL-JEPA) stays an offline QA and a drift check.
- **No speech-to-speech teacher** (see 2.3).
- **No Manim live.** Manim renders video offline in seconds to minutes; use it for precomputed animation assets if ever, not for the board.
- **No canvas app (tldraw, Excalidraw) as the board model.** They are human drawing tools; their shape records are a reasonable *reference* for an entity scene, but the value here is the kernel and the op contract, not the canvas.
- **No image generation.** Symbolic precision is the whole point (§7).

---

## 5 · Tools and libraries

| Need | Recommendation | Why | In repo? |
|---|---|---|---|
| Vector rendering | SVG + React (keep) | crisp, addressable elements, `getBBox` | yes |
| Hand-drawn feel | rough.js, perfect-freehand, Hershey fonts + GSAP dash reveal (keep) | already built; cheap | yes |
| Equations | KaTeX (keep); use `\htmlClass`/`\htmlId` with `trust` to make terms addressable for term-level focus | term spans for pointing at "the h" | yes (needs trust flag) |
| Geometry construction | own kernel ported from `canvas_dsl.py` to TS; spike **JSXGraph** as solver | exact, constraint-based, sliders | partial |
| Function graphs | keep the visx/`RoughGraphContent` path; **mafs** (React) or JSXGraph if you want pan/zoom and dependent objects | fast, declarative | yes |
| CAS / verification | **SymPy** (server), **Pint** (units); optional **nerdamer**/mathjs client-side for numeric checks | correctness gate | no |
| Physics simulation | small fixed-step integrator in TS; **matter.js** or **planck.js** for contact-heavy scenes | "watch it happen" | no |
| 3D (later) | react-three-fiber | vectors in 3D, fields | no |
| Voice | LiveKit Agents (keep); Deepgram nova-3 + Flux/turn-detector; Cartesia Sonic-3 with `add_timestamps` | TTFA ~190 ms, word timing | yes (flag off) |
| LLM | Anthropic: streaming, prompt caching, `eager_input_streaming`, structured outputs, strict tools, mid-conversation system messages (Opus 5), fast mode (Opus 5) | the loop in 2.3 | partial (models pinned to Sonnet 4 today) |
| Retrieval | existing Neo4j + sentence-transformers; Redis for the shared figure cache | strategy 02 A5 | partial |
| Offline animation assets | Manim (LLM2Manim-style pipeline) only for precompute | out of the hot path | no |

---

## 6 · Migration plan (reuses the existing code at every step)

**Phase 0 (about 1 week): fix the eyes and the clock.**
Restore the focus dimming and `point_at` on the frontend with an opacity-per-element treatment (doc 18's design) rather than an SVG mask, resolving positions from the live DOM as `TraceOverlay` does. Turn on `use_tts_aligned_transcript` / `add_timestamps` in `pipeline.py:create_tts`. In `doubt_delivery.py`, synthesise whole sentences and schedule marker ops by word timestamp from the worker's audio clock instead of splitting TTS per fragment. Measure ±ms against the spoken word with a test sentence. *Test:* a 40-sentence doubt with 20 markers lands every marker within ±200 ms; no audible seams.

**Phase 1 (2 to 3 weeks): one op contract.**
Write `contracts/board-ops.schema.json` and retire `contracts/visuals.schema.json`. Map the 28 manifest events and `board_events.py` onto it (mostly renames). Make `useExtractionPlayback` and the doubt path consume the same op stream. Add the entity scene to the slide (`SlideState` grows an entity map keyed by semantic id) and the board-state serializer. Because the runtime now paginates the notebook itself, the precompute pipeline's headless-Playwright measurement step (`manifest_composer/measurement.py`) and stamped pixel `placement` become unnecessary; keep them behind a flag until parity is proven. *Test:* an existing chapter plays back byte-identically through the new path; the serializer for any slide is ≤300 tokens and round-trips ids.

**Phase 2 (2 to 3 weeks): kernel and templates.**
Port `canvas_dsl.py` helpers to TS with a shared fixture suite; add `fit_to_viewbox` and the label placer; convert the 7 templates + 5 composites + the legacy `scene/` components into parametric templates with roles and build-up stages; write the compact line DSL parser (server and client) that compiles to ops. *Test:* every template renders in <100 ms, every role resolves, geometric invariants hold under parameter sweeps (right angle stays right, normal stays perpendicular).

**Phase 3 (2 weeks): the streaming teacher loop for doubts.**
Replace the doubt beat delivery's fixed `narration_text` with a streaming Sonnet 5 turn that emits speech + inline ops against the board state; keep the planner ahead. Hands = Haiku 4.5 writing the line DSL for `figure.request`, gated by deterministic QA. Anticipate from plan slots. *Test:* p50 op-to-board ≤300 ms; novel figure first stroke ≤1.5 s; zero pixel coordinates in any LLM output.

**Phase 4 (2 weeks): the math gate and simulations.**
SymPy service; `write.eq` verification with a re-derive loop; Pint on physics equations; `sim.*` ops for projectile, pendulum, spring, DC circuit. *Test:* 200 seeded wrong steps are all rejected before drawing; 200 correct steps pass; sims match closed-form solutions to 1%.

**Phase 5 (ongoing): live teaching on the same loop, and the eval harness.**
Bring back a live mode as "the doubt loop, running the lesson plan", not as a resurrection of the deleted 40-tool agent. Build the evaluation set: latency percentiles per op type, geometric invariants, CAS pass rate, and a human-rated "did the board say what the voice said" score on 50 recorded sessions.

Rough total: 10 to 12 weeks for one engineer to Phase 4, in parallel with the curriculum pipeline.

---

## 7 · Research and capabilities worth tracking (as of September 2026)

**Real-time voice.** OpenAI gpt-realtime-2.x and Gemini 3.1 Flash Live are true speech-to-speech models with ~200 to 300 ms first audio and native tool calling, but tool-call accuracy is still well below text models (OpenAI reports 66.5% on its own function-calling benchmark). The right use for Feynman today is turn-taking naturalness and the listening-heavy student-teaches mode, not driving the board. Cascaded pipelines with Cartesia Sonic-3 (~188 ms TTFA) and ElevenLabs Flash v2.5 (~260 to 290 ms) with word timestamps remain the precise option. Sources: [Gemini Live API overview](https://ai.google.dev/gemini-api/docs/live-api), [GPT-Realtime-2 vs Gemini Live (2026)](https://webscraft.org/blog/gptrealtime2-vs-gemini-live-api-scho-obrati-dlya-golosovogo-agenta-u-2026-rotsi?lang=en), [Speech-to-speech landscape](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/speech-to-speech-realtime-api-gemini-live-seamless), [Cartesia TTS plugin, LiveKit](https://docs.livekit.io/agents/integrations/cartesia/), [Cartesia WebSocket TTS](https://docs.cartesia.ai/api-reference/tts/websocket), [TTS API comparison 2026](https://gradium.ai/content/best-text-to-speech-api-voice-agents).

**LLM diagram generation, measured.** The 2025 to 2026 benchmarks converge on one finding: text-to-code (TikZ, SVG, a DSL) beats text-to-image on symbolic precision, and even frontier models still make geometric errors when they compute coordinates themselves. That is the empirical case for a kernel that computes and an LLM that specifies. Read: [Math-Vision Diagrams benchmark (2026)](https://arxiv.org/html/2608.08964), [DiagramEval](https://arxiv.org/pdf/2510.25761), [AutomaTikZ](https://arxiv.org/pdf/2310.00367), [SciFig](https://arxiv.org/pdf/2601.04390), [EduIllustrate](https://arxiv.org/pdf/2604.05005), [Evaluating LLMs on vector graphics (EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.213.pdf).

**Pedagogy-aware animation.** [LLM2Manim](https://arxiv.org/html/2604.05266) is a human-in-the-loop LLM → Manim pipeline that applies segmentation, signalling, and dual coding. Useful as a precompute asset generator and as a source of choreography heuristics, not as a real-time renderer. DrawDash-style "whiteboard assistant" work (proactive diagram completion) is the closest research to the hands.

**Anthropic API features that matter for the loop.** Streaming with fine-grained tool input streaming (`eager_input_streaming`), prompt caching (target 90%+ cached input on the teacher), structured outputs and strict tools for the planner and figure requests, mid-conversation system messages on Opus 5 for per-turn board state without cache invalidation, fast mode on Opus 5 for ~2.5x output speed, Haiku 4.5 at ~90 tok/s for the hands. Sources: [Haiku 4.5 overview](https://platform.claude.com/docs/en/models/haiku-4-5/overview), [Reducing latency](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency), [Artificial Analysis, Anthropic](https://artificialanalysis.ai/providers/anthropic).

**Small specialised models for the hands.** Strategy 03's fine-tuning track applies directly: distil Sonnet's DSL outputs into a 7B to 14B open model served with vLLM and speculative decoding; expect 200+ tok/s and a novel figure in 2 to 4 s. Do this after the DSL and template catalogue are stable, because the training data is the DSL.

**Perception.** Keep the Haiku drift check offline or at low cadence; VL-JEPA-style self-hosted perception (doc 16 5b) becomes relevant only once the board is an entity scene, because then "what should be there" is a structured target to compare against.

---

## 8 · Decisions for Yash

1. **Tags vs tool calls for inline ops.** Recommendation: tags for annotate/morph/notebook, strict tools for `figure.*` and `page.new`.
2. **Own kernel vs JSXGraph.** Recommendation: two-day spike on JSXGraph as solver-only; if theming is painful, port `canvas_dsl.py`.
3. **Teacher model tier.** Sonnet 5 default, Opus 5 fast mode as a paid tier. Pin models in `pipeline.py` and `diagram_generator.py` off Sonnet 4.
4. **Template coverage target for v0.** 60 for IGCSE maths + physics is the number I would commit to before touching JEE.
5. **Sequencing against the curriculum pipeline.** Phases 0 to 2 here are independent of it and make its Phase 12 (visual pre-generation) produce ops/templates instead of monolithic specs.
6. **Room pre-connect.** The lazy LiveKit connect saves cost but puts room creation, agent dispatch, and a Neo4j chapter load in front of the first doubt. Recommendation: connect on the first pause or the first hover over Ask Feynman, not on the tap.
