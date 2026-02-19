"""Visual instruction models — typed commands sent to frontend."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class VisualType(StrEnum):
    """Types of visual instructions the backend can send."""

    CLEAR = "clear"
    DRAW_DIAGRAM = "draw_diagram"
    SHOW_EQUATION = "show_equation"
    SHOW_TEXT = "show_text"
    SHOW_GRAPH = "show_graph"
    ANIMATE = "animate"
    HIGHLIGHT = "highlight"


class VisualInstruction(BaseModel):
    """A single visual instruction to be rendered by the frontend."""

    type: VisualType
    payload: dict[str, Any] = {}
    duration_ms: int | None = None
