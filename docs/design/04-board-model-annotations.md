# Board Model & Annotation Precision

## The Problem

When we say "circle the chloroplast" or "write a note near the glucose output" — how does the system KNOW where those things are on the screen? The LLM generates semantic instructions like `circle(target: "chloroplast")` but someone needs to translate that into actual pixel coordinates.

Additionally, annotations need to be **intelligent** — not mechanical highlighting every time a term is mentioned, but pedagogical: "highlight NOW because I'm making a key point about this part."

---

## The Two-Layer Board Model

**The LLM thinks semantically. The frontend thinks spatially. They share a board model between them.**

```
+---------------------------------------------------------+
|                    BOARD MODEL                          |
|                                                         |
|   LOGICAL LAYER (backend)          SPATIAL LAYER        |
|   "what's on the board"            (frontend)           |
|                                    "where it all is"    |
|   +---------------------+                               |
|   | board_id: "board_1" |    +------------------------+ |
|   | elements:            |    | spatial_index (RBush):  | |
|   |  -  |    |                        | |
|   |    zone: "center"    |    | chloroplast:           | |
|   |    components:       |    |   bbox: {x:340, y:220, | |
|   |     - chloroplast    |    |    w:120, h:80}        | |
|   |     - nucleus        |    |   center: {x:400,      | |
|   |     - cell_wall      |    |    y:260}              | |
|   |     - vacuole        |    |                        | |
|   |  - equation_1        |    | nucleus:               | |
|   |    zone: "right"     |    |   bbox: {x:250, y:180, | |
|   | annotations: []      |    |    w:100, h:100}       | |
|   +---------------------+    |                        | |
|                               | vacuole:               | |
|   The LLM sees THIS ^        |   bbox: {x:200, y:300, | |
|   Enough to reason about     |    w:160, h:90}        | |
|   the board without           |                        | |
|   pixel coordinates           | ... every element      | |
|                               +------------------------+ |
|                               The RENDERER builds this ^ |
|                               after drawing each element |
+---------------------------------------------------------+
```

---

## How Annotation Resolution Works

When the backend sends a semantic annotation instruction, the frontend resolves it spatially.

### Circle
```
Backend sends:  {"action": "circle", "target": "chloroplast"}

Frontend resolves:
  1. Look up "chloroplast" in spatial index
     -> bbox: {x:340, y:220, w:120, h:80}
  2. Calculate circle:
     center = bbox.center -> (400, 260)
     radius = max(w, h)/2 + padding -> 80
  3. Draw hand-drawn circle (Rough.js) at those coords
```

### Margin Note ("write something near")
```
Backend sends:  {"action": "margin_note", "near": "chloroplast",
                 "text": "this is the factory!"}

Frontend resolves:
  1. Look up chloroplast bbox -> (340, 220, 120, 80)
  2. Try placement candidates (priority order):
     - right of element: (340+120+gap, 220)
     - above element: (340, 220-gap-textHeight)
     - left of element: (340-gap-textWidth, 220)
     - below element: (340, 220+80+gap)
  3. For each candidate, check spatial index:
     "is this space FREE?" (no overlap with other elements)
  4. Pick first free candidate
  5. Draw text there + connector line to chloroplast
  6. Register annotation IN the spatial index
     (so next annotation avoids it too)
```

### Arrow Between Elements
```
Backend sends:  {"action": "arrow", "from": "sunlight_input",
                 "to": "chloroplast", "label": "light energy"}

Frontend resolves:
  1. Look up source bbox and target bbox
  2. Calculate edge points (closest edges between the two)
     source_edge: bottom-center of sunlight_input
     target_edge: top-center of chloroplast
  3. Check: is the straight path clear?
     (query spatial index for obstacles)
     -> Clear: straight arrow
     -> Blocked: bezier curve that arcs around obstacle
  4. Place label at arrow midpoint
  5. Register arrow path in spatial index
```

### Highlight
```
Backend sends:  {"action": "highlight", "target": "chloroplast",
                 "style": "glow"}

Frontend resolves:
  1. Look up chloroplast bbox
  2. Apply glow effect (CSS filter or canvas overlay)
     exactly on those bounds
  3. No spatial index query needed -- it's on top of the element
```

---

## The Feedback Loop: LLM Needs Board Awareness

The LLM needs to know ROUGHLY where things are — not for annotation placement (frontend handles that), but **so its SPEECH is spatially accurate**.

If the LLM says "look at the bottom-left" but the chloroplast is in the top-right — that's wrong even if the highlight lands in the right place.

### Frontend -> Backend: Board State Summary

After rendering, the frontend sends back a simplified spatial summary:

```json
{
  "board_state": {
    "diagram": "plant_cell",
    "zone": "center",
    "element_positions": {
      "chloroplast": {"quadrant": "upper-right", "relative": "right of nucleus"},
      "nucleus": {"quadrant": "center", "relative": "center of cell"},
      "vacuole": {"quadrant": "lower-center", "relative": "below nucleus"},
      "cell_wall": {"quadrant": "full", "relative": "outer boundary"},
      "mitochondria": {"quadrant": "lower-right", "relative": "near cell wall"}
    },
    "free_zones": ["left-margin", "top-margin", "bottom-right"],
    "active_annotations": []
  }
}
```

This goes into the LLM's context. Now it generates spatially accurate speech:
```
"Now look at the upper-right area -- see that green structure?
 That's the chloroplast."
```

**"Upper-right" matches reality because the LLM knows the layout.**

### What We Already Have

The `SceneGraph` class in `backend/src/feynman/agent/scene_graph.py` already does this:
- Collects pixel-precise bounds from the frontend via `BoundsReportPayload`
- Generates natural-language spatial summaries (positions, sizes, relationships)
- Tracks density per quadrant
- Finds largest free regions
- Reports spatial relationships between elements ("chloroplast is right-of nucleus")

The `BoardState` class already integrates the SceneGraph summary into the LLM prompt via `build_teaching_prompt()`.

---

## The Full Feedback Loop

```
+----------------------+
|    TEACHING BRAIN     |
|                       |
| Has board state:      |
| "chloroplast is       |
|  upper-right,         |
|  nucleus is center"   |
|                       |
| Generates beat:       |------semantic instruction----+
| "circle chloroplast,  |                              |
|  say 'upper-right'"   |                              |
+----------^------------+                              |
           |                                           |
   board state                                         |
   summary                                             v
   (after render)                           +---------------------+
           |                                |   FRONTEND RENDERER  |
           |                                |                     |
           |                                | 1. Receives "circle |
           |                                |    chloroplast"     |
           |                                | 2. Looks up spatial |
           |                                |    index -> (340,220)|
           |                                | 3. Draws circle at  |
           |                                |    exact position   |
           |                                | 4. Updates spatial  |
           |                                |    index            |
           |                                | 5. Sends board state|
           +--------------------------------|    summary back     |
                                            +---------------------+
```

---

## Where the Spatial Index Comes From

The spatial index builds itself during rendering:

```
Step 1: Backend sends "draw plant_cell diagram in center zone"

Step 2: Frontend diagram renderer draws the plant cell
        As it draws EACH component, it registers in the spatial index:

        renderer.drawComponent("cell_wall", cellWallPath)
        -> spatialIndex.insert("cell_wall", {x:100, y:50, w:400, h:350})

        renderer.drawComponent("nucleus", nucleusShape)
        -> spatialIndex.insert("nucleus", {x:250, y:180, w:100, h:100})

        renderer.drawComponent("chloroplast", chloroplastShape)
        -> spatialIndex.insert("chloroplast", {x:340, y:220, w:120, h:80})

Step 3: Spatial index is complete.
        Any future "circle X" or "write near Y" resolves instantly.

Step 4: Frontend generates board state summary, sends to backend.
```

**Every component knows its own bounds** because we render them. There's no guessing. The spatial index is a natural byproduct of rendering.

---

## Intelligent Annotation: "When Needed" Not "Every Time"

### Bad: Mechanical annotation
Every time "chloroplast" is mentioned, highlight it. Students learn to ignore the highlights.

### Good: Intentional annotation
A good teacher annotates intentionally:
- **First mention** -> just say it, students look at the diagram themselves
- **Key insight moment** -> circle it: "THIS is where the magic happens"
- **Student confusion** -> circle + arrow: "No, not this part -- THIS part"
- **Connecting concepts** -> draw line between them: "See how these are linked?"
- **Summary moment** -> circle multiple: "These three together make it work"

### How to Make the LLM Do This Intelligently

Give the LLM the CAPABILITY and let it decide, with clear principles:

```
ANNOTATION PRINCIPLES (in system prompt):
- Annotations are your "pointing hand" -- use like a teacher's marker
- Do NOT annotate every element you mention
- DO annotate when:
  * KEY insight ("THIS is why it works")
  * Correcting misconception ("NOT this -- this")
  * Spatial relationship IS the point ("see how these connect")
  * Summarizing ("these three things together")
  * Student asked about a specific part (direct their eyes)
- Fade annotations when moving to a new point
- Less is more. A circle means nothing if everything is circled.
```

**LLMs are actually good at this judgment** — it's a pedagogical reasoning task, not a visual accuracy task. The LLM doesn't need to know WHERE the chloroplast is (the renderer handles that). It just needs to decide "SHOULD I draw attention to it right now?"

---

## The Annotation Lifecycle on Screen

```
Base Diagram (persistent)
    |
    +-- Annotation Layer 1 (ephemeral)
    |   circle on chloroplast <- appears beat 7
    |   arrow sunlight->chloroplast <- appears beat 8
    |
    |   [fade_annotations at beat 10]
    |
    +-- Annotation Layer 2 (ephemeral)
    |   circle on mitochondria <- appears beat 12
    |   margin note "also makes ATP!" <- appears beat 13
    |   connection line chloroplast<->mitochondria <- beat 14
    |
    |   [fade_annotations at beat 16]
    |
    +-- Base diagram still clean underneath
```

Each annotation pass layers on, then fades. The base diagram remains pristine. Like a real whiteboard — draw, explain, erase annotations, draw new ones.

The Rough.js hand-drawn aesthetic makes annotations feel natural — a slightly wobbly circle looks intentional, even if placement is slightly off.

---

## Why Precision Is Easy Here

1. **We control the renderer.** We're not annotating a screenshot. We drew every element — we know exactly where each one is.

2. **Components have semantic IDs.** Each element is `id="chloroplast"` with a registered bounding box. Targeting is a dictionary lookup, not computer vision.

3. **The hand-drawn aesthetic is our friend.** A Rough.js circle is intentionally wobbly. Built-in placement tolerance.

4. **Relative positioning handles edge cases.** "Near", "above", "between" — resolved relative to known positions. Even if the viewport changes, annotations stay anchored to elements.

---

## Decision Points for Yash

1. **What annotation types for the prototype?** We already have: circle, underline, arrow (in `AnnotateInstruction`). Missing: margin_note (write text near element). Add margin_note or defer?

2. **How to handle the board state feedback loop latency?** The frontend sends bounds after rendering (currently via `BoundsReportPayload`). There's a small delay before the backend knows where things are. For the prototype, the spatial summary is available before the NEXT beat needs it (beat buffer covers it).

3. **Zone-based vs pixel-based LLM awareness?** Zone-based ("chloroplast is in upper-right") is what we have. Pixel coordinates would be more precise but add noise to the LLM context. Zone-based is enough for speech accuracy.

4. **Annotation auto-fade timing?** Currently duration_ms on annotations. Default 5-10 seconds is reasonable. The LLM can override per-annotation.
