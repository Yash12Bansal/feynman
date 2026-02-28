"""LLM function tools for visual instructions via LiveKit data channel."""

import json

import structlog
from livekit.agents import RunContext, function_tool

from feynman.visuals.instructions import VisualInstruction, VisualType

logger = structlog.get_logger()


async def _publish_visual(ctx: RunContext, instruction: VisualInstruction) -> None:
    room = ctx.session.room_io.room
    payload = json.dumps(instruction.model_dump())
    await room.local_participant.publish_data(payload, reliable=True, topic="visuals")
    logger.debug("visual.published", type=instruction.type)


@function_tool()
async def show_text(ctx: RunContext, text: str, title: str = "") -> str:
    """Display text on the classroom screen. Use for key points, definitions, important info.

    Args:
        text: The text content to display on the board.
        title: Optional heading for the text block.
    """
    await _publish_visual(
        ctx,
        VisualInstruction(type=VisualType.SHOW_TEXT, payload={"text": text, "title": title}),
    )
    return f"Displayed on board: {text[:80]}"


@function_tool()
async def show_equation(ctx: RunContext, equation: str, label: str = "") -> str:
    """Display a math equation on the classroom screen. Use LaTeX notation.

    Args:
        equation: The equation in LaTeX format (e.g., "E = mc^2").
        label: Optional label (e.g., "Newton's Second Law").
    """
    await _publish_visual(
        ctx,
        VisualInstruction(
            type=VisualType.SHOW_EQUATION, payload={"equation": equation, "label": label}
        ),
    )
    return f"Displayed equation: {equation}"


@function_tool()
async def draw_diagram(ctx: RunContext, description: str) -> str:
    """Draw a diagram on the classroom screen to illustrate a concept.

    Args:
        description: What the diagram shows (e.g., "Free body diagram of a block on an incline").
    """
    await _publish_visual(
        ctx,
        VisualInstruction(type=VisualType.DRAW_DIAGRAM, payload={"description": description}),
    )
    return f"Drew diagram: {description}"


@function_tool()
async def clear_board(ctx: RunContext) -> str:
    """Clear everything from the classroom screen to start fresh."""
    await _publish_visual(ctx, VisualInstruction(type=VisualType.CLEAR, payload={}))
    return "Board cleared"
