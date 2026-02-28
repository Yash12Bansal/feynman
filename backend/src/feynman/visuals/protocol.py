"""Backend-Frontend visual protocol.

Defines the framing for streaming visual instructions from the backend
to the frontend over the LiveKit data channel (topic="visuals").

Currently, individual instructions are published directly (not batched
into frames). The VisualFrame type is defined for future batching support.
"""

from __future__ import annotations

from pydantic import BaseModel

from feynman.visuals.instructions import VisualInstruction


class VisualFrame(BaseModel):
    """A batch of visual instructions (for future batching support)."""

    sequence: int
    instructions: list[VisualInstruction]
