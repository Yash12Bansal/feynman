# 07 — Contracts & Wire Protocols

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

## TL;DR

There are **two distinct wire formats** in the Feynman system:

1. **Live `VisualInstruction`** — what the live agent emits in real time, over the LiveKit data channel topic `"visuals"`. A discriminated union of 25 instruction types. Three-way mirror: `contracts/visuals.schema.json` (source of truth) ↔ `backend/src/feynman/visuals/schemas.py` (Pydantic) ↔ `frontend/src/types/visuals.ts` (TypeScript).

2. **Precompute `ManifestEvent`** — what the precompute pipeline emits offline, baked into `Chapter.chapter_manifest` and `Topic.standalone_manifest`. A discriminated union of 27 event types defined in `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py`. Played back by the frontend `LectureViewer`.

The two formats overlap conceptually (both encode "show this diagram", "write this equation", "focus on element X") but serialize differently. **`VisualInstruction` is for live streaming; `ManifestEvent` is for sequenced playback.**

Then there are four data-channel **topics** running over the LiveKit signaling layer, each with its own message vocabulary:

| Topic | Producer | Payload |
|---|---|---|
| `visuals` | Worker | `VisualInstruction` (live) |
| `bounds` | Frontend | `BoundsReportPayload` (rendered element rects) |
| `board_capture` | Worker or Frontend | Capture request / base64 PNG response |
| `doubt_signal` | Both | Lecture-mode doubt lifecycle messages |

This doc enumerates every type, shows the three-way mirror, and walks a single instruction end-to-end.

---

## 1. The single source of truth — `contracts/visuals.schema.json`

`contracts/visuals.schema.json` (~4,200 lines) is JSON Schema Draft 2020-12. It uses **constant `type` discriminators** for every instruction type. Both Python and TypeScript types mirror this schema.

The discriminator is always the `type` field:

```json
{
  "type": { "const": "show_equation", "default": "show_equation", "type": "string" }
}
```

### The 25 instruction types

| # | `type` | Class | Purpose |
|---|---|---|---|
| 1 | `clear` | `ClearInstruction` | Wipe board or a specific element. |
| 2 | `show_text` | `ShowTextInstruction` | Display text on the slide. |
| 3 | `show_equation` | `ShowEquationInstruction` | LaTeX equation. |
| 4 | `step_equation` | `StepEquationInstruction` | Multi-step solve with reveal. |
| 5 | `draw_diagram` | `DrawDiagramInstruction` | Structured diagram (nodes/edges, flowchart/concept_map/tree). |
| 6 | `draw_design_diagram` | `DrawDesignDiagramInstruction` | SVG diagram from design agent (see `06-design-agent.md`). |
| 7 | `draw_scene` | `DrawSceneInstruction` | Scientific diagram from a scene template (free-body, optics, etc.). |
| 8 | `show_graph` | `ShowGraphInstruction` | Chart (line/bar/scatter/function). |
| 9 | `highlight` | `HighlightInstruction` | Highlight an existing element. |
| 10 | `annotate` | `AnnotateInstruction` | Freehand annotation (circle/underline/arrow). |
| 11 | `highlight_walk` | `HighlightWalkInstruction` | Speech-synced spotlight sequence. |
| 12 | `switch_board` | `SwitchBoardInstruction` | Transition to a different board. |
| 13 | `scroll_view` | `ScrollViewInstruction` | Pan viewport. |
| 14 | `slide_pending` | `SlidePendingInstruction` | Show "drafting" loader during generation. |
| 15 | `write_equation` | `WriteEquationInstruction` | Equation on the notebook. |
| 16 | `write_step` | `WriteStepInstruction` | Numbered/unnumbered working step. |
| 17 | `write_text` | `WriteTextInstruction` | Notebook prose. |
| 18 | `write_section` | `WriteSectionInstruction` | Notebook section header. |
| 19 | `write_answer` | `WriteAnswerInstruction` | Boxed final answer. |
| 20 | `strikethrough` | `StrikethroughInstruction` | Cross out a notebook entry. |
| 21 | `new_page` | `NewPageInstruction` | Turn page (optionally carrying forward IDs). |
| 22 | `pin_label` | `PinLabelInstruction` | Label near a diagram element. |
| 23 | `draw_callout` | `DrawCalloutInstruction` | Speech-bubble callout. |
| 24 | `bracket` | `BracketInstruction` | Curly-brace spanning two elements. |
| 25 | `highlight_pulse` | `HighlightPulseInstruction` | One-shot pulse highlight. |

### Common fields (inherited by all)

```json
{
  "element_id":  { "type": "string", "default": null },
  "duration_ms": { "type": "integer", "default": null },
  "sync_mode":   { "$ref": "#/$defs/SyncMode", "default": "on_playout" },
  "term_hints":  { "type": "array", "items": {"$ref": "#/$defs/TermSyncHint"}, "default": null },
  "zone":        { "$ref": "#/$defs/BoardZone", "default": null },
  "board_id":    { "type": "string", "default": null },
  "position_x":  { "type": "number", "default": null },
  "position_y":  { "type": "number", "default": null },
  "panel":       { "$ref": "#/$defs/Panel", "default": null }
}
```

### Shared enums

| Enum | Values |
|---|---|
| `SyncMode` | `immediate`, `on_playout` (default), `term_sync`, `after_next_sentence` |
| `Panel` | `slide`, `notebook`, `reference` |
| `BoardZone` | 9-cell grid: `top-left`, `top-center`, `top-right`, `center-left`, `center-center`, `center-right`, `bottom-left`, `bottom-center`, `bottom-right` |
| `EquationAnimation` | `none`, `fade_in`, `term_by_term`, `write_on` |
| `HighlightStyle` | `glow`, `underline`, `box`, `pulse` |
| `DiagramType` | `flowchart`, `concept_map`, `force_diagram`, `tree`, `cycle`, `comparison`, `free_form` |
| `NodeShape` | `rectangle`, `rounded`, `circle`, `diamond`, `ellipse` |
| `EdgeStyle` | `solid`, `dashed`, `dotted` |
| `GraphType` | `line`, `bar`, `scatter`, `function` |
| `AnnotationAction` | `circle`, `underline`, `arrow` |
| `BoardIntent` | `new`, `revisit`, `reference` |

---

## 2. Backend mirror — `backend/src/feynman/visuals/`

### `instructions.py:51-78` — the discriminated union

```python
VisualInstruction = Annotated[
    ClearInstruction
    | ShowTextInstruction | ShowEquationInstruction | StepEquationInstruction
    | DrawDiagramInstruction | DrawDesignDiagramInstruction | DrawSceneInstruction
    | ShowGraphInstruction
    | HighlightInstruction | AnnotateInstruction | HighlightWalkInstruction
    | SwitchBoardInstruction | ScrollViewInstruction | SlidePendingInstruction
    | WriteEquationInstruction | WriteStepInstruction | WriteTextInstruction
    | WriteSectionInstruction | WriteAnswerInstruction | StrikethroughInstruction
    | NewPageInstruction
    | PinLabelInstruction | DrawCalloutInstruction | BracketInstruction
    | HighlightPulseInstruction,
    Discriminator("type"),
]
```

`Discriminator("type")` is Pydantic 2's tag — on `model_validate(dict)` it picks the right class.

### `schemas.py` — the actual models

All classes inherit from `_BaseInstruction`:

```python
class _BaseInstruction(BaseModel):                           # schemas.py:253-269
    element_id:  str | None = None
    duration_ms: int | None = None
    sync_mode:   SyncMode = SyncMode.ON_PLAYOUT
    term_hints:  list[TermSyncHint] | None = None
    zone:        BoardZone | None = None
    board_id:    str | None = None
    position_x:  float | None = None
    position_y:  float | None = None
    panel:       Panel | None = None
    placement:   PlacementIntent | None = Field(None, exclude=True)   # backend-only!
```

The `placement` field is **excluded from serialization** via `Field(exclude=True)`. It is the LLM's semantic placement intent (`near=other_id, relation=below, size_hint=medium`) used by the backend's Board Cortex solver to compute `position_x, position_y`. Never sent to the frontend.

### A representative instruction model

```python
class ShowEquationInstruction(_BaseInstruction):              # schemas.py:293-303
    """Display a LaTeX equation with optional animation metadata.

    The `latex` field may contain \\htmlId{id}{content} tags for per-term
    animation targeting (used by GSAP in the frontend renderer).
    """
    type:      Literal["show_equation"] = "show_equation"
    latex:     str
    label:     str = ""
    animation: EquationAnimation = EquationAnimation.FADE_IN
```

### One with validation logic

```python
class DrawDiagramInstruction(_BaseInstruction):              # schemas.py:306-327
    """Draw a structured diagram with nodes and edges."""
    type:        Literal["draw_diagram"] = "draw_diagram"
    diagram_type: DiagramType = DiagramType.FREE_FORM
    title:        str = ""
    description:  str = ""
    nodes:        list[DiagramNode] = []
    edges:        list[DiagramEdge] = []
    progressive:  bool = True

    @model_validator(mode="after")
    def _require_content(self) -> Self:
        if not self.description and not self.nodes:
            raise ValueError("Either description or nodes must be provided")
        return self
```

The `_require_content` validator is **backend-only**. The JSON Schema does not encode this constraint. The TypeScript type does not enforce it. If a future generator emits a `draw_diagram` with neither field, it'll succeed on the wire but fail at the backend Pydantic boundary on roundtrip.

### Serialization

The wire format is always **flattened** (no nested `payload`), and excludes `None` values:

```python
# In tools.py:_publish_visual (line 419):
data = json.dumps(instruction.model_dump(exclude_none=True, by_alias=True))
```

- `exclude_none=True` — strips null fields, keeping wire payloads tight.
- `by_alias=True` — uses alias names for special-cased fields. E.g., `SemanticSceneElement` has `from_ref` aliased to `from` (since `from` is a Python keyword).

---

## 3. Frontend mirror — `frontend/src/types/visuals.ts`

720 lines. Uses **interface inheritance** rather than the Pydantic-style discriminated union (TypeScript handles discrimination via the `type` field directly):

```typescript
interface BaseInstruction {                                  // visuals.ts:164-181
  element_id?: string;
  duration_ms?: number;
  sync_mode?:   SyncMode;
  term_hints?:  TermSyncHint[];
  zone?:        BoardZone;
  board_id?:    string;
  position_x?:  number;
  position_y?:  number;
  panel?:       Panel;
  _tileX?:      number;   // client-stamped only
  _tileY?:      number;   // client-stamped only
}
```

Notice `_tileX/_tileY` — these are **client-stamped fields**, only ever set by the frontend's `useBoardStore` for camera positioning, never sent from the backend. Symmetric to backend's `placement` exclusion.

### Per-type interfaces

```typescript
export interface ShowEquationInstruction extends BaseInstruction {
  type: "show_equation";
  latex: string;
  label?: string;
  animation?: EquationAnimation;
}

export interface DrawDiagramInstruction extends BaseInstruction {
  type: "draw_diagram";
  diagram_type?: DiagramType;
  title?: string;
  description?: string;
  nodes?: DiagramNode[];
  edges?: DiagramEdge[];
  progressive?: boolean;
}

// ... 23 more ...
```

### The discriminated union

```typescript
export type VisualInstruction =
  | ClearInstruction
  | ShowTextInstruction | ShowEquationInstruction | StepEquationInstruction
  | DrawDiagramInstruction | DrawDesignDiagramInstruction
  | ShowGraphInstruction
  | HighlightInstruction | AnnotateInstruction
  | SwitchBoardInstruction | DrawSceneInstruction | HighlightWalkInstruction
  | ScrollViewInstruction | SlidePendingInstruction
  | WriteEquationInstruction | WriteStepInstruction | WriteTextInstruction
  | WriteSectionInstruction | WriteAnswerInstruction | StrikethroughInstruction
  | NewPageInstruction
  | PinLabelInstruction | DrawCalloutInstruction | BracketInstruction
  | HighlightPulseInstruction;

export type VisualType = VisualInstruction["type"];
```

TypeScript narrows the type automatically when you check `.type`:

```typescript
function handle(instr: VisualInstruction) {
    if (instr.type === "show_equation") {
        console.log(instr.latex);      // TS knows this exists
        // instr.from_id              // TS error: not on ShowEquationInstruction
    }
}
```

---

## 4. Three-way sync — spot checks

### ShowEquationInstruction

| Source | Form |
|---|---|
| JSON Schema (lines 2494–2516) | `{"type": {"const": "show_equation"}, "latex": {"type": "string"}, "label": {"default": ""}, "animation": {"$ref": "#/$defs/EquationAnimation", "default": "fade_in"}}` |
| Pydantic | `class ShowEquationInstruction(_BaseInstruction): type: Literal["show_equation"]; latex: str; label: str = ""; animation: EquationAnimation = EquationAnimation.FADE_IN` |
| TypeScript | `interface ShowEquationInstruction extends BaseInstruction { type: "show_equation"; latex: string; label?: string; animation?: EquationAnimation; }` |

**Status:** ✓ in sync.

### NewPageInstruction (Phase 5 — split board)

| Source | Form |
|---|---|
| Pydantic (`schemas.py:592-601`) | `class NewPageInstruction(_BaseInstruction): type: Literal["new_page"]; carry_forward_ids: list[str] = Field(default_factory=list)` |
| TypeScript (`visuals.ts:591-594`) | `interface NewPageInstruction extends BaseInstruction { type: "new_page"; carry_forward_ids?: readonly string[]; }` |

**Status:** ✓ in sync (TS uses `readonly` for immutability hint).

### `placement` field

| Source | Present? | Notes |
|---|---|---|
| Pydantic (`schemas.py:268`) | Yes (`Field(None, exclude=True)`) | Backend-only. Used by Board Cortex. |
| JSON Schema | No | Intentional. |
| TypeScript | No | Intentional. |

**Status:** ✓ intentional asymmetry.

### `_tileX / _tileY`

| Source | Present? | Notes |
|---|---|---|
| TypeScript (`visuals.ts:177-180`) | Yes (`_tileX?: number; _tileY?: number`) | Client-stamped only. |
| Pydantic | No | Not seen by backend. |
| JSON Schema | No | Not part of the wire format. |

**Status:** ✓ intentional asymmetry.

### Validation logic — drift watch

The backend's `_require_content` on `DrawDiagramInstruction` is not mirrored in JSON Schema or TypeScript. If you author a `DrawDiagramInstruction` with neither `description` nor `nodes` in TypeScript, the type-check passes but the backend will reject it on roundtrip. **This is the kind of drift to watch.**

---

## 5. Transport — LiveKit data channels

### Publishing from the worker

`tools.py:_publish_visual` (`backend/src/feynman/agent/tools.py:410-427`):

```python
# 1. Optional playout wait
if wait_for_speech and instruction.sync_mode == SyncMode.ON_PLAYOUT:
    try:
        await ctx.wait_for_playout()
    except Exception:
        logger.warning("visual.playout_wait_failed", type=instruction.type, exc_info=True)

# 2. Serialize (flattened JSON, exclude None, by alias)
room = ctx.session.room_io.room
data = json.dumps(instruction.model_dump(exclude_none=True, by_alias=True))

# 3. Publish over LiveKit data channel, topic="visuals", reliable
await room.local_participant.publish_data(data, reliable=True, topic="visuals")

logger.debug("visual.published",
             type=instruction.type,
             element_id=instruction.element_id,
             zone=str(instruction.zone) if instruction.zone else None,
             board_id=instruction.board_id)
```

For `SwitchBoardInstruction` specifically, there's a separate `_publish_switch_board()` that publishes immediately (no playout wait, `SyncMode.IMMEDIATE`).

### Receiving on the frontend

`useVisualChannel.ts` (`frontend/src/livekit/useVisualChannel.ts:197-219`):

```typescript
const onMessage = useCallback(
  (msg: { payload: Uint8Array; topic?: string; from?: unknown }) => {
    try {
      const text = new TextDecoder().decode(msg.payload);
      const parsed = JSON.parse(text) as VisualInstruction;

      // Phase 2: deferred-by-sentence-boundary queue
      if (parsed.sync_mode === "after_next_sentence") {
        enqueueDeferred(parsed);
        return;
      }
      applyInstruction(parsed);
    } catch (err) {
      console.error("[VisualChannel] Failed to parse:", err);
    }
  },
  [applyInstruction, enqueueDeferred],
);

useDataChannel("visuals", onMessage);
```

`useDataChannel` is from `@livekit/components-react`. It abstracts over WebRTC data channels and gives a typed message callback. `decode_responses=True` semantics not needed — the payload is `Uint8Array`, decoded with `TextDecoder`.

### Sentence-boundary deferral (`sync_mode: "after_next_sentence"`)

The frontend holds these in a queue, drains on the next sentence-ending punctuation seen in the agent's transcription stream:

```typescript
const enqueueDeferred = useCallback((parsed: VisualInstruction) => {
  const entry = { instruction: parsed, timer: null };
  entry.timer = setTimeout(() => {
    // 2-second fallback in case the agent never hits a sentence boundary
    pendingRef.current = pendingRef.current.filter(e => e !== entry);
    applyInstruction(parsed);
  }, 2000);
  pendingRef.current.push(entry);
}, [applyInstruction]);

const SENTENCE_BOUNDARY = /[.!?]/;
const handleTranscription = useCallback((segments, participant) => {
  if (participant?.isLocal) return;     // ignore student STT
  let boundary = false;
  for (const seg of segments) {
    const prev = segmentLengthRef.current.get(seg.id) ?? 0;
    const delta = seg.text.slice(prev);
    segmentLengthRef.current.set(seg.id, seg.text.length);
    if (SENTENCE_BOUNDARY.test(delta)) boundary = true;
  }
  if (boundary) drainPending();
}, [drainPending]);
```

This is how inline `<highlight target="..."/>` tags land *with* the agent's spoken word, not before or after. The action-tag dispatcher (`backend/src/feynman/livekit/action_tag_dispatch.py`) publishes them with `sync_mode=AFTER_NEXT_SENTENCE` precisely because the agent says them *during* speech.

### Instruction application

```typescript
const applyInstruction = useCallback((parsed: VisualInstruction) => {
    if (parsed.type === "switch_board") {
        switchBoard(parsed);
        setActiveWalks([]);
    } else if (parsed.type === "scroll_view") {
        scrollTo(parsed.target_x, parsed.target_y);
    } else if (parsed.type === "clear") {
        clearBoard(parsed.board_id, parsed.target_id);
        instructionsRef.current = parsed.target_id
            ? instructionsRef.current.filter(i => i.element_id !== parsed.target_id)
            : [];
        if (!parsed.target_id) setActiveWalks([]);
    } else if (parsed.type === "highlight_walk") {
        setActiveWalks(prev => [...prev.filter(w => w.target_id !== parsed.target_id), parsed]);
        // Auto-expire after walk duration
        setTimeout(() => setActiveWalks(prev => prev.filter(w => w !== parsed)),
                   (parsed.duration_ms ?? parsed.steps.length * 5000) + 1000);
    } else {
        addInstruction(parsed);
        instructionsRef.current = [...instructionsRef.current, parsed];
    }
    setInstructions(instructionsRef.current);
    setLastInstruction(parsed);
}, [...]);
```

`addInstruction` is from `useBoardStore` — the multi-board state manager that tracks per-board instruction lists, active board, camera state, transitions, and pending slides.

---

## 6. Other data-channel topics

### `bounds` — element rect reports

After every render the frontend's `BoundsReporter` walks the DOM, collects `getBoundingClientRect()` for every registered element, and publishes:

```typescript
interface BoundsReportPayload {
    type: "bounds_report";
    board_id: string;
    timestamp: number;
    elements: {
        element_id: string;
        x: number; y: number; width: number; height: number;
    }[];
}
```

Worker side (`worker.py:869`):

```python
def _on_data_received(packet: rtc.DataPacket):
    if packet.topic == "bounds":
        report = BoundsReportPayload.model_validate_json(packet.data)
        teaching_ctx.board_manager.update_bounds(report.board_id, report)
```

`board_manager.update_bounds` routes to the correct `BoardState.update_spatial(report)`, which atomically updates `scene_graph` and `spatial_solver`. See `03-teaching-state-machine.md` §6.

### `board_capture` — screenshot exchange

Worker → Frontend: capture request when the drift checker or annotation verifier needs to see the board.

```json
{ "type": "capture_request", "board_id": "main", "request_id": "abc123" }
```

Frontend responds (via `html2canvas` or similar):

```json
{ "type": "capture_response", "request_id": "abc123", "png_b64": "data:image/png;base64,..." }
```

The worker passes the PNG to `BoardVerifier.handle_capture_response()` which feeds it to a vision model (Haiku) for verification or drift detection.

### `doubt_signal` — lecture-mode doubt lifecycle

Bidirectional. Used only in lecture-playback mode. See `04-livekit-agent-worker.md` §5 for the full sequence.

Message types (`type` field):

| Type | Direction | Payload |
|---|---|---|
| `doubt_intent` | Frontend → Worker | `{ chapter_id, cursor, topic_id, board_snapshot }` |
| `doubt_captured` | Worker → Frontend | `{ text, duration_ms }` |
| `thinking` | Worker → Frontend | `{ stage }` (UI shows spinner) |
| `resolution_ready` | Worker → Frontend | `{ beats: [...summary], matched_diagram_ids: [...] }` |
| `doubt_beat_start` | Worker → Frontend | `{ beat_index, target_diagram_id, annotation_actions: [...] }` |
| `satisfaction_prompt` | Worker → Frontend | `{ options: [{key, label, description}, ...] }` |
| `satisfaction_choice` | Frontend → Worker | `{ option: "crystal_clear" | "counter_doubt" | ... }` |
| `lecture_resume` | Worker → Frontend | `{}` |
| `doubt_resolution_failed` | Worker → Frontend | `{ reason }` |

The `board_snapshot` in `doubt_intent` is the **canonical view of "what is on the board right now"** — a `BoardSnapshot` carrying `page_index, topic_id, elements: list[BoardElement]`. It comes from the precompute manifest's `Chapter.board_snapshots[page_index]`, passed through `useExtractionPlayback`'s `currentSnapshot`. The doubt resolver scopes its planning to this snapshot, so it knows exactly what diagrams + notebook blocks the student is looking at.

This is the *core* of `feat/unify_boardstate`: the board state has one canonical form, and the same form is what the doubt resolver receives.

---

## 7. Precompute Manifest — the parallel contract

The precompute pipeline (`01-precompute-pipeline.md`) emits a different but parallel contract: **`Manifest`** carrying a sequence of `ManifestEvent`. Defined in `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py:58-500`.

```python
class Manifest(BaseModel):                                   # models.py:488
    events: list[ManifestEvent] = Field(default_factory=list)

    @property
    def total_audio_ms(self) -> int:
        return sum(e.duration_ms for e in self.events
                   if isinstance(e, (AudioEvent, PauseEvent)))
```

### 27 event types

Discriminated union (`models.py:365-395`):

```python
ManifestEvent = Annotated[
    Union[
        AudioEvent, PauseEvent, ShowDiagramEvent, TopicStartEvent,
        WriteSectionEvent, WriteEquationEvent, WriteStepEvent, WriteTextEvent,
        WriteKeyPointEvent, WriteAnswerEvent, StrikethroughEvent,
        NewPageEvent, PageBreakEvent,
        FocusEvent, UnfocusEvent, ClearAnnotationsEvent,
        TraceEvent, MarkPointEvent, PointAtEvent, WriteMarginEvent,
        # Legacy back-compat (still tolerated by frontend)
        PinEvent, CalloutEvent, BracketEvent, HighlightEvent, PulseEvent,
    ],
    Field(discriminator="type"),
]
```

Highlights:

```python
class AudioEvent(BaseModel):                                 # models.py:58
    type: Literal["audio"] = "audio"
    url: str
    duration_ms: int = Field(..., ge=0)

class ShowDiagramEvent(BaseModel):                           # models.py:69
    type: Literal["show_diagram"] = "show_diagram"
    diagram_id: str
    placement: Placement | None = None
    slide_element_bounds: dict[str, Rect] | None = None
    presentation_mode: Literal["build_up", "overview"] | None = None

class FocusEvent(BaseModel):                                 # models.py:202
    """Spotlight a single element of the active diagram.
    Doc 19 §A-3: target_element_id is PREFERRED (stable id from diagram
    dictionary). target_role kept for back-compat. Either field is required.
    """
    type: Literal["focus"] = "focus"
    diagram_id: str
    target_element_id: str | None = None
    target_role: str | None = None
    text: str = ""

    @model_validator(mode="after")
    def at_least_one_target(self) -> "FocusEvent":
        if not self.target_element_id and not self.target_role:
            raise ValueError("FocusEvent must specify ...")
        return self

class TraceEvent(BaseModel):                                 # models.py:249
    """Animate a stroke along the element's path."""
    type: Literal["trace"] = "trace"
    diagram_id: str
    element_id: str = Field(min_length=1)
    duration_ms: int = Field(default=1500, ge=0)

class MarkPointEvent(BaseModel):                             # models.py:262
    """Drop a small marker at (x, y) in diagram viewBox space."""
    type: Literal["mark_point"] = "mark_point"
    diagram_id: str
    x: float; y: float
    kind: Literal["dot", "cross", "star"] = "dot"
    label: str = ""

class PointAtEvent(BaseModel):                               # models.py:277
    type: Literal["point_at"] = "point_at"
    diagram_id: str
    element_id: str = Field(min_length=1)
    from_side: Literal["top", "bottom", "left", "right"] = "left"
```

### How the manifest plays — frontend's `useExtractionPlayback`

`frontend/src/hooks/useExtractionPlayback.ts` walks `chapter.events[]` sequentially:

```typescript
async function playOne() {
    const event = chapter.events[cursor];
    switch (event.type) {
        case "audio":         await playAudio(event.url, event.duration_ms); break;
        case "pause":         await sleep(event.duration_ms); break;
        case "topic_start":   setCurrentTopicId(event.topic_id); break;
        case "show_diagram":  setSlide({active: event.spec, status: "ready"}); break;
        case "focus":         setSlide(prev => ({...prev, focusedElementId: event.target_element_id})); break;
        case "trace":         appendTrace(event); break;
        case "mark_point":    appendMarkPoint(event); break;
        case "point_at":      appendPointer(event); break;
        case "write_margin":  appendMarginNote(event); break;
        case "write_equation":
        case "write_step":
        case "write_text":
        case "write_section":
        case "write_answer":  appendNotebookEntry(event); break;
        case "strikethrough": markStruck(event.target_id); break;
        case "new_page":      turnPage(event.carry_forward_ids); break;
        case "clear_annotations": clearAnnotations(event.diagram_id); break;
        // ...
    }
    cursor++;
}
```

See `08-frontend-architecture.md` §"Lecture viewer".

### Manifest vs VisualInstruction — they overlap but differ

Both can express "show this diagram." But:

| | VisualInstruction (live) | ManifestEvent (precomputed) |
|---|---|---|
| When emitted | At runtime, by the live agent | Offline, by the precompute pipeline |
| Wire format | LiveKit data channel JSON | Embedded in `Chapter.chapter_manifest` JSON in Neo4j |
| Timing | sync_mode (`on_playout`, etc.) — tied to live TTS | Pre-sequenced; `AudioEvent.duration_ms` fixes timing |
| Container | `_BaseInstruction` fields (sync_mode, term_hints, zone, panel) | Event-specific fields only; `Placement` carried inline on some events |
| Discriminator | `type` field, 25 variants | `type` field, 27 variants |
| Identity | `element_id` (per-board globally unique) | `diagram_id` / `id` (per-chapter scoped) |
| Validation | Three-way mirror (JSON Schema, Py, TS) | Single-source (precompute Pydantic only); frontend has TypeScript copies |
| Used by | Live teaching, action tags | LectureViewer playback, doubt resolver context |

When a doubt resolver in lecture-playback mode emits a beat (`doubt_beat_start` payload), it sends `annotation_actions: AnnotationAction[]` where `AnnotationAction` is a discriminated union of `FocusAction | PointAtAction | TraceAction | MarkPointAction` — **the same shape** as the precompute manifest's `FocusEvent | PointAtEvent | TraceEvent | MarkPointEvent`. This is intentional: the frontend renders them identically whether they came from playback or live doubt resolution.

---

## 8. End-to-end example — `ShowEquationInstruction` round trip

A concrete trace of one instruction from backend to frontend:

```
Step 1. Backend (agent/tools.py, in the show_equation tool):
   instr = ShowEquationInstruction(
       latex=r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}",
       label="Quadratic Formula",
       element_id="eq_001",     # auto-assigned by board_manager.next_id
       zone=BoardZone.TOP_CENTER,
       sync_mode=SyncMode.ON_PLAYOUT,
   )

Step 2. Serialize:
   data = json.dumps(instr.model_dump(exclude_none=True, by_alias=True))
   # Result:
   # {"type":"show_equation","latex":"\\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}",
   #  "label":"Quadratic Formula","element_id":"eq_001","zone":"top-center",
   #  "sync_mode":"on_playout","panel":"slide"}
   # Note: `placement`, `position_x`, `position_y`, `term_hints`, etc., are excluded
   # (None values stripped).

Step 3. Publish:
   await room.local_participant.publish_data(data, reliable=True, topic="visuals")

Step 4. WebRTC routes the message to the frontend.

Step 5. Frontend (useVisualChannel.ts onMessage):
   const text   = new TextDecoder().decode(msg.payload);   // UTF-8 JSON string
   const parsed = JSON.parse(text) as VisualInstruction;   // typed
   // parsed.type === "show_equation" → TS narrows to ShowEquationInstruction
   // parsed.latex is now safely typed as string

Step 6. Sync mode check:
   parsed.sync_mode === "on_playout"
   // Not "after_next_sentence", so apply immediately:
   applyInstruction(parsed);

Step 7. addInstruction(parsed) — pushed onto active board via useBoardStore.

Step 8. SplitBoard re-renders (or WhiteboardScene if not split-board mode).
        useSplitBoardState() picks parsed as the active slide instruction (because type
        is in DIAGRAM_TYPES set and panel === "slide").

Step 9. SlidePanel renders <InstructionSwitch instruction={parsed} />
        → EquationContent → KaTeX renders the LaTeX → DOM updates.

Step 10. ResizeObserver fires → BoundsReporter publishes a BoundsReportPayload over
         topic="bounds" → worker's _on_data_received catches it → board_manager updates
         scene_graph + spatial_solver for "eq_001".

Step 11. Next LLM turn:
         Worker assembles prompt including board_snapshot ASCII showing "eq_001" placed
         in the top-center zone with measured pixel bounds. Agent now knows where the
         equation is when planning the next beat.
```

---

## 9. Drift discipline — keeping the three sources in sync

Right now, on `feat/unify_boardstate`, the three sources are in sync for every shipped instruction type. But the trajectory has drift risk because there's no automated generator: each side is hand-written.

Discipline:

1. **Source of truth is JSON Schema (`contracts/visuals.schema.json`).** Update it first.
2. **Mirror to backend Pydantic** (`backend/src/feynman/visuals/schemas.py` + `instructions.py`). Add to the union.
3. **Mirror to TypeScript** (`frontend/src/types/visuals.ts`). Add to the union.
4. (If applicable) **Mirror to precompute** (`data_pre_compute_v2/.../models.py`) for the manifest analog.
5. Validators that exist on only one side (`_require_content`, `at_least_one_target`) should be **noted in the contract file as a comment** so future implementers know.

The `contracts/CLAUDE.md` says exactly this:

> 1. Update the JSON Schema file here.
> 2. Update the backend Pydantic models.
> 3. Update the frontend TypeScript types.
> All three must stay in sync.

There is no codegen today. This is intentional friction — every instruction type goes through human review on three sides — but it's also the riskiest place to introduce silent drift. **If you add an instruction type and forget the TS mirror, the frontend will log a parse error to the console and silently drop the instruction.**

---

## 10. Reading order for a new engineer

1. `contracts/CLAUDE.md`.
2. This doc.
3. `contracts/visuals.schema.json` — skim every `$defs/*Instruction` block.
4. `backend/src/feynman/visuals/schemas.py` — read top to bottom.
5. `backend/src/feynman/visuals/instructions.py` — see the union.
6. `frontend/src/types/visuals.ts` — read top to bottom.
7. `frontend/src/livekit/useVisualChannel.ts` — see how the wire form arrives.
8. `data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/models.py:58-500` — the parallel manifest.
9. `frontend/src/hooks/useExtractionPlayback.ts` — how manifests play.
