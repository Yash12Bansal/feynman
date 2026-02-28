"""Tests for visual instruction schemas and discriminated union."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from feynman.visuals.instructions import VisualInstruction
from feynman.visuals.schemas import (
    AxisConfig,
    ClearInstruction,
    DataPoint,
    DataSeries,
    DiagramEdge,
    DiagramNode,
    DiagramType,
    DrawDiagramInstruction,
    EdgeStyle,
    EquationAnimation,
    EquationStep,
    FunctionDef,
    GraphType,
    HighlightInstruction,
    HighlightStyle,
    NodeShape,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    StepEquationInstruction,
    TextStyle,
)

# Adapter for parsing the discriminated union from raw dicts / JSON
_ta = TypeAdapter(VisualInstruction)


# ── Construction ───────────────────────────────────────────────


class TestConstruction:
    def test_clear_defaults(self) -> None:
        instr = ClearInstruction()
        assert instr.type == "clear"
        assert instr.target_id is None
        assert instr.element_id is None
        assert instr.duration_ms is None

    def test_clear_with_target(self) -> None:
        instr = ClearInstruction(target_id="eq-1")
        assert instr.target_id == "eq-1"

    def test_show_text_required_field(self) -> None:
        instr = ShowTextInstruction(text="Hello, class!")
        assert instr.type == "show_text"
        assert instr.text == "Hello, class!"
        assert instr.title == ""
        assert instr.style == TextStyle.DEFAULT

    def test_show_text_all_fields(self) -> None:
        instr = ShowTextInstruction(
            text="Energy is conserved",
            title="Key Principle",
            style=TextStyle.KEY_POINT,
            element_id="txt-1",
            duration_ms=3000,
        )
        assert instr.title == "Key Principle"
        assert instr.style == TextStyle.KEY_POINT
        assert instr.element_id == "txt-1"
        assert instr.duration_ms == 3000

    def test_show_equation_defaults(self) -> None:
        instr = ShowEquationInstruction(latex="E = mc^2")
        assert instr.type == "show_equation"
        assert instr.latex == "E = mc^2"
        assert instr.label == ""
        assert instr.animation == EquationAnimation.FADE_IN

    def test_show_equation_with_animation(self) -> None:
        instr = ShowEquationInstruction(
            latex=r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
            label="Quadratic Formula",
            animation=EquationAnimation.TERM_BY_TERM,
        )
        assert instr.animation == EquationAnimation.TERM_BY_TERM

    def test_draw_diagram_with_description(self) -> None:
        instr = DrawDiagramInstruction(description="Water cycle")
        assert instr.type == "draw_diagram"
        assert instr.description == "Water cycle"
        assert instr.nodes == []
        assert instr.diagram_type == DiagramType.FREE_FORM

    def test_draw_diagram_with_nodes(self) -> None:
        nodes = [
            DiagramNode(id="a", label="Evaporation"),
            DiagramNode(id="b", label="Condensation", shape=NodeShape.CIRCLE),
        ]
        edges = [DiagramEdge(from_id="a", to_id="b", label="rises")]
        instr = DrawDiagramInstruction(
            diagram_type=DiagramType.CYCLE,
            title="Water Cycle",
            nodes=nodes,
            edges=edges,
            progressive=True,
        )
        assert len(instr.nodes) == 2
        assert instr.nodes[1].shape == NodeShape.CIRCLE
        assert instr.edges[0].label == "rises"

    def test_draw_diagram_requires_content(self) -> None:
        with pytest.raises(ValidationError, match="description or nodes"):
            DrawDiagramInstruction()

    def test_show_graph_function_plot(self) -> None:
        instr = ShowGraphInstruction(
            graph_type=GraphType.FUNCTION,
            title="Parabola",
            functions=[FunctionDef(expression="x^2 - 4")],
            x_axis=AxisConfig(label="x", min=-5, max=5),
            y_axis=AxisConfig(label="f(x)"),
        )
        assert instr.graph_type == GraphType.FUNCTION
        assert instr.functions[0].expression == "x^2 - 4"

    def test_show_graph_with_series(self) -> None:
        instr = ShowGraphInstruction(
            graph_type=GraphType.BAR,
            series=[
                DataSeries(
                    label="Scores",
                    points=[DataPoint(x=1, y=85), DataPoint(x=2, y=92)],
                )
            ],
        )
        assert len(instr.series[0].points) == 2

    def test_show_graph_requires_data(self) -> None:
        with pytest.raises(ValidationError, match="series or functions"):
            ShowGraphInstruction(graph_type=GraphType.LINE)

    def test_highlight(self) -> None:
        instr = HighlightInstruction(target_id="eq-1", style=HighlightStyle.PULSE)
        assert instr.type == "highlight"
        assert instr.target_id == "eq-1"
        assert instr.style == HighlightStyle.PULSE

    def test_highlight_requires_target(self) -> None:
        with pytest.raises(ValidationError):
            HighlightInstruction()  # type: ignore[call-arg]

    def test_step_equation_basic(self) -> None:
        instr = StepEquationInstruction(
            steps=[
                EquationStep(latex="2x + 4 = 10"),
                EquationStep(
                    latex="2x = 6",
                    annotation="Subtract 4 from both sides",
                    highlight_terms=["term-result"],
                ),
                EquationStep(
                    latex="x = 3",
                    annotation="Divide both sides by 2",
                ),
            ],
        )
        assert instr.type == "step_equation"
        assert len(instr.steps) == 3
        assert instr.title == ""

    def test_step_equation_requires_steps(self) -> None:
        with pytest.raises(ValidationError, match="At least one step"):
            StepEquationInstruction(steps=[])

    def test_step_equation_highlight_terms(self) -> None:
        step = EquationStep(
            latex="x = 3",
            highlight_terms=["term-x", "term-result"],
        )
        assert step.highlight_terms == ["term-x", "term-result"]

    def test_step_equation_defaults(self) -> None:
        instr = StepEquationInstruction(
            title="Solving for x",
            steps=[EquationStep(latex="x = 1")],
        )
        assert instr.title == "Solving for x"
        assert instr.steps[0].annotation == ""
        assert instr.steps[0].highlight_terms == []
        assert instr.element_id is None
        assert instr.duration_ms is None


# ── Discriminated union parsing ────────────────────────────────


class TestDiscriminatedUnion:
    def test_parse_clear(self) -> None:
        instr = _ta.validate_python({"type": "clear"})
        assert isinstance(instr, ClearInstruction)

    def test_parse_show_text(self) -> None:
        instr = _ta.validate_python({"type": "show_text", "text": "Hello"})
        assert isinstance(instr, ShowTextInstruction)
        assert instr.text == "Hello"

    def test_parse_show_equation(self) -> None:
        instr = _ta.validate_python({"type": "show_equation", "latex": "F = ma"})
        assert isinstance(instr, ShowEquationInstruction)
        assert instr.latex == "F = ma"

    def test_parse_draw_diagram(self) -> None:
        instr = _ta.validate_python(
            {
                "type": "draw_diagram",
                "description": "Forces on a block",
            }
        )
        assert isinstance(instr, DrawDiagramInstruction)

    def test_parse_show_graph(self) -> None:
        instr = _ta.validate_python(
            {
                "type": "show_graph",
                "graph_type": "function",
                "functions": [{"expression": "sin(x)"}],
            }
        )
        assert isinstance(instr, ShowGraphInstruction)

    def test_parse_highlight(self) -> None:
        instr = _ta.validate_python(
            {
                "type": "highlight",
                "target_id": "node-1",
            }
        )
        assert isinstance(instr, HighlightInstruction)

    def test_parse_step_equation(self) -> None:
        instr = _ta.validate_python(
            {
                "type": "step_equation",
                "title": "Solving for x",
                "steps": [
                    {"latex": "2x + 4 = 10"},
                    {"latex": "2x = 6", "annotation": "Subtract 4"},
                ],
            }
        )
        assert isinstance(instr, StepEquationInstruction)
        assert len(instr.steps) == 2

    def test_parse_unknown_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _ta.validate_python({"type": "explode"})

    def test_parse_missing_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _ta.validate_python({"text": "oops"})


# ── Serialization round-trip ───────────────────────────────────


class TestSerialization:
    def test_show_equation_roundtrip(self) -> None:
        original = ShowEquationInstruction(
            latex=r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}",
            label="Sum of integers",
            animation=EquationAnimation.WRITE_ON,
            element_id="eq-sum",
        )
        data = original.model_dump(exclude_none=True)
        assert data["type"] == "show_equation"
        assert data["latex"] == original.latex
        assert "duration_ms" not in data  # excluded because None

        # Round-trip through JSON
        json_str = json.dumps(data)
        parsed = _ta.validate_json(json_str)
        assert isinstance(parsed, ShowEquationInstruction)
        assert parsed.latex == original.latex
        assert parsed.animation == EquationAnimation.WRITE_ON

    def test_draw_diagram_roundtrip(self) -> None:
        original = DrawDiagramInstruction(
            diagram_type=DiagramType.FLOWCHART,
            title="Algorithm",
            nodes=[
                DiagramNode(id="start", label="Start", shape=NodeShape.CIRCLE),
                DiagramNode(id="process", label="Process"),
                DiagramNode(id="end", label="End", shape=NodeShape.CIRCLE),
            ],
            edges=[
                DiagramEdge(from_id="start", to_id="process"),
                DiagramEdge(from_id="process", to_id="end", style=EdgeStyle.DASHED),
            ],
        )
        json_str = json.dumps(original.model_dump(exclude_none=True))
        parsed = _ta.validate_json(json_str)
        assert isinstance(parsed, DrawDiagramInstruction)
        assert len(parsed.nodes) == 3
        assert parsed.edges[1].style == EdgeStyle.DASHED

    def test_clear_minimal_json(self) -> None:
        """ClearInstruction should produce minimal JSON."""
        instr = ClearInstruction()
        data = instr.model_dump(exclude_none=True)
        assert data == {"type": "clear"}

    def test_step_equation_roundtrip(self) -> None:
        original = StepEquationInstruction(
            title="Solving for x",
            steps=[
                EquationStep(latex="2x + 4 = 10"),
                EquationStep(
                    latex="2x = 6",
                    annotation="Subtract 4 from both sides",
                    highlight_terms=["term-result"],
                ),
                EquationStep(
                    latex="x = 3",
                    annotation="Divide both sides by 2",
                ),
            ],
            element_id="step-eq-1",
        )
        data = original.model_dump(exclude_none=True)
        assert data["type"] == "step_equation"
        assert len(data["steps"]) == 3
        assert "duration_ms" not in data

        json_str = json.dumps(data)
        parsed = _ta.validate_json(json_str)
        assert isinstance(parsed, StepEquationInstruction)
        assert parsed.title == "Solving for x"
        assert parsed.steps[1].annotation == "Subtract 4 from both sides"
        assert parsed.steps[1].highlight_terms == ["term-result"]

    def test_show_graph_roundtrip(self) -> None:
        original = ShowGraphInstruction(
            graph_type=GraphType.SCATTER,
            title="Height vs Weight",
            series=[
                DataSeries(
                    label="Students",
                    points=[
                        DataPoint(x=150, y=45),
                        DataPoint(x=165, y=58),
                        DataPoint(x=170, y=62, label="outlier"),
                    ],
                    color="#ff6384",
                )
            ],
            x_axis=AxisConfig(label="Height (cm)"),
            y_axis=AxisConfig(label="Weight (kg)"),
        )
        json_str = json.dumps(original.model_dump(exclude_none=True))
        parsed = _ta.validate_json(json_str)
        assert isinstance(parsed, ShowGraphInstruction)
        assert len(parsed.series[0].points) == 3


# ── Edge cases ─────────────────────────────────────────────────


class TestEdgeCases:
    def test_diagram_both_description_and_nodes(self) -> None:
        """When both description and nodes are provided, both are kept."""
        instr = DrawDiagramInstruction(
            description="Fallback text",
            nodes=[DiagramNode(id="a", label="A")],
        )
        assert instr.description == "Fallback text"
        assert len(instr.nodes) == 1

    def test_edge_defaults(self) -> None:
        edge = DiagramEdge(from_id="a", to_id="b")
        assert edge.style == EdgeStyle.SOLID
        assert edge.directed is True
        assert edge.label == ""

    def test_function_def_defaults(self) -> None:
        f = FunctionDef(expression="x^2")
        assert f.domain_min is None
        assert f.domain_max is None
        assert f.color == ""

    def test_enum_string_values(self) -> None:
        """Enum values should be lowercase strings for JSON serialization."""
        assert TextStyle.KEY_POINT == "key_point"
        assert EquationAnimation.TERM_BY_TERM == "term_by_term"
        assert DiagramType.FORCE_DIAGRAM == "force_diagram"
        assert GraphType.FUNCTION == "function"
        assert HighlightStyle.GLOW == "glow"
