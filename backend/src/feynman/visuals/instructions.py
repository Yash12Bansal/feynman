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
    AnnotateInstruction,
    BoardZone,
    ClearInstruction,
    DrawDesignDiagramInstruction,
    DrawDiagramInstruction,
    DrawSceneInstruction,
    HighlightInstruction,
    HighlightWalkInstruction,
    NewPageInstruction,
    Panel,
    PlacementIntent,
    ScrollViewInstruction,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    SizeHint,
    SlidePendingInstruction,
    StepEquationInstruction,
    StrikethroughInstruction,
    SwitchBoardInstruction,
    WriteAnswerInstruction,
    WriteEquationInstruction,
    WriteSectionInstruction,
    WriteStepInstruction,
    WriteTextInstruction,
)

VisualInstruction = Annotated[
    ClearInstruction
    | ShowTextInstruction
    | ShowEquationInstruction
    | StepEquationInstruction
    | DrawDiagramInstruction
    | DrawDesignDiagramInstruction
    | DrawSceneInstruction
    | ShowGraphInstruction
    | HighlightInstruction
    | AnnotateInstruction
    | HighlightWalkInstruction
    | SwitchBoardInstruction
    | ScrollViewInstruction
    | SlidePendingInstruction
    | WriteEquationInstruction
    | WriteStepInstruction
    | WriteTextInstruction
    | WriteSectionInstruction
    | WriteAnswerInstruction
    | StrikethroughInstruction
    | NewPageInstruction,
    Discriminator("type"),
]

__all__ = [
    "AnnotateInstruction",
    "BoardZone",
    "ClearInstruction",
    "DrawDesignDiagramInstruction",
    "DrawDiagramInstruction",
    "DrawSceneInstruction",
    "HighlightInstruction",
    "HighlightWalkInstruction",
    "NewPageInstruction",
    "Panel",
    "PlacementIntent",
    "ScrollViewInstruction",
    "ShowEquationInstruction",
    "ShowGraphInstruction",
    "ShowTextInstruction",
    "SizeHint",
    "SlidePendingInstruction",
    "StepEquationInstruction",
    "StrikethroughInstruction",
    "SwitchBoardInstruction",
    "VisualInstruction",
    "WriteAnswerInstruction",
    "WriteEquationInstruction",
    "WriteSectionInstruction",
    "WriteStepInstruction",
    "WriteTextInstruction",
]
