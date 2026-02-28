"""LLM function tools for visual instructions via LiveKit data channel."""

import json

import structlog
from livekit.agents import RunContext, function_tool

from feynman.visuals.schemas import (
    ClearInstruction,
    DrawDiagramInstruction,
    EquationAnimation,
    ShowEquationInstruction,
    ShowTextInstruction,
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
async def clear_board(ctx: RunContext) -> str:
    """Clear everything from the classroom screen to start fresh."""
    instruction = ClearInstruction()
    await _publish_visual(ctx, instruction)
    return "Board cleared"
