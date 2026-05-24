# 14 — Agent Diagram Awareness

> Make the teaching agent see what's on the slide. Replace opaque element IDs with a semantic dictionary, add four annotation tools (pin_label_near, draw_callout, bracket, highlight_pulse) so the agent can write *around* a diagram, not just to the notebook beside it.

**Status**: Design
**Date**: 2026-05-10
**Depends on**: `docs/design/10-split-board.md`, `docs/design/12-aanya-demo-v0.md`
**Blocks**: Aanya demo build (Phase C in plan)

---

## 1. Why this matters

The teaching agent today is effectively **blind** to the diagram on the slide panel. When the design_agent generates a `DiagramSpec`, it produces SVG primitives with element IDs like `side_AB`, `vertex_C`, `label_height`. These are opaque strings. The teaching agent never sees what they look like, where they are spatially, or what they semantically represent.

Two concrete consequences hurt the demo:

**(a) Brittle highlighting.** When the agent says *"look at the angle at the bottom-left"* and calls `highlight_diagram_part(target="vertex_A")`, it is guessing. It has no way to verify that `vertex_A` is in fact the bottom-left vertex, or that this is the angle being referenced. Today this works only because the design_agent prompt and the teaching_agent prompt happen to use overlapping conventions. Any inconsistency breaks the alignment.

**(b) No annotation around the diagram.** The split-board's slide panel holds one diagram. The notebook is on the right. There is **no way to write next to a specific element on the slide** — no callouts, no pinned labels, no brackets. A real teacher scribbles *"this is the key insight"* right next to the part of the diagram they're discussing. We can't. The agent can only write in the notebook, far from the visual it's referencing.

The "voice and visual coordination" magic beat in the Aanya demo (`12-aanya-demo-v0.md` §3 beats 2, 5, 6) depends on the agent confidently pointing at and annotating specific diagram elements. Without diagram awareness, those beats degrade to "voice plays while a static diagram sits there." The demo doesn't fail; it just feels unmagical.

---

## 2. Recommended approach: semantic metadata + new annotation tools

Two complementary additions:

1. **Diagram dictionary** — at design-time, the design_agent emits a structured semantic dictionary alongside the SVG primitives. The teaching agent receives this dictionary in its prompt and can refer to elements by *role* (`"hypotenuse"`) instead of by raw ID (`"side_AB"`).

2. **Annotation tools** — four new tools (`pin_label_near`, `draw_callout`, `bracket`, `highlight_pulse`) that draw on top of the diagram, anchored to specific elements. Render as an overlay layer above the SVG.

### Why this beats giving the LLM the rendered image (Yash's original proposal)

A vision-language LLM seeing the rendered PNG would work, but:

- **Cost**: every doubt branch and every highlight call would round-trip through a vision-LLM. ~10–30× more tokens per call.
- **Latency**: vision-LLM responses are slower (image processing overhead). Adds 200–500ms per call.
- **Determinism**: vision-LLM may misread the diagram in subtle ways. Semantic dictionary is exact.
- **Cacheability**: the diagram dictionary is generated once, cached forever. Vision-LLM calls are per-invocation.

The semantic metadata approach gives the agent **richer-than-pixels understanding** at no inference cost, because the structure was already known at the moment the diagram was generated. We're just preserving information that was being discarded.

**Vision-LLM stays as a v1.1 fallback** for cases where the dictionary doesn't cover what the agent wants to do. For v0, the dictionary is sufficient — empirically, ~95% of teaching-agent calls reference well-known elements (sides, angles, labels) that the dictionary already names.

---

## 3. The diagram dictionary

### Schema

```python
# design_agent/backend/schema.py — additions

class ElementMeta(BaseModel):
    """Semantic metadata for a single SVG element in a DiagramSpec."""
    role: str = Field(
        description=(
            "Functional role of this element. Common values: "
            "hypotenuse, opposite, adjacent, leg, vertex, angle, right_angle_marker, "
            "label, dimension, axis, curve, callout. Open vocabulary; design_agent "
            "picks descriptive role names. Teaching agent matches by role."
        )
    )
    semantic: str = Field(
        description=(
            "Plain-English description: 'the ladder, 10m', 'the angle of elevation, 60°'. "
            "Used in the teaching agent's prompt to reason about what the element means."
        )
    )
    position: Literal[
        "top", "bottom", "left", "right",
        "top-left", "top-right", "bottom-left", "bottom-right",
        "center", "diagonal"
    ]
    spatial_relations: list[str] = Field(
        default_factory=list,
        description=(
            "List of relations to other elements, encoded as 'relation:target_id'. "
            "Examples: ['adjacent_to:vertex_A', 'above:side_BC', 'opposite_to:vertex_C']."
        ),
    )
    bounds: tuple[float, float, float, float] | None = Field(
        default=None,
        description="Bounding box (x, y, width, height) in SVG coordinates. Used for annotation positioning.",
    )

class DiagramSpec(BaseModel):
    # ... existing fields (elements, parameters, animations, etc.) ...
    dictionary: dict[str, ElementMeta] = Field(
        default_factory=dict,
        description=(
            "Maps element_id → ElementMeta. Populated by design_agent at generation time. "
            "Empty dict means legacy/unenriched spec — teaching agent falls back to ID-only."
        ),
    )
```

### Example

For the Aanya demo's main ladder diagram:

```python
DiagramSpec(
    elements=[...],  # SVG primitives, unchanged
    dictionary={
        "side_AB": ElementMeta(
            role="hypotenuse",
            semantic="the ladder, 10 meters long",
            position="diagonal",
            spatial_relations=["from:vertex_A", "to:vertex_B", "longest_side"],
            bounds=(120, 100, 280, 360),
        ),
        "side_BC": ElementMeta(
            role="opposite",
            semantic="the wall, height up the wall (unknown, labeled '?')",
            position="right",
            spatial_relations=["from:vertex_B", "to:vertex_C", "vertical"],
            bounds=(380, 100, 4, 360),
        ),
        "side_AC": ElementMeta(
            role="adjacent",
            semantic="the ground, distance from foot of ladder to wall (unknown)",
            position="bottom",
            spatial_relations=["from:vertex_A", "to:vertex_C", "horizontal"],
            bounds=(120, 460, 260, 4),
        ),
        "vertex_A": ElementMeta(
            role="angle",
            semantic="the 60° angle the ladder makes with the ground",
            position="bottom-left",
            spatial_relations=["between:side_AB,side_AC", "labeled_60_deg"],
            bounds=(115, 455, 30, 30),
        ),
        "right_angle_C": ElementMeta(
            role="right_angle_marker",
            semantic="the right angle where the wall meets the ground",
            position="bottom-right",
            spatial_relations=["at:vertex_C"],
            bounds=(370, 450, 14, 14),
        ),
        # ... etc for label_height, label_distance ...
    },
)
```

### Design_agent prompt update

The system prompt for the design_agent gains a section instructing it to populate the dictionary:

> *After generating the SVG elements, populate the `dictionary` field. For every meaningful element (sides, angles, labels, key markers), include an entry with `role`, `semantic`, `position`, and `spatial_relations`. Roles should be functional terms a teacher would use ("hypotenuse", "opposite", "the angle of elevation"), not visual descriptions ("blue line", "diagonal stroke"). The teaching agent will use this dictionary to highlight, annotate, and reason about the diagram.*

We also provide 2–3 worked examples in the prompt so the design_agent learns the pattern.

---

## 4. New annotation tools

Four new tools added to `backend/src/feynman/agent/tools.py`. Each fires a new instruction type that the frontend renders as an overlay on the slide panel.

### 4.1 `pin_label_near`

```python
@tool
async def pin_label_near(
    element_or_role: str,
    text: str,
    position: Literal["above", "below", "left", "right"] = "above",
    timing: SyncMode = SyncMode.IMMEDIATE,
) -> None:
    """
    Place a small text label near a diagram element. Used for marginalia,
    quick annotations, identifying things ("←  hypotenuse").

    Args:
        element_or_role: either an exact element_id from the diagram, or a role string
            (e.g. "hypotenuse", "opposite") which the system resolves via the dictionary.
            If multiple elements share the role, picks the first.
        text: short label text (≤30 chars recommended).
        position: where to place the label relative to the element.
        timing: when to render (default: immediate, parallel to voice).
    """
```

Frontend instruction: `PinLabelInstruction(element_or_role, text, position)`. Resolved on backend before publish (element_or_role → element_id via dictionary lookup). Frontend renders text label with a thin connector line to the element's bounds, animated entry (fade-in over 300ms).

### 4.2 `draw_callout`

```python
@tool
async def draw_callout(
    from_element: str,
    text: str,
    direction: Literal["up", "down", "up-left", "up-right", "down-left", "down-right"] = "up-right",
    timing: SyncMode = SyncMode.IMMEDIATE,
) -> None:
    """
    Draw a speech-bubble-style callout from a specific diagram element.
    Used for emphasis or short pedagogical notes ("← key insight here!").

    Args:
        from_element: element_id or role.
        text: callout content (≤80 chars; longer = uglier).
        direction: which way the callout extends from the element.
    """
```

Frontend instruction: `DrawCalloutInstruction`. Renders as rounded-rectangle bubble with a tail pointing to the element. Animated entry: tail draws first (200ms), bubble inflates (300ms), text fades in (200ms).

### 4.3 `bracket`

```python
@tool
async def bracket(
    element_a: str,
    element_b: str,
    label: str,
    side: Literal["above", "below", "left", "right"] = "above",
    timing: SyncMode = SyncMode.IMMEDIATE,
) -> None:
    """
    Draw a curly bracket spanning two diagram elements with a centered label.
    Used to show a relationship between two parts ("right triangle" spanning
    hypotenuse and adjacent, "this is what we're measuring" across two sides).

    Args:
        element_a: first element_id or role.
        element_b: second element_id or role.
        label: text centered on the bracket.
        side: which side of the elements the bracket goes on.
    """
```

Frontend instruction: `BracketInstruction`. Renders as curly brace SVG path between bounds of the two elements, label text positioned at the midpoint. Animated entry: bracket draws (400ms via stroke-dashoffset), label fades in (200ms delay).

### 4.4 `highlight_pulse`

```python
@tool
async def highlight_pulse(
    element_or_role: str,
    duration_ms: int = 1200,
    color_token: str = "--sb-neon",
    timing: SyncMode = SyncMode.IMMEDIATE,
) -> None:
    """
    Pulse a single element with a brief glow. Simpler API than highlight_walk
    when you only want one element. Used for term-sync emphasis during voice.

    Args:
        element_or_role: element_id or role.
        duration_ms: total pulse duration (default 1200ms — one full pulse cycle).
        color_token: CSS variable for the glow color.
    """
```

Frontend instruction: `HighlightPulseInstruction`. Adds a CSS class with `@keyframes` animation to the element. Single pulse cycle (scale + glow + fade), no follow-up.

### Why these four

These cover the common annotation idioms a teacher actually uses on a board:
- `pin_label_near` — the "← name" gesture
- `draw_callout` — the "key insight here" gesture
- `bracket` — the "this whole thing is X" gesture
- `highlight_pulse` — the "look here" gesture

`highlight_walk` (existing) covers the "look here, then here, then here" multi-element sequence. `annotate` (existing) covers raw drawing on the board. The four new tools fill the gap between these and the notebook.

---

## 5. Backend schema additions

New instruction types in `backend/src/feynman/visuals/schemas.py`:

```python
class PinLabelInstruction(_BaseInstruction):
    type: Literal["pin_label"] = "pin_label"
    panel: Panel = Panel.SLIDE  # always slide; not a notebook tool
    element_id: str  # resolved from element_or_role on the backend
    text: str = Field(..., max_length=120)
    position: Literal["above", "below", "left", "right"] = "above"

class DrawCalloutInstruction(_BaseInstruction):
    type: Literal["draw_callout"] = "draw_callout"
    panel: Panel = Panel.SLIDE
    element_id: str
    text: str = Field(..., max_length=200)
    direction: Literal["up", "down", "up-left", "up-right", "down-left", "down-right"] = "up-right"

class BracketInstruction(_BaseInstruction):
    type: Literal["bracket"] = "bracket"
    panel: Panel = Panel.SLIDE
    element_a_id: str
    element_b_id: str
    label: str = Field(..., max_length=80)
    side: Literal["above", "below", "left", "right"] = "above"

class HighlightPulseInstruction(_BaseInstruction):
    type: Literal["highlight_pulse"] = "highlight_pulse"
    panel: Panel = Panel.SLIDE
    element_id: str
    duration_ms: int = Field(1200, ge=400, le=3000)
    color_token: str = "--sb-neon"
```

All four instructions carry `panel: Panel.SLIDE` — they target the slide panel by definition. Backend's `_stamp_panel` logic in `tools.py` handles the routing.

The `element_or_role` → `element_id` resolution happens in backend before publish. New helper:

```python
# backend/src/feynman/agent/diagram_dictionary.py (NEW, ~80 LOC)
class DictionaryResolver:
    """Resolves element_or_role → element_id using the active diagram's dictionary."""
    def __init__(self, tc: TeachingContext): ...
    def resolve(self, element_or_role: str) -> str:
        # If element_or_role exactly matches an id in current diagram's dictionary, return it.
        # Else search for elements whose role matches (case-insensitive).
        # If multiple match, return first (logged as a warning).
        # If none, return element_or_role as-is (let frontend decide; logs a warning).
```

The `tc.current_diagram_dictionary` is set when `draw_design_diagram` (or `draw_diagram`/`draw_scene`) fires, populated from the spec's `dictionary` field.

---

## 6. Frontend rendering

New annotation overlay layer in `frontend/src/engine/whiteboard/split/SlideAnnotationLayer.tsx` (~150 LOC).

Renders absolute-positioned SVG elements that sit *above* the diagram SVG but inside the slide panel container. Each annotation type has its own component:

- `<PinLabel position bounds text />` — text + connector line
- `<Callout direction bounds text />` — bubble + tail
- `<Bracket boundsA boundsB label side />` — curly brace + label
- `<HighlightPulse element duration color />` — adds CSS class to the target SVG element directly

The annotation layer subscribes to the same store as `DesignDiagramContent`. On receiving a `pin_label`/`draw_callout`/`bracket`/`highlight_pulse` instruction:

1. Look up the target element_id's bounds in the current `DiagramSpec.dictionary`.
2. Compute the annotation position from bounds + position/direction.
3. Render the annotation component with animated entry.
4. Persist until the next `draw_*_diagram` instruction (which clears all annotations).

CSS animations defined in `SlideAnnotationLayer.css`. All animations respect `prefers-reduced-motion`.

Reduced-motion fallback: instant appearance (no entry animation), no pulses (highlight_pulse becomes a static color change for the duration).

---

## 7. Teaching agent prompt enrichment

When a diagram is on the slide, the teaching agent's system prompt includes a section formatted from the dictionary:

```
## Diagram on Slide

Title: Ladder Problem (IGCSE 0580 — Topic 7: Trigonometry)

Available roles you can highlight or annotate:
- hypotenuse: the ladder, 10m (diagonal, from bottom-left to top-right)
- opposite: the wall, height up the wall (right side, vertical)
- adjacent: the ground, distance from foot of ladder (bottom, horizontal)
- angle (60°): the 60° angle the ladder makes with the ground (bottom-left vertex)
- right_angle_marker: the right angle at the wall-ground meeting (bottom-right)

Use these roles in highlight_pulse, pin_label_near, draw_callout, bracket, etc.
You can also use the raw element_ids if needed: side_AB, side_BC, side_AC,
vertex_A, vertex_B, vertex_C, right_angle_C, label_height, label_distance.

Spatial relationships:
- side_AB (hypotenuse) is the longest side
- side_BC (opposite) is to the right of side_AC
- vertex_A is at the bottom-left, vertex_C is at the bottom-right
```

This block is generated dynamically by `_render_diagram_dictionary_section(tc.current_diagram)` and injected into the system prompt during `_update_agent_prompt(ctx)` whenever the active slide changes.

The prompt also instructs the agent: *"Prefer roles over raw IDs when calling annotation tools — roles are more readable and survive diagram regeneration."*

---

## 8. Vision-LLM fallback (v1.1, deferred)

For v0 we deliberately do NOT add a vision-LLM path. Reasons:
- Semantic metadata covers ~95% of teaching-agent annotation needs
- Vision-LLM adds latency (200–500ms) and cost (10–30× tokens) per call
- Determinism is higher with structured metadata

For v1.1, when we have edge cases the dictionary can't cover, we'll add:
- A `request_diagram_inspection()` tool that the agent can call to receive the rendered PNG + freeform description from a vision-LLM
- Used only when explicitly invoked, not on every annotation call
- Cached per-diagram so repeated inspections cost nothing after first

This lives in a future doc; out of scope here.

---

## 9. Implementation Phases

This feature splits into two sub-phases (plus one optional). Each phase has a coherent mental model — backend Pydantic + Python in 1A, TypeScript + React in 1B — and ends with a verification gate before the next begins. The split reduces cognitive load (no Pydantic-vs-React mode-switching mid-feature) and surfaces bugs at the contract boundary, not after both stacks ship together.

| Phase | Scope | Days | Cumulative |
|---|---|---|---|
| **1A — Backend foundation** | Schema, design_agent prompt, 4 instruction types, 4 tool functions, dictionary resolver, prompt enrichment | 2 | day 2 |
| **1B — Frontend rendering** | SlideAnnotationLayer, animation CSS, store integration, instruction TS types | 1 | day 3 |
| **1C — Vision-LLM fallback (optional)** | PNG renderer, `inspect_diagram` tool, vision call, caching | 1–2 | +1–2 (after 2B) |

**Cross-feature ordering**: 1A → 1B → (continue in `15-doubt-orchestrator.md` for 2A → 2B) → Phase C (Aanya demo build per `13-aanya-demo-build-list.md`). Phase 1C, if added, slots after 2B.

### Phase 1A — Backend Foundation (2 days)

**Goal**: every backend requirement from §3, §4, §5, §7 is implemented and tested; `contracts/visuals.schema.json` is regenerated and committed. A frontend engineer can consume the contract without further backend changes.

#### Scope

| Requirement | File | Section |
|---|---|---|
| `ElementMeta` Pydantic model (role, semantic, position, spatial_relations, bounds) | `design_agent/backend/schema.py` | §3 |
| `DiagramSpec.dictionary: dict[str, ElementMeta]` field | `design_agent/backend/schema.py` | §3 |
| design_agent prompt addendum (populate dictionary) + 2–3 worked examples | `design_agent/backend/prompts.py` | §3 |
| `PinLabelInstruction` Pydantic model (panel=SLIDE, max_length=120) | `backend/src/feynman/visuals/schemas.py` | §5 |
| `DrawCalloutInstruction` Pydantic model (panel=SLIDE, max_length=200) | `backend/src/feynman/visuals/schemas.py` | §5 |
| `BracketInstruction` Pydantic model (panel=SLIDE, max_length=80) | `backend/src/feynman/visuals/schemas.py` | §5 |
| `HighlightPulseInstruction` Pydantic model (duration_ms 400–3000, color_token) | `backend/src/feynman/visuals/schemas.py` | §5 |
| `pin_label_near` tool function (with `element_or_role` resolution) | `backend/src/feynman/agent/tools.py` | §4.1 |
| `draw_callout` tool function | `backend/src/feynman/agent/tools.py` | §4.2 |
| `bracket` tool function | `backend/src/feynman/agent/tools.py` | §4.3 |
| `highlight_pulse` tool function | `backend/src/feynman/agent/tools.py` | §4.4 |
| Tool registration (`ALL_TOOLS`, `INSTRUCTION_TYPE_TO_PANEL`) | `backend/src/feynman/agent/tools.py` | §5 |
| `DictionaryResolver` class (case-insensitive role lookup, multi-match returns first, no-match falls back to raw input) | `backend/src/feynman/agent/diagram_dictionary.py` (NEW, ~80 LOC) | §5 |
| `tc.current_diagram_dictionary` field on TeachingContext | `backend/src/feynman/agent/teaching_context.py` | §5 |
| Set `current_diagram_dictionary` on `draw_*_diagram` publish; clear on `pop_board()` | `backend/src/feynman/agent/tools.py` (publish helpers) | §5 |
| `_render_diagram_dictionary_section` helper (Diagram on Slide section, lists roles, spatial relationships) | `backend/src/feynman/agent/prompts.py` | §7 |
| Inject in `build_teaching_prompt` whenever active slide changes (via `_update_agent_prompt`) | `backend/src/feynman/agent/prompts.py` | §7 |
| "Prefer roles over raw IDs" instruction in prompt section | `backend/src/feynman/agent/prompts.py` | §7 |
| Regenerate `contracts/visuals.schema.json` from Pydantic | `contracts/visuals.schema.json` | §5 |

#### Tests (must pass before 1B starts)

| Test | File | What it verifies |
|---|---|---|
| `test_element_meta_validation` | `backend/tests/visuals/test_schemas.py` | ElementMeta accepts valid roles/positions; rejects invalid |
| `test_diagram_spec_dictionary_round_trip` | `backend/tests/visuals/test_schemas.py` | DiagramSpec with dictionary serializes/deserializes correctly |
| `test_dictionary_resolver_role_lookup` | `backend/tests/agent/test_diagram_dictionary.py` (NEW) | Resolver finds element_id from role; case-insensitive; multi-match returns first; no-match falls back to raw input |
| `test_pin_label_near_resolves_role` | `backend/tests/agent/test_tools_annotation.py` (NEW) | `pin_label_near("hypotenuse", ...)` produces `PinLabelInstruction` with correct `element_id` |
| `test_panel_routing_includes_4_new_tools` | `backend/tests/agent/test_panel_routing.py` | All 4 new instruction types route to `Panel.SLIDE` |
| `test_diagram_dictionary_section_renders_in_prompt` | `backend/tests/agent/test_prompts.py` | When `current_diagram_dictionary` is set, prompt contains "Diagram on Slide" section with all roles and the "prefer roles" instruction |

#### Completion gate

All 6 tests green + `ruff` clean on touched files + `contracts/visuals.schema.json` regenerated and committed. Frontend engineer can consume the contract without further backend changes.

#### Completion note template (append to `active-features/foundational-features.md`)

```
## Phase 1A — DONE [date]
- 4 instruction types in schemas.py: PinLabel, DrawCallout, Bracket, HighlightPulse
- 4 tool functions in tools.py
- DictionaryResolver in diagram_dictionary.py (~80 LOC actual)
- Diagram dictionary section appears in build_teaching_prompt when slide active
- Contract regenerated. Frontend reads contracts/visuals.schema.json.
- 6/6 tests green. Phase 1B can start.
- Open question / known issue: [if any]
```

### Phase 1B — Frontend Rendering (1 day)

**Goal**: every frontend requirement from §6 is implemented; tests pass; a Beat-5-style stub from the Aanya demo runs cleanly with annotation tools landing within 800ms.

#### Scope

| Requirement | File | Section |
|---|---|---|
| TypeScript types for 4 new instructions (PinLabel, DrawCallout, Bracket, HighlightPulse) | `frontend/src/types/visuals.ts` | §6 |
| `SlideAnnotationLayer.tsx` component (~150 LOC) | `frontend/src/engine/whiteboard/split/SlideAnnotationLayer.tsx` (NEW) | §6 |
| Animation CSS (entry animations + reduced-motion fallback) | `frontend/src/engine/whiteboard/split/SlideAnnotationLayer.css` (NEW) | §6 |
| Sub-renderers: `<PinLabel>` (text + connector line), `<Callout>` (bubble + tail), `<Bracket>` (curly brace + label), `<HighlightPulse>` (CSS class injection on target element) | inside `SlideAnnotationLayer.tsx` | §6 |
| Wire into `SlidePanel.tsx` (mount above DesignDiagramContent, inside slide container) | `frontend/src/engine/whiteboard/split/SlidePanel.tsx` | §6 |
| Store integration: subscribe to annotation instructions; look up bounds from active `DiagramSpec.dictionary` | existing whiteboard store | §6 |
| Bounds-based positioning math (compute annotation position from element bounds + position/direction) | `SlideAnnotationLayer.tsx` | §6 |
| Persist annotations until next `draw_*_diagram` instruction (which clears all) | store reducer | §6 |
| Reduced-motion compliance: instant appearance, no pulses (highlight_pulse → static color change) | `SlideAnnotationLayer.css` + components | §6 |

#### Tests (must pass before 2A starts)

| Test | File | What it verifies |
|---|---|---|
| pin label position | `frontend/src/engine/whiteboard/split/__tests__/SlideAnnotationLayer.test.tsx` (NEW) | `pin_label_near("hypotenuse", "8m", "above")` renders label above hypotenuse bounds |
| callout direction | same | Callout renders with tail pointing the correct direction |
| bracket spanning | same | Bracket renders curly brace between two element bounds, label centered |
| pulse animation class | same | Highlight pulse adds correct CSS class to target SVG element |
| annotations clear on diagram swap | same | Firing `draw_design_diagram` clears prior annotations |
| reduced-motion test | same | `prefers-reduced-motion` set → instant render, no pulse animation |
| Manual: visual smoke at `/dev/split-board` | n/a | All 4 annotation types render and animate cleanly on a sample diagram |
| Manual: Beat 5 dry-run | n/a | `pin_label_near("opposite", "8.66 m", "right")` + `bracket("hypotenuse", "adjacent", "right triangle", "below")` lands in <800ms with voice |

#### Completion gate

All 6 vitest tests pass + visual smoke test + Beat 5 dry-run + `tsc` clean + lint clean on touched files. Feature 1 (Agent Diagram Awareness) is complete. Demo can use annotation tools.

#### Completion note template

```
## Phase 1B — DONE [date]
- SlideAnnotationLayer.tsx renders 4 annotation types with animated entry
- Reduced-motion fallback works
- Annotations clear on diagram swap
- Beat 5 stub passes <800ms latency target
- 6/6 vitest green. Visual smoke passes. Phase 2A can start.
- Open question / known issue: [if any]
```

### Phase 1C — Vision-LLM Fallback (optional, 1–2 days)

**Decision**: defer to after Phase 2B. Reconsider only if dictionary curation feels uncertain after 1A — i.e., the design_agent's dictionary output is inconsistent in test runs across 5+ sample prompts. Design lives in §8.

#### Scope (if added)

| Requirement | File | Section |
|---|---|---|
| Headless PNG renderer (Playwright + frontend renderer or SVG → PNG fallback) | `scripts/render_diagram_to_png.py` (NEW) | §8 |
| `inspect_diagram(question)` tool (callable on demand by agent) | `backend/src/feynman/agent/tools.py` | §8 |
| Vision-LLM call via Anthropic SDK (Claude Sonnet vision) | `backend/src/feynman/agent/diagram_inspector.py` (NEW) | §8 |
| PNG cache (per-DiagramSpec hash; repeated inspections cost nothing after first) | inside `diagram_inspector.py` | §8 |

#### Tests (if added)

| Test | File | What it verifies |
|---|---|---|
| `test_inspect_diagram_returns_description` | `backend/tests/agent/test_diagram_inspector.py` (NEW) | Tool returns non-empty description from vision-LLM for sample DiagramSpec |
| `test_dictionary_corruption_recovery` | same | Intentionally corrupt one demo diagram's dictionary; agent recovers via `inspect_diagram` and produces correct annotation |
| Manual: cost/latency profile | n/a | ≤500ms per call, ≤$0.003 per call on Sonnet |

#### Completion gate

3 tests green + cost/latency confirmed. Tool available to agent via prompt addendum.

### Phase Boundary Discipline (RLM protocol)

**Active feature state file**: `~/.claude/projects/-Users-yashbansal-proj-feynman/memory/active-features/foundational-features.md` — created at start of 1A; phase completion notes appended at each gate. Tracks 1A, 1B, 2A, 2B (and 1C if added) across both feature docs.

**Each phase ends with:**
1. All listed tests green
2. `ruff` (backend) / `tsc` + lint (frontend) clean on touched files
3. Completion note appended to state file using the template above
4. Git commit with phase identifier (e.g., "Phase 1A complete: diagram awareness backend foundation")

**Each phase begins with:**
1. 5-min re-orient: read relevant section of design doc + prior phase's completion note + immediately-relevant files
2. Confirm prior phase's gate is green (all tests still pass)
3. Update state file: mark phase as in_progress

**Rollback rule**: if any phase slips >0.5 days, stop and re-plan rather than rush.

### Decision Points

| Decision | When | Default |
|---|---|---|
| Add Phase 1C (vision-LLM fallback)? | After 1A, when dictionary quality is empirically observable | Skip; reconsider after 2B if demo dry-run reveals uncertainty |
| Tighten/loosen dictionary controlled vocabulary? | During 1A | Provide ~15 common roles in prompt; allow open vocabulary; normalize in resolver |
| Adjust Beat 5 latency budget? | During 1B if 800ms is unrealistic | Hold to 800ms — it's a load-bearing demo metric |

### Risks & Mitigations (cross-phase)

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| 1A's design_agent prompt produces inconsistent dictionaries | Medium | Demo would need vision-LLM (1C) | Run 1A with 5+ test prompts; if inconsistent, add controlled vocabulary list to prompt; fall back to 1C |
| 1B's animation timing feels off (too fast/slow/jittery) | Low | Demo less polished | Iterate during 1B's manual smoke test; fine-tune in Phase C |
| 1C vision-LLM latency too high for live use | Low (only if added) | inspect_diagram non-viable | Cache aggressively per-DiagramSpec hash; only call when uncertain; fallback to user-friendly "give me a moment" voice |

---

## 10. Acceptance criteria

The feature is ready to integrate with the Aanya demo when:

1. **Backend round-trip test**: a unit test creates a DiagramSpec with dictionary metadata, calls `pin_label_near("hypotenuse", "8m", "above")`, verifies the resulting `PinLabelInstruction` has correct `element_id` (resolved from role) and the published instruction reaches the frontend store.

2. **Frontend rendering test**: a vitest test renders SlideAnnotationLayer with a sample DiagramSpec + 4 annotation instructions, asserts each annotation is positioned correctly relative to the target element's bounds.

3. **End-to-end manual test**: open `/dev/split-board`, render a sample diagram with full dictionary, run a script that invokes all 4 annotation tools sequentially, visually verify each looks correct and animates cleanly.

4. **Demo dry-run**: run a stub of Beat 5 from the Aanya demo (`pin_label_near("opposite", "8.66 m", "right")` — and `bracket("hypotenuse", "adjacent", "right triangle", "below")`) — both annotations appear, voice and visual coordinate within 800ms.

5. **Reduced-motion compliance**: `prefers-reduced-motion` set → annotations appear instantly, highlight_pulse becomes static color change.

---

## 11. Risks & open questions

1. **Design_agent doesn't populate dictionary correctly.** The LLM may produce inconsistent role names ("hypoteneuse" vs "hypotenuse", "opp" vs "opposite"). Mitigation: provide a controlled vocabulary list in the prompt and show 2–3 worked examples. Add a normalization step in `DictionaryResolver` (case-insensitive, common-typo correction).

2. **Annotation overflow on small diagrams.** A `draw_callout` with 80 chars of text may not fit if the diagram is dense. Mitigation: max_length validation in Pydantic (already in schemas above). Frontend truncates with ellipsis if necessary.

3. **Stale dictionary after diagram regeneration.** If a kid asks a doubt, the slide swaps to a new diagram, then back — dictionary must update correctly. Mitigation: `tc.current_diagram_dictionary` is set on each `draw_*_diagram` call and cleared on `pop_board()`. Tests verify this.

4. **Annotation positioning math.** Bounds-based positioning is simple but may be ugly for complex shapes (curved paths, irregular polygons). Mitigation: for v0 we restrict annotations to straight-line elements (sides, axes) and points (vertices). Curves/regions get annotations centered on their bounding box; acceptable degraded path.

5. **Element_id collisions across diagrams.** Two different diagrams might both have `side_AB`. Mitigation: resolution is scoped per-active-diagram via `tc.current_diagram_dictionary`. No cross-diagram resolution.

---

## 12. Out of scope

- **Vision-LLM diagram understanding** — deferred to v1.1
- **Editable annotations** — annotations are read-only; agent can't modify a placed annotation, only fire a new one
- **Persistent annotations across diagram swaps** — annotations clear on diagram swap; agent must re-place them if needed
- **Annotation layer in notebook panel** — notebook has its own typography (write_*); annotations are slide-only
- **Custom annotation styles per subject** — v0 uses one consistent visual style (split-board palette); subject-specific theming in v1+

---

## 13. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-05-10 | Semantic metadata + 4 annotation tools is the v0 approach | Cheaper, faster, more deterministic than vision-LLM; covers ~95% of needs |
| 2026-05-10 | Vision-LLM fallback deferred to v1.1 | Not needed for the Aanya demo's annotation patterns; adds cost/latency without proportionate benefit at v0 |
| 2026-05-10 | 4 annotation tools chosen: pin_label_near, draw_callout, bracket, highlight_pulse | Covers the common annotation idioms a real teacher uses; minimal API surface |
| 2026-05-10 | Annotation layer is slide-only, panel-stamped at backend | Notebook has typography; annotations are visual marginalia for the slide |
| 2026-05-10 | Agent uses roles by default, IDs as fallback | Roles survive diagram regeneration; IDs are an escape hatch |
| 2026-05-10 | Annotations clear on diagram swap | Simpler state model; agent re-fires if needed |
| 2026-05-10 | Build splits into Phase 1A (backend, 2d) + Phase 1B (frontend, 1d) + optional Phase 1C (vision-LLM, 1–2d) | Coherent mental model per phase; verification gate at backend↔frontend seam catches contract drift early; RLM protocol applied (mid-feature context loss is the documented failure mode of single-phase ~7-day builds across two stacks) |

---

## 14. Next artifacts

- `docs/design/15-doubt-orchestrator.md` — the doubt orchestrator design (companion doc)
- After Phase B build: update `docs/design/12-aanya-demo-v0.md` beats 2/5/6 to use new annotation tools
- After Phase B build: update `docs/design/13-aanya-demo-build-list.md` to reflect new tool availability
