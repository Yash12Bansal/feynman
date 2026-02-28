"""Visual instruction engine — typed commands for the frontend renderer."""

from feynman.visuals.instructions import VisualInstruction
from feynman.visuals.schemas import (
    ClearInstruction,
    DrawDiagramInstruction,
    HighlightInstruction,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
)

__all__ = [
    "ClearInstruction",
    "DrawDiagramInstruction",
    "HighlightInstruction",
    "ShowEquationInstruction",
    "ShowGraphInstruction",
    "ShowTextInstruction",
    "VisualInstruction",
]
