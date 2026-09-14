# Design Doc 22 — Accurate Real-Time Writing, Drawing and Manipulation: Research Findings and Build Plan

**Status:** Research report + actionable plan. Written 2026-09-14.
**Question answered:** How do we build a tutor that, while speaking, accurately writes, draws, and manipulates what it drew (changes parts and state, points and highlights, annotates around a specific part), for maths and physics first, and how do we make it robust.
**Relationship to doc 21:** Doc 21 set the architecture (ops, kernel, streaming loop). This doc grounds each part of it in published results and turns it into a build plan with gates. Where the two differ, this doc wins.
**Method:** Three parallel literature and tool reviews (2024 to September 2026 papers, official docs, license files), plus direct reads of the key 2026 papers, plus a profile of our own 292 extracted diagrams. Every non-obvious claim carries a URL in §12.

---

## 0 · The answer in one paragraph

Every capability you asked for is feasible today at teaching quality, provided one rule is never broken: **the language model decides *what* to draw and *when*; deterministic code decides *where* and *whether it is correct*.** The 2025 to 2026 literature is unusually consistent on this. When frontier models emit executable construction commands and a kernel computes the geometry, they reach 79 to 83 percent on textbook constructions (GeoBuildBench, GGBench); when they emit images or free coordinates, they fall to the 20s to 40s, and their most common errors are label omission and coordinate miscalculation that "survive compilation" (Math-Vision Diagrams, MathemaTikZ). When a symbolic solver enforces the physics before rendering, force-diagram correctness rises from about 80 to about 95 percent and mean angular error drops from over 2 degrees to 0.4 degrees, in under a second per figure (PhyDrawGen). Editing free-form SVG or TikZ is the weakest capability of all (15 to 28 percent spec-faithful), which is why manipulation must be structured ops on a named scene, never text edits. And the learning science says the *timing* of a stroke or a highlight relative to the spoken word is worth more than the choice of cue, that pointing should lead the word by about 200 ms and never trail it by more than 400, and that a visible drawing agent (a pen cursor) is what makes progressive drawing pay off. The plan below follows from those facts.

---

## 1 · Feasibility matrix: what is accurately achievable, and how

| Capability | Feasible now? | How it is done accurately | What breaks it | Evidence |
|---|---|---|---|---|
| **Write** equations and working, line by line, paced to speech | Yes, fully | Model emits LaTeX per line as an inline op; KaTeX renders; a CAS check runs before the line is drawn; reveal is paced to TTS word timestamps with a visible pen cursor | Letting the model do arithmetic in its head; drawing unverified steps | Step-based tutors d = 0.76 vs answer-based ≈ 0.3 (VanLehn 2011); Andes "colour-by-numbers" verification; STACK CAS equivalence + form tests |
| **Draw** geometry (triangles, circles, tangents, constructions) | Yes, with a kernel | Model emits construction commands over named entities; kernel computes coordinates; auto-fit to the slide; declared constraints checked numerically | Model emitting pixel coordinates or angles it computed itself | GeoBuildBench 78.9% (GPT-5.1) with kernel + verifier loop; GGBench human score 83 for code vs 46 for image models; AlphaGeometry's construction language is correct by construction |
| **Draw** physics figures (free-body, ray, circuit, field) | Yes, with a solver | Model emits a typed scene graph (objects, surfaces, forces, constraints); a solver enforces ΣF = 0, normal ⟂ surface, Snell, thin lens, netlist topology; then render | Asking the model to place arrows | PhyDrawGen: 94.7% vector-correct vs 79.7% GPT-5-image; 0.4° vs 2.2° angular error; < 1 s/figure |
| **Draw** function graphs and plots | Yes, fully | Expression + domain; plotting is deterministic | None of note | Standard |
| **Change minute parts and state** of an existing figure | Yes, if the figure is an entity scene with dependencies | Entities are named; parameters drive dependent geometry; `param.set`, `entity.move(to=<construction>)`, `entity.style`, `erase`, `replace` re-solve the scene | Figures stored as flat SVG with baked coordinates (today's DiagramSpec); asking a model to edit SVG text | Vector-Bench: spec-faithful SVG repair 15%; vTikZ 28%; models "rewrite globally and cannot locate the target feature" |
| **Point and highlight** a part while explaining | Yes, fully | Op targets an entity id; renderer resolves pixels from the live DOM; dispatch scheduled to the spoken word, leading it by ~200 ms | Bounds estimated by the LLM (doc 16 fixed this); firing only at sentence boundaries | Signalling g ≈ 0.3 to 0.5; temporal contiguity d ≈ 0.87 to 1.22; gesture-stroke lead ≈ 200 ms; delay > 400 ms erases the benefit |
| **Point at a sub-term** of an equation | Yes | MathJax 4 semantic enrichment stamps every node with `data-semantic-id/type/role`; ops target `math:eq-3/exponent` | Equations as opaque images | Speech Rule Engine, Apache-2.0 |
| **Annotate around a part** (circle, underline, brace, arrow, margin note) | Yes, fully | Annotation ops take entity targets; freehand paths generated from live bounds (already in `annotation-paths.ts`); drawn in with a dash animation; strict cue budget | Annotations that accumulate (doc 18) | SketchVLM: tagged overlays on an existing picture at 4.6 px RMSE, 95.9% marker placement |
| **Erase and redraw**, recall an earlier figure | Yes | `erase(target)`, `figure.recall(id)` | – | – |
| **Run a live simulation** (projectile, pendulum, spring, circuit, ray) | Yes | `sim.*` ops on the entity scene with proper ODE solvers | 3D and contact-heavy scenes at first | myPhysicsLab (Apache-2.0), planck.js (MIT), ray-optics core (Apache-2.0) |
| **Novel figure the templates do not cover**, appearing instantly | Partly | First strokes in ~1 s by streaming construction commands; full figure in a few seconds; pre-generated when the plan knows it is coming; verifier loop for reliability | Expecting a 30-element novel figure whole in under a second | Nothing published draws accurate geometry live; EduIllustrate's "sequential anchoring" raises consistency 13% and cuts cost 94% |
| **3D solids and fields** | Later | react-three-fiber over the same entity model | – | 3D projection is the weakest category in Math-Vision Diagrams; PhyDrawGen limits itself to planar |

The honest boundary: accuracy is *by construction* for everything the kernel and solver cover, and *by verification loop* for novel constructions the model authors freely. So the first weeks of the plan make the covered set large.

---

## 2 · What the research says

### 2.1 Drawing and constructing: representation decides accuracy

| System / benchmark | Representation | Best result | Dominant failures | Read |
|---|---|---|---|---|
| AlphaGeometry / AlphaGeometry2 (DeepMind) | Construction language: `d = on_tline d b a c` (named constructions, predicates), numerically instantiated | AG2 solves 42/50 IMO problems; DDAR2 checks in 3.45 s | – | Constructions are correct by construction and cost a few dozen tokens; Newclid reimplements the engine with a Python API and GeoGebra file import |
| GeoBuildBench (2026) | Imperative construction DSL run by a Python kernel with explicit state; numeric constraint checks with tolerances; up to 5 verifier rounds | GPT-5.1 78.9%, Gemini-3-Flash 75.3%, Qwen3-VL-235B 42.2%, Llama-3.2-90B 21.3% | Undefined object references, unmet angle and incidence constraints | MIT; kernel reusable (`DSLExecutor`) |
| GGBench (CVPR 2026) | GeoGebra command code, 1,411 constructions with step snapshots | Code models: GPT-5 human 83.1, Claude Sonnet 4.5 72.1; image models: 45.8 and 20.1 | Misapplied theorems, containment confusion, syntax | "GeoGebra code acts as an unambiguous, machine-verifiable ground truth" |
| PhyDrawGen (2026) | LLM → typed scene graph (Object, Surface, Action, Force, Spatial, Constraint) → deterministic solver → planar straight-line graph → SVG | Vector correctness 94.7% vs 79.7% (GPT-5-image) and 57.9% (Gemini 3); label correctness 77.9% vs 47.1%; angular error 0.4° vs 2.2°; < 1 s on one RTX 4090 | Under-specified inputs; planar only | The exact decomposition doc 21 proposed, with numbers |
| Math-Vision Diagrams (2026) | Free code (TikZ, SVG, matplotlib) vs image models, 2,920 competition diagrams | Best code: Claude Opus 4.6, 89.1% compile; best image: Nano Banana Pro, 99.6% "compile" but worse structure | Label hallucination/omission (most common), coordinate/scale miscalculation ("survives compilation"), topology, 3D | Recommends hybrid code-first pipelines |
| MathemaTikZ (L@S 2025) | TikZ from K-12 descriptions | Compile 80 to 96% but mathematically correct only 12 to 74% depending on description quality | Spatial placement, constraint violations (angles not summing to 180°), 3D | Compile ≠ correct |
| DiagramIR (NeurIPS MathAI 2025) | Back-translate TikZ to an IR, run deterministic checks | κ 0.48 to 0.56 with humans vs 0.39 to 0.50 for LLM-as-judge | – | Our IR is native; the six checks are free |
| TheoremExplainAgent (ACL 2025) | Planner → Manim coder → compile-fix loop | o3-mini 93.8% success with 5 retries; 1,120 to 2,380 s per video | API hallucination, LaTeX, layout | Offline only |
| SketchAgent (CVPR 2025) | Stroke-by-stroke on a 50×50 numbered grid | Human-like, but ~8 s per stroke, no text | – | Grid addressing is a good idea; the latency is not |
| Whiteboard-of-Thought, Visual Sketchpad, MathCanvas | Code or pixels as a reasoning aid | Big reasoning gains; MathCanvas 21.9% on its own bench vs 47.9% for text-only Gemini 2.5 Pro | – | Drawing-to-reason ≠ drawing-to-teach |

Ranking by accuracy, consistently across papers: **construction DSL > code with coordinates > image generation**. TikZ has the most training data (DaTikZ-v2, 360k programs) and is what models spontaneously choose, but coordinate arithmetic and label placement are its top failures.

### 2.2 Editing what is already drawn: the weakest capability, unless it is structured

Vector-Bench (2026): surgical SVG repair passes the full spec on 15.0% of tasks for the best model (Claude Sonnet 5); 37.8% of attempts hit output-length limits because models rewrite the whole file. vTikZ: 28% success editing existing TikZ with five attempts, errors dominated by "feature not found" and unintended modifications. VectorGym and SVGenius show the same shape. GeoSVG-RL and Render-in-the-Loop improve structure by putting a renderer and a geometric reward in the loop.

Conclusion: "change a minute part" must be an op on a named entity in a scene graph (`entity.set`, `param.set`, `erase`, `replace`), executed by our runtime. A model must never be asked to edit SVG or TikZ text.

### 2.3 Pointing and annotating on an existing picture: feasible now

SketchVLM (2026): a VLM emits tagged primitives (rectangles, arrows, text, lines, Béziers) rendered as non-destructive overlays on an existing image; Gemini 3 Pro places connect-the-dots points at 4.6 px median RMSE with 95.9% marker-placement accuracy. In our case the targets are named entities with live bounds, so localisation is exact rather than estimated. This is the closest published evidence that "circle this part while I talk" works.

### 2.4 Learning science: what the board should do, with effect sizes

- **Temporal contiguity** (narration and the corresponding visual at the same moment): d ≈ 0.87 (Ginns 2006), median d = 1.22 in Mayer's tally. The single largest lever in the multimedia literature.
- **Signalling/cueing** (highlight, arrow, spotlight): retention g = 0.52, transfer g = 0.31 across 103 studies (Schneider et al. 2018); d ≈ 0.38 (Alpizar 2020). Stronger for novices.
- **Dynamic drawing**: watching a diagram drawn progressively beats the finished diagram, d = 0.35 to 0.58 (Fiorella & Mayer 2016; 2019 d = 0.54), **but only when a hand or at least a moving cursor tied to the narration is visible**. Hand-less self-animating diagrams were non-significant twice (Exp 3 d = −0.16; Exp 5 d = 0.33 n.s.) and a 2024 replication found a moving cursor equivalent to a drawing hand.
- **Deictic pointing** by the instructor: g ≈ 0.28 to 0.31 (2024 meta-analysis, 83 articles); pointing keeps eyes on content (Pi et al. 2019).
- **Segmenting**: d ≈ 0.4 (Rey et al. 2019). One new element per spoken clause.
- **Engagement**: Khan-style tablet drawing watched 1.5 to 2× longer than slides (Guo, Kim & Rubin 2014); continuous writing motion sustained engagement even at slow speech.
- **Gesture-speech timing**: the stroke leads the word by about 193 ms (ter Bekke 2024; Ferré 2010: 454 ms; Donnellan 2022: 370 ms); viewers tolerate early cues but detect late ones; a 500 ms delay reduced recall to the no-gesture level with a sharp decline after 400 ms.
- **Stroke speed**: no learning study; handwriting norms put fluent pen travel at 50 to 100 mm/s. Heuristic: a stroke group finishes within the clause that describes it.

### 2.5 Voice-visual synchronisation tooling

- **Word timestamps in streaming TTS**: Cartesia (`add_timestamps`, per-word start/end), ElevenLabs (per-character alignment, per-chunk offsets you must accumulate), Azure (WordBoundary events), Rime. Google Chirp 3 HD does not support SSML marks in streaming; OpenAI TTS has no timestamps. Kokoro exposes token timestamps in the PyTorch build (relevant for precompute).
- **LiveKit Agents 1.x**: `use_tts_aligned_transcript=True` yields `TimedString` chunks with `start_time/end_time` relative to the turn; with `json_format=True` the client receives `{"text","start_time","end_time"}` on the `lk.transcription` topic; only Cartesia, ElevenLabs and Rime give word-level timing. No client SDK exposes audio playout position; the browser must calibrate an offset. LiveKit text streams have no size limit and are ordered; data tracks carry a 64-bit user timestamp per frame.
- **Forced alignment as fallback**: NeMo Forced Aligner reaches 98.4% precision/recall at a 200 ms collar at 149 to 308× real time on GPU; MFA 3.0 is ~20 ms accurate but slow; WhisperX word boundaries average 110 ms error.
- **End of turn**: budget 300 to 600 ms (LiveKit eot-bench: turn detector 543 ms at a 5% false-cutoff budget, 295 ms at 10%).

### 2.6 Verification

- **Geometry**: AlphaGeometry and Newclid instantiate every construction numerically and check predicates on the sampled diagram; GeoBuildBench checks metric and angular conditions under tolerances, normalised to scale. Do this for every figure we draw.
- **Algebra**: Andes' "colour-by-numbers" substitutes the known solution values (random values for free parameters) into the student's equation and accepts it iff both sides balance, after a dimensional-analysis pass; it is provably equivalent to algebraic derivability and cheap enough to try many perturbations. STACK uses Maxima `simplify(ex1-ex2)=0` plus form tests (factored, simplified). Cognitive Tutor model tracing matches steps to production rules.
- **Vision judges**: BlindTest: GPT-4o 50.2% on trivial geometry (intersections 41.6%, overlapping circles 41.3%); VisOnlyQA: frontier models near random on angles and triangle properties; MLLM-as-a-Judge: pairwise agreement 82% but absolute-score Pearson 0.49. Judges can rank, not score. Never certify geometry with a VLM.

---

## 3 · Architecture for accuracy (the "how", concretely)

### 3.1 The entity scene: the object the tutor manipulates

A figure is a typed graph, not an SVG. Minimal schema (TypeScript on the client, Pydantic on the server, one JSON schema):

```
Entity { id: "F_normal", kind: "vector", role: "normal_force",
         construction: {op: "perp_from", args: ["block.center", "ramp"], length: "N"},
         style: {...}, label: {text: "N", side: "outside"}, deps: ["block", "ramp"] }
Figure { id, entities: Entity[], params: {theta: 30, mu: 0.4}, history: Op[], stage: number }
```

Every entity has a **construction**, not coordinates. Coordinates are derived by the kernel and cached. When a parameter or an upstream entity changes, dependents re-solve in topological order (the GeoGebra/JSXGraph model). This is what makes "change a minute part" a fifteen-token op instead of a regeneration, and it is the structured alternative to the SVG editing the literature shows failing.

Role vocabulary must be controlled. Our corpus today has 457 distinct roles across 292 diagrams; `label` alone is 448 entries. Adopt a closed ontology per domain (about 40 roles for geometry, 30 for mechanics, 20 for optics, 20 for circuits, 15 for graphs), validated at op time. Unknown roles are rejected with a suggestion; ambiguous roles within one figure are rejected with the candidates. That is the fix for the "six elements with role=object" targeting failure in doc 19 and for GeoBuildBench's dominant failure, undefined references.

### 3.2 The geometry kernel

Construction commands (the model's vocabulary; every argument is an entity reference or an expression over params, never a pixel):

```
point P at=(expr, expr) | on(seg, t) | midpoint(A,B) | intersect(l1,l2) | foot(P, seg) | polar(O, r, θ) | reflect(P, l)
line_pp A B | line_pd P dir | perp_from P seg | parallel_from P seg | bisector A B C
segment A B | ray A dir | circle_cr O r | circle_cp O P | circle_3p A B C | arc O A B | tangent_from P circle
angle at=B from=A to=C | right_angle_mark at=B | tick seg n
polygon A B C … | curve f(x) domain=[a,b]
```

This is deliberately the shape of AlphaGeometry's and GeoBuildBench's languages: named objects produced by named constructions, and predicates you can check. Kernel responsibilities: solve constructions in dependency order; `fit_to_viewbox` (scale and translate the whole scene into the slide with margins, so no model ever picks sizes); label placement (outside normal to a segment, away from other labels, using live `getBBox`); numeric verification of declared constraints (incidence within 0.5% of scene size, angles within 0.5° checking both θ and 360−θ, equal lengths within 1%, parallel/perpendicular within 0.5°).

Engine choice (see §4 for licenses): build the kernel in TypeScript on `@flatten-js/core` (MIT) with `robust-predicates` for orientation tests, and render with our own React SVG (or Mafs, MIT, as a thin renderer). Port the geometric helpers from `canvas_dsl.py`. Keep JSXGraph (MIT option) mounted lazily as a fallback for loci and conics we have not implemented. Do **not** embed GeoGebra: its licence is non-commercial and commercial embedding requires a negotiated, fee-bearing agreement. Verify exactness server-side with `sympy.geometry` on the same construction when a step must be exact.

### 3.3 The physics solver (the PhyDrawGen pattern, implemented as templates)

For mechanics, optics and circuits the model emits a **typed scene graph**, and a solver produces geometry:

```
scene mechanics
  surface ramp incline=30 friction=0.4
  object block mass=2 on=ramp
  action static_equilibrium
  forces auto        # solver adds W, N, f with correct directions and consistent magnitudes
```

Solver rules, encoded once per domain: weight from the centre of mass, straight down; normal perpendicular to the contact surface at the contact point; friction along the surface opposing relative (or impending) motion; tension along the string; vector closure for equilibrium so drawn magnitudes are consistent; Snell's law and the three principal rays for lenses and mirrors (use the Apache-2.0 ray-optics simulator core headlessly for refraction and reflection paths); modified nodal analysis for DC circuits with consistent current arrows (a resistor-and-source MNA solver is under 200 lines; do not bundle GPL CircuitJS); field lines with correct topology. PhyDrawGen reaches 94.7% vector correctness and 0.4° mean angular error with this decomposition; ours needs no vision loop because the renderer is deterministic.

### 3.4 The math gate

Every `write.eq` passes through `verify(prev, next, transform?, solution_point?)` before it is drawn:

1. Parse LaTeX to SymPy with Math-Verify / `latex2sympy2_extended` (Apache-2.0, maintained; handles sets, intervals, matrices), with a small fallback grammar for syllabus notations.
2. If a named transformation is given (expand, factor, collect, substitute, divide both sides by k, apply identity), apply it symbolically and compare.
3. Equivalence: `simplify(lhs_next − lhs_prev) == 0` and same for rhs; for equations compare solution sets; for inequalities sign-aware. Add STACK-style form tests when the beat claims "simplified" or "factorised".
4. Andes-style numeric check: substitute the problem's known values and random values for free symbols at 20 points; accept iff both sides balance within tolerance. This catches what symbolic simplification cannot close and is nearly free.
5. Units: Pint over any expression carrying units; reject dimensional mismatch.
6. On failure, return `{ok:false, reason}` to the model as a tool error; the model re-derives; the wrong line is never drawn.

Latency 5 to 40 ms in-process in a thread pool; never on the audio path.

### 3.5 Pointing, highlighting and annotating: one target model

All attention ops take `target: {kind: id | role | math_id | region}`. Resolution order: entity id, then role within the active figure (must be unique), then a sub-expression id inside a notebook line, then a named region (margin notes only).

- `focus(target)` dims everything else by per-element opacity (no SVG mask), one focus at a time.
- `point_at(target, from=side)`: a pen cursor travels to the live bounding box and dwells. The cursor is the "visible agent" the dynamic-drawing studies require, so it also leads every stroke.
- `trace(target)`: re-draws the target's own geometry as a moving stroke.
- `annot.circle(target)`, `annot.underline(target)`, `annot.brace(a, b, text)`, `annot.arrow(a, b, text)`, `annot.margin(target, text)`, `annot.dim(a, b, text)`: paths generated from live bounds with perfect-freehand pressure curves (already in `annotation-paths.ts`), drawn in over 400 to 600 ms, held, then cleared by `unfocus()` or a per-kind TTL.
- Sub-term targeting in equations: render notebook lines with MathJax 4 plus `semantic-enrich` (Speech Rule Engine, Apache-2.0), which stamps every node with `data-semantic-id`, `type`, `role`, `parent`, `children`; the model targets `math:eq-3/exponent[1]`. KaTeX stays for the streaming hot path if MathJax proves too slow, with backend-injected `\htmlId` under `trust: true`; but KaTeX does not understand structure, so semantic ids would have to be computed server-side.

Renderer-enforced cue budget: one focus, at most three annotations, oldest fades first (doc 18's invariant, now enforced in code rather than in a prompt).

### 3.6 The drawing hand

Every stroke-producing op renders as a path-length dash animation **led by a pen cursor** that moves along the path at 60 to 100 mm/s equivalent (scaled to the slide) and finishes within the clause that describes it. Between strokes the cursor rests near the last stroke; on `point_at` it travels to the target. This is not decoration: the evidence says progressive drawing without a visible agent does not reliably help, and with one it does (d ≈ 0.35 to 0.58).

---

## 4 · Tools and libraries, with licences

| Need | Recommendation | Licence | Why | Avoid |
|---|---|---|---|---|
| Geometry kernel | Own TypeScript kernel on `@flatten-js/core` + `robust-predicates`; port `canvas_dsl.py` helpers; `sympy.geometry` server-side for exactness | MIT / Unlicense / BSD | Full control of command language, DAG, rendering; grammar-constrainable | GeoGebra (non-commercial only; paid term sheet for embedding); planegcs (LGPL, no dependency graph); Penrose (optimiser, ~500 ms, non-deterministic) |
| Geometry fallback | JSXGraph, lazily mounted | LGPL-3 or MIT (dual) | Mature dependent-object engine for loci, conics; ~950 KB core | – |
| Renderer | Our React SVG; Mafs as thin helper if useful | MIT | Every element is a React node: label, highlight, animate, sketchify | Plotly (1.3 MB); Desmos (partnership-gated terms) |
| Hand-drawn look and draw-on | rough.js (seeded), perfect-freehand, GSAP DrawSVG | MIT; GSAP free for commercial use since Apr 2025 | Already in the stack | handwriting-synthesis (no licence file) |
| Physics | myPhysicsLab simulation classes (pendulum, springs, collisions, energy) drawn into our SVG; planck.js for contacts; ray-optics `dist-node` core for optics; own MNA DC solver | Apache-2.0 / MIT / Apache-2.0 | Proper ODE solvers built for teaching; headless cores | CircuitJS1 (GPL, iframe only); PhET sims (GPL code; post-2026 terms unclear); rapier (1.4 MB WASM, overkill) |
| Equations | MathJax 4 + `semantic-enrich` for addressable sub-terms; KaTeX for the fast path; MathLive for student input (MathJSON out) | Apache-2.0 / MIT / MIT | Semantic ids make "the exponent" resolvable | – |
| CAS / verification | SymPy + Math-Verify (`latex2sympy2_extended`) + Pint | BSD / Apache-2.0 / BSD | Maintained; robust LaTeX parsing | Giac WASM (GPL, 12.8 MB); mathsteps (archived; fork for step explanations only); Wolfram (per-query fees, no caching) |
| Voice | LiveKit Agents; Cartesia Sonic-3 with `add_timestamps` (ElevenLabs as alternate); Deepgram nova-3 + LiveKit turn detector | – | Word timestamps stream with audio; `TimedString` support in the SDK | OpenAI TTS and Google Chirp 3 HD for the tutor voice (no usable timestamps) |
| Transport | LiveKit text stream on topic `board` with `{op, start_time, end_time}` chunks; data tracks with 64-bit timestamps when available | – | Ordered, unlimited size, per-topic handlers | 15 KiB data-packet limit for large figures |
| Constrained decoding (later hands model) | vLLM V1 with llguidance or xgrammar (Lark grammar for the DSL); EAGLE-3 or n-gram speculative decoding | MIT / Apache-2.0 | Guaranteed-valid ops; ~2× output speed | SGLang EAGLE + grammar (open bugs) |
| Anthropic API for the teacher and hands | Streaming; `eager_input_streaming` on figure tools; structured outputs for the planner; prompt caching with the board state as the volatile trailer | – | Ops visible before the tool call completes | – |

Licensing red flags to act on: GeoGebra (do not embed), Desmos API (terms unreadable; assume partnership required), PhET (GPL sim code; iframe with logo only), CircuitJS1 and Giac (GPL; never bundle), planegcs and Asymptote (LGPL; separately loaded modules only, confirm with counsel), Mafs (last release Oct 2024; vendor if used), Motion Canvas (MIT today, GPL switch under discussion; not needed).

---

## 5 · Voice-board synchronisation design

1. **Timestamps at the source.** TTS returns per-word times. The worker keeps `TimedString` spans for each sentence it synthesises.
2. **Ops anchored to words.** An inline op carries `at: {word_index | phrase, lead_ms: 200}`. The worker converts the anchor to turn-relative audio time `t_word − 200 ms`.
3. **Worker-side scheduling.** The worker pushes every audio frame itself, so it knows exactly how much audio it has emitted. It dispatches the op when its emitted-audio clock reaches the anchor time minus a calibrated playout offset.
4. **Client-side calibration.** At session start the client measures the offset between the worker's emitted-audio clock and local playout using `RTCRtpReceiver.getSynchronizationSources().rtpTimestamp` and pins `jitterBufferTarget` so the offset stays stable. Board messages also carry `start_time`, so the client can correct late arrivals (apply immediately) and early arrivals (hold until the local clock reaches the time).
5. **Fallbacks.** No timestamps from the provider → sentence-boundary timing (today's Tier A) and a CTC forced aligner offline to keep the eval honest. Precomputed lectures store `at.ms` directly.
6. **Target precision.** ±150 ms, measured continuously in the harness by forced-aligning the recorded output audio against the dispatched-op log.
7. **Never late.** The scheduler clamps: if an op would fire more than 400 ms after its word, it fires immediately and logs a miss.

---

## 6 · Evaluation harness (built in week one, run forever)

**Geometry correctness (deterministic).** Every figure's declared constraints checked numerically as in §3.2; parameter sweeps for templates across the full slider range.

**Physics correctness.** PhyDrawGen's metrics: vector-configuration success rate (every force present, direction within 5°), label-correctness rate, mean angular error; plus equilibrium closure error, ray-law violations, netlist equality.

**Diagram quality (DiagramIR's six checks, native because we own the IR).** Fully in frame; readable scale; labels associated with the right element; no problematic overlap (bbox intersection over min area below 10%); labelled angles and lengths match drawn ones.

**Algebra.** Drawn-step CAS pass rate must be 100% by construction; measure rejection rate, re-derivation success, and false-rejection rate on 500 seeded correct syllabus steps.

**Timing.** Per op type: p50/p95 from emission to paint; anchor error in ms between the op and the spoken word via forced alignment; first-stroke latency for novel figures; anticipation hit rate.

**Attention hygiene.** Simultaneous cues (≤ 1 focus + ≤ 3 annotations); TTL adherence; pen cursor present on every stroke.

**Vision judge (pairwise only).** Haiku or Gemini compares a new figure against the previous version for regressions and legibility; it never certifies geometry (BlindTest, VisOnlyQA).

**Human rating (weekly, 50 clips).** "Did the board show what the voice said?", "Was anything wrong?", "Did it feel like a teacher's hand?" on 1 to 5; two raters; track κ.

**Regression corpora.** GGBench (1,411 NL-steps + GeoGebra code + images, Hugging Face `OpenRaiser/GGBench`), GeoBuildBench (489 problems, MIT), Math-Vision Diagrams prompts for the geometry categories, PhyDrawGen's categories (author 300 IGCSE/JEE physics scenes if their set is not released), and our own 292 extracted diagrams re-authored as construction programs.

---

## 7 · Data plan

1. **Template seed.** Cluster the 292 corpus diagrams by role signature and title; author templates for the top 60 by frequency across IGCSE 0580/0625 and JEE Maths/Physics (FBD on incline, v-t and s-t graphs, projectile, circular motion, work at an angle, ray diagrams, series/parallel circuits, right-triangle trig, unit circle, AP on a number line, solids of revolution, band diagrams).
2. **Construction corpus for the hands.** Convert every template and corpus figure into construction programs; translate GGBench's GeoGebra code to our DSL by script (commands map nearly one-to-one); synthesise more the AlphaGeometry/GeoFM way (sample valid constructions from the kernel, render, write the brief backwards, verify by re-execution).
3. **Physics scene-graph corpus.** Enumerate parameter variations and textbook phrasings per template; the solver gives ground truth for free.
4. **Algebra step corpus.** Mine `book_examples` into (prev, next, transform) triples; label with the CAS; keep failures as the false-rejection test set.
5. **Timing corpus.** 100 delivered explanations with timestamps and dispatch logs, forced-aligned.

---

## 8 · The build plan (phased, with gates)

Each phase ends with a demo you can watch and a metric you can read. Later phases wait for earlier gates, except the harness, which starts on day one.

### Phase 0 — Instruments, the clock, and the hand (week 1)

1. Harness skeleton: op latency logger, anchor-error measurement via forced alignment, DiagramIR-style checks over the 292 corpus figures, a dashboard page.
2. Word timestamps on: `use_tts_aligned_transcript=True` and Cartesia `add_timestamps` in `pipeline.py:create_tts`. In `doubt_delivery.py`, synthesise whole sentences and dispatch `<<FOCUS>>`/`<<TRACE>>` at the anchor word minus 200 ms from the worker's emitted-audio clock, with client offset calibration.
3. Restore focus dimming and `point_at` with per-element opacity and live-DOM placement; add the pen cursor that leads every trace and pointer.

Gate: 40-sentence doubt with 20 markers, every marker within ±200 ms of its word and none late by more than 400 ms; no audible seams; corpus report shows today's overlap and off-frame rates.

### Phase 1 — One op contract and the entity scene (weeks 2–4)

1. `contracts/board-ops.schema.json`: doc 21 §2.1's vocabulary plus §3.5's target model; generate TS types and Pydantic models; delete `contracts/visuals.schema.json`.
2. Map the 28 manifest events and `board_events.py` onto ops; `useExtractionPlayback` and the doubt path consume ops; byte-for-byte replay test on three chapters.
3. Entity scene on the slide; existing DiagramSpecs import as flat figures so nothing on disk breaks.
4. Board-state serializer (≤ 300 tokens) and the controlled role ontology with validation.
5. Draw-on animation with the pen cursor for every stroke-producing op.

Gate: three chapters replay identically; every op has a renderer, a fixture and a latency measurement; the serializer round-trips ids for every corpus figure.

### Phase 2 — Kernel, physics solver, templates, sub-term maths (weeks 4–8)

1. Kernel v1 in TypeScript (flatten-js + robust-predicates): §3.2 commands, dependency DAG, `fit_to_viewbox`, label placer, numeric verifier; shared fixtures with the Python port used by precompute. JSXGraph mounted lazily as fallback.
2. Physics solver v1: mechanics (flat, incline, pulley, string), kinematics (v-t, s-t, projectile), optics (thin lens, mirror, refraction via the ray-optics core), circuits (series, parallel, meters via MNA).
3. Template catalogue: convert the 7 templates, the 5 `canvas_dsl` composites and the legacy `scene/components` library into parametric constructions with roles and build-up stages; author the rest of the top 60; each with a parameter-sweep invariant test.
4. MathJax 4 semantic enrichment in the notebook; `math:` targets; KaTeX kept for streaming if MathJax latency is a problem.

Gate: 60 templates rendering in under 100 ms and passing sweeps; ≥ 95% vector correctness and ≤ 1° mean angular error on the 300-scene physics set; `point_at` an exponent works.

### Phase 3 — The streaming teacher loop on the doubt path (weeks 8–10)

1. Replace fixed `narration_text` delivery with a streaming Sonnet 5 turn emitting speech plus inline ops against the serialized board state; parser fires ops as tags close; sentences go to TTS; anchored ops schedule by word.
2. Hands worker: Haiku 4.5 (escalating to Sonnet 5 after two verifier failures) writes construction programs for `figure.request`; kernel executes; verifier returns named failing constraints; three-round loop; the figure streams op-by-op.
3. Anticipation by plan slot: `DiagramRequirement.required_elements` is the visual intent; the hands resolve the next beat's intent to template, retrieval or generation before the beat starts.
4. Prompt caching: static system prompt, template catalogue, role ontology and lesson plan in the cached prefix; board state as the volatile trailer.

Gate: p50 op-to-board ≤ 300 ms, p95 ≤ 600 ms; anchor error p90 ≤ 200 ms and zero late-by-400; novel figure first stroke ≤ 1.5 s p50; zero pixel coordinates in model output over 200 doubts; construction success ≥ 85% within three rounds.

### Phase 4 — The math gate and live simulations (weeks 10–12)

1. SymPy service with the six steps of §3.4; `write.eq` blocks on it; re-derivation loop; Pint units.
2. `sim.projectile`, `sim.pendulum`, `sim.spring`, `sim.collision_1d`, `sim.circuit_dc`, `sim.ray` on the entity scene using myPhysicsLab and ray-optics cores; scrubbing and parameter edits by voice.

Gate: 500 seeded wrong steps all rejected before drawing; false rejection ≤ 2% on 500 correct steps; sims match closed-form solutions within 1%.

### Phase 5 — Live teaching on the same loop; hardening (weeks 12–16)

1. Live mode as "the doubt loop running the lesson plan".
2. Cross-session figure cache in Redis keyed by construction-program hash; retrieval index over corpus and generated figures.
3. Offline QA: DiagramIR checks plus a pairwise vision judge on every new figure, feeding the template backlog.
4. Weekly human rating; κ tracked.

Gate: "board matched voice" ≥ 4.3/5 two weeks running; anticipation hit rate ≥ 80%; cost per hour within strategy 02's Phase A budget.

### Phase 6 — The hands become a small model (after traction)

Distil construction programs and scene graphs from the logs into a 7B to 14B open model served with vLLM, llguidance/xgrammar grammar constraints, and speculative decoding (expect ~2× on short command outputs). Target: novel figure complete in 2 to 4 s at a fraction of the cost. GeoBuildBench's gap between frontier (79%) and open models (21 to 42%) says this needs our own training data first.

---

## 9 · Cost of the new loop

Inline ops add roughly a quarter more teacher output tokens (about one op per 8 seconds, 40 tokens each). A novel figure by Haiku 4.5 is about 800 output tokens, under one cent, generated once and cached across sessions. The kernel, solver and CAS are CPU-only. Net: the visual system's marginal cost falls from strategy 02's $0.50 to $1.50 per hour of design-agent calls to well under $0.20, while the teacher's bill rises by roughly a fifth. Latency and accuracy improve at the same time.

---

## 10 · Risks and how the plan handles them

| Risk | Mitigation |
|---|---|
| Model emits constructions the kernel cannot satisfy or references undefined entities (GeoBuildBench's top failure) | Parser validates references against the live scene before dispatch; verifier returns named failing constraints; three-round loop; templates cover the recurring 80% |
| Label omission and misplacement (Math-Vision Diagrams' top failure) | Labels are entity properties placed by the kernel; DiagramIR's label-association check on every figure |
| Role ambiguity | Closed ontology; uniqueness enforced within a figure; ambiguous targets rejected with candidates |
| Cue overload (doc 18) | Renderer-enforced budget; TTL fades; the model cannot exceed it |
| Progressive drawing without a visible agent has no measured benefit | Pen cursor leads every stroke; measured in the harness |
| Timestamp drift or missing timestamps | Per-session offset calibration; sentence-boundary fallback; forced-alignment audit; never-late clamp |
| CAS parser cannot read syllabus LaTeX | Math-Verify plus a fallback grammar; Andes-style numeric check; false-rejection rate capped at 2% |
| Wrong engine choice | The command language is ours; swapping the engine touches one adapter |
| Licence exposure | No GeoGebra, no GPL in the bundle; LGPL only as separately loaded modules with counsel's sign-off |
| Scope creep into 3D and chemistry | Out of scope until Phase 5 gates pass; the entity model extends |

---

## 11 · Decisions for Yash

1. Approve the §0 rule as a standing constraint on every prompt and tool: no pixel coordinates from a model, no unverified equation drawn, no SVG text edits by a model.
2. Kernel: own TypeScript kernel with JSXGraph as lazy fallback (recommended), given GeoGebra's licence.
3. Equations: MathJax 4 with semantic enrichment for sub-term targeting (recommended) vs KaTeX with server-computed ids.
4. TTS: Cartesia with word timestamps (recommended, already integrated) vs ElevenLabs.
5. Template scope for v0: 60 figures across IGCSE 0580 and 0625; JEE additions after Phase 5.
6. Whether Phase 5's live mode is gated on the Aanya demo or on the doubt path's metrics alone.

---

## 12 · Sources

**Geometry and diagram generation.** AlphaGeometry https://github.com/google-deepmind/alphageometry · AlphaGeometry2 https://arxiv.org/abs/2502.03544 · Newclid https://arxiv.org/abs/2411.11938 https://github.com/Newclid/Newclid · GeoBuildBench https://arxiv.org/html/2605.13167 https://github.com/ooongs/GeoBuildBench · GGBench https://arxiv.org/html/2511.11134 https://huggingface.co/datasets/OpenRaiser/GGBench · GeoGramBench https://arxiv.org/abs/2505.17653 · PhyDrawGen https://arxiv.org/html/2605.30512 · Math-Vision Diagrams https://arxiv.org/html/2608.08964 · MathemaTikZ https://dl.acm.org/doi/abs/10.1145/3698205.3729558 · DiagramIR https://arxiv.org/abs/2511.08283 · DiagramEval https://arxiv.org/abs/2510.25761 · SciFig https://arxiv.org/abs/2601.04390 · EduIllustrate https://arxiv.org/abs/2604.05005 · SciForma https://arxiv.org/abs/2607.18091 · TheoremExplainAgent https://arxiv.org/abs/2502.19400 · LLM2Manim https://arxiv.org/abs/2604.05266 · SketchAgent https://arxiv.org/abs/2411.17673 · SketchVLM https://arxiv.org/html/2604.22875 · DrawDash https://www.arxiv.org/abs/2512.01234 · Whiteboard-of-Thought https://arxiv.org/abs/2406.14562 · Visual Sketchpad https://arxiv.org/abs/2406.09403 · MathCanvas https://arxiv.org/abs/2510.14958 · DeTikZify https://arxiv.org/abs/2405.15306 · Inter-GPS https://arxiv.org/abs/2105.04165 · Geoparsing https://arxiv.org/abs/2604.11600

**Editing.** Vector-Bench https://arxiv.org/html/2607.19056v1 · vTikZ https://arxiv.org/abs/2505.04670 · VectorGym https://arxiv.org/html/2603.29852 · SVGEditBench V2 https://arxiv.org/abs/2502.19453 · SVGenius https://arxiv.org/abs/2506.03139 · GeoSVG-RL https://arxiv.org/abs/2605.25447 · Render-in-the-Loop https://arxiv.org/abs/2604.20730

**Circuits and physics.** CircuitLM and Schemato https://arxiv.org/pdf/2411.13899 · EEschematic https://arxiv.org/pdf/2510.17002 · PhysReason https://en.papernotes.org/ACL2025/llm_evaluation/physreason_a_comprehensive_benchmark_towards_physics-based_reasoning/

**Judges.** BlindTest https://arxiv.org/html/2407.06581v6 · VisOnlyQA https://huggingface.co/papers/2412.00947 · MLLM-as-a-Judge https://arxiv.org/html/2402.04788 · Judges rank not score https://arxiv.org/abs/2604.25235

**Learning science.** Fiorella & Mayer 2016 https://escholarship.org/content/qt55v7s9t1/qt55v7s9t1_noSplash_87418a79f71257344483b22e7c67c540.pdf · Fiorella et al. 2019 https://eric.ed.gov/?id=EJ1230834 · 2024 replication https://pmc.ncbi.nlm.nih.gov/articles/PMC11779760/ · Mayer & Fiorella 2020 https://link.springer.com/article/10.1007/s11423-020-09749-6 · Schneider et al. 2018 signalling https://www.learntechlib.org/p/204443/ · Richter et al. 2016 https://www.sciencedirect.com/science/article/abs/pii/S1747938X15000664 · Alpizar et al. 2020 https://eric.ed.gov/?id=EJ1269127 · Ginns 2006 contiguity https://www.sciencedirect.com/science/article/abs/pii/S0959475206000806 · Rey et al. 2019 segmenting https://maria-wirzberger.de/wp-content/uploads/2019/01/Rey2019_Article_AMeta-analysisOfTheSegmentingE.pdf · Cook et al. 2008 https://cpb-us-w2.wpmucdn.com/voices.uchicago.edu/dist/c/1286/files/2018/09/Gesture-makes-learning-last-2gwi303.pdf · Pi et al. 2019 https://www.sciencedirect.com/science/article/abs/pii/S036013151830277X · Rueckert et al. 2017 https://pmc.ncbi.nlm.nih.gov/articles/PMC5281660/ · 2024 gesture meta-analysis https://link.springer.com/article/10.1007/s10648-024-09910-0 · Guo, Kim & Rubin 2014 https://www.cs.rochester.edu/hci/pubs/pdfs/edX-MOOC-video-production-and-engagement_LAS-2014.pdf · ter Bekke et al. 2024 https://pure.mpg.de/rest/items/item_3565972_2/component/file_3565973/content · Gesture timing and recall 2024 https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1345906/full · Leonard & Cummins 2011 https://www.tandfonline.com/doi/abs/10.1080/01690965.2010.500218 · VanLehn 2011 https://www.tandfonline.com/doi/abs/10.1080/00461520.2011.611369 · Andes verification https://www.physics.rutgers.edu/~shapiro/tutor/submission3.pdf · STACK answer tests https://docs.stack-assessment.org/en/Authoring/Answer_Tests/

**Sync tooling.** Cartesia WebSocket TTS https://docs.cartesia.ai/api-reference/tts/websocket · ElevenLabs timestamps https://elevenlabs.io/docs/api-reference/text-to-speech/stream-with-timestamps · Azure WordBoundary https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis · LiveKit text and transcriptions https://docs.livekit.io/agents/multimodality/text/ · LiveKit data packets https://docs.livekit.io/home/client/data/packets/ · text streams https://docs.livekit.io/home/client/data/text-streams/ · data tracks https://livekit.com/blog/livekit-data-tracks-realtime-streaming · getSynchronizationSources https://developer.mozilla.org/en-US/docs/Web/API/RTCRtpReceiver/getSynchronizationSources · jitterBufferTarget https://developer.mozilla.org/en-US/docs/Web/API/RTCRtpReceiver/jitterBufferTarget · MFA 3.0 https://arxiv.org/html/2606.18466v1 · NeMo Forced Aligner https://www.isca-archive.org/interspeech_2023/rastorgueva23_interspeech.pdf · LiveKit eot-bench https://livekit.com/blog/solving-end-of-turn-detection · Deepgram Flux https://developers.deepgram.com/docs/flux/configuration

**Libraries and licences.** JSXGraph https://github.com/jsxgraph/jsxgraph · GeoGebra licence https://www.geogebra.org/license https://github.com/geogebra/legal · CindyJS https://github.com/CindyJS/CindyJS · Mafs https://github.com/stevenpetryk/mafs · planegcs https://github.com/Salusoft89/planegcs · flatten-js https://www.npmjs.com/package/@flatten-js/core · robust-predicates https://github.com/mourner/robust-predicates · Penrose https://github.com/penrose/penrose · Desmos API https://www.desmos.com/api · myPhysicsLab https://github.com/myphysicslab/myphysicslab · planck.js https://github.com/piqnt/planck.js · matter.js https://github.com/liabru/matter-js · ray-optics https://github.com/ricktu288/ray-optics · CircuitJS1 https://github.com/pfalstad/circuitjs1 · PhET licensing https://phet.colorado.edu/en/licensing/html · KaTeX options https://katex.org/docs/options.html · MathJax a11y/semantic enrichment https://docs.mathjax.org/en/latest/web/components/accessibility.html · Speech Rule Engine https://github.com/Speech-Rule-Engine/speech-rule-engine · MathLive https://github.com/arnog/mathlive · SymPy https://pypi.org/project/sympy/ · Math-Verify https://github.com/huggingface/Math-Verify · latex2sympy2_extended https://github.com/huggingface/latex2sympy2_extended · Pint https://github.com/hgrecco/pint · mathsteps https://github.com/google/mathsteps · rough.js https://github.com/rough-stuff/rough · perfect-freehand https://github.com/steveruizok/perfect-freehand · GSAP licence https://gsap.com/community/standard-license/ · llguidance https://github.com/guidance-ai/llguidance · xgrammar https://github.com/mlc-ai/xgrammar · vLLM structured outputs https://docs.vllm.ai/en/latest/features/structured_outputs.html · vLLM speculative decoding https://docs.vllm.ai/en/latest/features/speculative_decoding/ · Anthropic Haiku 4.5 https://platform.claude.com/docs/en/models/haiku-4-5/overview
