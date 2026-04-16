# 07 — What's Actually Broken & What to Fix

> Ran a live SHM teaching session on Apr 4. The infrastructure works. The output is broken.

---

## The Brutal Truth

All 9 phases of board intelligence are built and tested (489 backend tests pass). But at runtime, **almost none of it is functioning as designed**. The anticipation cache never hits. The lesson plan isn't followed. Diagrams are cluttered. Highlighting is out of sync with voice. The board relationship graph is empty.

We built the engine. The engine isn't connected to the wheels.

---

## Problem 0: Runtime Systems Are Disconnected (BLOCKING EVERYTHING)

### 0A. Anticipation Cache Never Hits

**Evidence from logs:**
```
18:34:13  set_lesson_topic → anticipation.batch_start count=3
18:34:53  Agent calls draw_design_diagram → anticipation.no_match best_score=0
18:34:56  First cached spec finishes (43s elapsed)
18:35:04  All 3 specs cached (batch_done)
```

The agent needed the cache at `18:34:53`. The cache finished at `18:34:56`. **3 seconds too late.** Design agent takes 43-51 seconds to generate a spec. The teaching agent starts drawing within 40 seconds.

But even if the cache was ready, **Jaccard matching would still fail**:
- Cached prompt: `"Draw a detailed educational diagram for: Simple Harmonic Motion. Context: An oscillation is a repetitive motion. The restoring force proportional to displacement..."`
- Agent's actual call: `"A simple pendulum showing simple harmonic motion. Draw a pendulum with a string attached to a fixed point..."`
- Token overlap: ~1-2 words out of 20+. Jaccard ≈ 0.05. Threshold is 0.15.

**Root cause**: The cached prompts (built from graph node summaries) and the agent's prompts (specific diagram descriptions) use completely different vocabulary. The matching algorithm can't bridge this gap.

**Fix options:**
1. **Show the agent its pre-cached prompts** — the prompt building code at `prompts.py:776-789` tries to include `pre_gen` visual prompts, but warm() hasn't finished when the prompt is built. Either await warm() completion before building the first prompt, or update the prompt after warm completes.
2. **Switch from Jaccard to semantic matching** — embed both prompts and use cosine similarity. Heavyweight but actually works.
3. **Simpler: match on concept index only** — if the agent is on concept 0 and we have a cached spec for concept 0, just use it. Don't try to match prompt text at all. The curriculum graph already knows what diagram to show for each concept.

Option 3 is the fastest and most reliable. The anticipation engine already knows which concept the agent is on. Just use that.

**Files:** `backend/src/feynman/agent/anticipation.py` (match method), `backend/src/feynman/livekit/worker.py` (warm timing), `backend/src/feynman/agent/prompts.py` (pre_gen inclusion)

### 0B. Agent Doesn't Follow the Lesson Plan

**Evidence**: Agent receives `set_lesson_topic` with 13-concept SHM graph. Never calls `advance_concept()`. Teaches freestyle from the rich curriculum content in the prompt.

The prompt DOES tell the agent:
```
**CRITICAL — One concept at a time**:
- Teach ONLY the current concept (marked [>> CURRENT] in the sequence below).
- After covering all its key points and showing at least one visual, call advance_concept().
```

But the agent also sees rich teaching content from the graph and starts improvising. It never advances because it never feels "done" with concept 0.

**Fix:** Make the lesson plan enforcement stronger. The current instruction is buried deep in the prompt. Move it to the top-level system prompt. Add: "You MUST call advance_concept() after spending ~2-3 minutes on the current concept. Do not stay on one concept indefinitely."

**File:** `backend/src/feynman/agent/prompts.py` (STATE_TOOL_INSTRUCTIONS, build_teaching_prompt)

### 0C. Highlighting Out of Sync with Voice

**Evidence**: `"flush audio emitter due to slow audio generation"` appears 8+ times.

**Root cause**: `highlight_diagram_part` has no `timing` parameter. It publishes immediately. But TTS (gpt-4o-mini-tts) is generating audio too slowly — the highlight appears before the teacher says the corresponding words.

The teaching prompt says: "call highlight BEFORE speaking about each part." But the highlights fire, then TTS takes 5-15s to generate the speech. Student sees highlight flash, then 10 seconds later hears the explanation.

**Fix:** Add `timing` parameter to highlight tools (same as diagram tools). Default to `"visual_first"` but with a `wait_for_playout()` fallback. Or: investigate why TTS is so slow — gpt-4o-mini-tts should be faster than this.

**Files:** `backend/src/feynman/agent/tools.py` (highlight_diagram_part, highlight_walk)

### 0D. Board Relationship Graph Always Empty

**Evidence**: Every element logged as `orphan_element — created without relates_to`.

**Root cause**: The teaching prompt never mentions `relates_to`. The agent has the parameter available but no instruction to use it. Phase 6 built the graph infrastructure; nothing tells the agent to populate it.

**Fix:** Add examples to the teaching prompt showing `relates_to` usage:
```
When you draw a diagram that illustrates an equation already on the board,
pass relates_to="eq-1" to connect them semantically.
```

**File:** `backend/src/feynman/agent/prompts.py` (tool usage examples)

---

## Problem 1: Diagram Cluttering

### Hard Data from Generated Specs

Analyzed the actual JSON specs Claude generates. The numbers are damning:

| Diagram | Total Elements | Text/Latex | Close Pairs (< 25px apart) |
|---------|---------------|------------|---------------------------|
| SHM Overview | 48 | 27 | **12** |
| Pendulum | 30 | 14 | 5 |
| Key Parameters | 39 | 27 | **7** |
| Spring-Mass | 47 | 23 | **14** |

**27 text elements on a 900x650 canvas** with only 20px vertical gaps between them. KaTeX at fontSize 14 renders ~20-25px tall. The text literally touches or overlaps the element below.

Example from SHM spec:
```
(640, 125) "Restoring Force:"     fontSize=14
(640, 145) "F = -kx = -mω²x"     fontSize=14   ← 20px gap, KaTeX renders ~22px tall = OVERLAP
(640, 175) "Acceleration:"        fontSize=14
(640, 195) "a = -ω²x"            fontSize=14   ← 20px gap again
(475, 200) "Velocity vs Time"     fontSize=14   ← SAME Y-BAND, different column = visual collision
```

### Why It's Happening

The design agent prompt (`design_agent/backend/prompts.py`) Rule #3:
> "Clean layouts: use the full canvas. Spread elements out."

That's the ONLY layout instruction. No minimum spacing. No density limits. No font size floors.

### The Fix

**A. Rewrite design agent prompt Rule #3:**

```
3. **Layout rules (NON-NEGOTIABLE — violations make diagrams unreadable)**:
   - Minimum 40px vertical gap between ANY two svg_text or svg_latex elements
   - Minimum 30px clearance between text labels and diagram geometry
   - Maximum 5 text/latex elements per 250×250px region
   - Font size minimums: svg_text ≥ 13px, svg_latex ≥ 15px
   - Canvas structure:
     - Title zone: y = 0–80
     - Diagram zone: y = 80–480 (physical setup, shapes, arrows)
     - Info zone: y = 480–650 (equations, parameters, formulas — NEVER in diagram zone)
   - Step-by-step derivations: 50px vertical gap between steps
   - With >8 text elements: mentally grid into quadrants, distribute evenly
   - With interactive parameters: ALL explanatory text in bottom 25%
   - NEVER pack "Key Features" or "Summary" text blocks into the diagram area
```

**B. Cap element count in the design agent prompt:**

Add: "Maximum 15 text/latex elements per diagram. If you need more, split into logical groups and reduce to the most essential labels. A clean diagram with 8 labels is better than a cluttered one with 25."

**C. Pass zone dimensions from teaching agent:**

When draw_design_diagram targets center-left (290px wide on screen), tell the design agent: "This diagram renders at 290×475px. Use maximum 3 labels, fontSize ≥ 16, simple layout."

**D. Frontend collision detection (safety net):**

After rendering, check `getBoundingClientRect()` on all KaTeX overlays. Nudge overlapping elements down. Log collision count for monitoring.

**Files:**
- `design_agent/backend/prompts.py` — prompt rewrite
- `backend/src/feynman/agent/tools.py` — zone-aware sizing
- `frontend/src/engine/whiteboard/content/DesignDiagramContent.tsx` — collision detection

---

## Problem 2: Board Has No Visual Narrative

Content appears wherever the zone system places it. No flow, no story. The agent creates elements one at a time without thinking about the board as a composition.

### The Fix

**A. Board hygiene in teaching prompt:**
```
Before starting a new concept: if the board has >4 elements, clear it or scroll to a fresh tile.
One concept = one board composition. Start fresh for each concept.
```

**B. Density in board summary:**
```
Board: 6 elements (CROWDED)
  center-center: 3 elements — FULL
  center-right: 2 elements
  top-right, bottom-*: empty
```

**C. Enforce zone patterns as rules, not suggestions.**

**Files:** `backend/src/feynman/agent/prompts.py`, `backend/src/feynman/agent/board_state.py`

---

## Problem 3: Animation Polish (After 0-2 Are Fixed)

The slider/parameter system works. Once diagrams are clean, animations become powerful:

- **Progressive reveal**: Elements appear in groups matching the teacher's voice
- **Smooth transitions**: Diagram modifications morph instead of hard-cut
- **Showcase demos**: SHM spring-mass, pendulum, wave interference — hand-verified quality

---

## Priority Sequence

```
FIRST      Fix the runtime disconnects (Problem 0)
           ├── 0A: Anticipation cache hit rate (concept-index matching)
           ├── 0B: Lesson plan following (advance_concept enforcement)
           ├── 0C: Audio-visual sync (timing on highlights)
           └── 0D: Board graph population (relates_to in prompt)
           |
           |  Without these, the 9 phases of infrastructure we built are dead.
           |  This is unblocking work, not new features.
           v
SECOND     Fix diagram quality (Problem 1)
           ├── Prompt rewrite with hard spacing rules
           ├── Element count caps
           ├── Zone-aware sizing
           └── Frontend collision detection
           |
           |  Every diagram gets better immediately.
           v
THIRD      Board narrative (Problem 2)
           ├── Clear-before-draw discipline
           ├── Density metrics in board summary
           └── Stricter zone enforcement
           |
           v
FOURTH     Animation polish (Problem 3)
           ├── Progressive element reveal
           ├── Smooth morph transitions
           └── Showcase-quality demos
```

---

## Files That Matter Most

| Priority | File | What to change |
|----------|------|---------------|
| **0A** | `anticipation.py` | Match on concept index, not Jaccard. Or await warm before first prompt. |
| **0B** | `prompts.py` | Stronger advance_concept enforcement, move to top of prompt |
| **0C** | `tools.py` | Add `timing` param to highlight tools |
| **0D** | `prompts.py` | Add `relates_to` examples to tool usage section |
| **1A** | `design_agent/backend/prompts.py` | Hard spacing rules, element caps, canvas zoning |
| **1B** | `tools.py` | Pass zone dimensions to design agent |
| **1C** | `DesignDiagramContent.tsx` | Post-render collision detection |
| **2** | `prompts.py`, `board_state.py` | Board hygiene, density metrics |

---

## Success Criteria

**Runtime systems connected (Problem 0):**
- [ ] Anticipation cache hit rate > 80% for on-plan teaching
- [ ] Agent calls advance_concept() and progresses through lesson plan
- [ ] Highlights appear within 1s of corresponding speech
- [ ] Board graph has edges (no orphan elements)

**Diagram quality (Problem 1):**
- [ ] Generate 10 SHM diagrams — zero overlapping text
- [ ] Max 15 text elements per diagram
- [ ] Minimum 40px gap between all text elements in generated specs
- [ ] Side-zone diagrams (290px) are legible

**Board narrative (Problem 2):**
- [ ] 5-minute session — every board snapshot independently readable
- [ ] No board exceeds 6 elements
- [ ] Related content in adjacent zones

**Animations (Problem 3):**
- [ ] SHM demo: clean, animated, non-overlapping
- [ ] Progressive reveal for 3+ diagram types
- [ ] Smooth diagram modifications
