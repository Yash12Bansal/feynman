"""Visual instruction models — typed commands sent to frontend.

The `VisualInstruction` type is a discriminated union of all visual instruction
schemas, tagged by the `type` field. Pydantic automatically routes deserialization
to the correct model based on the type tag.

Wire format is flattened — no nested `payload` dict:
    {"type": "show_equation", "latex": "E = mc^2", "label": "Einstein"}

This replaces the previous untyped {"type": ..., "payload": dict[str, Any]} format.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Discriminator

from feynman.visuals.schemas import (
    ClearInstruction,
    DrawDiagramInstruction,
    HighlightInstruction,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    StepEquationInstruction,
)

VisualInstruction = Annotated[
    ClearInstruction
    | ShowTextInstruction
    | ShowEquationInstruction
    | StepEquationInstruction
    | DrawDiagramInstruction
    | ShowGraphInstruction
    | HighlightInstruction,
    Discriminator("type"),
]

__all__ = [
    "ClearInstruction",
    "DrawDiagramInstruction",
    "HighlightInstruction",
    "ShowEquationInstruction",
    "ShowGraphInstruction",
    "ShowTextInstruction",
    "StepEquationInstruction",
    "VisualInstruction",
]
