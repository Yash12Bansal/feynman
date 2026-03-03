"""LLM function tools — visual instructions + teaching state management."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog
from livekit.agents import RunContext, function_tool

from feynman.agent.prompts import build_teaching_prompt

if TYPE_CHECKING:
    from feynman.agent.teaching_context import TeachingContext

from feynman.visuals.schemas import (
    AnnotateInstruction,
    AnnotationAction,
    AxisConfig,
    BoardIntent,
    BoardZone,
    ClearInstruction,
    DataSeries,
    DiagramEdge,
    DiagramNode,
    DiagramType,
    DrawDiagramInstruction,
    DrawSceneInstruction,
    EquationAnimation,
    EquationStep,
    FunctionDef,
    GraphType,
    SceneTemplateId,
    SceneTemplateRef,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    StepEquationInstruction,
    SwitchBoardInstruction,
    SyncMode,
    TermSyncHint,
    _BaseInstruction,
)

logger = structlog.get_logger()

# Instruction types that skip auto-ID assignment.
_NO_AUTO_ID_TYPES = frozenset({"clear", "highlight", "annotate"})


def _parse_zone(zone: str) -> BoardZone | None:
    """Parse a zone string from the LLM, returning None on invalid input."""
    if not zone:
        return None
    try:
        return BoardZone(zone)
    except ValueError:
        logger.warning("visual.invalid_zone", zone=zone)
        return None


async def _publish_visual(
    ctx: RunContext,
    instruction: _BaseInstruction,
    *,
    wait_for_speech: bool = True,
) -> None:
    # Auto-assign element_id if not already set and type supports it.
    tc: TeachingContext = ctx.userdata
    if instruction.element_id is None and instruction.type not in _NO_AUTO_ID_TYPES:
        instruction.element_id = tc.board_manager.next_id(instruction.type)

    # Stamp active board ID on the instruction for frontend context.
    instruction.board_id = tc.board_manager.active_id

    if wait_for_speech:
        try:
            await ctx.wait_for_playout()
        except Exception:
            logger.warning("visual.playout_wait_failed", type=instruction.type, exc_info=True)

    room = ctx.session.room_io.room
    data = json.dumps(instruction.model_dump(exclude_none=True))
    await room.local_participant.publish_data(data, reliable=True, topic="visuals")
    logger.debug(
        "visual.published",
        type=instruction.type,
        element_id=instruction.element_id,
        zone=str(instruction.zone) if instruction.zone else None,
        board_id=instruction.board_id,
    )

    # Record the instruction's effect on the board state.
    tc.board_manager.record(instruction)


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
    room = ctx.session.room_io.room
    data = json.dumps(instruction.model_dump(exclude_none=True))
    await room.local_participant.publish_data(data, reliable=True, topic="visuals")
    logger.debug(
        "visual.switch_board",
        board_id=board_id,
        label=label,
        intent=intent,
    )


@function_tool()
async def show_text(ctx: RunContext, text: str, title: str = "", zone: str = "") -> str:
    """Display text on the classroom screen. Use for key points, definitions, important info.

    Args:
        text: The text content to display on the board.
        title: Optional heading for the text block.
        zone: Board zone for placement. Options: "top-left", "top-center", "top-right", \
"center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right". \
Leave empty for default placement.
    """
    instruction = ShowTextInstruction(text=text, title=title, zone=_parse_zone(zone))
    await _publish_visual(ctx, instruction)
    return f"Displayed on board: {text[:80]}"


@function_tool()
async def show_equation(
    ctx: RunContext,
    latex: str,
    label: str = "",
    animation: str = "fade_in",
    term_hints_json: str = "",
    zone: str = "",
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
        zone: Board zone for placement. Options: "top-left", "top-center", "top-right", \
"center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right". \
Leave empty for default placement.
    """
    eq_animation = EquationAnimation(animation)
    term_hints = None
    sync_mode = SyncMode.ON_PLAYOUT
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
    await _publish_visual(ctx, instruction)
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
        zone: Board zone for placement. Options: "top-left", "top-center", "top-right", \
"center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right". \
Leave empty for default placement.
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
    )
    await _publish_visual(ctx, instruction)
    return f"Drew diagram: {title or description or diagram_type}"


@function_tool()
async def step_equation(ctx: RunContext, steps_json: str, title: str = "", zone: str = "") -> str:
    """Show a step-by-step equation solve on the classroom screen. Perfect for walking through algebra, simplification, or any multi-step derivation.

    Args:
        steps_json: A JSON array of step objects. Each step has:
            - "latex" (required): The equation at this step in LaTeX.
            - "annotation" (optional): What was done (e.g., "Subtract 4 from both sides").
            - "highlight_terms" (optional): List of htmlId refs for changed terms.
            Example: [{"latex": "2x + 4 = 10"}, {"latex": "2x = 6", "annotation": "Subtract 4 from both sides"}]
        title: Optional heading (e.g., "Solving for x").
        zone: Board zone for placement. Options: "top-left", "top-center", "top-right", \
"center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right". \
Leave empty for default placement.
    """
    raw_steps = json.loads(steps_json)
    steps = [EquationStep(**s) for s in raw_steps]
    instruction = StepEquationInstruction(title=title, steps=steps, zone=_parse_zone(zone))
    await _publish_visual(ctx, instruction)
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
        zone: Board zone for placement. Options: "top-left", "top-center", "top-right", \
"center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right". \
Leave empty for default placement.
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
    )
    await _publish_visual(ctx, instruction)
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
    if ann_action == AnnotationAction.ARROW:
        return f"Drew arrow from {from_id} to {to_id}"
    return f"Drew {action} on {target_id}"


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
    return "Board cleared"


# Animation duration estimates (ms) per scene template.
# Derived from GSAP timeline: ~0.4s/path + 0.06s stagger + 0.25s/label.
_SCENE_DURATION_MS: dict[str, int] = {
    "free_body": 1200,
    "double_slit": 1500,
}


@function_tool()
async def draw_scene(
    ctx: RunContext,
    template_id: str,
    title: str = "",
    description: str = "",
    params_json: str = "",
    progressive: bool = True,
    zone: str = "",
) -> str:
    """Draw a scientific diagram on the classroom screen — physics apparatus, optics setups, etc.

    These are hand-drawn, spatially precise diagrams. Use draw_scene for physics/science
    illustrations where spatial accuracy matters (force diagrams, optics). Use draw_diagram
    for abstract relationships (flowcharts, concept maps).

    Args:
        template_id: Scene template. Available:
            - "free_body": Forces on an object. Params: showWeight, showNormal,
              showFriction, showApplied, showSpring (all bool).
            - "double_slit": Young's experiment. Params: showWaves, showPattern,
              showRays, showLabels (all bool), slitSeparation ("narrow"|"wide").
        title: Heading above the diagram.
        description: Alt-text describing what the diagram shows. Always provide this.
        params_json: JSON of template params. Example: {"showWeight": true, "showFriction": true}
        progressive: Animate drawing in progressively (default true).
        zone: Board zone ("center-left", "center-right", etc). Leave empty for default.
    """
    # Parse template params — graceful on malformed JSON.
    params: dict[str, str | int | float | bool] = {}
    if params_json:
        try:
            params = json.loads(params_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("draw_scene.invalid_params_json", raw=params_json)

    # Validate template_id against known enum — fallback to description-only.
    template: SceneTemplateRef | None = None
    try:
        valid_id = SceneTemplateId(template_id)
        template = SceneTemplateRef(template_id=valid_id, params=params)
    except ValueError:
        logger.warning("draw_scene.unknown_template", template_id=template_id)
        if not description:
            description = f"Scientific diagram: {template_id}"

    instruction = DrawSceneInstruction(
        title=title,
        description=description,
        template=template,
        progressive=progressive,
        zone=_parse_zone(zone),
    )
    await _publish_visual(ctx, instruction)

    # Sleep for estimated animation duration so the LLM doesn't talk over draw-in.
    duration_s = _SCENE_DURATION_MS.get(template_id, 1000) / 1000.0
    await asyncio.sleep(duration_s)

    label = title or description or template_id
    return f"Drew scene: {label}"


# ---------------------------------------------------------------------------
# State management tools
# ---------------------------------------------------------------------------


async def _update_agent_prompt(ctx: RunContext) -> None:
    """Rebuild and set the agent's system prompt from current teaching state."""
    tc: TeachingContext = ctx.userdata
    prompt = build_teaching_prompt(tc.lesson_plan, tc)
    ctx.session.current_agent.update_instructions(prompt)


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

    if next_concept is not None:
        # Create a new board for the next concept.
        branch = tc.state_machine.current
        new_board = tc.board_manager.create_and_switch(next_concept.title, branch.id)
        await _publish_switch_board(ctx, new_board.id, new_board.label, BoardIntent.NEW)

    await _update_agent_prompt(ctx)

    if next_concept is None:
        logger.info("lesson.complete", session_id=str(tc.session_id))
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

    branch = await tc.state_machine.push_branch(concept=related_concept)

    # Push a new board for the doubt — current board goes on stack.
    new_board = tc.board_manager.push_board(f"Doubt: {related_concept}", branch.id)
    await _publish_switch_board(ctx, new_board.id, new_board.label, BoardIntent.NEW)

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
    tc: TeachingContext = ctx.userdata

    if tc.state_machine.depth <= 1:
        return "Not in a doubt branch — already on the main lesson flow."

    # Pop board stack before popping branch — return to parent board.
    tc.board_manager.pop_board()
    parent_board = tc.board_manager.active_board
    await _publish_switch_board(ctx, parent_board.id, parent_board.label, BoardIntent.REVISIT)

    popped = await tc.state_machine.pop_branch()
    await _update_agent_prompt(ctx)

    current = tc.current_concept
    continue_msg = f"Continue teaching: {current.title}" if current else "Lesson complete"

    logger.info(
        "doubt.resolved",
        session_id=str(tc.session_id),
        resolved_concept=popped.concept,
        depth=tc.state_machine.depth,
    )
    return f"Doubt about '{popped.concept}' resolved. {continue_msg}"


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
