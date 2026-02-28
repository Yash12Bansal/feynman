"""Typed visual instruction schemas — one model per visual type.

Every visual instruction the backend can send to the frontend is defined here
as a Pydantic model with a Literal type tag. The union of all instruction types
forms the `VisualInstruction` discriminated union in instructions.py.

Design:
- Flattened (no nested `payload` dict) — type tag + fields at the same level.
- Each instruction carries optional `element_id` for incremental rendering identity
  and `duration_ms` for animation timing.
- Forward-looking fields (e.g., animation metadata) are defined now with sensible
  defaults so they're ready for phases 2-6 without schema changes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, model_validator

# ──────────────────────────────────────────────
# Shared enums
# ──────────────────────────────────────────────


class TextStyle(StrEnum):
    DEFAULT = "default"
    DEFINITION = "definition"
    KEY_POINT = "key_point"
    EXAMPLE = "example"


class EquationAnimation(StrEnum):
    NONE = "none"
    FADE_IN = "fade_in"
    TERM_BY_TERM = "term_by_term"
    WRITE_ON = "write_on"


class DiagramType(StrEnum):
    FLOWCHART = "flowchart"
    CONCEPT_MAP = "concept_map"
    FORCE_DIAGRAM = "force_diagram"
    TREE = "tree"
    CYCLE = "cycle"
    COMPARISON = "comparison"
    FREE_FORM = "free_form"


class NodeShape(StrEnum):
    RECTANGLE = "rectangle"
    ROUNDED = "rounded"
    CIRCLE = "circle"
    DIAMOND = "diamond"
    ELLIPSE = "ellipse"


class EdgeStyle(StrEnum):
    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"


class GraphType(StrEnum):
    LINE = "line"
    BAR = "bar"
    SCATTER = "scatter"
    FUNCTION = "function"


class HighlightStyle(StrEnum):
    GLOW = "glow"
    UNDERLINE = "underline"
    BOX = "box"
    PULSE = "pulse"


# ──────────────────────────────────────────────
# Sub-models (used inside instruction payloads)
# ──────────────────────────────────────────────


class DiagramNode(BaseModel):
    id: str
    label: str
    shape: NodeShape = NodeShape.ROUNDED
    color: str = ""


class DiagramEdge(BaseModel):
    from_id: str
    to_id: str
    label: str = ""
    style: EdgeStyle = EdgeStyle.SOLID
    directed: bool = True


class DataPoint(BaseModel):
    x: float
    y: float
    label: str = ""


class DataSeries(BaseModel):
    label: str = ""
    points: list[DataPoint] = []
    color: str = ""


class FunctionDef(BaseModel):
    """A mathematical function to plot, e.g. f(x) = x^2 + 2x - 3."""

    expression: str
    label: str = ""
    color: str = ""
    domain_min: float | None = None
    domain_max: float | None = None


class AxisConfig(BaseModel):
    label: str = ""
    min: float | None = None
    max: float | None = None


# ──────────────────────────────────────────────
# Base instruction (shared fields)
# ──────────────────────────────────────────────


class _BaseInstruction(BaseModel):
    """Fields shared by all visual instructions."""

    element_id: str | None = None
    duration_ms: int | None = None


# ──────────────────────────────────────────────
# Instruction types
# ──────────────────────────────────────────────


class ClearInstruction(_BaseInstruction):
    """Clear the board — all elements or a specific target."""

    type: Literal["clear"] = "clear"
    target_id: str | None = None


class ShowTextInstruction(_BaseInstruction):
    """Display text on the classroom screen."""

    type: Literal["show_text"] = "show_text"
    text: str
    title: str = ""
    style: TextStyle = TextStyle.DEFAULT


class ShowEquationInstruction(_BaseInstruction):
    """Display a LaTeX equation with optional animation metadata.

    The `latex` field may contain \\htmlId{id}{content} tags for per-term
    animation targeting (used by GSAP in the frontend renderer).
    """

    type: Literal["show_equation"] = "show_equation"
    latex: str
    label: str = ""
    animation: EquationAnimation = EquationAnimation.FADE_IN


class DrawDiagramInstruction(_BaseInstruction):
    """Draw a structured diagram with nodes and edges.

    Either `description` (text fallback for unstructured diagrams) or `nodes`
    (structured data for real rendering) must be provided. When both are present,
    `nodes` takes precedence and `description` is used as accessible alt-text.
    """

    type: Literal["draw_diagram"] = "draw_diagram"
    diagram_type: DiagramType = DiagramType.FREE_FORM
    title: str = ""
    description: str = ""
    nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []
    progressive: bool = True

    @model_validator(mode="after")
    def _require_content(self) -> Self:
        if not self.description and not self.nodes:
            msg = "Either description or nodes must be provided"
            raise ValueError(msg)
        return self


class ShowGraphInstruction(_BaseInstruction):
    """Display a graph or chart."""

    type: Literal["show_graph"] = "show_graph"
    graph_type: GraphType
    title: str = ""
    x_axis: AxisConfig = AxisConfig()
    y_axis: AxisConfig = AxisConfig()
    series: list[DataSeries] = []
    functions: list[FunctionDef] = []
    animated: bool = True

    @model_validator(mode="after")
    def _require_data(self) -> Self:
        if not self.series and not self.functions:
            msg = "Either series or functions must be provided"
            raise ValueError(msg)
        return self


class EquationStep(BaseModel):
    """A single step in a multi-step equation solve."""

    latex: str
    annotation: str = ""
    highlight_terms: list[str] = []


class StepEquationInstruction(_BaseInstruction):
    """Display a multi-step equation solve with progressive reveal.

    Each step appears with its transformation annotation, changed terms
    highlight, and previous steps dim — like a teacher at a whiteboard.
    """

    type: Literal["step_equation"] = "step_equation"
    title: str = ""
    steps: list[EquationStep]

    @model_validator(mode="after")
    def _require_steps(self) -> Self:
        if not self.steps:
            msg = "At least one step is required"
            raise ValueError(msg)
        return self


class HighlightInstruction(_BaseInstruction):
    """Highlight an existing element on the board."""

    type: Literal["highlight"] = "highlight"
    target_id: str
    style: HighlightStyle = HighlightStyle.GLOW
    color: str = ""
