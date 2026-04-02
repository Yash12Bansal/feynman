"""Diagram DSL schema — Pydantic models for the structured diagram specification."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Each coordinate can be a number or an expression string (e.g. "L * sin(theta)")
Coord = Union[float, str]


# ---------------------------------------------------------------------------
# SVG element models (pixel coordinates, origin top-left, y-down)
# ---------------------------------------------------------------------------


class SvgPath(BaseModel):
    type: Literal["svg_path"] = "svg_path"
    id: Optional[str] = None
    d: str = "M 0 0 L 100 100"
    stroke: str = "#000"
    strokeWidth: float = 2
    fill: str = "none"
    strokeDasharray: str = ""


class SvgCircle(BaseModel):
    type: Literal["svg_circle"] = "svg_circle"
    id: Optional[str] = None
    cx: Coord = 0
    cy: Coord = 0
    r: Coord = 10
    stroke: str = "#000"
    fill: str = "none"
    strokeWidth: float = 2
    strokeDasharray: str = ""


class SvgEllipse(BaseModel):
    type: Literal["svg_ellipse"] = "svg_ellipse"
    id: Optional[str] = None
    cx: Coord = 0
    cy: Coord = 0
    rx: Coord = 10
    ry: Coord = 5
    stroke: str = "#000"
    fill: str = "none"
    strokeWidth: float = 2


class SvgText(BaseModel):
    type: Literal["svg_text"] = "svg_text"
    id: Optional[str] = None
    x: Coord = 0
    y: Coord = 0
    text: str = ""
    fontSize: float = 14
    fill: str = "#000"
    textAnchor: str = "middle"
    fontWeight: str = "normal"


class SvgGroup(BaseModel):
    type: Literal["svg_group"] = "svg_group"
    id: Optional[str] = None
    transform: str = ""
    elements: list[Any] = Field(default_factory=list, description="Child SVG elements")


class SvgLine(BaseModel):
    type: Literal["svg_line"] = "svg_line"
    id: Optional[str] = None
    x1: Coord = 0
    y1: Coord = 0
    x2: Coord = 100
    y2: Coord = 100
    stroke: str = "#000"
    strokeWidth: float = 2
    strokeDasharray: str = ""


class SvgRect(BaseModel):
    type: Literal["svg_rect"] = "svg_rect"
    id: Optional[str] = None
    x: Coord = 0
    y: Coord = 0
    width: Coord = 100
    height: Coord = 50
    fill: str = "none"
    stroke: str = "#000"
    strokeWidth: float = 2
    rx: Coord = 0


class SvgArc(BaseModel):
    type: Literal["svg_arc"] = "svg_arc"
    id: Optional[str] = None
    cx: Coord = 0
    cy: Coord = 0
    r: Coord = 50
    startAngle: Coord = 0
    endAngle: Coord = 90
    stroke: str = "#000"
    strokeWidth: float = 2
    fill: str = "none"
    strokeDasharray: str = ""


class SvgLatex(BaseModel):
    type: Literal["svg_latex"] = "svg_latex"
    id: Optional[str] = None
    expression: str = Field(..., description="LaTeX math expression")
    x: Coord = 0
    y: Coord = 0
    fontSize: float = 16
    color: Optional[str] = "#000"


class SvgArrow(BaseModel):
    type: Literal["svg_arrow"] = "svg_arrow"
    id: Optional[str] = None
    x1: Coord = 0
    y1: Coord = 0
    x2: Coord = 100
    y2: Coord = 100
    stroke: str = "#000"
    strokeWidth: float = 2
    strokeDasharray: str = ""


# ---------------------------------------------------------------------------
# Graph element — inset plot with axes rendered by visx
# ---------------------------------------------------------------------------


class GraphCurve(BaseModel):
    expression: str = Field(..., description="JS math expression with x as variable")
    color: str = "steelblue"
    strokeWidth: float = 2


class GraphElement(BaseModel):
    type: Literal["graph"] = "graph"
    id: Optional[str] = None
    x: Coord = 0
    y: Coord = 0
    width: Coord = 300
    height: Coord = 200
    xDomain: tuple[float, float] = (-10, 10)
    yDomain: tuple[float, float] = (-10, 10)
    xLabel: str = ""
    yLabel: str = ""
    backgroundColor: str = "#f9f9f9"
    borderColor: str = "#ccc"
    curves: list[GraphCurve] = Field(default_factory=list)
    showGrid: bool = True


# ---------------------------------------------------------------------------
# Discriminated union of all element types
# ---------------------------------------------------------------------------

DiagramElement = Annotated[
    Union[
        SvgPath,
        SvgCircle,
        SvgEllipse,
        SvgText,
        SvgGroup,
        SvgLine,
        SvgRect,
        SvgArc,
        SvgLatex,
        SvgArrow,
        GraphElement,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Interactive parameter (slider)
# ---------------------------------------------------------------------------


class SliderParameter(BaseModel):
    name: str
    min: float
    max: float
    default: float
    step: float = 0.1
    label: Optional[str] = None


# ---------------------------------------------------------------------------
# Animation spec
# ---------------------------------------------------------------------------


# Accept any dict for animations — Claude generates varied formats
# and we don't render animations yet anyway.
class AnimationSpec(BaseModel):
    model_config = {"extra": "allow"}
    duration: float = 2.0
    loop: bool = True


# ---------------------------------------------------------------------------
# Top-level diagram specification
# ---------------------------------------------------------------------------


class DiagramSpec(BaseModel):
    """Complete diagram specification returned by the agent."""

    title: str = "Untitled Diagram"
    description: str = ""
    width: int = 900
    height: int = 650
    backgroundColor: str = "#ffffff"
    elements: list[DiagramElement] = Field(default_factory=list)
    parameters: list[SliderParameter] = Field(default_factory=list)
    animations: list[AnimationSpec] = Field(default_factory=list)
