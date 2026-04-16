"""Tests for visual pre-generation: generator, validator, writer, and UID derivation."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    ExtractionNode,
    ExtractionSource,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.visuals.models import DiagramSpec
from lecture_pipeline.curriculum.visuals.neo4j_visual_writer import (
    Neo4jVisualWriter,
    VisualWriteReport,
)
from lecture_pipeline.curriculum.visuals.spec_validator import VisualSpecValidator
from lecture_pipeline.curriculum.visuals.visual_generator import (
    VisualGenerationReport,
    VisualGenerator,
    _concept_visual_uid,
    _extract_json,
)
from lecture_pipeline.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_DIAGRAM_JSON = json.dumps(
    {
        "title": "Simple Harmonic Motion",
        "description": "Spring-mass energy diagram",
        "width": 900,
        "height": 650,
        "backgroundColor": "#ffffff",
        "elements": [
            {
                "type": "svg_circle",
                "id": "mass",
                "cx": 450,
                "cy": 300,
                "r": 20,
                "fill": "#4682b4",
                "stroke": "#000",
            },
            {
                "type": "svg_line",
                "id": "spring",
                "x1": 100,
                "y1": 300,
                "x2": 430,
                "y2": 300,
                "stroke": "#555",
                "strokeDasharray": "5,5",
            },
            {
                "type": "svg_latex",
                "id": "formula",
                "expression": "F = -kx",
                "x": 450,
                "y": 550,
                "fontSize": 20,
            },
            {
                "type": "svg_text",
                "id": "label",
                "x": 450,
                "y": 260,
                "text": "Mass",
                "fontSize": 14,
            },
        ],
        "parameters": [
            {
                "name": "displacement",
                "min": -5,
                "max": 5,
                "default": 0,
                "step": 0.1,
                "label": "Displacement",
            }
        ],
        "animations": [],
    }
)


def _source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="Test Book",
        chapter_title="Ch1",
        page_range="1-10",
        extractor_model="mock",
    )


def _node(uid: str, topic: str, visual_hint: str | None = None) -> ExtractionNode:
    return ExtractionNode(
        uid=uid,
        topic_name=topic,
        concept_type=ConceptType.DEFINITION,
        resolution_level=ResolutionLevel.CONCEPT,
        summary="A test concept.",
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=1,
        visual_hint=visual_hint,
    )


def _extraction(nodes: list[ExtractionNode] | None = None) -> CurriculumExtractionResult:
    if nodes is None:
        nodes = [
            _node("curriculum:physics:ch1:shm", "SHM", "Spring-mass diagram"),
            _node("curriculum:physics:ch1:energy", "Energy in SHM", "KE/PE curves"),
            _node("curriculum:physics:ch1:period", "Period formula", None),  # no hint
        ]
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="Test Book",
        scope="book",
        source=_source(),
        nodes=nodes,
        relationships=[],
    )


def _mock_llm(response_json: str = VALID_DIAGRAM_JSON) -> MagicMock:
    llm = MagicMock()
    llm.generate_json.return_value = LLMResponse(
        content=response_json,
        model="mock-model",
    )
    return llm


# ---------------------------------------------------------------------------
# Tests — VisualGenerator
# ---------------------------------------------------------------------------


class TestVisualGenerator:
    @pytest.mark.asyncio
    async def test_generates_for_concepts_with_hints(self):
        llm = _mock_llm()
        gen = VisualGenerator(llm, concurrency=2)
        extraction = _extraction()

        visuals, report = await gen.generate_visuals(extraction)

        assert report.total_concepts == 3
        assert report.concepts_with_hints == 2
        assert report.visuals_generated == 2
        assert report.visuals_failed == 0
        assert len(visuals) == 2
        # LLM called once per hinted concept
        assert llm.generate_json.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_concepts_without_hints(self):
        llm = _mock_llm()
        gen = VisualGenerator(llm, concurrency=2)
        # All nodes without hints
        extraction = _extraction(
            nodes=[
                _node("curriculum:physics:ch1:a", "Concept A", None),
                _node("curriculum:physics:ch1:b", "Concept B", None),
            ]
        )

        visuals, report = await gen.generate_visuals(extraction)

        assert report.concepts_with_hints == 0
        assert report.visuals_generated == 0
        assert len(visuals) == 0
        assert llm.generate_json.call_count == 0

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self):
        llm = _mock_llm()
        call_count = 0

        def _failing_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM API error")
            return LLMResponse(content=VALID_DIAGRAM_JSON, model="mock")

        llm.generate_json.side_effect = _failing_generate
        gen = VisualGenerator(llm, concurrency=1)
        extraction = _extraction()

        visuals, report = await gen.generate_visuals(extraction)

        assert report.visuals_generated == 1
        assert report.visuals_failed == 1
        assert len(report.errors) == 1
        assert "LLM API error" in report.errors[0]

    @pytest.mark.asyncio
    async def test_handles_invalid_json_gracefully(self):
        llm = _mock_llm(response_json="not valid json at all")
        gen = VisualGenerator(llm, concurrency=2)
        extraction = _extraction()

        visuals, report = await gen.generate_visuals(extraction)

        assert report.visuals_generated == 0
        assert report.visuals_failed == 2
        assert len(visuals) == 0

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        fenced = f"```json\n{VALID_DIAGRAM_JSON}\n```"
        llm = _mock_llm(response_json=fenced)
        gen = VisualGenerator(llm, concurrency=2)
        extraction = _extraction()

        visuals, report = await gen.generate_visuals(extraction)

        assert report.visuals_generated == 2

    @pytest.mark.asyncio
    async def test_report_summary(self):
        llm = _mock_llm()
        gen = VisualGenerator(llm, concurrency=2)
        extraction = _extraction()

        _, report = await gen.generate_visuals(extraction)

        summary = report.summary()
        assert "2/2 generated" in summary
        assert "OK" in summary


# ---------------------------------------------------------------------------
# Tests — UID derivation
# ---------------------------------------------------------------------------


class TestVisualUid:
    def test_curriculum_prefix_replaced(self):
        assert _concept_visual_uid("curriculum:physics:shm:energy") == "visual:physics:shm:energy"

    def test_non_curriculum_prefix(self):
        assert _concept_visual_uid("custom:some:id") == "visual:custom:some:id"

    def test_empty_string(self):
        assert _concept_visual_uid("") == "visual:"


# ---------------------------------------------------------------------------
# Tests — _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == '{"a": 1}'

    def test_fenced_json(self):
        assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_fenced_no_lang(self):
        assert _extract_json('```\n{"a": 1}\n```') == '{"a": 1}'


# ---------------------------------------------------------------------------
# Tests — VisualSpecValidator
# ---------------------------------------------------------------------------


class TestSpecValidator:
    def test_valid_spec(self):
        spec = DiagramSpec.model_validate_json(VALID_DIAGRAM_JSON)
        validator = VisualSpecValidator()
        warnings = validator.validate(spec)
        # displacement param is not referenced in element coordinate expressions
        # (elements use hardcoded numbers), so we expect 1 warning
        assert any("not referenced" in w for w in warnings)

    def test_empty_elements(self):
        spec = DiagramSpec(elements=[])
        validator = VisualSpecValidator()
        warnings = validator.validate(spec)
        assert any("no elements" in w.lower() for w in warnings)

    def test_duplicate_ids(self):
        spec = DiagramSpec.model_validate(
            {
                "elements": [
                    {"type": "svg_line", "id": "dup"},
                    {"type": "svg_line", "id": "dup"},
                ]
            }
        )
        validator = VisualSpecValidator()
        warnings = validator.validate(spec)
        assert any("Duplicate" in w for w in warnings)

    def test_empty_latex_expression(self):
        spec = DiagramSpec.model_validate(
            {
                "elements": [
                    {"type": "svg_latex", "id": "eq1", "expression": "  "},
                ]
            }
        )
        validator = VisualSpecValidator()
        warnings = validator.validate(spec)
        assert any("Empty LaTeX" in w for w in warnings)


# ---------------------------------------------------------------------------
# Tests — Neo4jVisualWriter
# ---------------------------------------------------------------------------


class TestNeo4jVisualWriter:
    def test_build_params(self):
        spec = DiagramSpec.model_validate_json(VALID_DIAGRAM_JSON)
        writer = Neo4jVisualWriter()

        params = writer._build_params(
            "curriculum:physics:shm:energy", spec, "claude-sonnet-4"
        )

        assert params["visual_uid"] == "visual:physics:shm:energy"
        assert params["concept_uid"] == "curriculum:physics:shm:energy"
        assert params["generation_model"] == "claude-sonnet-4"
        assert params["element_count"] == 4
        assert params["has_params"] is True
        assert params["width"] == 900
        assert params["title"] == "Simple Harmonic Motion"
        # diagram_spec is valid JSON string
        json.loads(params["diagram_spec"])

    @pytest.mark.asyncio
    async def test_write_empty_list(self):
        driver = MagicMock()
        writer = Neo4jVisualWriter()

        report = await writer.write_visuals(
            driver, [], generation_model="test"
        )

        assert report.visuals_written == 0
        assert report.edges_written == 0


# ---------------------------------------------------------------------------
# Tests — DiagramSpec model
# ---------------------------------------------------------------------------


class TestDiagramSpecModel:
    def test_roundtrip(self):
        spec = DiagramSpec.model_validate_json(VALID_DIAGRAM_JSON)
        assert spec.title == "Simple Harmonic Motion"
        assert len(spec.elements) == 4
        assert len(spec.parameters) == 1
        # Roundtrip
        json_str = spec.model_dump_json()
        spec2 = DiagramSpec.model_validate_json(json_str)
        assert spec2.title == spec.title
        assert len(spec2.elements) == len(spec.elements)

    def test_minimal_spec(self):
        spec = DiagramSpec()
        assert spec.title == "Untitled Diagram"
        assert spec.width == 900
        assert spec.height == 650
        assert spec.elements == []
