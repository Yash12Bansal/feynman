"""LLM function tools — visual instructions + teaching state management."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import TYPE_CHECKING, Any, Literal

import structlog
from livekit.agents import RunContext, function_tool

from feynman.agent.prompts import build_teaching_prompt

if TYPE_CHECKING:
    from feynman.agent.teaching_context import TeachingContext

from feynman.agent.board_graph import BoardRelation
from feynman.agent.placement_executor import resolve_placement
from feynman.agent.scenario_planner import detect_scenario, plan_scenario
from feynman.visuals.schemas import (
    AnnotateInstruction,
    AnnotationAction,
    AxisConfig,
    BoardIntent,
    BoardZone,
    BracketInstruction,
    ClearInstruction,
    DataSeries,
    DiagramEdge,
    DiagramNode,
    DiagramType,
    DrawCalloutInstruction,
    DrawDesignDiagramInstruction,
    DrawDiagramInstruction,
    DrawSceneInstruction,
    EquationAnimation,
    EquationStep,
    FunctionDef,
    GraphType,
    HighlightInstruction,
    HighlightPulseInstruction,
    HighlightStyle,
    HighlightWalkInstruction,
    HighlightWalkStep,
    NewPageInstruction,
    Panel,
    PinLabelInstruction,
    PlacementIntent,
    SceneTemplateId,
    SceneTemplateRef,
    ScrollViewInstruction,
    SemanticSceneElement,
    ShowEquationInstruction,
    ShowGraphInstruction,
    SizeHint,
    SlidePendingInstruction,
    StepEquationInstruction,
    StrikethroughInstruction,
    SwitchBoardInstruction,
    SyncMode,
    TermSyncHint,
    WriteAnswerInstruction,
    WriteEquationInstruction,
    WriteSectionInstruction,
    WriteStepInstruction,
    WriteTextInstruction,
    _BaseInstruction,
)

logger = structlog.get_logger()

# Instruction types that skip auto-ID assignment.
_NO_AUTO_ID_TYPES = frozenset({"clear", "highlight", "annotate", "highlight_walk"})


# Split-board panel assignment, keyed by instruction `type` literal. This is the
# single source of truth: any new instruction type MUST get an entry here (the
# mapping-coverage test in test_panel_routing.py enforces this).
INSTRUCTION_TYPE_TO_PANEL: dict[str, Panel] = {
    # Notebook (right panel — written content)
    "show_text": Panel.NOTEBOOK,
    "show_equation": Panel.NOTEBOOK,
    "step_equation": Panel.NOTEBOOK,
    "show_graph": Panel.NOTEBOOK,
    # Notebook (write-tools — Phase 5 native surface)
    "write_equation": Panel.NOTEBOOK,
    "write_step": Panel.NOTEBOOK,
    "write_text": Panel.NOTEBOOK,
    "write_section": Panel.NOTEBOOK,
    "write_answer": Panel.NOTEBOOK,
    "strikethrough": Panel.NOTEBOOK,
    "new_page": Panel.NOTEBOOK,
    # Slide (left panel — one diagram at a time)
    "draw_diagram": Panel.SLIDE,
    "draw_design_diagram": Panel.SLIDE,
    "draw_scene": Panel.SLIDE,
    "slide_pending": Panel.SLIDE,
    # Slide annotation overlays (diagram awareness)
    "pin_label": Panel.SLIDE,
    "draw_callout": Panel.SLIDE,
    "bracket": Panel.SLIDE,
    "highlight_pulse": Panel.SLIDE,
    # Reference (targets an existing element or is a meta-operation)
    "highlight": Panel.REFERENCE,
    "highlight_walk": Panel.REFERENCE,
    "annotate": Panel.REFERENCE,
    "clear": Panel.REFERENCE,
    "switch_board": Panel.REFERENCE,
    "scroll_view": Panel.REFERENCE,
}


def _stamp_panel(instruction: _BaseInstruction) -> None:
    """Stamp `panel` on an instruction based on its `type` literal.

    Raises `KeyError` if the instruction type has no mapping — this is a
    correctness contract, not a runtime failure: the mapping-coverage test
    guarantees every registered instruction type is present.
    """
    instruction.panel = INSTRUCTION_TYPE_TO_PANEL[instruction.type]


def _parse_zone(zone: str) -> BoardZone | None:
    """Parse a zone string from the LLM, returning None on invalid input."""
    if not zone:
        return None
    try:
        return BoardZone(zone)
    except ValueError:
        logger.warning("visual.invalid_zone", zone=zone)
        return None


# LLM-friendly timing names → SyncMode mapping.
_TIMING_MAP: dict[str, SyncMode] = {
    "visual_first": SyncMode.IMMEDIATE,
    "after_speech": SyncMode.ON_PLAYOUT,
    "term_sync": SyncMode.TERM_SYNC,
}


def _parse_timing(timing: str) -> SyncMode:
    """Map an LLM-friendly timing name to a SyncMode value."""
    if not timing:
        return SyncMode.ON_PLAYOUT
    # Accept raw enum values ("immediate", "on_playout") and friendly aliases.
    if mapped := _TIMING_MAP.get(timing.lower()):
        return mapped
    try:
        return SyncMode(timing)
    except ValueError:
        logger.warning("visual.invalid_timing", timing=timing)
        return SyncMode.ON_PLAYOUT


def _declare_relation(
    ctx: RunContext,
    source_id: str,
    relates_to: str,
    relation: str,
    default: BoardRelation = BoardRelation.ILLUSTRATES,
) -> None:
    """Record a semantic edge on the active board's graph."""
    if not relates_to or not source_id:
        return
    try:
        rel = BoardRelation(relation) if relation else default
    except ValueError:
        rel = default
    tc: TeachingContext = ctx.userdata
    tc.board_manager.active_board.state.board_graph.add_edge(
        source_id=source_id,
        target_id=relates_to,
        relation=rel,
    )
    tc.audit.record(
        "board_graph",
        "edge_declared",
        f"{source_id} --{rel.value}--> {relates_to}",
        source_id=source_id,
        target_id=relates_to,
        relation=rel.value,
    )


def _build_placement(near: str, near_side: str, size_hint: str) -> PlacementIntent | None:
    """Build PlacementIntent from tool params. Returns None if no placement params set."""
    if not (near or near_side or size_hint):
        return None
    try:
        hint = SizeHint(size_hint) if size_hint else SizeHint.MEDIUM
    except ValueError:
        hint = SizeHint.MEDIUM
    return PlacementIntent(
        near=near or None,
        relation=near_side or None,
        size_hint=hint,
    )


async def _publish_visual(
    ctx: RunContext,
    instruction: _BaseInstruction,
    *,
    wait_for_speech: bool | None = None,
) -> None:
    # Auto-assign element_id if not already set and type supports it.
    tc: TeachingContext = ctx.userdata
    if instruction.element_id is None and instruction.type not in _NO_AUTO_ID_TYPES:
        instruction.element_id = tc.board_manager.next_id(instruction.type)

    # Stamp active board ID on the instruction for frontend context.
    instruction.board_id = tc.board_manager.active_id

    # Resolve placement intent → exact coordinates.
    board_state = tc.board_manager.active_board.state
    resolve_placement(instruction, board_state.spatial_solver, board_state.scenario_plan)
    instruction.placement = None  # Strip before serialization (defense in depth)

    # Split-board: stamp panel deterministically from instruction type.
    _stamp_panel(instruction)

    # Infer wait behavior from the instruction's sync_mode when not explicit.
    if wait_for_speech is None:
        wait_for_speech = instruction.sync_mode == SyncMode.ON_PLAYOUT

    if wait_for_speech:
        try:
            await ctx.wait_for_playout()
        except Exception:
            logger.warning("visual.playout_wait_failed", type=instruction.type, exc_info=True)

    room = ctx.session.room_io.room
    data = json.dumps(instruction.model_dump(exclude_none=True, by_alias=True))
    await room.local_participant.publish_data(data, reliable=True, topic="visuals")
    logger.debug(
        "visual.published",
        type=instruction.type,
        element_id=instruction.element_id,
        zone=str(instruction.zone) if instruction.zone else None,
        board_id=instruction.board_id,
    )

    # Audit: track every tool call for the routing summary. For notebook
    # instructions (Phase 5b), also record the full payload so `notebook.py`
    # can reconstruct the live page state for prompt injection.
    zone_str = str(instruction.zone.value) if instruction.zone else "none"
    audit_meta: dict[str, Any] = {
        "tool": instruction.type,
        "element_id": instruction.element_id or "",
        "zone": zone_str,
        "concept_index": tc.current_concept_index if tc.lesson_plan else -1,
    }
    if INSTRUCTION_TYPE_TO_PANEL.get(instruction.type) == Panel.NOTEBOOK:
        audit_meta["content"] = instruction.model_dump(exclude_none=True, mode="json")
    tc.audit.record(
        "routing",
        "tool_call",
        f"{instruction.type} zone={zone_str}",
        **audit_meta,
    )

    # Warn when spatial content is placed without an explicit zone.
    spatial_types = {"draw_design_diagram", "draw_diagram", "show_graph", "draw_scene"}
    if instruction.type in spatial_types and not instruction.zone:
        tc.audit.record(
            "layout",
            "zone_missing",
            f"{instruction.type} {instruction.element_id or ''} placed without explicit zone",
            tool=instruction.type,
            element_id=instruction.element_id or "",
        )

    # Record the instruction's effect on the board state, stamped with concept context.
    concept = tc.current_concept
    tc.board_manager.record(
        instruction,
        concept_title=concept.title if concept else "",
        concept_index=tc.current_concept_index if tc.lesson_plan else None,
    )

    # Auto-tick doubt-branch checklist items whose `auto_satisfied_by` lists
    # this tool. No-op outside doubt branches or when the branch isn't tracked.
    tc.doubt_orchestrator.on_tool_invoked(
        instruction.type,
        tc.state_machine.current.id,
    )


async def _publish_switch_board(
    ctx: RunContext,
    board_id: str,
    label: str,
    intent: BoardIntent,
) -> None:
    """Publish a SwitchBoardInstruction immediately (no playout wait)."""
    instruction = SwitchBoardInstruction(
        board_id=board_id,
        label=label,
        intent=intent,
        sync_mode=SyncMode.IMMEDIATE,
    )
    _stamp_panel(instruction)
    room = ctx.session.room_io.room
    data = json.dumps(instruction.model_dump(exclude_none=True, by_alias=True))
    await room.local_participant.publish_data(data, reliable=True, topic="visuals")
    logger.debug(
        "visual.switch_board",
        board_id=board_id,
        label=label,
        intent=intent,
    )


# @function_tool()
# async def show_text(
#     ctx: RunContext,
#     text: str,
#     title: str = "",
#     zone: str = "",
#     timing: str = "",
#     relates_to: str = "",
#     relation: str = "",
#     near: str = "",
#     near_side: str = "",
#     size_hint: str = "",
# ) -> str:
#     """Display text on the classroom screen. Use for key points, definitions, important info.

#     Args:
#         text: The text content to display on the board.
#         title: Optional heading for the text block.
#         zone: Board zone for placement (9-zone grid). Prefer near+near_side for precise placement.
#         timing: When the visual appears relative to your speech. \
# "visual_first" (appears while you speak), "after_speech" (default — waits for your sentence to finish).
#         relates_to: Element ID this text relates to (e.g., "design-1", "eq-2"). \
# Declares a semantic relationship for board intelligence.
#         relation: Relationship type: "supports" (default — supporting detail), \
# "illustrates", "compares_with".
#         near: Place near an existing element by its ID (e.g., "design-1", "eq-2"). \
# The system computes exact position. Prefer this over zone.
#         near_side: Which side of the `near` element: "right_of" (default), \
# "below", "above", "left_of".
#         size_hint: Expected size: "small", "medium" (default), "large". \
# Helps the system check fit before placing.
#     """
#     instruction = ShowTextInstruction(
#         text=text, title=title, zone=_parse_zone(zone), sync_mode=_parse_timing(timing)
#     )
#     instruction.placement = _build_placement(near, near_side, size_hint)
#     await _publish_visual(ctx, instruction)
#     if relates_to and instruction.element_id:
#         _declare_relation(ctx, instruction.element_id, relates_to, relation, BoardRelation.SUPPORTS)
#     return f"Displayed on board: {text[:80]}"


@function_tool()
async def show_equation(
    ctx: RunContext,
    latex: str,
    label: str = "",
    animation: str = "fade_in",
    term_hints_json: str = "",
    zone: str = "",
    timing: str = "",
    relates_to: str = "",
    relation: str = "",
    near: str = "",
    near_side: str = "",
    size_hint: str = "",
) -> str:
    """Display a math equation on the classroom screen. Use LaTeX notation.

    Args:
        latex: The equation in LaTeX format (e.g., "E = mc^2", "\\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}").
            Use \\htmlId{term-1}{content} to tag individual terms for term_by_term animation.
        label: Optional label (e.g., "Newton's Second Law").
        animation: How the equation appears. Options: "none", "fade_in" (default), "term_by_term", "write_on".
        term_hints_json: JSON array mapping term IDs to trigger words for voice sync.
            Example: [{"term_id": "term-F", "trigger_words": ["force", "F"]},
                       {"term_id": "term-m", "trigger_words": ["mass", "m"]}]
            When provided with animation="term_by_term", terms reveal as you speak.
        zone: Board zone for placement (9-zone grid). Prefer near+near_side for precise placement.
        timing: When the equation appears. "visual_first" (while you speak), \
"after_speech" (default), or "term_sync" (terms reveal as you say them — use with term_by_term animation).
        relates_to: Element ID this equation relates to (e.g., "design-1"). \
Declares a semantic relationship for board intelligence.
        relation: Relationship type: "illustrates" (default — equation for a diagram), \
"derives_from" (next step in chain), "supports" (supporting detail).
        near: Place near an existing element by its ID (e.g., "design-1", "eq-2"). \
The system computes exact position. Prefer this over zone.
        near_side: Which side of the `near` element: "right_of" (default), \
"below", "above", "left_of".
        size_hint: Expected size: "small", "medium" (default), "large". \
Helps the system check fit before placing.
    """
    eq_animation = EquationAnimation(animation)
    term_hints = None
    sync_mode = _parse_timing(timing) if timing else SyncMode.ON_PLAYOUT
    if term_hints_json:
        term_hints = [TermSyncHint(**h) for h in json.loads(term_hints_json)]
        if eq_animation == EquationAnimation.TERM_BY_TERM:
            sync_mode = SyncMode.TERM_SYNC
    instruction = ShowEquationInstruction(
        latex=latex,
        label=label,
        animation=eq_animation,
        sync_mode=sync_mode,
        term_hints=term_hints,
        zone=_parse_zone(zone),
    )
    instruction.placement = _build_placement(near, near_side, size_hint)
    await _publish_visual(ctx, instruction)
    if relates_to and instruction.element_id:
        _declare_relation(
            ctx, instruction.element_id, relates_to, relation, BoardRelation.ILLUSTRATES
        )
    elif not relates_to and instruction.element_id:
        tc: TeachingContext = ctx.userdata
        tc.audit.record(
            "board_graph",
            "orphan_element",
            f"Equation {instruction.element_id} ({latex[:40]}) created without relates_to",
            element_id=instruction.element_id,
            tool="show_equation",
        )
    return f"Displayed equation: {latex}"


@function_tool()
async def draw_diagram(
    ctx: RunContext,
    diagram_type: str = "free_form",
    title: str = "",
    description: str = "",
    nodes_json: str = "",
    edges_json: str = "",
    progressive: bool = True,
    zone: str = "",
    timing: str = "visual_first",
    relates_to: str = "",
    relation: str = "",
    near: str = "",
    near_side: str = "",
    size_hint: str = "",
) -> str:
    """Draw a structured diagram on the classroom screen — flowcharts, force diagrams, concept maps, etc.

    Args:
        diagram_type: Layout style. Options: "flowchart", "concept_map", "force_diagram", "tree", "cycle", "comparison", "free_form" (default).
        title: Optional heading displayed above the diagram.
        description: Text description. Used as alt-text when nodes are provided, or as the primary content when they are not.
        nodes_json: A JSON array of node objects. Each node has:
            - "id" (required): Unique identifier.
            - "label" (required): Display text.
            - "shape" (optional): "rectangle", "rounded" (default), "circle", "diamond", "ellipse".
            - "color" (optional): Hex color for the node (e.g., "#60a5fa").
            Example: [{"id": "a", "label": "Start", "shape": "circle"}, {"id": "b", "label": "Process"}]
        edges_json: A JSON array of edge objects. Each edge has:
            - "from_id" (required): Source node ID.
            - "to_id" (required): Target node ID.
            - "label" (optional): Edge label text.
            - "style" (optional): "solid" (default), "dashed", "dotted".
            - "directed" (optional): true (default) for arrow, false for plain line.
            Example: [{"from_id": "a", "to_id": "b", "label": "next"}]
        progressive: Whether to animate nodes and edges appearing progressively (default true).
        zone: Board zone for placement (9-zone grid). Prefer near+near_side for precise placement.
        timing: When the diagram appears. "visual_first" (default — starts drawing while you speak, \
use with "Let me draw this..."), "after_speech" (waits for your sentence).
        relates_to: Element ID this diagram relates to (e.g., "eq-1"). \
Declares a semantic relationship for board intelligence.
        relation: Relationship type: "illustrates" (default), "compares_with", "supports".
        near: Place near an existing element by its ID (e.g., "design-1", "eq-2"). \
The system computes exact position. Prefer this over zone.
        near_side: Which side of the `near` element: "right_of" (default), \
"below", "above", "left_of".
        size_hint: Expected size: "small", "medium" (default), "large". \
Helps the system check fit before placing.
    """
    nodes = [DiagramNode(**n) for n in json.loads(nodes_json)] if nodes_json else []
    edges = [DiagramEdge(**e) for e in json.loads(edges_json)] if edges_json else []
    dtype = DiagramType(diagram_type)
    instruction = DrawDiagramInstruction(
        diagram_type=dtype,
        title=title,
        description=description,
        nodes=nodes,
        edges=edges,
        progressive=progressive,
        zone=_parse_zone(zone),
        sync_mode=_parse_timing(timing),
    )
    instruction.placement = _build_placement(near, near_side, size_hint)
    await _publish_visual(ctx, instruction)
    if relates_to and instruction.element_id:
        _declare_relation(
            ctx, instruction.element_id, relates_to, relation, BoardRelation.ILLUSTRATES
        )
    return f"Drew diagram: {title or description or diagram_type}"


@function_tool()
async def step_equation(
    ctx: RunContext,
    steps_json: str,
    title: str = "",
    zone: str = "",
    timing: str = "",
    relates_to: str = "",
    relation: str = "",
    near: str = "",
    near_side: str = "",
    size_hint: str = "",
) -> str:
    """Show a step-by-step equation solve on the classroom screen. Perfect for walking through algebra, simplification, or any multi-step derivation.

    Args:
        steps_json: A JSON array of step objects. Each step has:
            - "latex" (required): The equation at this step in LaTeX.
            - "annotation" (optional): What was done (e.g., "Subtract 4 from both sides").
            - "highlight_terms" (optional): List of htmlId refs for changed terms.
            Example: [{"latex": "2x + 4 = 10"}, {"latex": "2x = 6", "annotation": "Subtract 4 from both sides"}]
        title: Optional heading (e.g., "Solving for x").
        zone: Board zone for placement (9-zone grid). Prefer near+near_side for precise placement.
        timing: When the steps appear. "visual_first" (while you speak), "after_speech" (default).
        relates_to: Element ID this derivation relates to (e.g., "design-1", "eq-1"). \
Declares a semantic relationship for board intelligence.
        relation: Relationship type: "derives_from" (default — derivation from a source), \
"illustrates", "supports".
        near: Place near an existing element by its ID (e.g., "design-1", "eq-2"). \
The system computes exact position. Prefer this over zone.
        near_side: Which side of the `near` element: "right_of" (default), \
"below", "above", "left_of".
        size_hint: Expected size: "small", "medium" (default), "large". \
Helps the system check fit before placing.
    """
    raw_steps = json.loads(steps_json)
    steps = [EquationStep(**s) for s in raw_steps]
    instruction = StepEquationInstruction(
        title=title,
        steps=steps,
        zone=_parse_zone(zone),
        sync_mode=_parse_timing(timing),
    )
    instruction.placement = _build_placement(near, near_side, size_hint)
    await _publish_visual(ctx, instruction)
    # Declare relationship to the referenced element.
    if relates_to and instruction.element_id:
        _declare_relation(
            ctx,
            instruction.element_id,
            relates_to,
            relation,
            BoardRelation.DERIVES_FROM,
        )
    elif not relates_to and instruction.element_id:
        tc: TeachingContext = ctx.userdata
        tc.audit.record(
            "board_graph",
            "orphan_element",
            f"Step equation {instruction.element_id} ({title or 'untitled'}) created without relates_to",
            element_id=instruction.element_id,
            tool="step_equation",
        )
    return f"Displayed step-by-step equation: {title or steps[-1].latex}"


@function_tool()
async def show_graph(
    ctx: RunContext,
    graph_type: str = "line",
    title: str = "",
    x_axis_label: str = "",
    x_min: float | None = None,
    x_max: float | None = None,
    y_axis_label: str = "",
    y_min: float | None = None,
    y_max: float | None = None,
    series_json: str = "",
    functions_json: str = "",
    animated: bool = True,
    zone: str = "",
    timing: str = "visual_first",
    relates_to: str = "",
    relation: str = "",
    near: str = "",
    near_side: str = "",
    size_hint: str = "",
) -> str:
    """Display a graph or chart on the classroom screen — line charts, bar charts, scatter plots, or function plots.

    Args:
        graph_type: Chart style. Options: "line" (default), "bar", "scatter", "function".
        title: Optional heading displayed above the chart.
        x_axis_label: Label for the x-axis (e.g., "Time (s)").
        x_min: Optional minimum value for the x-axis.
        x_max: Optional maximum value for the x-axis.
        y_axis_label: Label for the y-axis (e.g., "Height (m)").
        y_min: Optional minimum value for the y-axis.
        y_max: Optional maximum value for the y-axis.
        series_json: A JSON array of data series. Each series has:
            - "label" (optional): Legend label for this series.
            - "points" (required): Array of data points, each with "x" (number), "y" (number), and optional "label" (string, for bar chart category labels).
            - "color" (optional): Hex color for this series (e.g., "#60a5fa").
            Example: [{"label": "Scores", "points": [{"x": 1, "y": 85, "label": "Math"}, {"x": 2, "y": 92, "label": "Science"}]}]
        functions_json: A JSON array of function definitions for function plots. Each function has:
            - "expression" (required): Math expression using variable x (e.g., "x^2", "sin(x)", "2*x + 3", "sqrt(x)").
            - "label" (optional): Legend label.
            - "color" (optional): Hex color.
            - "domain_min" (optional): Minimum x value to plot.
            - "domain_max" (optional): Maximum x value to plot.
            Example: [{"expression": "x^2 - 4", "label": "f(x) = x² - 4"}, {"expression": "2*x", "label": "g(x) = 2x", "color": "#60a5fa"}]
        animated: Whether to animate the chart drawing in (default true).
        zone: Board zone for placement (9-zone grid). Prefer near+near_side for precise placement.
        timing: When the graph appears. "visual_first" (default — starts drawing while you speak), \
"after_speech" (waits for your sentence).
        relates_to: Element ID this graph relates to (e.g., "eq-1", "design-1"). \
Declares a semantic relationship for board intelligence.
        relation: Relationship type: "illustrates" (default — graph visualizing an equation/concept), \
"supports", "compares_with".
        near: Place near an existing element by its ID (e.g., "design-1", "eq-2"). \
The system computes exact position. Prefer this over zone.
        near_side: Which side of the `near` element: "right_of" (default), \
"below", "above", "left_of".
        size_hint: Expected size: "small", "medium" (default), "large". \
Helps the system check fit before placing.
    """
    series = [DataSeries(**s) for s in json.loads(series_json)] if series_json else []
    functions = [FunctionDef(**f) for f in json.loads(functions_json)] if functions_json else []
    gtype = GraphType(graph_type)
    x_axis = AxisConfig(label=x_axis_label, min=x_min, max=x_max)
    y_axis = AxisConfig(label=y_axis_label, min=y_min, max=y_max)
    instruction = ShowGraphInstruction(
        graph_type=gtype,
        title=title,
        x_axis=x_axis,
        y_axis=y_axis,
        series=series,
        functions=functions,
        animated=animated,
        zone=_parse_zone(zone),
        sync_mode=_parse_timing(timing),
    )
    instruction.placement = _build_placement(near, near_side, size_hint)
    await _publish_visual(ctx, instruction)
    if relates_to and instruction.element_id:
        _declare_relation(
            ctx, instruction.element_id, relates_to, relation, BoardRelation.ILLUSTRATES
        )
    return f"Displayed graph: {title or graph_type}"


@function_tool()
async def annotate(
    ctx: RunContext,
    action: str,
    target_id: str = "",
    from_id: str = "",
    to_id: str = "",
    color: str = "",
) -> str:
    """Draw a freehand annotation — circle, underline, or arrow.

    Use to direct student attention to elements already on the board.
    Annotations are transient gestures that draw in and fade out automatically.

    Args:
        action: The annotation type. Options: "circle" (ring around an element), \
"underline" (line beneath an element), "arrow" (from one element to another).
        target_id: Element ID to annotate. Required for "circle" and "underline" \
(e.g., "eq-1", "text-2").
        from_id: Source element ID. Required for "arrow".
        to_id: Destination element ID. Required for "arrow".
        color: Optional hex color for the annotation (e.g., "#ef4444"). \
Defaults to accent red on the frontend.
    """
    ann_action = AnnotationAction(action)
    instruction = AnnotateInstruction(
        action=ann_action,
        target_id=target_id,
        from_id=from_id,
        to_id=to_id,
        color=color,
        sync_mode=SyncMode.IMMEDIATE,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    # Auto-declare annotates relationship.
    if ann_action == AnnotationAction.ARROW and from_id and to_id:
        tc: TeachingContext = ctx.userdata
        tc.board_manager.active_board.state.board_graph.add_edge(
            source_id=from_id, target_id=to_id, relation=BoardRelation.ANNOTATES
        )
        return f"Drew arrow from {from_id} to {to_id}"
    return f"Drew {action} on {target_id}"


@function_tool()
async def highlight_diagram_part(
    ctx: RunContext,
    target_id: str,
    sub_element_ids: str,
    style: str = "glow",
    color: str = "#fbbf24",
) -> str:
    """Highlight specific parts of a design diagram — like pointing with a laser pointer.

    Use this to direct student attention to specific elements within a design diagram.
    The highlight appears immediately and stays until you highlight a different part
    or clear it. Each new highlight on the same diagram automatically dims the previous one.

    Call this tool naturally during your explanation to make each part light up as you
    discuss it. You don't need to wait — the highlight fires instantly.

    Args:
        target_id: The element_id of the design diagram (e.g., "design-1"). \
Must match the element_id returned by draw_design_diagram.
        sub_element_ids: Comma-separated list of sub-element IDs to highlight \
(e.g., "barrier" or "slit-a,slit-b"). These are the SVG element IDs \
listed by draw_design_diagram after drawing.
        style: Highlight effect. Options: "glow" (default, soft glow), "pulse" (pulsing scale effect).
        color: Hex color for the highlight glow (default "#fbbf24" amber). \
Use "#ef4444" for red, "#60a5fa" for blue, "#4ade80" for green, "#a78bfa" for purple.
    """
    ids = [s.strip() for s in sub_element_ids.split(",") if s.strip()]
    if not ids:
        return "No sub-element IDs provided."

    hl_style = (
        HighlightStyle(style)
        if style in HighlightStyle.__members__.values()
        else HighlightStyle.GLOW
    )
    instruction = HighlightInstruction(
        target_id=target_id,
        style=hl_style,
        color=color,
        sub_element_ids=ids,
        sync_mode=SyncMode.IMMEDIATE,
        duration_ms=8000,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    return f"Highlighted {', '.join(ids)} in {target_id}"


@function_tool()
async def highlight_walk(
    ctx: RunContext,
    target_id: str,
    steps_json: str,
) -> str:
    """Walk through parts of a diagram, highlighting each part as you talk about it.

    Use this AFTER drawing a diagram or scene to guide students through it part by part.
    Each step highlights one sub-element when you say its trigger words. Only one part
    is highlighted at a time — the previous one dims when the next one lights up.

    Args:
        target_id: The element_id of the diagram or scene to walk through \
(e.g., "diagram-1", "scene-2"). Must already be on the board.
        steps_json: A JSON array of step objects. Each step has:
            - "sub_element_id" (required): ID of the sub-element to highlight. \
For diagrams: use the node id (same as the "id" field in nodes_json). \
For scenes: use the element id (same as the "id" field in elements_json).
            - "trigger_words" (required): List of words you will say that trigger \
this step's highlight. When you say any of these words, this part lights up.
            - "style" (optional): "glow" (default), "pulse", "box", or "underline".
            - "color" (optional): Hex color for the highlight (e.g., "#fbbf24").
            Example: [
                {"sub_element_id": "block", "trigger_words": ["block", "object", "box"]},
                {"sub_element_id": "W", "trigger_words": ["weight", "gravity", "mg"]},
                {"sub_element_id": "N", "trigger_words": ["normal", "support"]}
            ]
    """
    raw_steps = json.loads(steps_json)
    steps = [HighlightWalkStep(**s) for s in raw_steps]

    # Populate term_hints so the frontend SyncManager can reuse its word-matching.
    term_hints = [
        TermSyncHint(term_id=s.sub_element_id, trigger_words=s.trigger_words) for s in steps
    ]

    instruction = HighlightWalkInstruction(
        target_id=target_id,
        steps=steps,
        sync_mode=SyncMode.TERM_SYNC,
        term_hints=term_hints,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    return f"Highlight walk active on {target_id} with {len(steps)} steps"


@function_tool()
async def clear_board(ctx: RunContext, target_id: str = "") -> str:
    """Clear the classroom screen. Clears everything by default, or a specific element by ID.

    Args:
        target_id: Optional element ID to remove (e.g., "eq-1", "diagram-2"). \
Leave empty to clear the entire board.
    """
    instruction = ClearInstruction(
        sync_mode=SyncMode.IMMEDIATE,
        target_id=target_id or None,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    if target_id:
        return f"Removed element: {target_id}"
    # Full clear → no diagram is on the slide anymore.
    tc: TeachingContext = ctx.userdata
    tc.current_diagram_dictionary = {}
    return "Board cleared"


@function_tool()
async def clear_cluster(ctx: RunContext, element_id: str) -> str:
    """Clear an element and everything semantically related to it.

    Removes the full cluster: the diagram, its equation, its derivation
    steps, its annotations — everything connected. Much faster than
    clearing elements one by one.

    Args:
        element_id: Any element in the cluster to remove (e.g., "design-1"). \
All semantically connected elements will also be cleared.
    """
    tc: TeachingContext = ctx.userdata
    graph = tc.board_manager.active_board.state.board_graph
    cluster = graph.get_cluster(element_id)
    for eid in sorted(cluster):
        instruction = ClearInstruction(target_id=eid, sync_mode=SyncMode.IMMEDIATE)
        await _publish_visual(ctx, instruction, wait_for_speech=False)
    return f"Cleared cluster ({len(cluster)} elements): {', '.join(sorted(cluster))}"


# ──────────────────────────────────────────────
# Slide annotation tools (diagram awareness)
#
# Write *around* the diagram on the slide — pinned labels, callouts, brackets,
# pulse highlights. Use these the way a real teacher uses a marker on the
# board: mark the part being talked about. Each tool resolves
# ``element_or_role`` against the active ``DiagramSpec.dictionary`` so the LLM
# can refer to elements by role (``"hypotenuse"``) instead of opaque IDs.
# ──────────────────────────────────────────────


def _resolve_diagram_target(ctx: RunContext, element_or_role: str) -> str:
    """Resolve ``element_or_role`` against the active diagram's dictionary."""
    from feynman.agent.diagram_dictionary import DictionaryResolver

    tc: TeachingContext = ctx.userdata
    return DictionaryResolver(tc).resolve(element_or_role)


@function_tool()
async def pin_label_near(
    ctx: RunContext,
    element_or_role: str,
    text: str,
    position: str = "above",
) -> str:
    """Place a small text label near a diagram element with a thin connector line.

    Use this for marginalia and quick identifications — a "← hypotenuse" tag
    next to a side, or "8 m" next to a measured length. The label fades in
    over ~300ms and stays until the diagram is replaced.

    Args:
        element_or_role: Either an exact element_id from the diagram \
(e.g. "side_AB") or a semantic role from the diagram's dictionary \
(e.g. "hypotenuse"). Roles are preferred — they survive diagram regeneration.
        text: Short label text. Keep it under ~30 chars; max 120.
        position: Where to place the label relative to the element. \
Options: "above" (default), "below", "left", "right".
    """
    target_id = _resolve_diagram_target(ctx, element_or_role)
    pos: Literal["above", "below", "left", "right"] = (
        position if position in ("above", "below", "left", "right") else "above"  # type: ignore[assignment]
    )
    instruction = PinLabelInstruction(
        target_element_id=target_id,
        text=text,
        position=pos,
        sync_mode=SyncMode.IMMEDIATE,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    tc: TeachingContext = ctx.userdata
    if instruction.element_id:
        tc.active_annotations.append(instruction.element_id)
    return f'Pinned "{text}" {position} of {target_id}'


@function_tool()
async def draw_callout(
    ctx: RunContext,
    from_element: str,
    text: str,
    direction: str = "up-right",
) -> str:
    """Draw a speech-bubble callout from a diagram element.

    Use sparingly for emphasis or short pedagogical notes — "← key insight!" or
    "this is what we're solving for". The bubble's tail draws first (~200ms),
    then the bubble inflates (~300ms), then the text fades in.

    Args:
        from_element: Element ID or semantic role of the element the callout \
points at. Roles are preferred.
        text: Callout content. Keep it under ~80 chars; max 200.
        direction: Which way the callout extends from the element. \
Options: "up-right" (default), "up-left", "down-right", "down-left", "up", "down".
    """
    target_id = _resolve_diagram_target(ctx, from_element)
    valid_dirs = {"up", "down", "up-left", "up-right", "down-left", "down-right"}
    direction_value: Literal["up", "down", "up-left", "up-right", "down-left", "down-right"] = (
        direction if direction in valid_dirs else "up-right"
    )  # type: ignore[assignment]
    instruction = DrawCalloutInstruction(
        target_element_id=target_id,
        text=text,
        direction=direction_value,
        sync_mode=SyncMode.IMMEDIATE,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    tc: TeachingContext = ctx.userdata
    if instruction.element_id:
        tc.active_annotations.append(instruction.element_id)
    return f"Callout '{text[:40]}' on {target_id}"


@function_tool()
async def bracket(
    ctx: RunContext,
    element_a: str,
    element_b: str,
    label: str,
    side: str = "above",
) -> str:
    """Draw a curly bracket spanning two diagram elements with a centered label.

    Use this to show a relationship between two parts — "right triangle"
    spanning hypotenuse and adjacent, or "this is what we're measuring" across
    two sides. The bracket draws (~400ms), then the label fades in.

    Args:
        element_a: Element ID or role of the first element.
        element_b: Element ID or role of the second element.
        label: Text centered on the bracket. Max 80 chars.
        side: Which side of the elements the bracket goes on. \
Options: "above" (default), "below", "left", "right".
    """
    a_id = _resolve_diagram_target(ctx, element_a)
    b_id = _resolve_diagram_target(ctx, element_b)
    side_value: Literal["above", "below", "left", "right"] = (
        side if side in ("above", "below", "left", "right") else "above"  # type: ignore[assignment]
    )
    instruction = BracketInstruction(
        element_a_id=a_id,
        element_b_id=b_id,
        label=label,
        side=side_value,
        sync_mode=SyncMode.IMMEDIATE,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    tc: TeachingContext = ctx.userdata
    if instruction.element_id:
        tc.active_annotations.append(instruction.element_id)
    return f"Bracketed {a_id}↔{b_id} ({label})"


@function_tool()
async def highlight_pulse(
    ctx: RunContext,
    element_or_role: str,
    duration_ms: int = 1200,
    color_token: str = "--sb-neon",
) -> str:
    """Pulse a single diagram element with one short glow cycle.

    Simpler than ``highlight_walk`` when you only need to spotlight one element
    while saying its name. Fires instantly — call it BEFORE speaking about
    the element, like a teacher tapping the board.

    Args:
        element_or_role: Element ID or semantic role of the element to pulse. \
Roles are preferred.
        duration_ms: Total pulse duration in ms. Default 1200; clamped 400-3000.
        color_token: CSS variable for the glow color. Default "--sb-neon".
    """
    target_id = _resolve_diagram_target(ctx, element_or_role)
    instruction = HighlightPulseInstruction(
        target_element_id=target_id,
        duration_ms=duration_ms,
        color_token=color_token,
        sync_mode=SyncMode.IMMEDIATE,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    tc: TeachingContext = ctx.userdata
    if target_id and target_id not in tc.active_highlights:
        tc.active_highlights.append(target_id)
    return f"Pulsed {target_id} ({duration_ms}ms)"


# ──────────────────────────────────────────────
# Notebook write-tools (split-board Phase 5)
#
# Native surface for writing in the notebook panel. Prefer these over the
# slide-era `show_*` tools when composing equations/steps/answers as part of
# the notebook's working column. Panel is stamped deterministically to
# `Panel.NOTEBOOK` via INSTRUCTION_TYPE_TO_PANEL.
# ──────────────────────────────────────────────


@function_tool()
async def write_equation(
    ctx: RunContext,
    latex: str,
    label: str = "",
    align_group: str = "",
    indent: int = 0,
) -> str:
    """Write an equation in the notebook's working column.

    Use this instead of ``show_equation`` when the equation is part of the
    notebook's working — solving, deriving, re-arranging in sequence.
    Multiple equations that share the same ``align_group`` render vertically
    aligned at the ``=`` sign (like hand-written algebra).

    Args:
        latex: The equation in LaTeX (e.g., ``"F = m a"``, ``"a = \\frac{F}{m}"``).
        label: Optional annotation shown to the right of the equation.
        align_group: Any stable string identifier (e.g. ``"solve-for-a"``). \
Equations sharing this value line up at the ``=`` sign. Leave empty for no alignment.
        indent: Indent level 0-3 (24px each). Use 1 for sub-steps of a derivation.
    """
    instruction = WriteEquationInstruction(
        latex=latex,
        label=label,
        align_group=align_group or None,
        indent=indent,
    )
    await _publish_visual(ctx, instruction)
    return f"Wrote equation: {latex[:40]}"


@function_tool()
async def write_step(
    ctx: RunContext,
    text: str,
    number: int = 0,
    indent: int = 0,
) -> str:
    """Write a working step — a narrative line in the notebook.

    Use for text that describes the next move in a derivation or solution
    (e.g., ``"Solve for a"``, ``"Substitute F = 10 into the equation"``).

    Args:
        text: The step text in plain prose; no LaTeX.
        number: Optional step number (1, 2, 3...). Pass 0 for an unnumbered step.
        indent: Indent level 0-3 (24px each). Use 1 for sub-steps.
    """
    instruction = WriteStepInstruction(
        text=text,
        number=number if number > 0 else None,
        indent=indent,
    )
    await _publish_visual(ctx, instruction)
    return f"Wrote step: {text[:40]}"


@function_tool()
async def write_text(
    ctx: RunContext,
    text: str,
    style: str = "default",
    indent: int = 0,
) -> str:
    """Write a plain text line or a key-point box in the notebook.

    Args:
        text: The text content (plain prose; no LaTeX).
        style: ``"default"`` for a plain line, or ``"key_point"`` for a \
bordered box that draws extra attention.
        indent: Indent level 0-3 (24px each).
    """
    resolved_style: Literal["default", "key_point"] = (
        "key_point" if style == "key_point" else "default"
    )
    instruction = WriteTextInstruction(
        text=text,
        style=resolved_style,
        indent=indent,
    )
    await _publish_visual(ctx, instruction)
    return f"Wrote text: {text[:40]}"


@function_tool()
async def write_section(
    ctx: RunContext,
    title: str,
) -> str:
    """Write a section header in the notebook.

    Use at the start of each new concept, worked example, or sub-topic. Renders
    as a bold line marked with ``§`` and a divider below — a visual "now we're
    starting a new section of the working" cue.

    Args:
        title: The section heading (e.g., ``"Newton's Second Law"``).
    """
    instruction = WriteSectionInstruction(title=title)
    await _publish_visual(ctx, instruction)
    return f"Wrote section: {title}"


@function_tool()
async def write_answer(
    ctx: RunContext,
    latex: str = "",
    text: str = "",
) -> str:
    """Write the boxed final answer in the notebook.

    The answer renders with a green border and a subtle glow — a visual "this
    is the result we were after" cue. Provide exactly one of ``latex`` or
    ``text``.

    Args:
        latex: LaTeX for the boxed answer (e.g., ``"a = 5\\,\\text{m/s}^2"``).
        text: Plain text for the boxed answer (e.g., ``"pH = 7.0"``).
    """
    instruction = WriteAnswerInstruction(
        latex=latex or None,
        text=text or None,
    )
    await _publish_visual(ctx, instruction)
    return f"Wrote answer: {(latex or text)[:40]}"


@function_tool()
async def strikethrough(
    ctx: RunContext,
    target_id: str,
) -> str:
    """Cross out an existing notebook entry — like striking through a wrong step.

    Use when you realize a previously written line is wrong and want to visibly
    correct it before writing the right version. The struck line stays visible
    but has a red line drawn through it.

    Args:
        target_id: The ``element_id`` of the notebook entry to strike \
(e.g., ``"eq-3"``, ``"step-5"``). The ID is returned by the previous write tool.
    """
    instruction = StrikethroughInstruction(
        target_id=target_id,
        sync_mode=SyncMode.IMMEDIATE,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    return f"Struck entry: {target_id}"


@function_tool()
async def new_page(
    ctx: RunContext,
    carry_forward_ids: list[str] | None = None,
) -> str:
    """Turn to a fresh blank page in the notebook.

    Call when the current page is full and you want to keep writing. The
    students see the page flip, then the notebook is clean for the next batch
    of working. Previous pages are retained in history.

    Pass ``element_id``s in ``carry_forward_ids`` to show those entries at
    the top of the new page as muted, inert reminders — useful when a
    premise (e.g. the starting equation) from the previous page still
    applies. Carried reminders track the original's state (they appear
    struck-through if the original was crossed out).
    """
    instruction = NewPageInstruction(
        carry_forward_ids=list(carry_forward_ids or []),
        sync_mode=SyncMode.IMMEDIATE,
    )
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    return "Turned to new page"


def _recent_notebook_entries(ctx: RunContext, n: int = 5) -> list[dict[str, str]]:
    """Return the last ``n`` notebook-panel tool calls from the audit log.

    Used by Phase 5b prompt integration to show the agent a compact recap of
    what it has already written. Not wired into the prompt in Phase 5 — this
    helper is here so the next phase can insert it without a new file hop.
    """
    tc: TeachingContext = ctx.userdata
    notebook_tools = {
        t for t, panel in INSTRUCTION_TYPE_TO_PANEL.items() if panel == Panel.NOTEBOOK
    }
    hits: list[dict[str, str]] = []
    for evt in reversed(tc.audit.events_for("routing")):
        tool = evt.metadata.get("tool", "")
        if tool in notebook_tools:
            hits.append(
                {
                    "tool": tool,
                    "element_id": evt.metadata.get("element_id", ""),
                    "detail": evt.detail,
                }
            )
            if len(hits) >= n:
                break
    hits.reverse()
    return hits


@function_tool()
async def draw_design_diagram(
    ctx: RunContext,
    prompt: str,
    zone: str = "",
    timing: str = "visual_first",
    relates_to: str = "",
    relation: str = "",
    near: str = "",
    near_side: str = "",
    size_hint: str = "",
) -> str:
    """Draw a detailed, precise SVG diagram using the AI design agent.

    Use this for diagrams that need spatial precision, rich visual detail, or
    complex layouts — physics apparatus, biological structures, mathematical constructions,
    annotated illustrations, etc. Takes 5-15 seconds (use modify_design_diagram for updates).

    After drawing, use highlight_diagram_part or highlight_walk to walk through parts.
    Each element in the generated diagram has a unique ID for highlighting.

    Args:
        prompt: Detailed description of the diagram to draw. Be specific about what to show, \
labels, colors, layout. Example: "A free body diagram of a 5kg block on a 30-degree \
inclined plane showing weight (mg), normal force (N), and friction (f) vectors with \
proper angles labeled."
        zone: Board zone for placement (9-zone grid). Prefer near+near_side for precise placement.
        timing: When the diagram appears. "visual_first" (default — starts rendering while you speak), \
"after_speech" (waits for your sentence).
        relates_to: Element ID this diagram relates to (e.g., "eq-1"). \
Declares a semantic relationship for board intelligence.
        relation: Relationship type: "illustrates" (default), "compares_with", "supports".
        near: Place near an existing element by its ID (e.g., "design-1", "eq-2"). \
The system computes exact position. Prefer this over zone.
        near_side: Which side of the `near` element: "right_of" (default), \
"below", "above", "left_of".
        size_hint: Expected size: "small", "medium" (default), "large". \
Helps the system check fit before placing.
    """
    from feynman.agent.design_bridge import generate_design_diagram

    tc: TeachingContext = ctx.userdata

    try:
        # Check anticipation cache first.
        cached = tc.anticipation.match(prompt, tc.current_concept_index)
        if cached:
            spec = cached
            logger.info(
                "draw_design_diagram.cache_hit",
                concept=tc.current_concept_index,
                prompt=prompt[:60],
            )
            tc.audit.record(
                "anticipation",
                "cache_hit",
                f"concept={tc.current_concept_index}, prompt='{prompt[:60]}'",
            )
        else:
            concept = tc.current_concept
            caption_title = (concept.title if concept else "") or prompt.strip().split("\n", 1)[0][
                :80
            ]
            await _publish_visual(
                ctx,
                SlidePendingInstruction(title=caption_title),
                wait_for_speech=False,
            )
            spec = await generate_design_diagram(prompt, model="sonnet")
            logger.info(
                "draw_design_diagram.cache_miss",
                concept=tc.current_concept_index,
                prompt=prompt[:60],
            )
            tc.audit.record(
                "anticipation",
                "cache_miss",
                f"concept={tc.current_concept_index}, prompt='{prompt[:60]}'",
            )
    except Exception:
        logger.exception("draw_design_diagram.generation_failed", prompt=prompt[:100])
        tc.audit.record("doubt", "fallback_to_scene", f"prompt='{prompt[:60]}'")
        return (
            "Failed to generate design diagram. Use draw_scene instead — "
            "it has components for physics (free_body, optics), circuits, geometry, and chemistry."
        )

    title = spec.get("title", "")
    description = spec.get("description", prompt[:200])
    instruction = DrawDesignDiagramInstruction(
        title=title,
        description=description,
        spec=spec,
        zone=_parse_zone(zone),
        sync_mode=_parse_timing(timing),
    )
    instruction.placement = _build_placement(near, near_side, size_hint)
    await _publish_visual(ctx, instruction)

    # Store the design spec for future modification via modify_design_diagram.
    if instruction.element_id:
        tc.board_manager.store_design_spec(instruction.element_id, spec)

    # Diagram awareness: expose the spec's dictionary so the teaching agent
    # (and DictionaryResolver) can refer to elements by role.
    tc.current_diagram_dictionary = dict(spec.get("dictionary") or {})

    # Declare semantic relationship.
    if relates_to and instruction.element_id:
        _declare_relation(
            ctx, instruction.element_id, relates_to, relation, BoardRelation.ILLUSTRATES
        )
    elif not relates_to and instruction.element_id:
        tc.audit.record(
            "board_graph",
            "orphan_element",
            f"Design diagram {instruction.element_id} ({prompt[:40]}) created without relates_to",
            element_id=instruction.element_id,
            tool="draw_design_diagram",
        )

    # Give frontend time to render the SVG diagram.
    element_count = len(spec.get("elements", []))
    render_time = max(1.0, element_count * 0.05)
    await asyncio.sleep(render_time)

    # Collect sub-element IDs so the agent can reference them in highlight_walk.
    sub_ids = [el.get("id") for el in spec.get("elements", []) if el.get("id")]
    eid = instruction.element_id  # e.g. "design-1"

    # Background visual verification (at most once per concept).
    if tc.board_verifier and not tc._verified_this_concept:
        board_ctx = tc.board_manager.active_board.state.summary()
        _verify_task = asyncio.create_task(  # noqa: RUF006
            tc.board_verifier.request_verification(
                element_id=eid,
                concept_index=tc.current_concept_index,
                board_context=board_ctx,
            )
        )
        tc._verified_this_concept = True
        logger.info(
            "visual_verification.fired",
            element_id=eid,
            concept=tc.current_concept_index,
        )

    result = f'Drew design diagram (element_id: "{eid}"): {title or prompt[:80]}'
    if sub_ids:
        result += (
            f"\nHighlightable sub-element IDs: {', '.join(sub_ids)}"
            f'\nUse highlight_walk(target_id="{eid}", ...) with these IDs as sub_element_id.'
        )
    return result


@function_tool()
async def modify_design_diagram(
    ctx: RunContext,
    target_id: str,
    modification: str,
    zone: str = "",
    timing: str = "visual_first",
) -> str:
    """Modify an existing design diagram on the board instead of redrawing from scratch.

    This is much faster than draw_design_diagram (~1-3 seconds vs 5-15 seconds) because
    the existing diagram spec is sent to the AI along with your modification request,
    so it only needs to make targeted changes rather than inventing a new layout.

    Use this when a design diagram is already on the board and you want to:
    - Add new elements (e.g., "add a friction vector")
    - Remove elements (e.g., "remove the third resistor")
    - Change properties (e.g., "change the angle to 45 degrees")
    - Update labels or colors (e.g., "make the mitochondria green")
    - Adapt the diagram for a follow-up explanation

    If the target diagram no longer exists (was cleared), use draw_design_diagram instead.

    Args:
        target_id: Element ID of the existing design diagram to modify (e.g., "design-1"). \
Must be a design diagram currently on the board.
        modification: Natural language description of what to change. Be specific. \
Example: "Add a friction force vector pointing up the incline, labeled 'f', in red."
        zone: Optional zone override if you want to move the diagram. Usually leave empty \
to keep it in place.
        timing: When the updated diagram appears. "visual_first" (default) or "after_speech".
    """
    from feynman.agent.design_bridge import modify_design_diagram_spec

    tc: TeachingContext = ctx.userdata

    # Retrieve the stored spec for this diagram.
    existing_spec = tc.board_manager.get_design_spec(target_id)
    if existing_spec is None:
        return (
            f'No design diagram found with element_id "{target_id}". '
            f"It may have been cleared. Use draw_design_diagram to create a new one."
        )

    try:
        t0 = time.monotonic()
        modified_spec = await modify_design_diagram_spec(existing_spec, modification)
        elapsed_ms = (time.monotonic() - t0) * 1000
    except Exception:
        logger.exception(
            "modify_design_diagram.failed",
            target_id=target_id,
            modification=modification[:100],
        )
        return (
            f'Failed to modify diagram "{target_id}". '
            f"Try using draw_design_diagram with a fresh prompt instead."
        )

    title = modified_spec.get("title", "")
    description = modified_spec.get("description", modification[:200])
    instruction = DrawDesignDiagramInstruction(
        title=title,
        description=description,
        spec=modified_spec,
        zone=_parse_zone(zone) if zone else None,
        sync_mode=_parse_timing(timing),
    )
    # Use the SAME element_id so the frontend replaces in-place.
    instruction.element_id = target_id

    # Preserve existing position — modification stays in place, not re-placed.
    existing_rect = tc.board_manager.active_board.state.spatial_solver.occupied.get(target_id)
    if existing_rect:
        instruction.position_x = existing_rect.x
        instruction.position_y = existing_rect.y

    await _publish_visual(ctx, instruction)

    # Update the stored spec with the modified version.
    tc.board_manager.store_design_spec(target_id, modified_spec)

    # Diagram awareness: refresh dictionary to match the new spec.
    tc.current_diagram_dictionary = dict(modified_spec.get("dictionary") or {})

    logger.info(
        "modify_design_diagram.complete",
        target_id=target_id,
        elapsed_ms=round(elapsed_ms),
        elements=len(modified_spec.get("elements", [])),
    )
    tc.audit.record(
        "modify_diagram",
        "modified",
        f"target={target_id}, concept={tc.current_concept_index}, elapsed={elapsed_ms:.0f}ms",
        target_id=target_id,
        concept_index=tc.current_concept_index,
        elapsed_ms=elapsed_ms,
    )

    # Log board spatial state after modification for observability.
    board_summary = tc.board_manager.active_board.state.summary()
    if board_summary:
        logger.info("modify_design_diagram.board_state", summary=board_summary[:300])

    # Give frontend time to render.
    element_count = len(modified_spec.get("elements", []))
    render_time = max(1.0, element_count * 0.05)
    await asyncio.sleep(render_time)

    # Collect sub-element IDs.
    sub_ids = [el.get("id") for el in modified_spec.get("elements", []) if el.get("id")]

    result = f'Modified design diagram (element_id: "{target_id}"): {modification[:80]}'
    if sub_ids:
        result += (
            f"\nHighlightable sub-element IDs: {', '.join(sub_ids)}"
            f'\nUse highlight_walk(target_id="{target_id}", ...) with these IDs.'
        )
    return result


# Animation duration estimates (ms) per scene template.
# Derived from GSAP timeline: ~0.4s/path + 0.06s stagger + 0.25s/label.
_SCENE_DURATION_MS: dict[str, int] = {
    "free_body": 1200,
    "double_slit": 1500,
}


@function_tool()
async def draw_scene(
    ctx: RunContext,
    title: str = "",
    description: str = "",
    template_id: str = "",
    params_json: str = "",
    scene_type: str = "",
    elements_json: str = "",
    progressive: bool = True,
    zone: str = "",
    timing: str = "visual_first",
    relates_to: str = "",
    relation: str = "",
    near: str = "",
    near_side: str = "",
    size_hint: str = "",
) -> str:
    """Draw a scientific diagram on the classroom screen — physics apparatus, optics setups, circuits, geometry.

    These are hand-drawn, spatially precise diagrams. Use draw_scene for physics/science/math
    illustrations where spatial accuracy matters. Use draw_diagram for abstract relationships
    (flowcharts, concept maps).

    Two modes:
    1. **Semantic spec** (preferred): set scene_type + elements_json to compose any diagram
       from the component library. Flexible, supports all 33 components.
    2. **Template** (legacy): set template_id for pre-built scenes. Limited to 2 templates.

    Args:
        title: Heading above the diagram.
        description: Alt-text describing what the diagram shows. Always provide this.
        template_id: (Legacy) Pre-built template. Available: "free_body", "double_slit".
            Prefer scene_type + elements_json for flexibility.
        params_json: JSON of template params. Example: {"showWeight": true, "showFriction": true}
        scene_type: Layout strategy for composable diagrams. Available:
            - "free_body": Forces on an object. Component kinds: box, force_arrow, spring, surface, inclined_plane
            - "optics": Optical setups. Kinds: convex_lens, concave_lens, point_source, ray, screen, barrier, wavefront_arc, prism
            - "circuit": Electrical circuits. Kinds: battery, resistor, capacitor, inductor, switch, bulb, ammeter, voltmeter, wire, junction, ground
            - "geometry": Math constructions. Kinds: point, line_segment, circle_shape, triangle, angle_arc, right_angle_mark, parallel_mark, congruence_mark, arc
            - "chemistry": Chemical reactions and apparatus. Kinds: molecule, arrow_label, beaker, flask, test_tube, bunsen_burner, thermometer, tubing
        elements_json: JSON array of semantic elements. Each element:
            {"id": "unique_id", "kind": "component_kind", "label": "display label", ...}
            Optional fields: "from" and "to" (anchor references), "direction", "angle", "magnitude", "color",
            "extras" (dict of component-specific params).
        progressive: Animate drawing in progressively (default true).
        zone: Board zone for placement (9-zone grid). Prefer near+near_side for precise placement.
        timing: When the scene appears. "visual_first" (default — starts drawing while you speak), \
"after_speech" (waits for your sentence).
        relates_to: Element ID this scene relates to (e.g., "eq-1"). \
Declares a semantic relationship for board intelligence.
        relation: Relationship type: "illustrates" (default), "compares_with", "supports".
        near: Place near an existing element by its ID (e.g., "design-1", "eq-2"). \
The system computes exact position. Prefer this over zone.
        near_side: Which side of the `near` element: "right_of" (default), \
"below", "above", "left_of".
        size_hint: Expected size: "small", "medium" (default), "large". \
Helps the system check fit before placing.
    """
    tc: TeachingContext = ctx.userdata

    # Parse semantic elements — graceful on malformed JSON.
    elements: list[dict] = []
    if elements_json:
        try:
            elements = json.loads(elements_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("draw_scene.invalid_elements_json", raw=elements_json)

    sync_mode = _parse_timing(timing)

    # Semantic spec path: scene_type + elements takes priority.
    if scene_type and elements:
        validated_elements = [SemanticSceneElement.model_validate(e) for e in elements]
        instruction = DrawSceneInstruction(
            title=title,
            description=description,
            scene_type=scene_type,
            elements=validated_elements,
            progressive=progressive,
            zone=_parse_zone(zone),
            sync_mode=sync_mode,
        )
        instruction.placement = _build_placement(near, near_side, size_hint)
        await _publish_visual(ctx, instruction)
        if relates_to and instruction.element_id:
            _declare_relation(
                ctx,
                instruction.element_id,
                relates_to,
                relation,
                BoardRelation.ILLUSTRATES,
            )

        # Semantic specs: base 800ms + 150ms per element.
        duration_s = (800 + len(validated_elements) * 150) / 1000.0
        await asyncio.sleep(duration_s)

        # Background visual verification (at most once per concept).
        if tc.board_verifier and not tc._verified_this_concept:
            eid = instruction.element_id
            board_ctx = tc.board_manager.active_board.state.summary()
            _verify_task = asyncio.create_task(  # noqa: RUF006
                tc.board_verifier.request_verification(
                    element_id=eid,
                    concept_index=tc.current_concept_index,
                    board_context=board_ctx,
                )
            )
            tc._verified_this_concept = True
            logger.info(
                "visual_verification.fired",
                element_id=eid,
                concept=tc.current_concept_index,
            )

        label = title or description or scene_type
        return f"Drew scene: {label}"

    # Template path: existing behavior.
    params: dict[str, str | int | float | bool] = {}
    if params_json:
        try:
            params = json.loads(params_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("draw_scene.invalid_params_json", raw=params_json)

    template: SceneTemplateRef | None = None
    if template_id:
        try:
            valid_id = SceneTemplateId(template_id)
            template = SceneTemplateRef(template_id=valid_id, params=params)
        except ValueError:
            logger.warning("draw_scene.unknown_template", template_id=template_id)
            if not description:
                description = f"Scientific diagram: {template_id}"

    # Description-only fallback when neither semantic nor template provided.
    if not template and not description:
        description = "Scientific diagram"

    instruction = DrawSceneInstruction(
        title=title,
        description=description,
        template=template,
        progressive=progressive,
        zone=_parse_zone(zone),
        sync_mode=sync_mode,
    )
    instruction.placement = _build_placement(near, near_side, size_hint)
    await _publish_visual(ctx, instruction)
    if relates_to and instruction.element_id:
        _declare_relation(
            ctx, instruction.element_id, relates_to, relation, BoardRelation.ILLUSTRATES
        )

    # Sleep for estimated animation duration so the LLM doesn't talk over draw-in.
    duration_s = _SCENE_DURATION_MS.get(template_id, 1000) / 1000.0
    await asyncio.sleep(duration_s)

    # Background visual verification (at most once per concept).
    if tc.board_verifier and not tc._verified_this_concept:
        eid = instruction.element_id
        board_ctx = tc.board_manager.active_board.state.summary()
        _verify_task = asyncio.create_task(  # noqa: RUF006
            tc.board_verifier.request_verification(
                element_id=eid,
                concept_index=tc.current_concept_index,
                board_context=board_ctx,
            )
        )
        tc._verified_this_concept = True
        logger.info(
            "visual_verification.fired",
            element_id=eid,
            concept=tc.current_concept_index,
        )

    label = title or description or template_id
    return f"Drew scene: {label}"


@function_tool()
async def teach_pause(ctx: RunContext, seconds: float = 2.0) -> str:
    """Pause for a moment — let students absorb what they see on the board.

    Use this after showing a complex diagram or equation, before asking a question,
    or when you want students to think. Like a real teacher pausing at the board.

    Args:
        seconds: How long to pause, between 1 and 5 seconds. Default 2.
    """
    capped = min(max(seconds, 0.5), 5.0)
    await ctx.wait_for_playout()
    await asyncio.sleep(capped)
    logger.debug("teach.pause", duration_s=capped)
    return f"Paused {capped:.1f}s — students had time to look at the board."


# ---------------------------------------------------------------------------
# State management tools
# ---------------------------------------------------------------------------


async def _update_agent_prompt(ctx: RunContext) -> None:
    """Rebuild and set the agent's system prompt from current teaching state."""
    tc: TeachingContext = ctx.userdata
    prompt = build_teaching_prompt(tc.lesson_plan, tc)
    await ctx.session.current_agent.update_instructions(prompt)


@function_tool()
async def advance_concept(ctx: RunContext) -> str:
    """Signal that you've finished teaching the current concept and are ready to move on.

    Call this when the class has understood the current concept and you're ready
    for the next one. Returns information about the next concept to teach.
    """
    tc: TeachingContext = ctx.userdata

    if tc.lesson_plan is None:
        return "No lesson plan — teaching in free-form mode."

    next_concept = tc.advance()

    # Reset verification guard for the new concept.
    tc._verified_this_concept = False

    if next_concept is not None:
        # Create a new board for the next concept.
        branch = tc.state_machine.current
        new_board = tc.board_manager.create_and_switch(next_concept.title, branch.id)
        await _publish_switch_board(ctx, new_board.id, new_board.label, BoardIntent.NEW)

        # Detect teaching scenario and pre-plan board layout.
        scenario = detect_scenario(
            next_concept.description,
            next_concept.visual_suggestions,
        )
        board_state = new_board.state
        board_state.scenario_plan = plan_scenario(scenario, board_state.spatial_solver)
        logger.info(
            "scenario.planned",
            scenario=scenario.value,
            slots=len(board_state.scenario_plan.slots),
            concept=next_concept.title,
        )

        # Evict stale anticipation cache entries (concepts we've passed).
        new_index = tc.current_concept_index
        tc.anticipation.evict_before(new_index)

        # Pre-generate design diagrams for upcoming concepts.
        _warm_task = asyncio.create_task(  # noqa: RUF006
            tc.anticipation.warm(
                tc.lesson_plan,
                start=new_index + 1,
                count=2,
                curriculum=tc.curriculum,
            )
        )

        # Ensure the current concept has a plan, and pre-plan the next one.
        # Usually new_index is already planned (fired during the previous concept)
        # but if the teacher advanced fast or planning failed, handle it here.
        # Each plan receives the previous plan for narrative continuity.
        if tc.curriculum and tc.lesson_plan:
            from feynman.agent.concept_planner import plan_concept

            async def _ensure_plans() -> None:
                for idx in (new_index, new_index + 1):
                    if idx < tc.lesson_plan.total_concepts and idx not in tc.concept_plans:
                        result = await plan_concept(
                            idx,
                            tc.curriculum,
                            tc.lesson_plan,
                            board_summary=tc.board_manager.summary(),
                            audit=tc.audit,
                            prev_plan=tc.concept_plans.get(idx - 1),
                        )
                        if result:
                            tc.concept_plans[idx] = result
                # If the current concept's plan just arrived, rebuild the prompt.
                if new_index in tc.concept_plans:
                    await _update_agent_prompt(ctx)

            asyncio.create_task(_ensure_plans())  # noqa: RUF006

    # Log audit checkpoint at each concept advance.
    logger.info(
        "session_audit.checkpoint",
        concept=tc.current_concept_index,
        report=tc.audit.summary(),
    )
    logger.info("session_audit.checkpoint_text", report=tc.audit.summary_text())

    await _update_agent_prompt(ctx)

    if next_concept is None:
        logger.info("lesson.complete", session_id=str(tc.session_id))
        logger.info(
            "session_audit.final",
            session_id=str(tc.session_id),
            report=tc.audit.summary(),
        )
        logger.info("session_audit.final_text", report=tc.audit.summary_text())
        return (
            "All concepts covered! Summarize the key takeaways from today's lesson, "
            "ask if there are any final questions, and wrap up."
        )

    logger.info(
        "concept.advanced",
        session_id=str(tc.session_id),
        concept=next_concept.title,
        progress=tc.progress_summary,
    )
    return (
        f"Moving to: {next_concept.title}\n"
        f"Description: {next_concept.description}\n"
        f"Key points: {', '.join(next_concept.key_points)}\n"
        f"Visual suggestions: {', '.join(next_concept.visual_suggestions)}"
    )


@function_tool()
async def start_doubt_branch(ctx: RunContext, related_concept: str) -> str:
    """A student has a doubt — branch off to address it without losing your place.

    Args:
        related_concept: Brief description of what the doubt is about (e.g., "why negative times negative is positive").
    """
    tc: TeachingContext = ctx.userdata

    # Capture the parent branch id BEFORE the push — orchestrator's snapshot
    # needs it, and `tc.state_machine.current` becomes the new doubt branch
    # the moment `push_branch` returns.
    parent_branch_id = tc.state_machine.current.id

    branch = await tc.state_machine.push_branch(concept=related_concept)

    # Push a new board for the doubt — current board goes on stack.
    new_board = tc.board_manager.push_board(f"Doubt: {related_concept}", branch.id)
    await _publish_switch_board(ctx, new_board.id, new_board.label, BoardIntent.NEW)

    # Snapshot parent state and register the doubt branch with the orchestrator.
    # Checklist starts empty here; the async `_plan_doubt` below populates it
    # once the planning agent has produced a checklist.
    await tc.doubt_orchestrator.on_push(
        branch,
        related_concept,
        parent_branch_id=parent_branch_id,
    )
    # Doubt board starts visually blank — the parent's overlays were captured
    # in the snapshot and will be replayed on resume.
    tc.active_highlights.clear()
    tc.active_annotations.clear()

    # Fire background visual generation for the doubt.
    parent = tc.current_concept
    board_summary = tc.board_manager.active_board.state.summary()
    _doubt_warm = asyncio.create_task(  # noqa: RUF006
        tc.anticipation.warm_doubt(
            related_concept,
            board_summary=board_summary,
            parent_concept=parent.title if parent else "",
        )
    )

    # Fire background doubt planning. Once the plan lands, push its checklist
    # into the orchestrator so resolution gating reflects the real plan.
    if tc.curriculum:
        from feynman.agent.concept_planner import plan_doubt

        async def _plan_doubt() -> None:
            result = await plan_doubt(
                related_concept,
                parent_concept=parent.title if parent else "",
                board_summary=board_summary,
                curriculum=tc.curriculum,
                audit=tc.audit,
            )
            if result:
                tc.doubt_plan = result
                state = tc.doubt_orchestrator.get_state(branch.id)
                if state is not None and result.resolution_checklist:
                    state.checklist = list(result.resolution_checklist)
                    branch.checklist = state.checklist
                    logger.info(
                        "doubt.checklist_loaded",
                        branch_id=str(branch.id),
                        items=len(state.checklist),
                    )
                await _update_agent_prompt(ctx)

        asyncio.create_task(_plan_doubt())  # noqa: RUF006

    await _update_agent_prompt(ctx)

    logger.info(
        "doubt.started",
        session_id=str(tc.session_id),
        branch_id=str(branch.id),
        concept=related_concept,
        depth=tc.state_machine.depth,
    )
    return (
        f"Doubt branch opened about: {related_concept}\n"
        f"Address this thoroughly. When done, call resolve_doubt() to return to the main lesson."
    )


@function_tool()
async def resolve_doubt(ctx: RunContext) -> str:
    """The doubt has been addressed — return to the main lesson flow.

    Call this after you've fully answered the student's question and
    are ready to continue where you left off.
    """
    from feynman.common.exceptions import ToolConstraintError

    tc: TeachingContext = ctx.userdata

    if tc.state_machine.depth <= 1:
        return "Not in a doubt branch — already on the main lesson flow."

    # Gate on the resolution checklist BEFORE we touch any state. The orchestrator
    # returns a clear message listing pending items so the LLM can either address
    # them or invoke mark_doubt_step_complete to override.
    current_branch = tc.state_machine.current
    allowed, reason = tc.doubt_orchestrator.is_resolution_allowed(current_branch.id)
    if not allowed:
        raise ToolConstraintError(reason)

    # Pop board stack before popping branch — return to parent board.
    tc.board_manager.pop_board()
    parent_board = tc.board_manager.active_board
    await _publish_switch_board(ctx, parent_board.id, parent_board.label, BoardIntent.REVISIT)

    popped = await tc.state_machine.pop_branch()
    tc.anticipation.clear_doubt_cache()
    tc.doubt_plan = None
    # Diagram awareness: parent board's diagram (if any) needs its own
    # dictionary; the doubt-branch dictionary no longer applies.
    tc.current_diagram_dictionary = {}

    # Auto-restore parent state via the orchestrator: re-fire highlight pulses
    # for every captured target and surface the verbatim return cue. No LLM
    # call required — both side effects run through callbacks supplied here.
    async def _replay_pulse(instr: _BaseInstruction) -> None:
        await _publish_visual(ctx, instr, wait_for_speech=False)

    async def _say_return_cue(text: str) -> None:
        say_fn = getattr(ctx.session, "say", None)
        if say_fn is not None:
            try:
                result = say_fn(text, allow_interruptions=False)
                if asyncio.iscoroutine(result):
                    await result
                return
            except TypeError:
                # Older signature without `allow_interruptions`; retry plain.
                result = say_fn(text)
                if asyncio.iscoroutine(result):
                    await result
                return
        # Fallback: instruct the LLM to emit it verbatim.
        ctx.session.generate_reply(instructions=f'Say exactly this and nothing else: "{text}"')

    await tc.doubt_orchestrator.on_pop(
        popped,
        publish_visual=_replay_pulse,
        say=_say_return_cue,
        forced=False,
    )

    await _update_agent_prompt(ctx)

    current = tc.current_concept
    continue_msg = f"Continue teaching: {current.title}" if current else "Lesson complete"

    logger.info(
        "doubt.resolved",
        session_id=str(tc.session_id),
        resolved_concept=popped.concept,
        depth=tc.state_machine.depth,
    )
    logger.info(
        "session_audit.doubt_resolved",
        report=tc.audit.summary_text(),
    )
    return f"Doubt about '{popped.concept}' resolved. {continue_msg}"


@function_tool()
async def mark_doubt_step_complete(ctx: RunContext, step_index: int) -> str:
    """Manually tick a resolution-checklist item that auto-tick missed.

    Use this only when you've actually addressed a checklist item but no
    auto-tick fired (e.g., the answer was purely verbal with no matching
    tool call). Calling this on items the agent hasn't actually addressed
    defeats the purpose of the gate — be honest with yourself.

    Args:
        step_index: 0-based index into the active doubt's resolution checklist.
    """
    from feynman.common.exceptions import ToolConstraintError

    tc: TeachingContext = ctx.userdata
    if tc.state_machine.depth <= 1:
        raise ToolConstraintError("Not in a doubt branch — no checklist to tick.")
    branch_id = tc.state_machine.current.id
    tc.doubt_orchestrator.mark_step_complete(branch_id, step_index)
    state = tc.doubt_orchestrator.get_state(branch_id)
    item = state.checklist[step_index] if state else None
    return f"Marked checklist item {step_index} done" + (f": {item.description}" if item else ".")


@function_tool()
async def switch_board(ctx: RunContext, board_id: str, intent: str = "reference") -> str:
    """Switch to a different board to show previously drawn content.

    Use this to flip back to an earlier board when referencing a concept,
    or to navigate between boards.

    Args:
        board_id: The ID of the board to switch to (e.g., "board-1", "board-2").
        intent: Why you're switching. Options: "revisit" (returning to continue work), \
"reference" (quick look at earlier content). Default: "reference".
    """
    tc: TeachingContext = ctx.userdata

    board = tc.board_manager.get_board(board_id)
    if board is None:
        return f"Board not found: {board_id}. Check available boards in the prompt."

    board_intent = BoardIntent(intent)
    tc.board_manager.switch_to(board_id)
    await _publish_switch_board(ctx, board_id, board.label, board_intent)
    await _update_agent_prompt(ctx)

    return f"Switched to board: {board.label} ({board_id})"


@function_tool()
async def scroll_board(
    ctx: RunContext,
    direction: str = "",
    element_id: str = "",
) -> str:
    """Scroll the board to reveal new space or return to earlier content.

    The board is an infinite canvas. You see a 1920x1080 viewport at a time.
    Use this when the visible area is filling up and you need fresh space,
    or when you want to reference/show something drawn earlier.

    Args:
        direction: Scroll direction — "right", "left", "down", "up". \
Moves the viewport by one full screen in that direction.
        element_id: Instead of a direction, scroll to center a specific element \
on screen. Pass the element's ID (e.g., "diagram-3").
    """
    tc: TeachingContext = ctx.userdata
    board_state = tc.board_manager.active_board.state

    if element_id:
        tile = board_state.element_tile(element_id)
        if tile is None:
            return f"Element not found: {element_id}"
        board_state.scroll_to_tile(tile[0], tile[1])
    elif direction:
        dx, dy = {
            "right": (1, 0),
            "left": (-1, 0),
            "down": (0, 1),
            "up": (0, -1),
        }.get(direction.lower(), (0, 0))
        if dx == 0 and dy == 0:
            return f"Unknown direction: {direction}. Use right, left, down, or up."
        new_x = max(0, board_state.camera_tile_x + dx)
        new_y = max(0, board_state.camera_tile_y + dy)
        board_state.scroll_to_tile(new_x, new_y)
    else:
        return "Provide either a direction or element_id."

    # Publish scroll instruction to frontend.
    scroll_instr = ScrollViewInstruction(
        target_x=board_state.camera_tile_x,
        target_y=board_state.camera_tile_y,
    )
    scroll_instr.board_id = tc.board_manager.active_id
    _stamp_panel(scroll_instr)
    room = ctx.session.room_io.room
    data = json.dumps(scroll_instr.model_dump(exclude_none=True, by_alias=True))
    await room.local_participant.publish_data(data, reliable=True, topic="visuals")

    # Rebuild prompt so agent sees updated board state.
    await _update_agent_prompt(ctx)

    visible_count = len(board_state.visible_elements())
    total_count = len(board_state._elements)
    tile_pos = f"({board_state.camera_tile_x}, {board_state.camera_tile_y})"

    tc.audit.record(
        "scroll",
        "viewport_moved",
        f"tile={tile_pos}, visible={visible_count}, total={total_count}",
    )

    return (
        f"Scrolled to tile {tile_pos}. "
        f"{visible_count} elements visible, {total_count} total on board. "
        f"Free zones: {', '.join(z.value for z in sorted(board_state.visible_free_zones()))}"
    )


# ---------------------------------------------------------------------------
# Dynamic lesson plan from spoken topic
# ---------------------------------------------------------------------------


@function_tool()
async def set_lesson_topic(
    ctx: RunContext,
    topic: str,
    subject: str = "",
    grade_level: str = "",
) -> str:
    """Activate structured teaching for a topic the student requested.

    Call this when a student asks to learn about a specific topic
    (e.g., "I want to learn about simple harmonic motion").
    This generates a full lesson plan with visual aids and concept sequencing.

    Args:
        topic: The topic to teach (e.g., "Simple Harmonic Motion").
        subject: Optional subject area — "physics", "chemistry", "biology", "math".
        grade_level: Optional grade level (e.g., "Class 11", "Grade 10").
    """
    from feynman.agent.curriculum_loader import load_curriculum
    from feynman.agent.lesson_plan import lesson_plan_from_curriculum
    from feynman.common.types import Subject

    tc: TeachingContext = ctx.userdata

    # Reset state for the new topic.
    tc.reset_for_new_topic()
    tc.anticipation.evict_all()

    parsed_subject: Subject | None = None
    if subject:
        with contextlib.suppress(ValueError):
            parsed_subject = Subject(subject.lower())

    tc.audit.record(
        "curriculum",
        "set_lesson_topic",
        f"topic='{topic}', subject={subject or 'auto'}, grade={grade_level or 'auto'}",
        source="spoken_request",
    )

    # Load curriculum from Neo4j — no fallbacks.
    # Raises CurriculumNotFoundError if topic not in Neo4j.
    curriculum = await load_curriculum(topic, subject or None)
    tc.curriculum = curriculum

    plan = lesson_plan_from_curriculum(
        curriculum,
        grade_level=grade_level,
        subject=parsed_subject,
    )
    logger.info(
        "set_lesson_topic.loaded_from_neo4j",
        topic=topic,
        chapter=curriculum.chapter_title,
        concepts=len(curriculum.concepts),
        visuals=len(curriculum.pre_generated_visuals),
    )

    # --- COMMENTED OUT: Old fallback paths. ---
    # Previously: graph = await load_concept_graph(topic)
    # if graph: plan = lesson_plan_from_graph(...)
    # else: plan = await generate_lesson_plan(...)  # runtime LLM fallback
    # Now: CurriculumNotFoundError propagates if topic not in Neo4j.
    # --- END COMMENTED OUT ---

    tc.lesson_plan = plan

    # Label the active board with the first concept.
    first_concept = plan.concept_at(0)
    if first_concept:
        tc.board_manager.active_board.label = first_concept.title

    # Fire anticipation pre-generation for first 3 concepts.
    # With pre-generated visuals from Neo4j, many will be instant cache hits.
    warm_task = asyncio.create_task(
        tc.anticipation.warm(
            plan,
            start=0,
            count=3,
            curriculum=tc.curriculum,
        )
    )
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(asyncio.shield(warm_task), timeout=5.0)
    tc._warm_task = warm_task

    # Refresh the system prompt with the full lesson context.
    # Now includes pre-rendered visuals if warming completed in time.
    await _update_agent_prompt(ctx)

    logger.info(
        "set_lesson_topic.ready",
        topic=plan.topic,
        num_concepts=plan.total_concepts,
        source="curriculum",
    )

    # Return summary for the agent to narrate.
    parts = [
        f"Lesson plan ready for '{plan.topic}'.",
        f"Objective: {plan.objective}",
        f"{plan.total_concepts} concepts to cover.",
    ]
    if first_concept:
        parts.append(f"Start with: {first_concept.title}")
    return " ".join(parts)
