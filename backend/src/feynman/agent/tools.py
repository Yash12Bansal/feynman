"""LLM function tools for visual instructions via LiveKit data channel."""

import json

import structlog
from livekit.agents import RunContext, function_tool

from feynman.visuals.schemas import (
    ClearInstruction,
    DiagramEdge,
    DiagramNode,
    DiagramType,
    DrawDiagramInstruction,
    EquationAnimation,
    EquationStep,
    ShowEquationInstruction,
    ShowTextInstruction,
    StepEquationInstruction,
    _BaseInstruction,
)

logger = structlog.get_logger()


async def _publish_visual(ctx: RunContext, instruction: _BaseInstruction) -> None:
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
    ctx: RunContext, latex: str, label: str = "", animation: str = "fade_in"
) -> str:
    """Display a math equation on the classroom screen. Use LaTeX notation.

    Args:
        latex: The equation in LaTeX format (e.g., "E = mc^2", "\\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}").
            Use \\htmlId{term-1}{content} to tag individual terms for term_by_term animation.
        label: Optional label (e.g., "Newton's Second Law").
        animation: How the equation appears. Options: "none", "fade_in" (default), "term_by_term", "write_on".
    """
    eq_animation = EquationAnimation(animation)
    instruction = ShowEquationInstruction(latex=latex, label=label, animation=eq_animation)
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
async def clear_board(ctx: RunContext) -> str:
    """Clear everything from the classroom screen to start fresh."""
    instruction = ClearInstruction()
    await _publish_visual(ctx, instruction)
    return "Board cleared"
