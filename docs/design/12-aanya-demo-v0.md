# 12 — Aanya Demo v0 (Executable Storyboard)

> The 7-minute personalized lesson we ship in 2–3 weeks and validate with 5–10 IB/IGCSE moms. Every engineering decision over the next month gets ranked against "does this make Aanya's lesson better." This doc is the single source of truth for what we build.

**Status**: Spec — executable storyboard
**Date**: 2026-05-10 (topic switched from similar triangles → trigonometry on 2026-05-10 — see Decision log)
**Depends on**: `docs/strategy/01-consumer-product-thesis.md`, `docs/design/10-split-board.md`
**Defines**: the v0 demo. Engineering builds straight from this doc.

---

## 1. The setup (one paragraph)

It is 8 PM on a Wednesday. Aanya is 13, Year 9 at an IGCSE school in Bangalore. She has a math worksheet due tomorrow and is stuck on a trigonometry word problem from a past paper revision packet. Her tutor isn't coming until Saturday. Her parents could help with elementary math but not Year 9 IGCSE trigonometry. She is too proud to ask anyway. She opens Feynman in a browser tab on her laptop, pastes the question into the input, and hits enter.

What happens next is the product.

---

## 2. The past paper question

A representative Cambridge IGCSE 0580 Paper 4 (Extended) right-triangle trigonometry question. We hardcode this exact question in the v0 demo:

> A ladder of length 10 m leans against a vertical wall. The ladder makes an angle of 60° with the horizontal ground.
>
> (a) Calculate the height the ladder reaches up the wall.
> (b) Calculate the distance from the foot of the ladder to the base of the wall.

Why this question: it tests the three things the agent must demonstrate — (i) building a right triangle from a word problem, (ii) identifying which side is opposite, adjacent, hypotenuse relative to the given angle, (iii) picking the right trig ratio (sine vs cosine) and applying it. Answers are h ≈ 8.66 m and d = 5 m. The cosine answer (d = 5) is clean; the sine answer (h = 10 × sin 60° ≈ 8.66) is authentic to real IGCSE problems and verifiable via Pythagoras (h² + 5² should ≈ 100). The kid-solves-it confirmation problem uses sin(30°) = 0.5 for a perfectly clean closing answer.

---

## 3. The 7-minute arc — beat-by-beat

The lesson is 8 beats over 7 minutes. Each beat is specified with: verbatim voice script, real tool calls, sync mode, branch state. Engineering should be able to build this without inventing anything.

**Format conventions:**
- Voice in **italic blockquote** = the actual words the AI says (verbatim, not guidance).
- Slide / Notebook tool calls in code blocks = real Python tool signatures from `backend/src/feynman/agent/tools.py`.
- Sync mode references `SyncMode` enum from `backend/src/feynman/agent/tools.py:129–147`.
- Branch state references `BranchContext` from `backend/src/feynman/agent/state_machine.py:27–33`.

---

### Beat 1 — Open (0:00 – 0:30)

**Trigger:** Aanya pastes the question text. Frontend sends it to the agent as the opening lesson context.

**Voice (verbatim):**
> *"Got it — a ladder problem. Classic. We've got a right triangle here: the wall is vertical, the ground is horizontal, and the ladder is the hypotenuse. The whole problem comes down to picking the right trig ratio. Let me draw it."*

**Slide panel:**
```python
draw_design_diagram(
    prompt=(
        "A right triangle on a dark board representing a ladder against a wall. "
        "Hypotenuse: a thick soft-cyan line going from bottom-left up to upper-right, labeled '10 m' (the ladder). "
        "Vertical leg: rightmost side, going up — represents the wall, labeled '? (height)' in peach. "
        "Horizontal leg: bottom side — represents the ground, labeled '? (distance)' in peach. "
        "A small right-angle square at the bottom-right corner where wall meets ground. "
        "The angle between the ladder and the ground (bottom-left vertex) is marked '60°' with a small arc. "
        "Title above: 'Ladder Problem'. Caption below: 'IGCSE 0580 — Topic 7: Trigonometry'."
    ),
    timing="visual_first",  # SyncMode.IMMEDIATE
)
```
**Cache:** must be cache-hit via anticipation engine. Diagram is pre-generated offline as `diagrams/aanya_demo/ladder_problem_main.json` and pre-loaded into `tc.anticipation` at session start.

**Notebook panel:** empty (intentional — let the slide land first)

**Branch state:** main, `state=TEACHING`, `concept="trig_ladder_paper_4"`, depth=1

**Beat goal:** establish trust + frame the path. Aanya should think: *this AI knows what it's doing.*

---

### Beat 2 — Name the three sides (0:30 – 1:30)

**Voice (verbatim):**
> *"Whenever you have a right triangle with one of the non-right angles known, three sides matter — and they each have a name. The side directly opposite the angle is called the *opposite*. The side next to the angle, that's not the hypotenuse, is called the *adjacent*. And the hypotenuse is always the longest side, opposite the right angle. Look at the diagram. The 60° angle is at the foot of the ladder. So: the wall — the side going up — is your opposite. The ground — the side going across — is your adjacent. And the ladder itself is your hypotenuse."*

**Slide panel:** sequential highlight of each side with its label appearing.
```python
highlight_walk(
    targets=["side_opposite", "side_adjacent", "side_hypotenuse"],
    duration_per_step_ms=900,
    timing="term_sync",
)
```
The `highlight_walk` cues are timed to land on the words "the wall — your opposite", "the ground — your adjacent", "the ladder itself — your hypotenuse" — uses `SyncMode.TERM_SYNC` against `\htmlId{side_*}{}` tags in the diagram.

**Notebook panel:**
```python
write_section(title="Naming the sides")
write_text(
    text="Opposite — across from the angle",
    style="key_point",
    timing="after_speech",
)
write_text(
    text="Adjacent — next to the angle (not the hypotenuse)",
    timing="after_speech",
)
write_text(
    text="Hypotenuse — opposite the right angle (always the longest side)",
    timing="after_speech",
)
```
Both `write_text` calls use `SyncMode.ON_PLAYOUT` so they stamp into the notebook *as the relevant phrase finishes*, not before.

**Branch state:** main, unchanged

**Beat goal:** plant the vocabulary the rest of the lesson hangs on. Without this, SOH CAH TOA is just a chant. With this, it's a tool.

---

### Beat 3 — SOH CAH TOA (1:30 – 2:30)

**Voice (verbatim):**
> *"Now the three trig ratios. SOH CAH TOA. Sine is opposite over hypotenuse — SOH. Cosine is adjacent over hypotenuse — CAH. Tangent is opposite over adjacent — TOA. Each one is just a ratio of two of the three sides we just named. Let's write them down."*

**Notebook panel:**
```python
write_section(title="SOH CAH TOA")
write_equation(
    latex=r"\sin(\theta) = \frac{\text{opposite}}{\text{hypotenuse}}",
    label="SOH",
    align_group="ratios",
    indent=0,
    timing="after_speech",
)
write_equation(
    latex=r"\cos(\theta) = \frac{\text{adjacent}}{\text{hypotenuse}}",
    label="CAH",
    align_group="ratios",
    indent=0,
    timing="after_speech",
)
write_equation(
    latex=r"\tan(\theta) = \frac{\text{opposite}}{\text{adjacent}}",
    label="TOA",
    align_group="ratios",
    indent=0,
    timing="after_speech",
)
```

**Slide panel:** keep main diagram. No change.

**Branch state:** main, unchanged

**Beat goal:** introduce the three ratios — but leave one beat of "wait, why are these the right things to remember?" tension before the next sentence applies them. This tension is what the doubt branch fills, and we want Aanya to feel the question forming before she asks it.

---

### Beat 4 — DOUBT BRANCH (2:30 – 3:30) ⭐

This is the irreducible moat. **The doubt is real, not scripted.** Detailed in §4 below; summary here.

**Trigger (live, not scripted):** at any point during beats 1–3 (most likely during beat 3, when the ratio rule is introduced), the student speaks. They might ask the canonical question ("why is sine always opposite over hypotenuse?"), or something simpler ("wait, what's the adjacent again?"), or something else entirely. The agent listens to whatever comes in.

LiveKit VAD interrupts current TTS. Transcript reaches the agent. The agent's prompt instructs it: *if the student's utterance is a clarifying question that touches the conceptual basis of what we're explaining, call `start_doubt_branch` with a concise `related_concept` derived from the actual question; otherwise acknowledge briefly and continue the main flow.*

**Tool call (with LLM-extracted concept):**
```python
start_doubt_branch(
    related_concept=<LLM extracts from actual student utterance>,
    # examples — what the LLM might pass:
    #   "why trig ratios depend only on the angle"
    #   "the difference between opposite and adjacent sides"
    #   "why sin and cos are different ratios"
    #   "what to do if the angle isn't given"
    # — depends on what the student actually asked
)
# Internally fires (real, not faked):
#   - tc.state_machine.push_branch(...) → new BranchContext, state=HANDLING_DOUBT
#   - tc.board_manager.push_board(...) → new active board
#   - tc.anticipation.warm_doubt(...) → background generation kicks off
#   - plan_doubt() → LLM generates a structured response plan based on the actual question
#   - _update_agent_prompt(ctx) → LLM sees doubt plan
```

**Voice (verbatim — bridging acknowledgment, the ONLY scripted line in this beat):**
> *"Beautiful question — let me show you."*

This bridging line is short on purpose: by the time the AI finishes speaking it (~1.5s), `tc.anticipation.match()` has done a Jaccard similarity lookup against the pre-cached likely-doubts library and either returned a cache hit or kicked off live generation. Everything else in this beat — the response voice, the notebook entries, the explanation length — is live LLM output, not scripted.

**Slide panel — anticipation match (cache hit ≤800ms) or live generation (≤5s with DraftingLoader):**

The pre-cache library contains 4–5 anticipated doubt diagrams (see §6 build dependencies). The LLM's `related_concept` argument is matched via `anticipation.match()` against the cached prompts:

| Anticipated doubt | Pre-cached diagram |
|---|---|
| Why is sin = opp/hyp? Why is the ratio constant? | `doubt_why_sin_opp_hyp.json` — three same-shape, different-size right triangles, opp/hyp computed |
| Which side is opposite/adjacent? | `doubt_which_side_is_opposite.json` — labeled-sides reference |
| What's the difference between sin and cos? | `doubt_sin_vs_cos.json` — side-comparison view |
| Why use ratios at all? | `doubt_why_ratios.json` — scale-invariance demonstration |
| What if I don't have the angle? | `doubt_no_angle.json` — graceful "we'll cover that next" hint |

Match flow: LLM's `related_concept` → `anticipation.match()` → instant hit (≤800ms) OR `slide_pending` instruction fires → `DraftingLoader` plays while `generate_design_diagram()` runs live. Bridging acknowledgment plus a short follow-on ("let me sketch this for you…") buys ~5–8s of cover for the live path.

**Notebook panel:** parent notebook page fades to 50% opacity. Doubt notebook is fresh. Entries are LLM-generated based on the actual response, not pre-scripted. Suggested style: 1–2 short text entries, the second `style="key_point"` for the main insight. The agent's prompt for this beat says: *write 1–2 short notebook entries that anchor the answer; use `style="key_point"` for the load-bearing insight*.

**Voice (live LLM-generated response, ~25–35 seconds):** the LLM produces an explanation tailored to the *actual question asked*, anchored on the diagram that matched (or was generated). The system prompt for this beat does NOT bind a verbatim script — only behavioral guidance:
- Tone: warm, direct, not condescending. Indian English.
- Anchor on the diagram visually (point at things using term-sync if possible).
- Tie back to "this is why what we just wrote down works."
- Length: 25–35 seconds. Don't over-explain.
- End with a smooth handoff cue ("OK so now…", "with that in mind…", or similar) before the verbatim return-cue fires.

**Tool call (resolution):**
```python
resolve_doubt()
# Internally (real, not faked):
#   - tc.state_machine.pop_branch() → back to parent BranchContext (state=TEACHING)
#   - tc.board_manager.pop_board() → parent board reactivated
#   - Anticipation cache cleared for doubt
#   - _update_agent_prompt(ctx) → LLM prompt resets to parent
```

**Slide panel (cross-fade back, ≤800ms):** doubt slide out, parent ladder diagram in. Notebook fades back to 100%.

**Voice (verbatim — return cue, ties resolution back to where we left off):**
> *"OK — back to your ladder. Let's use what we just wrote down."*

This return cue is verbatim because it's the AI's transition back to the bound main lesson, not a response to the student. Reliability matters here.

**Branch state:** during beat = doubt (`state=HANDLING_DOUBT`, depth=2, concept derived from actual student utterance). After resolve = main (depth=1, exactly where the doubt was triggered).

**Beat goal:** demonstrate the irreducible feature *for real*. Student asks anything; the system handles it authentically — branches state, generates response, returns cleanly. No chatbot does this; no video does this. The kid feels heard mid-flow, gets a meaningful answer to their actual question, and lands back on the parent thread without losing place. This is the beat that sells the product. The pre-cache library is anticipation (real teachers do this too), not theater.

---

### Beat 5 — Apply sine to find the height (3:30 – 4:30)

**Voice (verbatim):**
> *"Part (a): height up the wall. That's the *opposite* side — across from the 60° angle. We know the *hypotenuse* — the ladder — it's 10 metres. So we want the ratio that connects opposite and hypotenuse. That's sine."*

**Notebook panel:**
```python
write_section(title="Step 1: Find the height (part a)")
write_step(
    text="Known: angle = 60°, hypotenuse = 10. Want: opposite (h)",
    number=1,
    indent=0,
    timing="after_speech",
)
write_equation(
    latex=r"\sin(60°) = \frac{h}{10}",
    align_group="part_a",
    indent=1,
    timing="after_speech",
)
write_step(
    text="Multiply both sides by 10:",
    number=2,
    indent=0,
    timing="after_speech",
)
write_equation(
    latex=r"h = 10 \times \sin(60°)",
    align_group="part_a",
    indent=1,
    timing="after_speech",
)
write_equation(
    latex=r"h = 10 \times 0.866 = 8.66 \text{ m}",
    align_group="part_a",
    indent=1,
    timing="after_speech",
)
```

**Slide panel:** highlight the height side and the angle on the diagram, then animate the "?" label on the wall side to "8.66 m".
```python
highlight_diagram_part(
    target="side_opposite",
    color_token="--sb-neon",
    timing="visual_first",
)
highlight_diagram_part(
    target="angle_60",
    color_token="--sb-neon",
    timing="visual_first",
)
annotate(
    target="label_height",
    style="replace_text",
    label="8.66 m",
    timing="term_sync",  # lands on the word "8.66" in voice
)
```

**Branch state:** main

**Beat goal:** show the method working. Identify which side is which → pick the matching ratio → solve. Make the *picking* feel mechanical once the sides are named.

---

### Beat 6 — Apply cosine to find the distance (4:30 – 5:30)

**Voice (verbatim):**
> *"Part (b): distance from the foot of the ladder to the wall. That's the *adjacent* side — next to the angle. Same hypotenuse, same angle. So this time we want the ratio that connects adjacent and hypotenuse. That's cosine. Watch."*

**Notebook panel:**
```python
write_section(title="Step 2: Find the distance (part b)")
write_step(
    text="Now we want: adjacent (d)",
    number=3,
    indent=0,
    timing="after_speech",
)
write_equation(
    latex=r"\cos(60°) = \frac{d}{10}",
    align_group="part_b",
    indent=1,
    timing="after_speech",
)
write_equation(
    latex=r"d = 10 \times \cos(60°)",
    align_group="part_b",
    indent=1,
    timing="after_speech",
)
write_equation(
    latex=r"d = 10 \times 0.5 = 5 \text{ m}",
    align_group="part_b",
    indent=1,
    timing="after_speech",
)
```

**Slide panel:** highlight the adjacent side, animate the "?" label to "5 m".
```python
highlight_diagram_part(
    target="side_adjacent",
    color_token="--sb-neon",
    timing="visual_first",
)
annotate(
    target="label_distance",
    style="replace_text",
    label="5 m",
    timing="term_sync",
)
```

**Branch state:** main

**Beat goal:** show how the method generalizes. Same triangle, different missing side, different ratio — same procedure. The kid should feel the *cleanness* of "name the sides, pick the ratio." Cosine of 60° is 0.5 — clean arithmetic that lands as an *answer*, not a number on a calculator.

---

### Beat 7 — Boxed answer (5:30 – 6:00)

**Voice (verbatim):**
> *"There you go. Height up the wall: 8.66 metres. Distance from the wall: 5 metres. And once you know which side is which, picking the right ratio is automatic. SOH CAH TOA isn't something you memorize — it's something you read off the triangle."*

**Notebook panel:**
```python
write_answer(
    latex=r"h = 8.66 \text{ m}, \quad d = 5 \text{ m}",
    timing="after_speech",
)
```
The `write_answer` tool draws an SVG rect overlay around the result with the `sb-answer-glow` pulse — the visual signature of "this is the final answer." The answer-box trace animation is 320ms (per `10-split-board.md` Phase 6).

**Branch state:** main

**Beat goal:** the win moment. The kid sees the final answer boxed, hears the "automatic, not memorized" reframe, and feels the lesson land. This beat closes the original problem.

---

### Beat 8 — Confirmation problem (6:00 – 7:00) ⭐

The kid solves it. Not the AI.

**Voice (verbatim):**
> *"Try one. I'll just watch — talk through it as you go."*

**Notebook panel:**
```python
new_page(
    carry_forward_ids=["soh_cah_toa"],  # carries forward the SOH CAH TOA equation block, dimmed
)
write_section(title="Try this one")
write_text(
    text=(
        "A flagpole is supported by a wire. The wire goes from the top of the pole to a point on the ground, "
        "making a 30° angle with the ground. The wire is 8 m long. How tall is the flagpole?"
    ),
    timing="after_speech",
)
```

**Slide panel:** swap to a fresh diagram (cache-hit pre-generated, `diagrams/aanya_demo/flagpole_confirmation.json`):
```python
draw_design_diagram(
    prompt=(
        "A vertical flagpole on a dark board. A diagonal wire goes from the top of the flagpole down to a point on horizontal ground. "
        "The wire is labeled '8 m'. The flagpole length is labeled '? (height)'. "
        "The angle between the wire and the ground (at the ground end of the wire) is marked '30°' with a small arc. "
        "A small right-angle square at the base of the flagpole. "
        "Soft cyan/peach palette. Title: 'Flagpole'."
    ),
    timing="visual_first",
)
```

**Aanya speaks aloud (voice input, transcribed by LiveKit):**
> *"OK so… the wire is the hypotenuse, that's 8. The flagpole is the opposite — it's across from the 30° angle. So I want sine. sin(30°) = h over 8. So h is 8 times sin(30°). Sin of 30 is 0.5. So h is 4 metres?"*

**Voice (warm, brief — does not repeat what the kid said):**
> *"Beautiful. 4 metres exactly. And notice — you picked sine without thinking about it. That's because you understood why sine is the right ratio, not just what to chant. That's the whole game."*

**Notebook panel (responsive to kid's solve):**
```python
write_step(
    text="Wire = hypotenuse = 8. Flagpole = opposite (across from 30°). Use sin.",
    number=1,
    indent=0,
)
write_equation(
    latex=r"\sin(30°) = \frac{h}{8}",
    align_group="confirm",
    indent=1,
)
write_equation(
    latex=r"h = 8 \times 0.5 = 4 \text{ m}",
    align_group="confirm",
    indent=1,
)
write_answer(latex=r"h = 4 \text{ m}")
```

**Edge case — kid stuck or wrong:**
- If kid says wrong ratio (e.g. "cosine"): AI says "Hmm — which side did you say is the flagpole? Opposite or adjacent?" (a question, not the answer)
- If kid is silent for >8 seconds: AI says "Take your time. What's the first thing you want to identify?"
- If kid identifies sides correctly but stalls on the arithmetic: AI says "What's sin of 30 degrees?"
- These nudges are coded as a small policy in the agent; for v0 we hardcode 3 nudge templates.

**Branch state:** main (stays main; no new branch)

**Beat goal:** the kid wins. Lesson ends with the kid's reasoning, not the AI's. This is the engagement loop — the kid leaves understanding it AND knowing they understood it. That feeling brings them back tomorrow.

---

## 4. The doubt branch — detailed spec

The doubt branch in beat 4 is our irreducible moat. **It is real, not scripted.** The student asks whatever they actually want to ask; the agent handles it authentically. Pre-caching is a latency optimization (anticipation), not a fakery layer. Specifying every piece because every piece must work flawlessly under real conditions.

### 4.1 Trigger

The student speaks — whatever they actually want to ask. Could be the canonical "why is sine always opposite over hypotenuse?" or something simpler ("wait, what's adjacent again?") or something off-piste. LiveKit VAD detects speech, interrupts current TTS playback (`STTLLMTTSPipeline` has built-in interrupt support). The audio is transcribed and reaches the agent as a user message.

The agent's system prompt instructs: *if the student's utterance is a clarifying question on the conceptual basis of the current explanation, call `start_doubt_branch(related_concept=<a short string derived from the actual question>)`. If the utterance is not a doubt (chatter, agreement, off-topic), acknowledge briefly and continue the main flow.*

### 4.2 The push (real, with anticipation)

```python
related_concept = <extracted by LLM from the actual transcript>
await tc.state_machine.push_branch(concept=related_concept)
# state_machine.py:74–90 — pushes new BranchContext with state=HANDLING_DOUBT
tc.board_manager.push_board(
    name=f"Doubt: {related_concept}",
    branch_id=branch.id,
)
# board.py:140–150 — new active board, parent preserved
asyncio.create_task(tc.anticipation.warm_doubt(related_concept))
# anticipation.py:281–361 + 564–606 — real background generation; no-op if cache hit
asyncio.create_task(plan_doubt(related_concept))
# concept_planner.py — real LLM-generated structured plan based on the actual question
await _update_agent_prompt(ctx)  # LLM now sees the doubt plan
```

When the LLM next calls `draw_design_diagram(...)`, `tc.anticipation.match()` (anticipation.py:463–548) runs Jaccard similarity against the pre-cache library of 4–5 anticipated doubts. Target: ~80% hit rate on common student questions (≤800ms diagram). Cache miss → live generation with `slide_pending` + DraftingLoader (5–15s degraded path).

### 4.3 The slide swap

Cross-fade out parent slide (300ms) → cross-fade in doubt slide (300ms). Total ≤800ms on cache hit, including network round-trip and React render. On cache miss: DraftingLoader fires immediately (no blank), bridging voice plays, real diagram swaps in within 5–15s.

Parent notebook fades from 100% to 50% opacity (250ms). Doubt notebook page is empty; LLM populates it during the explanation.

### 4.4 The doubt mini-lesson (live, not scripted)

The LLM produces ~25–35 seconds of voice tailored to the *actual question asked*, anchored on the diagram that matched (or was generated). Voice script is **not bound** for this beat — the prompt provides only behavioral guidance:

- Tone: warm, direct, not condescending. Indian English.
- Anchor on the diagram visually — use term-sync to point at things if the diagram has `\htmlId` tags.
- Tie back to "this is why what we just wrote down works."
- Length: 25–35 seconds. Don't over-explain.
- End with a soft handoff cue ("with that in mind…", "OK so now…") before the verbatim return cue.

The LLM also writes 1–2 short notebook entries during the explanation, with `style="key_point"` on the load-bearing insight.

### 4.5 The pop (real)

```python
resolve_doubt()
# tools.py:1696
await tc.state_machine.pop_branch()  # back to parent BranchContext
tc.board_manager.pop_board()          # parent board reactivated
tc.anticipation.clear_doubt_cache()
await _update_agent_prompt(ctx)       # LLM prompt resets to parent
```

Slide cross-fades back (ladder reappears). Notebook fades back to 100%. The notebook still has the `Naming the sides` and `SOH CAH TOA` sections from beats 2 and 3 — exactly where we paused. **Nothing is lost.**

### 4.6 The return voice cue (verbatim)

> *"OK — back to your ladder. Let's use what we just wrote down."*

This sentence is verbatim because it's the AI's transition back into the bound main lesson, not a response to the student. Reliability matters here — keep it short, deterministic, predictable.

### 4.7 What can go wrong (real-world failure modes)

- **Student's utterance isn't recognized as a doubt.** Agent acknowledges briefly and continues the main flow. Acceptable — not every "wait" needs a branch. The prompt's directiveness on what counts as a doubt is the key.
- **Cache miss on doubt diagram.** DraftingLoader fires for 5–15s; the bridging acknowledgment + a short follow-on ("let me sketch this for you…") covers the gap. Degraded but not broken. Acceptable if hit rate stays above ~70% on the most common doubts.
- **LLM gives a poor or wrong response.** Mitigation: temperature tuning, the doubt-plan structured output, and the pre-cache library effectively constraining what topics the LLM goes deep on. Acceptance criteria require testing 3+ different ad-hoc doubts to verify response quality.
- **Pop-back is jarring.** Cross-fade timing + verbatim return cue both engineered for clean cognitive return.
- **Nested doubt** (student asks a doubt about the doubt). Architecture supports it via stack-based branching; for v0 we don't optimize the prompt for it. If it happens, the agent handles it correctly but without dedicated pre-cached diagrams — acceptable degraded path.
- **Off-topic question** (student says "I'm hungry"). Agent's prompt instructs it to acknowledge warmly and redirect ("after we finish — let's keep going"). Not a doubt; doesn't trigger `start_doubt_branch`.

---

## 5. Magic beats — engineering implications

Three moments must land. If any fails, the demo fails.

### Beat A — diagram appears with voice (no pause)

- All 3 main diagrams (ladder problem, ratio invariance, flagpole confirmation) are pre-generated offline before the demo URL is opened. Generated via `design_agent` → cached as JSON files → loaded into `tc.anticipation` at session start.
- On `draw_design_diagram(prompt=...)` call, `tc.anticipation.match(prompt, concept_index)` returns the cached spec instantly (`tools.py:1076–1100`).
- Frontend renders the `DrawDesignDiagramInstruction` within ~200ms of receipt.
- Stroke-reveal animation (`.dd-stroke-path` CSS) plays over ~700–1500ms while voice continues.
- **Net latency from voice cue to first visible stroke: ≤800ms.** Verified against `10-split-board.md` Phase 4 timings.

If cache miss: `slide_pending` instruction fires immediately, `DraftingLoader.tsx` shows neon drafting animation for up to 5s. For v0 demo we **must hit cache** — failing this kills the magic.

### Beat B — branch and return (REAL, not scripted)

- Detailed in §4. The mechanics already exist (`state_machine.py`, `board.py`, `tools.py:1637–1730`).
- The student asks whatever they actually want to ask. The agent extracts the concept, calls `start_doubt_branch`, and responds live.
- The pre-cache library (4–5 anticipated doubts) is anticipation — like a teacher with rehearsed answers for common questions. Real, not theater. Cache hit ≤800ms; cache miss → DraftingLoader for ≤5s while live generation runs.
- Only two voice lines in this beat are verbatim-bound: the bridging acknowledgment ("Beautiful question — let me show you.") and the return cue ("OK — back to your ladder. Let's use what we just wrote down."). The 25–35s explanation is live LLM output.
- Acceptance test: 3+ different testers ask 3 different ad-hoc questions. All branch correctly. All respond meaningfully.

### Beat C — kid solves it

- Beat 8. The agent is in *listen mode* during this beat — voice does not fill silence. `wait_for_playout()` is not the right primitive; we need `wait_for_user_speech(timeout_s=8)`.
- If the user does not have this primitive: build a 1-day add to the LiveKit pipeline, exposing a tool the agent can call to "be silent and listen."
- Three hardcoded nudge templates for stuck/wrong cases. The agent picks one based on whether kid said nothing, said wrong ratio, or said wrong final answer.
- **No automatic problem-completion logic.** The agent waits for the kid to state the answer, then confirms. This is intentional — the kid owns the win.

---

## 6. Build dependencies (the v0 hit list)

Five blockers between today and the demo running:

| # | Dependency | Owner | Estimate | File(s) |
|---|---|---|---|---|
| 1 | **In-memory `LessonPlan` loader** for the demo concept (bypass Neo4j) | Backend | 1 day | `backend/src/feynman/agent/lesson_plan.py` — add `lesson_plan_in_memory(concepts: list[ConceptNode])` constructor |
| 2 | **Pre-cached DiagramSpec library** — 7 diagrams (3 main lesson + 4 anticipated doubts) | Design + Backend | 2.5–3 days | Generate via `design_agent`; store as JSON in `data/aanya_demo/diagrams/`; load into `tc.anticipation` at session start. **Main 3:** ladder problem, ratio invariance, flagpole confirmation. **Doubt library 4:** `doubt_why_sin_opp_hyp`, `doubt_which_side_is_opposite`, `doubt_sin_vs_cos`, `doubt_why_ratios`. LLM matches via Jaccard similarity at runtime. Iterate on visual quality (front-load the main 3). |
| 3 | **Verbatim script binding in agent prompt** (main lesson beats only — beat 4 doubt is live) | Backend (prompt engineering) | 1 day | Inject the §3 voice script as `target_voice_script` field on beats 1, 2, 3, 5, 6, 7. Beat 4 gets ONLY the bridging acknowledgment and return cue as bound; the 25–35s explanation is live. Beat 8 is listen-mode. Add "follow target_voice_script verbatim when set; otherwise improvise per behavioral guidance" instruction in `prompts.py`. |
| 4 | **Question-paste UX** on dev URL | Frontend | 0.5 day | Hardcoded `<textarea>` on dev route (`/dev/aanya-demo`) pre-filled with §2 question; submit sends to agent as opening lesson context. |
| 5 | **`wait_for_user_speech` primitive** for beat 8 | Backend (LiveKit pipeline) | 1 day | New tool `listen(timeout_s)` exposed to LLM; pauses TTS, waits for STT result with timeout. |

**Optional but recommended:**
| # | Item | Estimate |
|---|---|---|
| 6 | Indian English TTS voice configuration | 0.5 day |
| 7 | Demo-specific session reset endpoint (so we can run the demo cleanly multiple times for moms) | 0.5 day |

**Total estimate: 6–8 days of focused work** for one engineer (you), assuming current capabilities hold up. The doubt library expansion adds ~1 day on Item 2. That fits inside the 2–3 week window with buffer for iteration on visual quality and script timing.

---

## 7. What we are NOT specifying (cut from v0 scope)

| Area | Status |
|---|---|
| Auth, payments, onboarding flow | Not in v0 demo |
| Parent dashboard | Not in v0 |
| Voice ID, multi-user | Not in v0 (single hardcoded user) |
| Microphone setup / permissions UX | Use browser default |
| Mobile / tablet experience | Laptop only |
| Multi-question / question library | Single hardcoded question |
| Subject switcher | Math only |
| Improvisation beyond script | Main-lesson beats are script-bound for v0; **beat 4 doubt is live**; loosened further in v1 |
| Camera-based perception | Parked (see archived `11-classroom-perception.md`) |
| Multi-lesson continuity / knowledge graph reads | v1+ — first lesson does not read graph |

---

## 8. Acceptance criteria

The demo is ready to show when **all** are true:

1. End-to-end runs in **<8 minutes wall-clock** (incl. ~30s buffer for kid's confirmation solve).
2. **All three magic beats land**:
   - Beat A: diagram visible within 800ms of voice cue, every time, all three main diagrams.
   - Beat B: **real doubt handling verified** — 3+ different testers each ask a different ad-hoc question during the doubt window. All branch correctly. All produce meaningful, non-generic responses tied to the actual question. Cache-hit rate ≥3/4 across the 4 most-likely doubts. Cache-miss path (DraftingLoader + live gen) gracefully degrades within 8s. Return-to-parent is clean every time. **Theater test: no scripted student utterances; the system responds to whatever is actually asked.**
   - Beat C: kid solves the confirmation problem; AI does not deliver the answer.
3. **No latency stalls >2 seconds** where voice is silent waiting on visual (cache-hit path); ≤8s with bridging voice (cache-miss path).
4. **≥3 of 5 internal viewers** (you, me, friends-as-test-audience) say *"whoa"* unprompted at one of the magic beats. This is the cheap pre-validation gate before we run the moms test.
5. The viewer (or kid playing kid) **actually understands** the SOH CAH TOA decision logic by the end — verified by asking them: *"if the wire was on a 45° angle instead of 30°, how would you find the flagpole height?"* They should answer "still sine, h = 8 × sin(45°)" without the AI's help.

If any criterion fails: stop, fix, re-test. Do not proceed to mom-validation until all five are green.

---

## 9. Validation test (after acceptance criteria pass)

- 5 IB/IGCSE moms recruited via founder network. Mix: 3 with kids in Year 9–10, 2 with kids in Year 7–8.
- Each session: 15 minutes. Mom watches the demo. Aanya's role is played by a tester (could be the mom's actual kid if available, or a friend's kid, or one of us). The tester asks a *real, unscripted* doubt at beat 4 — different from session to session — to demonstrate real handling. Recorded.
- Post-demo questions: (i) "what did you notice?" (open-ended), (ii) "if this existed today, what would you pay per month?" (number + reaction time), (iii) "would you give this to your daughter?" (yes/no/conditional + reason).
- **Pass gate**: ≥3 of 5 moms have unprompted "whoa" at one of the magic beats AND ≥3 of 5 say a price ≥₹3000/mo without prompting. If both gates pass, we proceed to Phase 1 product surface (auth/payments/onboarding/5–10 topics). If either fails, we revisit demo design before any product-surface work.

---

## 10. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-05-10 | Past paper question chosen: ladder against wall, length 10 m, 60° angle. Find height (sin) and distance (cos). | Classic IGCSE 0580 Paper 4 trig word problem. Tests side identification + ratio selection in one question. cos(60°)=0.5 gives a clean answer for one part; sin(60°) is authentically irrational like real IGCSE problems. |
| 2026-05-10 | Doubt chosen: "why is sine always opposite over hypotenuse — why is that ratio constant?" | The single deepest "why" in trigonometry. Resolution teaches similar-triangles-as-foundation-of-trig — two topics in 30 seconds. Natural pedagogical question for a 13-year-old. |
| 2026-05-10 | Confirmation problem: flagpole + wire, 30° angle, wire = 8 m. Find flagpole height. | Same conceptual structure (identify sides → pick sin) with cleaner arithmetic (sin 30° = 0.5 → h = 4 m). Kid wins with mental math. |
| 2026-05-10 | Latency budget: cache-hit ≤800ms, cache-miss ≤5s with DraftingLoader. Demo MUST be cache-hit on all 3 diagrams | 5–15s drafting loader during a 7-min demo kills the magic |
| 2026-05-10 | Script binding: verbatim script for v0; improvisation deferred to v1+ | Reliability over flexibility for the moment-of-truth demo |
| 2026-05-10 | Lesson plan: in-memory bypass for demo, full Neo4j ingestion deferred | 1 day instead of 2; demo doesn't need full curriculum machinery |
| 2026-05-10 | TTS voice: Indian English preferred but not blocker for internal acceptance test; required for mom validation | Audience perception |
| 2026-05-10 | Beat 8 confirmation problem: kid solves, AI does not deliver answer | Engagement loop — kid owns the win |
| 2026-05-10 | **Topic switched: similar triangles → right-triangle trigonometry** | Trigonometry is the more iconic IGCSE Year 9 pain point with higher parent recognition. The doubt branch ("why is sin = opp/hyp constant?") still teaches similar-triangle invariance — we get both topics in one demo, with stronger emotional resonance for moms watching. |
| 2026-05-10 | **Doubt branch is real, not scripted.** Pre-cache 4–5 anticipated doubts; LLM matches via Jaccard similarity; live response | The whole pitch is "AI handles whatever your kid asks." A scripted doubt undermines the pitch — moms eventually catch on. Anticipation pre-caching is real teaching practice (rehearsed answers for common questions), not theater. Adds ~1 day to build sprint. |

---

## 11. Next artifacts

After this spec is reviewed and approved:

1. **Codebase audit / blocker hit list** — turn §6 into a sized engineering ticket list with file-level changes. Already partially specified above; needs a deeper read of `livekit/pipeline.py` to size dependency #5. Lives at `docs/design/13-aanya-demo-build-list.md`.
2. **Pre-generation script** — small Python script that runs `design_agent` against the 3 diagram prompts in §3 and saves the resulting `DiagramSpec` JSON to `data/aanya_demo/diagrams/`. We iterate visual quality here before any other engineering starts.
3. **Build sprint** — 5 days of focused work against the hit list. Daily check-in against the acceptance criteria.
