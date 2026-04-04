# 07 — Visual Quality & Next Steps

> What's standing between the current product and something that makes people say "holy shit."

---

## The Brutal Truth

The board intelligence infrastructure is solid (9 phases done, 489 tests). The anticipation engine works. The modify tool works. The teaching state machine works.

**But none of that matters if what appears on screen looks like garbage.**

Right now, diagrams come out with overlapping text, cramped labels, and zero visual hierarchy. A student looking at the board can't parse what they're seeing. The underlying systems are strong — the output layer is failing.

Three things to fix, in order.

---

## Problem 1: Diagram Cluttering (CRITICAL)

### What's happening

Claude generates DiagramSpec JSON with absolute pixel coordinates for every text element. It frequently places labels on top of other labels, equations on top of diagram geometry, and parameter lists on top of everything.

Screenshots show: SHM diagrams where "Key Features of SHM" text collides with "Energy Conservation" text, equation parameters overlapping each other, formula blocks unreadable.

### Why it's happening

**The design agent prompt (`design_agent/backend/prompts.py`) has exactly one layout instruction:**

> "Clean layouts: use the full canvas. Spread elements out."

That's it. No minimum spacing. No collision rules. No density limits. Claude is guessing at coordinates and getting it wrong ~40% of the time.

**Compounding factors:**
- Canvas is 900x650 but may render at 290px wide in a side zone — text designed for 900px becomes microscopic
- Frontend renders every element at the exact coordinates Claude specified, no validation
- KaTeX overlays are positioned with CSS `left`/`top` percentages — no overlap check
- No feedback: the agent never knows a diagram came out bad

### The Fix

**A. Rewrite design agent prompt with hard spatial rules**

File: `design_agent/backend/prompts.py`, Rule #3

Replace the vague "spread elements out" with:

```
3. **Layout rules (non-negotiable)**:
   - Minimum 40px vertical gap between any two text/latex elements
   - Minimum 30px clearance between labels and diagram geometry (lines, shapes, arrows)
   - Maximum 5 text elements per 250x250px region
   - Font size floor: 13px for labels, 15px for equations, 11px for fine annotations
   - Canvas zones: title area (y: 0-80), diagram area (y: 80-500), formula/parameter area (y: 500-650)
   - NEVER place parameter lists or formula summaries inside the diagram area — always below it
   - For step-by-step derivations: 50px vertical gap between steps
   - If you have >8 text elements: mentally grid the canvas into quadrants and distribute evenly
   - When parameters/sliders exist: keep all explanatory text in the bottom 25% of canvas
```

**B. Pass actual display dimensions to the design agent**

File: `backend/src/feynman/agent/tools.py` (in `draw_design_diagram`)

When the teaching agent requests a diagram, include the zone it will render in:

```python
# Before calling design agent, compute actual display size
zone = instruction.zone or "center-center"
display_width, display_height = get_zone_dimensions(zone)  # e.g., 290x475 for side zones

# Add to the design agent request
prompt = f"{user_description}\n\n[Display context: this diagram renders at {display_width}x{display_height}px. Design accordingly — use fewer labels and larger font if narrow.]"
```

If the zone is 290px wide: max 3 labels, font size 16px minimum, no parameter sections (show those separately via `show_equation` tool instead).

**C. Frontend post-render collision detection**

File: `frontend/src/engine/whiteboard/content/DesignDiagramContent.tsx`

After rendering KaTeX overlays, check for overlap:

```typescript
useEffect(() => {
  const overlays = containerRef.current?.querySelectorAll('.katex-overlay');
  if (!overlays) return;
  const rects = Array.from(overlays).map(el => el.getBoundingClientRect());
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      if (rectsOverlap(rects[i], rects[j])) {
        // Nudge the later element down by the overlap amount + 8px padding
        const overlap = rects[i].bottom - rects[j].top + 8;
        (overlays[j] as HTMLElement).style.transform = `translateY(${overlap}px)`;
      }
    }
  }
}, [spec]);
```

This is a safety net, not the primary fix. The prompt rewrite (A) should prevent most collisions. This catches the rest.

**Estimated effort:** 1 session for prompt rewrite + testing, 1 session for zone-aware sizing, 1 session for frontend collision detection.

---

## Problem 2: Board Has No Visual Narrative

### What's happening

Content appears wherever the zone system places it. There's no flow, no story, no visual logic. A student sees scattered equations and diagrams with no sense of "this leads to that."

The existing zone placement patterns (5 teaching scenarios in prompts.py) exist but are too loose — the agent treats them as suggestions, not rules.

### Why it's happening

- Zone patterns describe WHERE to put things but not HOW to compose them into a narrative
- No "clear before new concept" discipline — the board accumulates clutter across concepts
- Board summary tells the LLM what's on the board but not how crowded it is
- The agent doesn't think about the board as a whole composition — it thinks one tool call at a time

### The Fix

**A. Enforce board discipline in the teaching prompt**

File: `backend/src/feynman/agent/prompts.py`

Add a "Board Hygiene" section:

```
## Board Hygiene

- Before starting a new concept: check the board summary. If >4 elements exist, clear the board
  or scroll to a fresh tile. Don't keep piling onto a full board.
- One concept = one board composition. When you move to the next concept, start fresh.
- Every board composition should be readable as a standalone snapshot — a student glancing at the
  board should understand the current concept without needing prior context.
```

**B. Add density to board summary**

File: `backend/src/feynman/agent/board_state.py`

Include zone density in the summary the LLM sees:

```
Board: 6 elements (CROWDED)
  center-center: 3 elements [diagram, equation, text] — FULL
  center-right: 2 elements [equation, equation]
  top-left: 1 element [text]
  top-right, bottom-*: empty
```

When the LLM sees "CROWDED" and "FULL" it should naturally decide to clear or scroll.

**C. Visual grouping via spatial proximity**

When placing related content (an equation that describes a diagram, a label that annotates a shape), use consistent spatial patterns. The agent should place the equation *next to* the diagram it describes, not in a random empty zone.

This is partially handled by the board relationship graph (phase 6) but needs tighter integration into the zone selection logic.

**Estimated effort:** 1-2 sessions.

---

## Problem 3: Animations Should Showcase, Not Just Exist

### What's happening

The slider/parameter system works — you can animate phase diagrams, change amplitude, adjust frequency. But the diagrams being animated are cluttered (problem 1), so the animations look bad even though the mechanism is good.

### The Fix (After Problem 1)

**A. Clean up the showcase diagrams**

Once the prompt rewrite lands, re-test with SHM (Simple Harmonic Motion) and other physics animations. The spring-mass system, pendulum, wave interference — these should be the "wow" demos. Each one needs to be hand-verified for visual quality.

**B. Progressive element reveal**

Instead of all elements appearing at once, reveal them in groups that match the teacher's voice:

1. First: the physical setup (spring, mass, surface)
2. Then: the motion indicators (arrows, trajectory)
3. Then: the equations
4. Then: the parameter sliders become active

This uses the existing `timing` parameter system but needs the design agent to output elements in a meaningful order (grouped by reveal stage).

Add to design agent prompt:
```
Order elements by visual importance: physical objects first, then annotations,
then labels, then equations. The frontend reveals elements progressively —
earlier elements in the array appear first.
```

**C. Smooth transitions on diagram modification**

When the modify tool updates a diagram (e.g., changing a force vector's magnitude), animate the change. Current behavior: hard replacement with a fade. Better: GSAP morph from old element positions to new ones.

File: `frontend/src/engine/whiteboard/content/DesignDiagramContent.tsx` — track previous spec, diff against new spec, animate changed elements.

**Estimated effort:** 1 session for cleanup, 2 sessions for progressive reveal, 2 sessions for morph transitions.

---

## Priority Sequence

```
NOW        Fix diagram cluttering (prompt rewrite + zone-aware sizing)
           |
           |  This alone will make the biggest visible difference.
           |  Every diagram gets better immediately.
           v
NEXT       Board narrative discipline (clear-before-draw + density awareness)
           |
           |  Board starts feeling composed, not chaotic.
           v
THEN       Animation polish (progressive reveal + smooth transitions)
           |
           |  This is where "wow" happens. But only if diagrams are clean first.
           v
AFTER      Production hardening (monitoring, error recovery, load testing)
```

---

## Files That Matter Most

| Priority | File | What to change |
|----------|------|---------------|
| 1 | `design_agent/backend/prompts.py` | Hard spatial rules, spacing minimums, canvas zoning |
| 2 | `backend/src/feynman/agent/tools.py` | Pass zone dimensions to design agent |
| 3 | `frontend/src/engine/whiteboard/content/DesignDiagramContent.tsx` | Post-render collision detection |
| 4 | `backend/src/feynman/agent/prompts.py` | Board hygiene rules, stricter zone patterns |
| 5 | `backend/src/feynman/agent/board_state.py` | Density metrics in board summary |
| 6 | `design_agent/backend/prompts.py` | Element ordering for progressive reveal |
| 7 | `frontend/src/engine/whiteboard/content/DesignDiagramContent.tsx` | GSAP morph transitions |

---

## Success Criteria

**Diagram quality (problem 1 solved):**
- [ ] Generate 10 SHM diagrams — zero overlapping text in all 10
- [ ] Generate 10 optics diagrams — all labels readable at actual rendered size
- [ ] Side-zone diagrams (290px wide) are clean and legible, not just scaled-down versions of full-width diagrams

**Board narrative (problem 2 solved):**
- [ ] Record a 5-minute teaching session — every board snapshot is independently readable
- [ ] No board has >6 visible elements at any point
- [ ] Related content (equation + its diagram) always appears in adjacent zones

**Animations (problem 3 solved):**
- [ ] SHM spring-mass demo: clean, animated, parameters visible and non-overlapping
- [ ] Progressive reveal works for at least 3 diagram types
- [ ] Diagram modifications animate smoothly (no hard cuts)
