# Design Doc 19 — The Feynman-Standard Lecture Pipeline

**Status:** Spec locked. Implementation starting Phase A + B.
**Authors:** Yash (product spec, §0–§9). Claude (architecture + plan, §10–§14).
**Date opened:** 2026-05-23
**Supersedes:** parts of `18-attention-direction-redesign.md` (the concept-beat-must-have-diagram enforcement). Spotlight + presentation_mode survive.
**Branch:** TBD off `diagram-aware-teaching-agent`

---

## 0 · The one idea everything else serves

Feynman teaches concepts. It does not "display slides while a voice talks." Every change to this codebase is measured against a single test:

> **Would the greatest teacher on this planet be proud to put their name on this lecture?**

Richard Feynman, Walter Lewin, the teacher you remember who made you fall in love with a subject — they did not survive on volume. They survived on attention. They earned a student's attention in the first ten seconds and never gave it back. They drew one diagram and made it unforgettable. They asked a question you couldn't stop thinking about, then answered it so cleanly it felt inevitable.

That "X-factor" is the spec. The rest of this document is just how to build it.

---

## 1 · The concrete failures to fix

The system today does the following, and all of it is wrong:

1. **It scales diagrams by quantity, not need.** More diagrams are being generated as if more pictures equals more teaching. The opposite is true. Noise dilutes the signal.
2. **Diagrams are inert.** There is no live annotation while the agent speaks — no highlighting that lands, no pointing, no marking, no labeling, no drawing-on synced to the narration. The picture just sits there.
3. **Diagrams often don't contain what's being explained.** This is the most damning failure. The agent narrates "the ball follows a parabolic path," and the diagram on screen has no parabola in it. The visual and the words are disconnected. A diagram that doesn't depict the idea is worse than no diagram.
4. **A core instruction was misread.** "There must never be a moment where the screen is empty while the agent keeps speaking" was interpreted as "fill the screen with more diagrams." That is not what it means. See §2.
5. **The voice is flat.** Concepts are recited, not taught. No tension, no curiosity, no question-and-payoff rhythm.

---

## 2 · What "the screen is never empty" actually means

It does **not** mean "generate more diagrams to fill space."

It means: **every single word of the lecture is a hook.** The student's attention is never allowed to drop, because there is always something pulling them forward — a question they want answered, a line being drawn, a part lighting up, a payoff arriving. A diagram is one very powerful kind of hook (visualization is one of the strongest hooks that exists), so we use it deliberately and well. But silence-with-a-static-image is a failure, and so is image-spam. The fix for a dead moment is **better teaching**, not another picture.

---

## 3 · The teaching pipeline — the agent must PLAN before it speaks

For every concept, the agent must run an explicit planning pass and produce a lesson plan **before** generating any narration or visuals. This is hard-coded as a real, inspectable stage in the pipeline — not an afterthought. The plan has five steps, in order:

### Step 1 — Scope

Decide how much of this concept actually needs to be taught. The syllabus is the guardrail (see §6): it tells us what not to miss and what not to over-teach. But within that boundary, the agent decides depth. A throwaway sub-point gets one sentence. A load-bearing concept gets a full treatment. The agent is responsible for this judgment — the textbook is not.

### Step 2 — Pedagogy

Decide how to teach it. What's the hook? What's the misconception to attack? What's the order of ideas that makes it click? What question will the lecture be built around? And explicitly mark the **one or two load-bearing facts** — the things the student must not miss — so the narration can deliberately press them twice and flag their importance (see §5).

### Step 3 — Visual plan

Decide what diagrams — if any — are genuinely required, and for each one, specify exactly what it must literally contain. If the explanation references a parabola, the visual plan must state "diagram contains the parabolic trajectory." If it references a force vector, the plan states the vector is drawn. The plan also chooses diagram type: a rigorous **study diagram** when the concept demands precision, or a simple illustrative **sketch** when a quick mental image is all that's needed. Generate the minimum diagrams — even one, even zero — and make each one carry its full weight.

### Step 4 — Choreography

Decide how the narration moves across the diagram. **This is the missing layer.** The plan must script which part of the diagram is highlighted, pointed to, traced, marked, or labeled at each moment of the explanation, synced to the spoken words. The diagram and the voice are one performance, not two tracks playing independently.

### Step 5 — Math plan

Decide which equations need to be introduced, in what order, and how each is **motivated before it appears**. Equations are taught, not dumped.

Only after this plan exists does the agent generate the lecture.

---

## 4 · The diagram quality bar (non-negotiable)

1. **Minimum count, maximum weight.** If one diagram clears the concept, generate one. Never pad. Quantity is not a goal; it is a cost.
2. **Completeness.** A diagram must contain every element the narration refers to. If the agent will say a word, the thing that word names must be visible (or about to be drawn) on screen. No narrating parabolas onto straight lines.
3. **A live annotation layer is required.** Diagrams are not static images. The agent must be able to, in sync with speech: **highlight** a region, **point** with an arrow or marker, **trace/draw-on** a path as it's described, **mark** specific points (launch point, landing point, peak), and **label** parts with short text. This layer is the single most important engineering deliverable in this document. If it does not exist, build it first.
4. **Complexity matches need.** Don't render a detailed instrumented diagram when a clean schematic teaches better, and don't render a cartoon when the concept requires precision. The visual plan (§3, Step 3) decides which.

---

## 5 · The hook and the voice

Every lecture **MUST** open with a hook. **First. Before anything.** The most amazing question, the most surprising fact, the most counterintuitive claim available for this concept — something that makes the student need the answer and refuse to look away until they get it. A lecture that opens with "In this section we will study..." is a failure and should never ship.

Throughout the lecture, run a **question → payoff rhythm**. The agent poses an intriguing question about the very thing it's explaining, lets it hang for a beat, then answers it accurately and cleanly. Curiosity, tension, release. Repeat. This is how attention is sustained — not by filling the screen, but by making the student want the next sentence.

**Press the crucial facts twice.** Real teachers don't say the most important sentence once and move on. They land it, pause, and say it again — sometimes in the same words for weight, sometimes rephrased so it lands from a second angle — and they tell you why it matters: _"Remember this — this one idea is what the whole chapter hangs on."_ The agent must do the same. For each concept, the lesson plan should mark the one or two load-bearing facts, and the narration should deliberately repeat and emphasize them, flagging their importance out loud, rather than letting them slide by at the same weight as everything else. This is where the annotation layer earns its keep: when the key fact is repeated, the relevant part of the diagram should re-light or get marked again so the visual reinforces the spoken emphasis. The result should feel human — a teacher who knows what matters and makes sure you don't miss it — not an even, uniform readout where every sentence has the same importance.

**Kill the flat voice.** No monotone recitation. The delivery should sound like someone who finds this genuinely fascinating and can't wait to show you why.

---

## 6 · Syllabus vs. content — know the difference

The syllabus is a **guardrail**, not a script. Its only two jobs:

1. Make sure we don't miss anything the student is responsible for.
2. Make sure we don't over-teach beyond what's required.

That's it. The syllabus does not dictate teaching quality, depth of explanation, choice of hook, or how a concept is brought to life. Teaching content and quality are our responsibility, not the textbook's — and textbook phrasing is usually mediocre, so the agent must not simply regurgitate it. Take the **what** from the syllabus; the **how** and the **how well** are entirely on us.

---

## 7 · The standard, worked: "a ball thrown inside a moving train"

Use this as the reference for what "good" looks like end to end.

**The concept:** A ball thrown straight up inside a train moving at constant velocity. To the passenger, it goes straight up and falls straight back into their hand. To someone standing on the ground, the same ball traces a parabola, because it keeps the train's forward velocity the whole time. (Frames of reference / Galilean relativity / projectile motion.)

**How Feynman should teach it:**

1. **Hook (opens the lecture):**

   > "Throw a ball straight up on a moving train and it lands right back in your hand — as if the train weren't moving at all. But someone watching from the platform swears the ball flew in a curve. Both of them are right. How?"

2. **Scope:** Core concept, full treatment — this is where frames of reference click or never do.

3. **Visual plan:** **One diagram is enough.** It must literally contain: the train, the passenger, the ball's straight-up-and-down path in the train's frame, and — critically — the **parabolic arc** in the ground frame, with the train's forward displacement marked underneath. The parabola is not optional. It is the entire point. The current product drawing a straight line here is the exact bug.

4. **Choreography:**
   - As the agent says _"in your frame, straight up,"_ it **traces** the vertical line and **marks** the launch point.
   - As it says _"but you're also moving forward this whole time,"_ it **highlights** the train's horizontal velocity vector and shows it staying constant (no horizontal force → velocity conserved).
   - As it says _"so from the platform, those two motions combine,"_ it **draws** the parabola on, point by point, and **marks** where the ball lands — directly back in the moving hand.
   - The landing point lighting up on the hand is the **payoff**.

5. **Math plan:** Introduce horizontal motion (constant velocity) and vertical motion (constant acceleration) separately, motivate why they're independent, then combine. Equations arrive **after** the picture has made them obvious, not before.

6. **Question → payoff mid-lecture:**
   > _"If the ball isn't being pushed forward once it leaves the hand, how does it keep up with the train?"_
   > …then the clean answer: **because nothing ever took its forward speed away.**

If Feynman can teach this concept the way described above — one complete diagram, traced live, built around a question, opened with a hook — the engine is working. If the parabola is missing or the annotation is dead, it is not.

---

## 8 · Definition of done

A lecture ships only if all of the following are true:

- [ ] It opens with a genuine **hook** (question / fact / paradox), never with "in this section."
- [ ] An explicit **lesson plan** (scope → pedagogy → visual plan → choreography → math) was generated and persisted before narration.
- [ ] The number of diagrams is the **minimum** that fully clears the concept.
- [ ] Every diagram contains **every element** the narration references — nothing is narrated onto a picture that doesn't show it.
- [ ] The diagram is **annotated live** (highlight / point / trace / mark / label) in sync with the spoken explanation.
- [ ] Depth is **calibrated to the concept**, bounded by the syllabus but not dictated by the textbook's wording.
- [ ] The voice runs a **question → payoff** rhythm and never goes flat.
- [ ] The one or two crucial facts are **pressed twice** and flagged as important — not delivered at the same flat weight as everything else.
- [ ] A student watching it would **want to keep watching** — not because the screen is busy, but because they need the answer.

---

## 9 · Anti-patterns — never do these

- Adding diagrams to "fill" silence or screen space.
- Generating a diagram that doesn't depict what's being said.
- Static, un-annotated images sitting on screen during explanation.
- Reciting the textbook's phrasing instead of teaching the idea.
- Opening with a table of contents, a definition, or "in this lecture we will."
- Treating the syllabus as the source of teaching quality rather than as a boundary.
- A monotone, list-reading delivery with no questions and no payoffs.

---

## 10 · What we tear down

The current pipeline ships much of this in the wrong shape. Concrete rollback list, by file:

| Throw away                                                                                                       | Why                                                                                                                                                                          |
| ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `concept_planner.py` concept-beat-must-have-diagram enforcement (doc 18 Step 3 `_enforce_concept_beat_diagrams`) | Made the count go up, which is the wrong direction per §1                                                                                                                    |
| Role-based `FOCUS` (only `target_role`, no `target_element_id`)                                                  | Bug. One role maps to multiple elements (e.g. 6 elements with `role='object'` in §47.1 "Principle of Relativity"); spotlight lands on the wrong one. Switch to `element_id`. |
| `BeatNarrationWriter` choosing its own FOCUS placement                                                           | Narration should be a wordsmith over a pre-decided choreography, not the choreographer itself                                                                                |
| `diagram_spec_generator.py` generating from a free-text brief                                                    | Brief → "draw something about relativity" → LLM picks elements at random → narration references things that don't exist                                                      |
| `_BUILD_UP_BEAT_TYPES` heuristic (presentation_mode per beat_type)                                               | Replaced by explicit choreography per narration chunk                                                                                                                        |
| Hook beat as just-another-beat-type                                                                              | Hook must be classified, validated (no "in this section we will study"), and is the gatekeeper of the topic                                                                  |
| `BeatType.misconception` / `bridge` etc. as planner-driven labels                                                | Replaced by an opinionated `LessonPlan` structure that names roles explicitly: `hook`, `misconception`, `aha_moment`, `crucial_facts` are top-level fields, not beat tags    |

**Keep:**

- The spotlight (highlight + inline label) — one annotation primitive of the layer we still need to build out.
- `presentation_mode` on `Diagram` — useful signal for the renderer; will be set explicitly by the LessonPlan rather than heuristically.
- Manifest events for audio + pause + show_diagram — the runtime substrate is sound.
- ManifestComposer / TTS chunker / Kokoro pipeline — wraps fine around the new event types.

---

## 11 · The new architecture — five hard stages

This maps §3 one-to-one to the codebase. Each stage is a real, inspectable, persisted artifact in `extraction.json` — not an implicit step inside another LLM call.

```
[textbook section + syllabus entry]
        │
        ▼
  Stage 1: SCOPE              → plan.scope: brief | moderate | full
                                plan.crucial_facts: 1–2 strings
        │
        ▼
  Stage 2: PEDAGOGY           → plan.hook: { type: question | fact | paradox, text }
                                plan.misconception
                                plan.aha_moment
                                plan.idea_order
        │
        ▼
  Stage 3: VISUAL PLAN        → plan.diagrams: list[DiagramRequirement]
                                  DiagramRequirement.required_elements:
                                    [ { element_id, semantic, kind, must_be_drawn } … ]
                                  DiagramRequirement.style: study | sketch
                                  (typically 1, max 2 without justification)
        │
        ▼
  Stage 4: CHOREOGRAPHY       → plan.beats: list[ChoreographyStep]
                                  per step:
                                    narration_chunk: str
                                    action: FOCUS | TRACE | MARK_POINT |
                                            WRITE_MARGIN | POINT_AT | NONE
                                    element_id: str | None
                                    coords: { x, y } | None
                                    label_text: str | None
                                    presses_crucial_fact: bool
                                    is_question | is_payoff
        │
        ▼
  Stage 5: MATH PLAN          → plan.equations: list[ { equation, motivation, order } ]
        │
        ▼
  [LessonPlan persisted to extraction.json — inspectable, reviewable]
        │
        ▼
  Stage 6 (downstream): Diagram generation FROM VisualPlan
                                  must produce every required_element with the exact element_id
                                  validator regenerates if any element missing
        │
        ▼
  Stage 7 (downstream): Narration polish FROM ChoreographyStep[]
                                  wordsmith only; cannot move FOCUS placement
                                  emits action markers tightly bound to phrases
        │
        ▼
  Stage 8 (downstream): Quality gate (LLM-as-judge)
                                  - is the hook actually a hook?
                                  - does every narrated element exist on the diagram?
                                  - are crucial facts pressed twice?
                                  - does choreography sync to words?
                                  if no → regenerate the offending stage with explicit feedback
        │
        ▼
  TTS + ManifestComposer (existing; takes new event types)
```

### Key inversion vs today

**Diagrams are generated AFTER the lesson plan, FROM the lesson plan, not before.** Every element the narration will say is declared up front, with a unique stable id. The diagram generator's job is to produce those exact elements, validated.

### Pydantic shape (target — illustrative, not final)

```python
class Hook(BaseModel):
    type: Literal["question", "fact", "paradox", "observation"]
    text: str
    @field_validator("text")
    def forbid_generic_openers(cls, v):
        v_lower = v.lower().strip()
        for bad in ("in this section", "in this lecture", "let us study", "we will learn"):
            if v_lower.startswith(bad):
                raise ValueError(f"Hook may not open with '{bad}'. See doc 19 §5.")
        return v

class ElementRequirement(BaseModel):
    element_id: str  # MUST be stable, unique within the diagram
    semantic: str
    kind: Literal["object", "vector", "path", "label", "axis", "point", "region"]
    must_be_drawn: bool = True

class DiagramRequirement(BaseModel):
    title: str
    purpose: str  # 1-sentence: why this diagram exists, what insight it serves
    style: Literal["study", "sketch"]
    required_elements: list[ElementRequirement]  # min 1, no upper limit but planner stays terse

class ChoreographyAction(str, Enum):
    FOCUS = "focus"
    TRACE = "trace"
    MARK_POINT = "mark_point"
    WRITE_MARGIN = "write_margin"
    POINT_AT = "point_at"
    NONE = "none"  # narration only, no board change

class ChoreographyStep(BaseModel):
    narration_chunk: str
    action: ChoreographyAction
    element_id: str | None = None
    coords: tuple[float, float] | None = None
    label_text: str | None = None
    presses_crucial_fact: bool = False
    is_question: bool = False
    is_payoff: bool = False
    pause_after_ms: int = 0

class EquationIntroduction(BaseModel):
    equation: str  # KaTeX
    motivation: str  # the 1-sentence "why this equation, why now"
    order: int

class LessonPlan(BaseModel):
    topic_id: str
    scope: Literal["brief", "moderate", "full"]
    crucial_facts: list[str]  # 1–2, hard cap
    hook: Hook
    misconception: str
    aha_moment: str
    idea_order: list[str]  # brief outline of the explanation arc
    diagrams: list[DiagramRequirement]  # typically 1, max 2
    beats: list[ChoreographyStep]
    equations: list[EquationIntroduction]
```

---

## 12 · The live annotation layer — the deliverable §4 says to build first

Spotlight (built in doc 18) only handles "highlight a region with an inline label." §4 of this spec needs four more primitives. All five are sync'd to TTS by `cumulative_audio_ms` (the existing mechanism the spotlight uses).

| Primitive      | What it does                                                                                                       | Backend event                                        | Frontend component                                                    |
| -------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------- | --------------------------------------------------------------------- |
| `FOCUS` (have) | Dim everything else, ring + inline label around the element                                                        | `FocusEvent` ✓                                       | `Spotlight.tsx` ✓                                                     |
| `TRACE`        | Animate a path stroke-revealing live as the agent speaks ("trace the parabola point by point")                     | `TraceEvent { element_id, duration_ms }`             | `TraceOverlay.tsx` — stroke-dasharray reveal sync'd to event duration |
| `MARK_POINT`   | Place a marker (dot / cross / arrow-tip) at specific viewBox coords with optional label ("mark the landing point") | `MarkPointEvent { x, y, kind, label }`               | `MarkPoint.tsx` — pulsing dot/cross with label tag                    |
| `POINT_AT`     | A pointing arrow from a margin location into a target element (different from spotlight; pointer-style emphasis)   | `PointAtEvent { element_id, from_side }`             | `Pointer.tsx` — animated arrow draw                                   |
| `WRITE_MARGIN` | Write a short equation/text in the slide margin next to the diagram, mid-explanation                               | `WriteMarginEvent { text, anchor_element_id, side }` | `MarginNote.tsx` — handwriting-style text reveal                      |

All five live on `SlideAnnotationLayer` so they share the diagram's viewBox.

### Bounds resolution

All annotations resolve target geometry via the existing `useResolvedBounds` hook (live-DOM lookup via `getBoundingClientRect` + `screenCTM` matrix inversion + `data-design-element` attribute, with dictionary fallback). The new primitives reuse this — no new resolution machinery needed.

### Reduced motion

Each component honors `prefers-reduced-motion`: TRACE renders the full path immediately; MARK_POINT skips the pulse; POINT_AT renders the final arrow; WRITE_MARGIN renders the final text. All visual states are static-friendly.

---

## 13 · Execution sequence

| Phase                           | Scope                                                                                                                                                                                                                                                                                                                                                | Days | Why this order                                                                 |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------------ |
| **A — Foundation**              | New `LessonPlan` Pydantic models (`lecture_plan/lesson_plan_models.py`); new event types `TraceEvent` / `MarkPointEvent` / `PointAtEvent` / `WriteMarginEvent` in `models.py`; chunker markers for the new actions; roll back doc-18 concept-beat enforcement; switch `FocusEvent` to require `element_id` (`target_role` becomes deprecated alias). | 1.5  | Unblocks everything downstream. Tests + types first.                           |
| **B — Live annotation layer**   | Four new frontend components (`TraceOverlay.tsx`, `MarkPoint.tsx`, `Pointer.tsx`, `MarginNote.tsx`); walker emits the four new event types; chunker parses `<<TRACE:…>>` `<<MARK:…>>` `<<POINT:…>>` `<<WRITE:…>>`. CSS / SVG animation. Vitests per component.                                                                                       | 2    | §4 says build this FIRST. The user can't evaluate the rest without it.         |
| **C — Insight-first planner**   | Kernel: replace `plan_concept` with `plan_lesson` producing the full 5-stage plan. New prompts with hard rules (hook classifier with the validator above, "in this section" forbidden, max 2 diagrams without justification, crucial_facts mandatory with 1–2 cap). v2: `lecture_plan/lesson_planner.py` replaces `concept_planner.py`.              | 3    | This is the IP. Without a real plan, the rest is decoration.                   |
| **D — Diagram coupling**        | New `diagram_spec_generator.py` that takes a `DiagramRequirement` and must produce all required elements with exact ids; validator with regen-on-miss feedback ("you missed `parabola-ground-frame`, regenerate including it").                                                                                                                      | 2    | Closes the gap "narration says parabola, diagram has no parabola."             |
| **E — Choreographed narration** | New `beat_narration_writer` that does wordsmithing over a fixed choreography; press-twice mechanism (`crucial_facts` → 2nd choreography step with `presses_crucial_fact=true` for each); question → pause → payoff pattern. Action markers use `element_id`, never `role`.                                                                           | 2    | This is where the voice gets a heartbeat.                                      |
| **F — Quality gate**            | LLM-as-judge over LessonPlan + diagrams + narration. Regen loop with explicit feedback. Stops after 2 retries; surfaces the rejection to the user as a `lesson.quality_failure` warning so we can iterate prompts.                                                                                                                                   | 1.5  | Catches drift; lets us tune by editing prompts, not architecture.              |
| **G — Voice prosody**           | Kokoro pause/emphasis markers; question intonation hints; press-twice get explicit pacing. Drop SSML if Kokoro doesn't support it; use chunked-segment volume/rate variation as fallback.                                                                                                                                                            | 1    | Lifts a flat read to a teacher's read. Worth doing even at v0.                 |
| **H — Worked-example proof**    | Build the **ball-in-moving-train** lesson from §7 end-to-end. Eyeball it together. Iterate prompts, not code.                                                                                                                                                                                                                                        | 1    | This is the gate. If §7 doesn't land, the spec is right and the impl is wrong. |

**Total: ~14 days** (single dev). Could be tighter with focus and parallelism (some prompt iteration in Phase C/E can overlap with Phase F judge build).

### Branch strategy

- Implementation on **`feynman-standard-lecture-pipeline`** off `diagram-aware-teaching-agent`.
- Per-phase sub-branches if a phase exceeds 1 day: `feynman-standard-lecture-pipeline-phaseA`, etc.
- Phase B + H land on a screen-able state; everything else is internal until that point.

---

## 14 · Chosen starting move

Per discussion 2026-05-23: **option (b)** — Phase A + B + a hand-tuned §7 demo before generalizing.

### Why (b) over (a)

Yash's standard is "a lecture a student loves," not "well-structured event types." The §7 proof is the only artifact that can validate the spec at the right level of abstraction. We do not want to discover after 14 days that the architecture is right but the _teaching_ misses the spec. The hand-tuned §7 lets us see a complete lecture in ~4–5 days, react to the actual artifact, and only then generalize.

### Concretely, the first push

1. **Phase A** (1.5 days): models + event types + chunker markers + rollback + FOCUS by element_id.
2. **Phase B** (2 days): the four new frontend components + walker emitters + Vitests.
3. **§7 hand-build** (1 day): I hand-author the LessonPlan JSON for "ball thrown inside a moving train," hand-author the matching DiagramSpec with `parabola-ground-frame` / `vertical-drop-train-frame` / `landing-point` / `train-velocity-vector` as explicit elements, and let the runtime play it. Iterate prompts only AFTER we watch this.

**Then we stop and look together.** If the §7 lecture passes the §8 definition-of-done, we proceed to Phase C–F (insight-first planner + diagram coupling + choreography narration + quality gate). If it doesn't, we iterate the runtime, not the planner.

---

## 15 · Open redirect points

Documenting these so they don't quietly become decisions:

1. **Syllabus source-of-truth.** Today there's no IGCSE syllabus map in the codebase. Planner uses BookSkeleton + topic position as a weak proxy. When we get IGCSE 0580 (math) or 0625 (physics) mapped, the planner uses that for §3 Step 1 scope decisions. Until then, scope = LLM judgment.
2. **Kokoro prosody ceiling.** Kokoro's prosody control may be too limited for true voice modulation (currently flat). If Phase G surfaces this, we evaluate a switch to a TTS with stronger SSML support (ElevenLabs, Cartesia, etc.) as a separate ticket. Voice-side cost shifts; track B (LLM provider routing) may absorb this.
3. **Live-agent impact.** All of this is `data_pre_compute_v2/` only. The kernel `plan_lesson` signature change is gated behind a kwarg so the live agent (which still calls `plan_concept`) keeps working. Eventually we migrate the live agent too, but not in this push.
4. **`presentation_mode` field on `Diagram`.** Stays, but now the LessonPlan sets it explicitly (per diagram, not per beat-type heuristic). Default `overview`; `build_up` requires the plan to opt in for that diagram.
5. **Back-compat for old extractions.** Existing `out/extraction_*.json` files use the old event shape. Frontend handlers stay tolerant (no-op on unknown events) so old extractions still play, just without the new annotation richness.
6. **Quality-gate retry budget.** Default 2 retries per stage. Surfaces failures rather than infinite-loops if the LLM can't satisfy the hook validator. Tune in Phase F.

---

## 16 · Bottom line for the build

Quantity of diagrams is a cost, not a feature. The deliverables, in priority order:

1. **A live diagram-annotation layer synced to narration** — the five primitives in §12.
2. **A real planning stage that decides scope / visuals / choreography per concept** — the LessonPlan in §11.
3. **A hook-first, question-driven narration style** — enforced in the planner (§5).
4. **A hard guarantee that every diagram literally contains what the agent is talking about** — diagram coupling in Phase D.

Build it so a student simply loves it.
