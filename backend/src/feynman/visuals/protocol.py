"""Backend↔Frontend visual contract.

Defines the protocol for streaming visual instructions from the backend
to the frontend. The frontend renders these instructions on the classroom screen.
"""

from __future__ import annotations

from pydantic import BaseModel

from feynman.visuals.instructions import VisualInstruction


class VisualFrame(BaseModel):
    """A frame of visual instructions sent over WebSocket."""

    sequence: int
    instructions: list[VisualInstruction]
