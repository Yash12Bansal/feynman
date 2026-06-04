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
# Staged reveal — declarative, narration-paced element ordering
# ---------------------------------------------------------------------------


class AnimationStep(BaseModel):
    """One step of a diagram's staged reveal (the `animations` list).

    A step names a set of elements — by dictionary *role* (preferred, robust to
    id churn) and/or explicit element id — that become visible together when the
    narration reaches `cue`. The renderer reveals one step per narration beat;
    elements never un-reveal (reveal is monotonic, the final frame is the full
    static diagram → INV-1).

    There is deliberately **no** `loop`, `autoplay`, `delay`, or `interval`
    field: steps can only advance on a narration/interaction event, never on a
    timer. Autoplay is therefore unrepresentable → INV-2 holds by construction.
    Do NOT add a timing-trigger field here.

    The common case is an EMPTY `animations` list (most diagrams are static
    references shown all at once). Steps are opt-in, for diagrams whose meaning
    is a sequence the student should watch unfold.
    """

    model_config = {"extra": "allow"}

    # Ordinal — steps are revealed in ascending `step`, ties keep list order.
    step: int = 0
    # Dictionary roles to reveal this step (resolved id-agnostically).
    role_targets: list[str] = Field(default_factory=list)
    # Explicit element ids to reveal this step (escape hatch when no role fits).
    element_targets: list[str] = Field(default_factory=list)
    # Narration phrase that should trigger this step (composer aligns the
    # reveal event to it). Advisory metadata; the renderer reveals on the event.
    cue: Optional[str] = None
    # Fade-in duration for this step's elements, ms. Visual polish only.
    duration_ms: int = 400


# ---------------------------------------------------------------------------
# Semantic dictionary — maps element IDs to teacher-readable metadata
# ---------------------------------------------------------------------------


ElementPosition = Literal[
    "top",
    "bottom",
    "left",
    "right",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "center",
    "diagonal",
]


class ElementMeta(BaseModel):
    """Semantic metadata for a single SVG element in a DiagramSpec.

    Populated by the design_agent at generation time. Consumed by the
    teaching agent so it can refer to elements by *role* (`"hypotenuse"`)
    instead of raw IDs (`"side_AB"`), and so it can reason about what's
    on the slide.
    """

    role: str = Field(
        description=(
            "Functional role of this element. Common values: "
            "hypotenuse, opposite, adjacent, leg, vertex, angle, right_angle_marker, "
            "label, dimension, axis, curve, callout. Open vocabulary; design_agent "
            "picks descriptive role names. Teaching agent matches by role."
        )
    )
    semantic: str = Field(
        description=(
            "Plain-English description: 'the ladder, 10m', "
            "'the angle of elevation, 60°'. Used in the teaching agent's "
            "prompt to reason about what the element means."
        )
    )
    position: ElementPosition
    spatial_relations: list[str] = Field(
        default_factory=list,
        description=(
            "List of relations to other elements, encoded as 'relation:target_id'. "
            "Examples: ['adjacent_to:vertex_A', 'above:side_BC', 'opposite_to:vertex_C']."
        ),
    )
    bounds: Optional[tuple[float, float, float, float]] = Field(
        default=None,
        description=(
            "Bounding box (x, y, width, height) in SVG coordinates. "
            "Used for annotation positioning."
        ),
    )


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
    animations: list[AnimationStep] = Field(
        default_factory=list,
        description=(
            "Optional staged-reveal ordering. Empty (the common case) means the "
            "whole diagram is shown at once. Each step reveals a group of "
            "elements on a narration beat; reveal is monotonic and the final "
            "frame is the full static diagram. No autoplay/loop — see AnimationStep."
        ),
    )
    presentation_mode: Optional[Literal["build_up", "overview"]] = Field(
        default=None,
        description=(
            "How the renderer should introduce this diagram. 'build_up' starts "
            "with elements hidden and reveals them in narration-paced steps "
            "(see `animations`); 'overview' shows everything at once and uses "
            "focus to spotlight. None defaults to 'overview' at render time."
        ),
    )
    dictionary: dict[str, ElementMeta] = Field(
        default_factory=dict,
        description=(
            "Maps element_id → ElementMeta. Populated by design_agent at "
            "generation time. Empty dict means legacy/unenriched spec — "
            "teaching agent falls back to ID-only references."
        ),
    )
