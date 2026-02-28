"""LLM function tools for visual instructions via LiveKit data channel."""

import json

import structlog
from livekit.agents import RunContext, function_tool

from feynman.visuals.schemas import (
    ClearInstruction,
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
async def draw_diagram(ctx: RunContext, description: str) -> str:
    """Draw a diagram on the classroom screen to illustrate a concept.

    Args:
        description: What the diagram shows (e.g., "Free body diagram of a block on an incline").
    """
    instruction = DrawDiagramInstruction(description=description)
    await _publish_visual(ctx, instruction)
    return f"Drew diagram: {description}"


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
