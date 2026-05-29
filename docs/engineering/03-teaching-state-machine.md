# 03 — Teaching State Machine & Agent Core (`backend/src/feynman/agent/`)

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

## TL;DR

The teaching agent is the **core IP**. It is an async, stack-based state machine wrapped around a LiveKit `Agent`, driven by Claude via tool calls. The agent module is the deepest single subsystem in the codebase: ~30 files, ~10k+ lines.

The mental model:

```
            ┌────── LiveKit AgentSession (STT → LLM → TTS) ───────┐
            │                                                      │
            │      ┌──────── TeachingContext (userdata) ────┐      │
            │      │                                         │      │
            │      │   ┌─ TeachingStateMachine ─┐            │      │
            │      │   │  stack of BranchContext │            │      │
            │      │   └─────────────────────────┘            │      │
            │      │                                          │      │
            │      │   ┌─ BoardManager ──────────┐            │      │
            │      │   │  active board's BoardState           │      │
            │      │   │  ├─ SceneGraph (pixel bounds)        │      │
            │      │   │  ├─ BoardGraph (semantic edges)      │      │
            │      │   │  └─ SpatialSolver (free-space)       │      │
            │      │   └──────────────────────────┘           │      │
            │      │                                          │      │
            │      │   AnticipationEngine, DoubtOrchestrator, │      │
            │      │   SessionAudit, BoardVerifier, ...       │      │
            │      └──────────────────────────────────────────┘      │
            │                                                        │
            │  ~40 LLM tools (visuals, notebook, board management,   │
            │  doubts, transitions) — all reach into TeachingContext │
            │  via ctx.userdata and publish results via the LiveKit  │
            │  data channel topic "visuals".                         │
            └────────────────────────────────────────────────────────┘
```

Three principles you'll see repeatedly:

1. **Stack discipline.** Every doubt is a new stack frame: push branch, push board, snapshot state, return when done.
2. **One canonical board state.** The branch name `feat/unify_boardstate` refers to making `BoardManager.active_board.state` the **single** source of truth. It carries three views (semantic / spatial / scene) that update atomically.
3. **Everything goes through `_publish_visual`.** Tool calls AND inline action tags AND the design-bridge all converge on the same publish path so placement, audit, board-state record, and wire format stay consistent.

---

## 1. States — `states.py`

```python
class TeachingState(StrEnum):                       # states.py:6-17
    IDLE                = "idle"
    GREETING            = "greeting"
    TEACHING            = "teaching"
    ASKING_QUESTION     = "asking_question"
    WAITING_FOR_RESPONSE = "waiting_for_response"
    HANDLING_DOUBT      = "handling_doubt"
    SOLVING_PROBLEM     = "solving_problem"
    SUMMARIZING         = "summarizing"
    ENDING              = "ending"
```

These are mirrored in `SessionInfo.teaching_state` (HTTP-exposed) and the Redis hot store. Transitions are owned by the state machine; **no string is mutated outside of `transition()` or `push_branch()` / `pop_branch()`**.

---

## 2. State machine — `state_machine.py`

The whole file is ~120 lines.

```python
@dataclass
class BranchContext:                                # state_machine.py:32-48
    id: UUID
    state: TeachingState
    concept: str = ""
    metadata: dict = field(default_factory=dict)
    return_anchor: ReturnAnchor | None = None       # set on push by DoubtOrchestrator
    checklist: list[ChecklistItem] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
```

`BranchContext` is **the unit of stack-based branching.** Each push creates a fresh one. `return_anchor` is the snapshot of where the parent was, used to restore visuals/audio when the doubt pops.

```python
class TeachingStateMachine:                         # state_machine.py:50-120
    def __init__(self, session_id):
        self._lock = asyncio.Lock()
        root = BranchContext(id=uuid4(), state=TeachingState.IDLE)
        self._stack: list[BranchContext] = [root]

    @property
    def current(self) -> BranchContext:   return self._stack[-1]
    @property
    def state(self)   -> TeachingState:   return self.current.state
    @property
    def depth(self)   -> int:             return len(self._stack)

    async def transition(self, new_state):           # state_machine.py:74-86
        async with self._lock:
            self.current.state = new_state

    async def push_branch(self, concept, **metadata) -> BranchContext:
        async with self._lock:
            branch = BranchContext(
                id=uuid4(), state=TeachingState.HANDLING_DOUBT,
                concept=concept, metadata=metadata,
            )
            self._stack.append(branch)
            return branch

    async def pop_branch(self) -> BranchContext:
        async with self._lock:
            if len(self._stack) <= 1:
                raise RuntimeError("Cannot pop root branch")
            return self._stack.pop()
```

The lock makes the state machine safe under LiveKit's async dispatch. The depth check on `pop_branch` is the only structural invariant — everything else (whether a tool is allowed in a given state) is enforced one level up via the `@state_constrained` decorator.

`depth == 1` ⇒ on the main branch. `depth > 1` ⇒ inside a doubt. Some tools (`advance_concept`, `start_doubt_branch`, `switch_board`) are forbidden when `depth > 1`.

---

## 3. Prompts — `prompts.py` (~550 lines)

`TEACHING_SYSTEM_PROMPT` is **modular**. The full prompt is assembled at runtime by `build_teaching_prompt(...)` (in `tools.py`) and includes the board snapshot, notebook state, scenario plan, upcoming concepts, and any active perception feedback.

The static modules in `prompts.py`:

| Module | Lines | Purpose |
|---|---|---|
| `TEACHING_SYSTEM_PROMPT` | 17–38 | Persona, Feynman-style explanation, natural-speech rules, tool-use philosophy. |
| `VISUAL_SYNC_INSTRUCTIONS` | 40–127 | Teaching beats — voice-visual choreography. Three modes: "draw then explain," "equation term-by-term," "highlight while explaining." Timing values: `visual_first`, `after_speech`, `term_sync`. |
| `HIGHLIGHT_WALK_INSTRUCTIONS` | 130–167 | How to auto-sequence highlight steps while narrating. |
| `SCENE_INSTRUCTIONS` | 169–312 | Component-library diagrams (free_body, optics, circuit, geometry, chemistry, apparatus). Used by the fast-path `draw_scene` tool. |
| `DESIGN_DIAGRAM_INSTRUCTIONS` | 314–391 | When to call `draw_design_diagram` (AI-generated SVG, slow). |
| `MODIFY_DIAGRAM_INSTRUCTIONS` | 393–430 | Incremental updates to existing diagrams via `modify_design_diagram`. |
| `TOOL_ROUTING_INSTRUCTIONS` | 432–463 | Decision matrix — which tool for which content type. |
| `PLACEMENT_INSTRUCTIONS` | 465–519 | Strategies — `near`, `zone`, `auto`. |
| `BOARD_RELATIONSHIPS_INSTRUCTIONS` | 521–535 | Semantic edges (`relates_to` + `relation`). |
| Diagram awareness | 537+ | Inline annotations (`pin_label`, `draw_callout`, `bracket`). |

The runtime assembly also injects:

- The current `ConceptTeachingPlan` rendered as markdown via `format_plan_for_prompt()` from `feynman_teaching_kernel`.
- Active board snapshot (ASCII grid from `board_snapshot.generate_snapshot()`).
- Notebook state (`notebook.reconstruct()` walks audit events to mirror what the frontend rendered).
- Scenario plan slot occupancy.
- Curriculum data (loaded from Neo4j at session start).
- Perception-feedback queue (drained before each LLM turn).

---

## 4. Tools — `tools.py` (~2,600 lines, ~40 tools)

Every tool is decorated with LiveKit's `@function_tool()`. Each takes `ctx: RunContext` first and reads `TeachingContext` from `ctx.userdata`. All visual-emitting tools converge on `_publish_visual()` (the central instruction publisher) so behavior stays uniform.

### Categories

#### Slide-panel content (one diagram on the left at a time)

| Tool | Lines | Effect |
|---|---|---|
| `draw_design_diagram(prompt, mode, ...)` | 1556–1757 | Calls `design_bridge.generate_design_diagram(prompt)` → DiagramSpec JSON → publish as `draw_design_diagram` instruction. The slow path (5–15s). Mode `auto/direct/python` dispatches to direct-JSON or Python-DSL generation. |
| `modify_design_diagram(target_id, modification)` | 1759–1912 | Incremental edit of an existing design diagram. Cached spec is mutated then republished. |
| `draw_scene(scene_type, elements_json, ...)` | 1914–2080 | Fast-path semantic scenes (free-body, optics, circuit, etc.). Component library rendered instantly. |
| `draw_diagram(description, nodes_json, edges_json, layout, ...)` | 616–686 | Structured graphs (flowchart, concept_map, tree, cycle). Frontend runs dagre/circular layout. |

#### Notebook-panel content (right-hand sequential column)

| Tool | Lines | Effect |
|---|---|---|
| `write_equation(latex, align_group?, boxed?)` | 1352–1382 | Adds an equation line. `align_group` shares alignment across equations. |
| `write_step(text, indent)` | 1384–1408 | A derivation step. Indent 0–3. |
| `write_text(text)` | 1410–1435 | Free prose. |
| `write_section(title)` | 1437–1454 | Section header. |
| `write_answer(latex_or_text, boxed)` | 1456–1478 | Final boxed answer. |
| `strikethrough(target_id)` | 1480–1501 | Cross out a previous notebook entry. |
| `new_page(carry_forward_ids?)` | 1503–1525 | Begin a fresh notebook page; optionally copy nominated entries. |

#### Inline visual content (text + equation, when not yet a full diagram)

| Tool | Lines | Effect |
|---|---|---|
| `show_text(text, label, style, ...)` | 543–614 | Free text on the slide. |
| `show_equation(latex, label, animation, term_hints_json, ...)` | 543–614 | Equation; `animation` is `none/fade_in/term_by_term/write_on`. `term_hints_json` is parsed into the `term_hints` field which the frontend syncs to spoken transcript via `SyncManager`. |
| `step_equation(steps, label, ...)` | 688–752 | Multi-step solve, revealed progressively. |
| `show_graph(graph_type, series, functions, axes, ...)` | 754–837 | Chart.js-style graph. |

#### Reference / annotation tools (target existing element by `element_id` or `role`)

| Tool | Lines | Effect |
|---|---|---|
| `highlight(target_id, color, style)` | 839–881 | Sustained glow (call **before** speaking about it). |
| `pin_label_near(target_id, text, position)` | 1103–1163 | Small label + connector line. |
| `draw_callout(from_element, text, direction)` | 1165–1223 | Speech-bubble callout. |
| `bracket(sub_element_ids, color, side, label)` | 1225–1287 | Grouping bracket spanning two elements. |
| `highlight_pulse(target_id)` | 1289–1350 | Quick attention pulse. |
| `highlight_walk(target_id, steps)` | 931–976 | Auto-sequence multiple highlights with trigger words. |
| `annotate(target_id, action, color)` | 839–881 | Ephemeral circle/underline/arrow. |
| `clear_cluster(element_id)` | 999–1028 | Clear all elements in a board-graph cluster. |
| `clear_board(target_id?)` | 978–997 | Clear all or one element on the active board. |

#### Board management

| Tool | Lines | Effect |
|---|---|---|
| `switch_board(board_id, intent)` | 2496–2520 | Activate a different board (with transition animation). Forbidden in `HANDLING_DOUBT`. |
| `scroll_board(direction)` | 2522–2597 | Pan an infinite canvas. |
| `set_lesson_topic(topic)` | 2599+ | Set curriculum topic (unused in v0). |

#### Teaching flow

| Tool | Lines | Effect |
|---|---|---|
| `teach_pause(seconds)` | 2082–2102 | Brief silence (for absorption). |
| `advance_concept()` | 2117–2242 | Move to next concept on the main branch. **Forbidden in HANDLING_DOUBT** via `@state_constrained`. Triggers async planning of the next concept's `ConceptTeachingPlan` via `feynman_teaching_kernel.plan_concept`. |
| `start_doubt_branch(related_concept)` | 2250–2348 | Push a doubt branch (state_machine + board_manager + doubt_orchestrator). **Forbidden in HANDLING_DOUBT** (no nested doubts in v0). |
| `mark_doubt_step_complete(step_index)` | 2466–2488 | Tick off a checklist item explicitly. |
| `resolve_doubt()` | 2440–2464 | Pop the doubt; only allowed when `doubt_orchestrator.is_resolution_allowed()` is true (all checklist items `done`). Restores parent state via `ReturnAnchor`. |

### The publish pipeline — `_publish_visual()`

This is the heart. Lines 386–473 in `tools.py`:

```python
async def _publish_visual(ctx, instruction, wait_for_speech=True):
    # 1. Assign element_id from the global counter on BoardManager if not set
    instruction.element_id = instruction.element_id or board_manager.next_id(instruction.type)

    # 2. Stamp the current active board_id
    instruction.board_id = board_manager.active_id

    # 3. Resolve placement intent → exact (position_x, position_y) via spatial solver
    resolve_placement(instruction, solver, scenario_plan)

    # 4. Strip backend-only fields (e.g. placement is exclude=True on the model)
    # 5. Stamp panel (slide | notebook | reference) based on instruction type
    _stamp_panel(instruction)

    # 6. Decide sync_mode → maybe await wait_for_playout()
    if wait_for_speech and instruction.sync_mode == SyncMode.ON_PLAYOUT:
        await ctx.wait_for_playout()

    # 7. Record on board (BoardState updates _elements, board_graph, spatial_solver atomically)
    board_manager.record(instruction, concept_title=..., concept_index=...)

    # 8. Audit
    audit.record("routing", "tool_call",
                 detail=f"{instruction.type} @ {instruction.zone}",
                 concept_index=current_concept_index, ...)

    # 9. Publish over LiveKit data channel, topic="visuals", reliable=True
    data = json.dumps(instruction.model_dump(exclude_none=True, by_alias=True))
    await ctx.session.room_io.room.local_participant.publish_data(
        data, reliable=True, topic="visuals"
    )
```

The wire format is the model dump with `exclude_none=True, by_alias=True`. See `07-contracts-and-protocols.md` for the receiver side.

---

## 5. Tool constraints — `tool_constraints.py`

The state guard is a decorator stacked between `@function_tool()` and the tool body:

```python
@function_tool()
@state_constrained(
    forbidden_states={TeachingState.HANDLING_DOUBT},
    error_template="Cannot advance the main concept while resolving a doubt.",
)
async def advance_concept(ctx: RunContext) -> str:
    ...
```

Mechanics (`tool_constraints.py:1-97`):

1. The wrapper reads `ctx.userdata.state_machine.current.state`.
2. If the state matches `forbidden_states` (or isn't in `allowed_states` when that's set), raises `ToolConstraintError(error_template)`.
3. LiveKit surfaces the error back to the LLM as a tool error string. The agent is free to recover by routing to a different tool.

Currently constrained tools:
- `advance_concept` — forbidden in `HANDLING_DOUBT`.
- `start_doubt_branch` — forbidden in `HANDLING_DOUBT` (no nesting in v0).
- `switch_board` — forbidden in `HANDLING_DOUBT` (stay on the doubt's board).

---

## 6. The unified board state

The branch name `feat/unify_boardstate` is the key: there is **one canonical board-state object per board**, and it carries three internally-consistent views.

### `BoardManager` — `board.py`

Multi-board container. Created once per session (`TeachingContext.board_manager`). Holds:

- `_boards: dict[str, Board]` — every board ever created.
- `_stack: list[str]` — active-board stack, mirrors `state_machine._stack`.
- `_active_id: str` — currently active.
- `_id_counters: dict[str, int]` — **global** per-instruction-type counter so `"eq-1"` is unique across boards.
- `_design_specs: dict[element_id, DiagramSpec]` — cached design diagrams.

Key methods:

```python
class BoardManager:                                # board.py:40-200+
    def next_id(self, instruction_type: str) -> str:
        # Returns globally unique element_id like "design-5", "eq-12"
        self._id_counters[instruction_type] = self._id_counters.get(instruction_type, 0) + 1
        return f"{instruction_type.replace('_', '-')}-{self._id_counters[instruction_type]}"

    def record(self, instruction, concept_title, concept_index):
        self.active_board.state.record(instruction, concept_title, concept_index)

    def create_board(self, label, branch_id) -> str: ...   # create without switching
    def push_board(self, label, branch_id) -> str: ...     # create + switch (mirrors push_branch)
    def pop_board(self) -> str: ...                        # switch back to parent

    def store_design_spec(self, element_id, spec): ...     # cache on active board
    def get_design_spec(self, element_id) -> DiagramSpec | None: ...   # search ALL boards
    def update_bounds(self, board_id, report): ...         # route bounds report to correct board's BoardState
```

### `BoardState` — `board_state.py`

Per-board state object. **The unification:** one `BoardState` holds three views, all updated atomically when an instruction is recorded.

```python
class BoardState:                                  # board_state.py:96-340+
    def __init__(self):
        self._elements: dict[str, BoardElement] = {}   # source of truth
        self.scene_graph: SceneGraph     = SceneGraph()         # pixel bounds
        self.board_graph: BoardGraph     = BoardGraph()         # semantic edges
        self.spatial_solver: SpatialSolver = SpatialSolver()   # free-space MaxRects
        self.scenario_plan: ScenarioPlan | None = None         # pre-allocated layout slots
        self.camera_tile_x: int = 0
        self.camera_tile_y: int = 0
        self._design_specs: dict[str, dict] = {}

    def record(self, instruction, concept_title, concept_index):       # line 125
        elem = BoardElement(...)
        self._elements[instruction.element_id] = elem
        if has_size_estimate(instruction):
            self.spatial_solver.place(instruction.element_id, rect_from_position(instruction))
        if instruction.relates_to:
            self.board_graph.add_edge(instruction.element_id, instruction.relates_to, instruction.relation)
        # SceneGraph is updated later when the frontend sends a bounds_report

    def update_spatial(self, report: BoundsReportPayload):
        # Frontend just rendered → has real pixel bounds. Update scene_graph atomically.
        self.scene_graph.update_bounds(report)
        # Sync spatial_solver with the actual measured rectangles
        for element_id, bounds in self.scene_graph.entries():
            self.spatial_solver.place(element_id, bounds.to_rect())

    def remove(self, element_id): ...    # remove from all three subsystems
    def clear(self):              ...    # wipe everything
    def summary(self) -> str:     ...    # for the LLM prompt: clustered → spatial → flat fallback
```

The three views answer different questions:

| View | Answers |
|---|---|
| `_elements` | "What exists on the board, by ID?" — flat keyed by `element_id`. |
| `scene_graph` (`scene_graph.py`) | "Where are things in pixels?" — populated from frontend bounds reports. |
| `board_graph` (`board_graph.py`) | "How are things related semantically?" — directed edges with relations (`ILLUSTRATES`, `DERIVES_FROM`, `COMPARES_WITH`, `SUPPORTS`, `ANNOTATES`). |
| `spatial_solver` (`spatial_solver.py`) | "Where's the free space?" — maximal-free-rectangle tracker for placement. |

### `BoardGraph` — `board_graph.py`

```python
class BoardRelation(StrEnum):                      # board_graph.py:19-26
    ILLUSTRATES   = "illustrates"     # equation/text describes diagram
    DERIVES_FROM  = "derives_from"    # next step in derivation
    COMPARES_WITH = "compares_with"   # parallel comparison
    SUPPORTS      = "supports"        # supporting detail
    ANNOTATES     = "annotates"       # annotation/highlight

class BoardGraph:                                  # board_graph.py:47-300+
    def add_edge(source_id, target_id, relation): ...
    def remove_element(element_id): ...
    def get_cluster(element_id) -> set[str]: ...           # BFS connected component
    def get_anchor(cluster, board_elements) -> str: ...    # main visual (most incoming edges → diagram type → oldest)
    def summary(board_elements, scene_graph) -> str: ...   # grouped human-readable text for the prompt
```

Used by `clear_cluster` (wipes a connected component) and by `summary()` in the prompt assembler.

### `SpatialSolver` — `spatial_solver.py`

A MaxRects free-space packer. Maintains `_free_rects: list[Rect]` as the set of maximal free rectangles. `place(id, rect)` subtracts the new rect; `remove(id)` re-merges free rects. Used by `placement_executor` to find the best spot for a new instruction given size estimate + relation.

### `SceneGraph` + bounds reports — `scene_graph.py`

The frontend sends a `BoundsReportPayload` (type `"bounds_report"`) over the `"bounds"` data channel after every render:

```python
class BoundsReportPayload(BaseModel):              # scene_graph.py:102-108
    type: Literal["bounds_report"] = "bounds_report"
    board_id: str
    timestamp: float
    elements: list[ElementBoundsEntry]   # [(element_id, x, y, width, height), ...]
```

The worker (`livekit/worker.py:869-892`) registers a handler that routes this to `board_manager.update_bounds(board_id, report)`, which delegates to the right `BoardState`.

### `board_snapshot.py`

Generates the **ASCII visualization** that goes into the LLM prompt:

```python
def generate_snapshot(solver, board_elements) -> str:  # 72-cols × 18-rows ASCII canvas
def generate_board_context(solver, board_elements, scenario, board_graph, concept_index, upcoming) -> str
```

The output looks like a 2D grid showing occupied regions, free zones, and an embedded reading-flow indicator. The LLM uses this to decide where to place the next visual.

---

## 7. Placement — `placement_executor.py` and `scenario_planner.py`

### `resolve_placement(instruction, solver, scenario_plan)` — 4-strategy fallback

```python
# placement_executor.py:78-200+
def resolve_placement(instruction, solver, scenario_plan):
    # 1. Scenario slot. If scenario_plan has a matching slot (role match), use it.
    # 2. PlacementIntent. If instruction.placement.near is set → solver finds adjacent space.
    # 3. Zone. If instruction.zone is set → zone center with collision avoidance.
    # 4. Auto. Solver picks best-fit in free space.
    # 5. Otherwise: warning, leave unpositioned; frontend zone flex handles it.
    instruction.position_x, instruction.position_y = chosen.x, chosen.y
```

### `ScenarioPlanner` — `scenario_planner.py`

Detects which "shape" the current concept is teaching and pre-allocates a layout:

```python
class TeachingScenario(StrEnum):                   # scenario_planner.py:18-24
    CONCEPT_INTRO    = "concept_intro"      # title + main diagram + equation + supporting text
    DERIVATION       = "derivation"         # ref diagram + start equation + steps + result
    PROBLEM_SOLVING  = "problem_solving"    # given/find + diagram + solution + answer
    COMPARISON       = "comparison"         # case A | case B + shared insight
    SINGLE_FOCUS     = "single_focus"       # one big centered visual
    FREE_FORM        = "free_form"

def detect_scenario(concept_description, visual_suggestions): ...   # keyword match
def plan_scenario(scenario, solver) -> ScenarioPlan: ...            # pre-reserve slots
```

A `ScenarioPlan` holds a list of `ScenarioSlot(role, rect, filled, element_id)`. As tools execute, slots are filled by role match before the solver falls back to auto-placement.

### Diagram dictionary, size estimator

- `diagram_dictionary.py` — maps diagram element role/semantic → canonical IDs for back-references.
- `size_estimator.py` — estimates rendered size for instructions that don't have known dimensions yet (used during placement before the bounds report comes back).

---

## 8. Anticipation — `anticipation.py`

Pre-generates expensive visuals **before** the agent needs them, so cache-hit reduces latency from 5-15s to ~0ms.

```python
class AnticipationEngine:                          # anticipation.py
    def __init__(self, design_bridge): ...

    async def warm_for_concepts(self, concepts, count=3):
        # Inspect each concept's visual_suggestions
        # For ones that need design_agent generation, fire generate_design_diagram() in parallel
        # Specs are cached by design_bridge's FIFO cache (64 entries)

    def _needs_design_agent(self, text) -> bool:
        # regex check on the visual suggestion text
        ...
```

Triggers:
- **Session start** — warm the first 3 concepts in the lesson plan.
- **`advance_concept`** — warm N+2 (one ahead).
- **`set_lesson_topic`** — warm fresh sequence.

Critical for the magic-moment feel: when the agent says "let me draw a force diagram," the diagram appears within ~200ms because the spec is already in the FIFO cache that `design_bridge.generate_design_diagram()` consults.

---

## 9. Lesson plan & curriculum — `lesson_plan.py`, `curriculum_loader.py`

### `LessonPlan` — `lesson_plan.py`

```python
class ConceptNode(BaseModel):                      # lesson_plan.py:18-25
    title: str
    description: str
    key_points: list[str]
    visual_suggestions: list[str]
    estimated_minutes: int = 5

class LessonPlan(BaseModel):                       # lesson_plan.py:28-44
    topic: str
    subject: Subject
    grade_level: str = ""
    objective: str = ""
    concepts: list[ConceptNode]

    def concept_at(self, index) -> ConceptNode | None: ...
    @property
    def total_concepts(self) -> int: ...
```

### `curriculum_loader.py`

`load_curriculum(subject, topic, neo4j_session) -> CurriculumData` queries Neo4j for relevant chapters/topics matching the subject + topic string. Returns a `CurriculumData` carrying:

- Topics + concepts (the actual content to teach).
- Pre-generated visuals (`Diagram` nodes from the precompute pipeline).
- Cross-topic relationships (prereq, leads-to).

`lesson_plan_from_curriculum(curriculum_data)` flattens this into a `LessonPlan`. Stored on `TeachingContext.lesson_plan`.

---

## 10. Doubts — `doubt_orchestrator.py` and `doubt_resolution/`

### `DoubtOrchestrator` — `doubt_orchestrator.py`

Owns three things:
1. Snapshotting parent state when a doubt starts (`ReturnAnchor`).
2. Gating `resolve_doubt` on a checklist of requirements being satisfied.
3. Watchdog timeouts: soft nudge after 60s, force-resolve after 120s (configurable).

```python
@dataclass
class ReturnAnchor:                                # doubt_orchestrator.py:56-68
    parent_branch_id: UUID
    parent_concept_index: int
    last_beat_index: int
    last_voice_anchor: str            # last sentence the agent said before doubt
    active_highlights: list[Highlight]
    active_annotations: list[Annotation]
    notebook_cursor: NotebookCursor
    timestamp: datetime

@dataclass
class DoubtState:                                  # doubt_orchestrator.py:71-87
    branch_id: UUID
    related_concept: str
    return_anchor: ReturnAnchor
    checklist: list[ChecklistItem]
    started_at: datetime
    soft_nudge_fired: bool = False
    force_resolve_fired: bool = False

class DoubtOrchestrator:                           # doubt_orchestrator.py:106-250+
    async def on_push(self, branch_context, related_concept, *,
                       parent_branch_id, checklist, on_soft_nudge, force_resolve):
        # 1. Snapshot parent (active highlights, annotations, notebook cursor, last voice)
        # 2. Create DoubtState, register
        # 3. Start watchdog task

    def is_resolution_allowed(self, branch_id) -> bool:
        # True iff every checklist item is "done"

    async def on_pop(self, branch, publish_visual, say, forced):
        # 1. Restore active_highlights (re-publish them)
        # 2. Restore active_annotations
        # 3. Restore notebook cursor
        # If forced (watchdog), say "Let me bring this back to where we were..."

    def on_tool_invoked(self, tool_name, branch_id):
        # Tick checklist items whose auto_satisfied_by contains tool_name

    def on_voice_emitted(self, transcript, branch_id):
        # Tick items whose keywords match the transcript
```

The checklist is produced by `feynman_teaching_kernel.plan_doubt()` and stored on the `BranchContext`. The kernel generates 2-4 items, each with:

- `description` — what the agent must address.
- `auto_satisfied_by` — list of tool names that auto-tick (e.g., `["draw_design_diagram"]`).
- `keywords` — list of words that auto-tick if spoken (e.g., `["right angle", "perpendicular"]`).

### Doubt resolution sub-pipeline — `agent/doubt_resolution/`

This is the **structured Phase 4+ doubt resolver** used in lecture-playback mode (when the lecture is precomputed but the student asks a doubt). The flow:

```
doubt_intent → DoubtClassifier → ResolutionPlanner → DiagramFitMatcher → DoubtDelivery
```

Files:

| File | Purpose |
|---|---|
| `models.py` | `ResolutionBeat (narration_text, visual_intent_description, annotation_actions, target_diagram_id)`, `ResolutionPlan (beats[])`, `AnnotationAction` (discriminated union of `FocusAction`, `PointAtAction`, `TraceAction`, `MarkPointAction`), `ChapterContext`, `DoubtRecord`. |
| `doubt_classifier.py` | Classify by type: `conceptual`, `procedural`, `prerequisite`, `perceptual`, `strategic`. |
| `resolution_planner.py` | One LLM call (Claude Sonnet, structured output) turns classified doubt into 3-5 beats. `plan_resolution(*, doubt_text, classification, chapter_context, current_topic_id, prior_doubts, different_angle, prior_resolution_summary, board_snapshot)` returns `ResolutionPlan | None`. Up to 2 attempts; returns None on persistent failure. |
| `diagram_fit_matcher.py` | Haiku call — "does this precomputed diagram fit this beat?" Returns `FitVerdict(fits, confidence, rationale)`. |
| `prereq_walker.py` | BFS the prereq graph backward for scope context. |
| `lecture_session.py` | `LectureDoubtSession` — stateful orchestrator; loads chapter via `chapter_loader.py`, holds session doubt history, runs the full pipeline. |
| `chapter_loader.py` | Load `ChapterContext` from Neo4j (topics + diagrams + visual term lookup). |

The actual *speaking* of the resolution is owned by `livekit/doubt_delivery.py` (see `04-livekit-agent-worker.md` §5).

### Doubt branch lifecycle (interactive mode)

```
Agent emits start_doubt_branch(related_concept):
  1. state_machine.push_branch()  → state HANDLING_DOUBT
  2. board_manager.push_board()   → fresh empty board, new active_id
  3. doubt_orchestrator.on_push() → snapshot parent into ReturnAnchor, register checklist
                                    start 60s soft-nudge / 120s force-resolve watchdog

Agent teaches the doubt:
  - Tool calls auto-tick checklist (via on_tool_invoked)
  - Voice ticks checklist (via on_voice_emitted on each transcript word)
  - advance_concept, start_doubt_branch, switch_board are blocked by @state_constrained

Agent emits resolve_doubt():
  - If is_resolution_allowed() is False → raise ToolConstraintError, agent re-routes
  - Else:
    1. state_machine.pop_branch() → state restored to parent's state
    2. board_manager.pop_board() → parent board active again
    3. doubt_orchestrator.on_pop() → restore highlights / annotations / notebook cursor / last voice anchor
```

Doubts are **not persisted to Postgres or Neo4j**. They're session-only.

---

## 11. Drift & audit — `drift_state.py`, `session_audit.py`

### Drift checking — `drift_state.py`

The worker fires a periodic vision check every 30s (see `04-livekit-agent-worker.md` §"drift check"). Helpers:

```python
def compute_drift_state_hash(concept_index, element_ids, versions) -> str:
    # Stable hash of (concept, sorted element IDs, per-element version)
    # Used to dedup drift checks: don't re-run if nothing changed.

def build_element_summary(visible_diagram_ids, original_claims, versions, limit=10):
    # Tuples of (element_id, original_claim, modify_count) for the drift prompt.
```

### Session audit — `session_audit.py`

Append-only event log of *what the system actually did*, not just successes:

```python
@dataclass
class AuditEvent:                                  # session_audit.py:32-39
    system: str          # "curriculum", "anticipation", "routing", "board_graph", "layout", "modify_diagram", "doubt", "drift_check"
    event:  str          # "tool_call", "fallback", "skip", ...
    detail: str
    timestamp: datetime
    metadata: dict

class SessionAudit:
    def record(self, system, event, detail, **metadata): ...
    def events_for(self, system) -> list[AuditEvent]: ...
    def count(self, system, event) -> int: ...
    def summary(self) -> dict: ...
```

Used to produce post-session reports, drive the perception feedback queue, and let the `notebook.reconstruct()` walker rebuild what the frontend rendered.

---

## 12. Action tags & design bridge — `action_tag_parser.py`, `design_bridge.py`

### Action tag parser — `action_tag_parser.py`

The LLM can embed inline pointing tags in its TTS-bound text, e.g. `"And here you can see <highlight target="weight"/> the downward force."` These are stripped from the audio and dispatched as instant visual annotations.

```python
ALLOWED_VERBS = frozenset({"highlight", "pulse", "callout", "bracket", "pin"})

class ActionTagParser:                             # action_tag_parser.py:71-156
    def feed(self, chunk: str) -> tuple[clean_text, list[ActionTag]]:
        # Stateful streaming parser, tolerant of partial tags across chunk boundaries
        # Buffer capped at 256 chars; if exceeded, log warn + flush

    def finalize(self) -> str:
        # Flush any remaining buffered clean text; drop orphan tag fragments
```

The worker's `Agent.tts_node` override wraps the LLM text stream with `strip_action_tags()` which calls `parser.feed(chunk)` for each chunk, yielding clean text to TTS and routing each `ActionTag` to `dispatch_action_tag()` (in `livekit/action_tag_dispatch.py`). See `04-livekit-agent-worker.md` §4.

### Design bridge — `design_bridge.py`

The teaching agent's `draw_design_diagram` tool ultimately calls one of two paths in `design_bridge.py`:

```python
async def generate_design_diagram(prompt, model="sonnet", max_tokens=16000) -> dict:
    # 1. Cache lookup: key = (prompt, mode="direct", provider, model, prompt_file_mtime)
    #    FIFO cache of 64 entries
    # 2. Route to _call_anthropic() or _call_ollama() based on settings.design_agent_provider
    # 3. _parse_response(): extract JSON, repair truncated specs, validate
    # 4. _ensure_dictionary_completeness(): auto-fill missing semantic dict entries
    # 5. Persist to design_agent/generated/
    # 6. Return spec dict

async def generate_via_python(prompt, model="sonnet", max_tokens=8000) -> dict:
    # Same shape but uses prompts_python.py + sandbox execution.
    # 1. LLM writes Python using the Canvas DSL
    # 2. visuals.sandbox.execute_python(code) → Canvas
    # 3. canvas.to_dict() → DiagramSpec dict
```

The system prompts are loaded **directly from `design_agent/backend/prompts.py`** (and `prompts_python.py`), not via HTTP. The standalone design_agent FastAPI on port 8000 is a developer playground; production teaching uses these in-process. See `06-design-agent.md`.

Dispatch heuristic — `_dispatch_mode(prompt)`:

```python
# Regex on the prompt for geometric precision keywords:
#   exact angle, exactly, perpendicular, tangent, intersect, parallel, normal,
#   bisect, parametric, polar
# + STEM diagram names: right triangle, free body, ray diagram, lens, lewis structure
# If matched → "python" path (precise geometry via Canvas DSL)
# Else → "direct" path (raw JSON)
```

---

## 13. Visuals module — `backend/src/feynman/visuals/`

The instruction contract.

| File | Lines | Purpose |
|---|---|---|
| `instructions.py` | 1–106 | The discriminated `VisualInstruction` union (25 types). Each tool emits one of these. |
| `schemas.py` | 1–720+ | The actual Pydantic model for each instruction type plus all enums (`SyncMode`, `BoardZone`, `Panel`, `DiagramType`, `HighlightStyle`, `AnnotationAction`, `EquationAnimation`, etc.). |
| `protocol.py` | 1–22 | `VisualFrame(sequence, instructions[])` — future batching wrapper, currently unused. |
| `canvas_dsl.py` | 1–400+ | Python DSL for parametric diagrams: `Canvas` class + geometric helpers (`midpoint`, `polar`, `perpendicular_to`, `parallel_at_distance`, `intersect`, `tangent_to`) + shape adders (`add_line/circle/text/path/arc/arrow`, etc.). Outputs a DiagramSpec dict via `canvas.to_dict()`. |
| `sandbox.py` | 1–300+ | Restricted Python executor. Used to run LLM-authored Canvas scripts safely. AST whitelist (no `import`, no `try`, no `exec`/`eval`/`open`), whitelisted builtins, `asyncio.to_thread` + `asyncio.wait_for(timeout=2s)`. |

The visuals contract is the wire format between backend (tools) and frontend (renderer). See `07-contracts-and-protocols.md` for the full type list and the JSON-Schema-Py-TS sync story.

### Sandbox details

`execute_python(code, *, imports={}, timeout=2)` (in `sandbox.py`) parses the user-authored Python with `ast.parse`, walks the tree, and refuses on any node in `_FORBIDDEN_NODES` (Import, ImportFrom, Global, Nonlocal, Try, TryStar) or any name in `_FORBIDDEN_NAMES` (`__import__`, `__builtins__`, `open`, `exec`, `eval`, etc.). Builtins are restricted to a whitelist (`range, len, enumerate, zip, list, dict, set, tuple, str, int, float, bool, abs, min, max, sum, sorted, reversed, all, any, round`). Execution runs in `asyncio.to_thread` with a 2-second timeout.

Threat model: Claude writes the Python, students don't. The risk is accidental hangs and prompt-injection-driven escape. The sandbox addresses both.

---

## 14. Teaching context — `teaching_context.py`

The mutable session state accessible to every tool via `ctx.userdata`:

```python
@dataclass
class TeachingContext:                             # teaching_context.py:36-126
    session_id: UUID
    state_machine: TeachingStateMachine

    # Curriculum
    lesson_plan: LessonPlan | None = None
    current_concept_index: int = 0
    completed_indices: list[int] = field(default_factory=list)
    curriculum: ChapterContext | None = None       # loaded from Neo4j at on_enter
    concept_plans: dict[int, ConceptTeachingPlan] = field(default_factory=dict)
    doubt_plan: ConceptTeachingPlan | None = None

    # Board / visuals
    board_manager: BoardManager = field(default_factory=BoardManager)
    audit: SessionAudit = field(default_factory=SessionAudit)
    anticipation: AnticipationEngine = field(default_factory=AnticipationEngine)
    doubt_orchestrator: DoubtOrchestrator = field(default_factory=DoubtOrchestrator)
    board_verifier: BoardVerifier | None = None    # set by worker at start

    # Perception feedback (Phase 5a)
    perception_feedback_queue: list[PerceptionFeedback] = field(default_factory=list)
    perception_feedback_budget_used: dict[int, int] = field(default_factory=dict)
    annotation_verified: set[tuple[str, str, int]] = field(default_factory=set)
    last_diagram_claims: dict[str, DiagramClaim] = field(default_factory=dict)
    diagram_version: dict[str, int] = field(default_factory=dict)
    diagram_intent_verified: set[tuple[str, int, int]] = field(default_factory=set)
    diagram_layout_verified: set[tuple[str, int, int]] = field(default_factory=set)
    original_diagram_claims: dict[str, str] = field(default_factory=dict)

    # Drift checks
    last_drift_check_hash: str = ""
    drift_feedback_budget_used: dict[int, int] = field(default_factory=dict)

    # Board awareness
    current_diagram_dictionary: dict[str, ElementMeta] = field(default_factory=dict)
    active_highlights: list[Highlight] = field(default_factory=list)
    active_annotations: list[Annotation] = field(default_factory=list)
    last_beat_index: int = 0

    @property
    def current_plan(self) -> ConceptTeachingPlan | None:
        return self.doubt_plan if self.state_machine.depth > 1 else self.concept_plans.get(self.current_concept_index)

    @property
    def current_concept(self) -> ConceptNode | None:
        return self.lesson_plan.concept_at(self.current_concept_index) if self.lesson_plan else None
```

---

## 15. The `notebook.py` reconstructor

Backend mirror of the frontend's `useSplitBoardState.ts`. Walks `audit.events_for("routing")` and replays every notebook tool call:

```python
class NotebookState:                               # notebook.py:63-88
    pages: list[list[NotebookEntry]]
    struck_ids: set[str]

@dataclass
class NotebookEntry:
    page: int
    id: str
    kind: Literal["equation", "step", "text", "section_header", "key_point", "answer", "graph"]
    content: str
    align_group: str = ""
    indent: int = 0
    struck: bool = False
    carried_forward: bool = False

def reconstruct(audit: SessionAudit) -> NotebookState:
    state = NotebookState(pages=[[]], struck_ids=set())
    for event in audit.events_for("routing"):
        if event.metadata.get("tool") == "write_equation":
            state.pages[-1].append(NotebookEntry(...))
        # ... one branch per notebook tool ...
    return state
```

The reconstructed notebook is injected into the LLM prompt on every turn so the agent **sees what it already wrote** and avoids blind duplicates.

---

## 16. Board flow & verifier — `board_flow.py`, `board_verifier.py`

### `board_flow.py`

Density and reading-flow analysis used to advise the LLM when to clear/scroll/cleanup:

```python
def analyze_flow(solver) -> FlowAnalysis:
    # reading_direction, density_balance, weight_center, crowding_zones, suggested_action

def advise_scroll(solver, board_elements) -> ScrollAdvice:
    # direction, reason, urgency

def suggest_cleanup(board_graph, spatial_solver, board_elements) -> list[CleanupCandidate]:
    # which elements to clear given lack of free space + age + relations

def reserve_for_upcoming(upcoming_concepts, solver) -> list[ReservationHint]:
    # pre-reserve space for known-upcoming visuals (from anticipation)
```

### `board_verifier.py`

Vision-model verification of rendered diagrams. Used by:

- **Annotation verification** — after a `highlight`/`pin_label`/etc. is published, verify the target element is actually where the LLM thinks it is. If not, enqueue perception feedback.
- **Drift checks** — every 30s, screenshot the active board, ask a vision model (Haiku) "do these diagrams still match the intent?" If drift detected, enqueue perception feedback.

Communicates with the frontend via the `"board_capture"` data channel: send a capture request, the frontend ships back a base64-encoded PNG snapshot of the active board.

---

## 17. Putting it all together — the agent loop

The teaching loop the LLM executes (per turn):

```
1. Student speech → LiveKit STT → transcript chunk → chat_ctx
2. Worker's Agent.llm_node override:
   a. drain_perception_feedback() → inject [PERCEPTION_FEEDBACK ...] synthetic message
   b. Call Claude with TEACHING_SYSTEM_PROMPT + assembled context (concept plan, board snapshot, notebook, scenario plan, curriculum, perception)
3. Claude emits response chunks + tool calls
4. For each tool call:
   - @state_constrained decorator gates it on current state
   - Tool body reads TeachingContext from ctx.userdata
   - Calls _publish_visual() which:
     • assigns element_id via board_manager.next_id
     • stamps board_id and panel
     • resolve_placement() picks coordinates
     • board_manager.record() updates _elements + board_graph + spatial_solver atomically
     • audit.record() logs
     • publish_data over LiveKit topic="visuals"
   - DoubtOrchestrator.on_tool_invoked() ticks checklist items
5. Response text streams to TTS via Agent.tts_node override:
   - strip_action_tags() pulls inline tags out
   - Each tag → dispatch_action_tag() → _build_instruction() → _publish_visual(wait_for_speech=False)
   - Cleaned text → TTS → audio frames → room audio track
6. After turn:
   - Frontend renders any new instructions → sends bounds_report → worker → board_manager.update_bounds → BoardState.update_spatial → scene_graph + spatial_solver refresh
   - Periodic drift check (every 30s) may enqueue perception feedback
```

For an end-to-end trace of one specific lesson, see `09-end-to-end-trace.md`.

---

## File map summary

| File | LoC est. | Purpose |
|---|---|---|
| `states.py` | 18 | TeachingState enum. |
| `state_machine.py` | 120 | Stack-based branching. |
| `prompts.py` | 550 | Modular system prompts. |
| `tools.py` | 2600 | ~40 LLM function tools, central `_publish_visual` pipeline. |
| `tool_constraints.py` | 97 | `@state_constrained` decorator. |
| `board.py` | 200+ | `BoardManager` (multi-board). |
| `board_state.py` | 340+ | `BoardState` (unified per-board state). |
| `board_graph.py` | 230 | Semantic edge graph. |
| `board_snapshot.py` | 150 | ASCII visualization for prompts. |
| `scene_graph.py` | 250 | Pixel bounds from frontend. |
| `spatial_solver.py` | 250 | MaxRects free-space packer. |
| `placement_executor.py` | 250 | 4-strategy fallback for coordinates. |
| `scenario_planner.py` | 200 | Teaching scenario detection + slot pre-allocation. |
| `diagram_dictionary.py` | — | Semantic-role → ID mapping. |
| `size_estimator.py` | — | Size estimation for placement. |
| `anticipation.py` | 150 | Pre-generation of expensive visuals. |
| `lesson_plan.py` | 100 | LessonPlan + ConceptNode models. |
| `curriculum_loader.py` | — | Neo4j curriculum fetch. |
| `doubt_orchestrator.py` | 250 | Doubt lifecycle, checklist, watchdog. |
| `doubt_resolution/models.py` | 232 | ResolutionPlan, ResolutionBeat, AnnotationAction union. |
| `doubt_resolution/doubt_classifier.py` | 200 | Classify doubt type. |
| `doubt_resolution/resolution_planner.py` | 150 | LLM-call to plan 3-5 beats. |
| `doubt_resolution/diagram_fit_matcher.py` | 200 | Vision check: does diagram fit beat? |
| `doubt_resolution/prereq_walker.py` | 50 | BFS prereq graph. |
| `doubt_resolution/lecture_session.py` | 150 | LectureDoubtSession orchestrator. |
| `doubt_resolution/chapter_loader.py` | 200 | Load chapter from Neo4j. |
| `drift_state.py` | 66 | Drift hash + element summary helpers. |
| `session_audit.py` | 200 | Append-only event log. |
| `action_tag_parser.py` | 197 | Inline `<verb attr="x"/>` parser. |
| `design_bridge.py` | 640 | Bridge to design_agent prompts + cache. |
| `teaching_context.py` | 150 | Mutable session state container. |
| `notebook.py` | 200 | Backend notebook reconstruction. |
| `board_flow.py` | 150 | Density, scroll, cleanup advice. |
| `board_verifier.py` | — | Vision model verification (Haiku). |
| `visuals/instructions.py` | 106 | VisualInstruction discriminated union. |
| `visuals/schemas.py` | 720 | Per-type Pydantic models + enums. |
| `visuals/protocol.py` | 22 | VisualFrame (future). |
| `visuals/canvas_dsl.py` | 400 | Python DSL for parametric diagrams. |
| `visuals/sandbox.py` | 300 | Restricted Python executor. |

---

## Reading order for a new engineer

1. `agent/CLAUDE.md` and this doc.
2. `states.py` and `state_machine.py` — read fully, they're short.
3. `prompts.py` lines 17-127 — feel the persona and the visual-sync philosophy.
4. `tools.py:386-473` — `_publish_visual` is the artery; trace one tool through it.
5. `board.py` then `board_state.py` — understand the unified board.
6. `teaching_context.py` — everything else lives on this object.
7. `doubt_orchestrator.py` — the most interesting state-machine extension.
8. Then `09-end-to-end-trace.md` for a concrete trace through all of this.
