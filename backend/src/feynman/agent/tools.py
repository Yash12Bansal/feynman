"""LLM function tools — visual instructions + teaching state management."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
from livekit.agents import RunContext, function_tool

from feynman.agent.prompts import build_teaching_prompt

if TYPE_CHECKING:
    from feynman.agent.teaching_context import TeachingContext

from feynman.visuals.schemas import (
    AxisConfig,
    ClearInstruction,
    DataSeries,
    DiagramEdge,
    DiagramNode,
    DiagramType,
    DrawDiagramInstruction,
    EquationAnimation,
    EquationStep,
    FunctionDef,
    GraphType,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    StepEquationInstruction,
    SyncMode,
    TermSyncHint,
    _BaseInstruction,
)

logger = structlog.get_logger()


async def _publish_visual(
    ctx: RunContext,
    instruction: _BaseInstruction,
    *,
    wait_for_speech: bool = True,
) -> None:
    if wait_for_speech:
        try:
            await ctx.wait_for_playout()
        except Exception:
            logger.warning("visual.playout_wait_failed", type=instruction.type, exc_info=True)

    room = ctx.session.room_io.room
    data = json.dumps(instruction.model_dump(exclude_none=True))
    await room.local_participant.publish_data(data, reliable=True, topic="visuals")
    logger.debug("visual.published", type=instruction.type)


@function_tool()
async def show_text(ctx: RunContext, text: str, title: str = "") -> str:
    """Display text on the classroom screen. Use for key points, definitions, important info.

    Args:
        text: The text content to display on the board.
        title: Optional heading for the text block.
    """
    instruction = ShowTextInstruction(text=text, title=title)
    await _publish_visual(ctx, instruction)
    return f"Displayed on board: {text[:80]}"


@function_tool()
async def show_equation(
    ctx: RunContext,
    latex: str,
    label: str = "",
    animation: str = "fade_in",
    term_hints_json: str = "",
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
    )
    await _publish_visual(ctx, instruction)
    return f"Drew diagram: {title or description or diagram_type}"


@function_tool()
async def step_equation(ctx: RunContext, steps_json: str, title: str = "") -> str:
    """Show a step-by-step equation solve on the classroom screen. Perfect for walking through algebra, simplification, or any multi-step derivation.

    Args:
        steps_json: A JSON array of step objects. Each step has:
            - "latex" (required): The equation at this step in LaTeX.
            - "annotation" (optional): What was done (e.g., "Subtract 4 from both sides").
            - "highlight_terms" (optional): List of htmlId refs for changed terms.
            Example: [{"latex": "2x + 4 = 10"}, {"latex": "2x = 6", "annotation": "Subtract 4 from both sides"}]
        title: Optional heading (e.g., "Solving for x").
    """
    raw_steps = json.loads(steps_json)
    steps = [EquationStep(**s) for s in raw_steps]
    instruction = StepEquationInstruction(title=title, steps=steps)
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
    )
    await _publish_visual(ctx, instruction)
    return f"Displayed graph: {title or graph_type}"


@function_tool()
async def clear_board(ctx: RunContext) -> str:
    """Clear everything from the classroom screen to start fresh."""
    instruction = ClearInstruction(sync_mode=SyncMode.IMMEDIATE)
    await _publish_visual(ctx, instruction, wait_for_speech=False)
    return "Board cleared"


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
