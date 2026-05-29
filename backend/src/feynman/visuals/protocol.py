# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# """Backend-Frontend visual protocol.

# Defines the framing for streaming visual instructions from the backend
# to the frontend over the LiveKit data channel (topic="visuals").

# Currently, individual instructions are published directly (not batched
# into frames). The VisualFrame type is defined for future batching support.
# """

# from __future__ import annotations

# from pydantic import BaseModel

# from feynman.visuals.instructions import VisualInstruction


# class VisualFrame(BaseModel):
#     """A batch of visual instructions (for future batching support)."""

#     sequence: int
#     instructions: list[VisualInstruction]
