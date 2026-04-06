"""Tests for gap-filling sub-agent — mocked LLM, no API calls."""

from __future__ import annotations

import json

import pytest

from lecture_pipeline.curriculum.anchors.models import (
    ExtractionAnchors,
    SectionAnchor,
)
from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.validation.gap_filler import GapFiller
from lecture_pipeline.curriculum.validation.models import (
    ValidationReport,
)
from lecture_pipeline.curriculum.validation.prompts import (
    build_gap_fill_user_prompt,
    get_gap_fill_system_prompt,
)
from lecture_pipeline.curriculum.validation.structural import StructuralValidator
from lecture_pipeline.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """LLM provider that returns preconfigured responses in sequence."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, str]] = []
        self._call_index = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return self.generate_json(system_prompt, user_prompt)

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self._call_index < len(self.responses):
            content = self.responses[self._call_index]
            self._call_index += 1
        else:
            content = '{"nodes": [], "relationships": []}'
        return LLMResponse(content=content, model="mock-model", usage=None)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


CHAPTER_TEXT = """12.1 Simple Harmonic Motion
A particle executing SHM moves back and forth about an equilibrium position.
The displacement is x = A sin(ωt + φ).

12.2 Energy in SHM
The kinetic energy is KE = ½mv².

12.3 Damped Oscillations
Real oscillations lose energy due to friction. F = -bv.

Figure 12.1 shows the displacement diagram.
Figure 12.2 shows the energy diagram.
Example 12.1 demonstrates spring-mass calculation.
"""

ANCHORS_WITH_GAPS = ExtractionAnchors(
    section_numbers=[
        SectionAnchor(section_number="12.1", title="Simple Harmonic Motion", depth=2),
        SectionAnchor(section_number="12.2", title="Energy in SHM", depth=2),
        SectionAnchor(section_number="12.3", title="Damped Oscillations", depth=2),
    ],
    equations=["Eq. (12.1)"],
    figure_refs=["Figure 12.1", "Figure 12.2"],
    example_refs=["Example 12.1"],
    defined_terms=[],
    page_count=22,
)


def _make_node(
    uid: str,
    topic_name: str = "Test Concept",
    concept_type: ConceptType = ConceptType.TOPIC,
    section_number: str | None = "12.1",
    summary: str = "A summary.",
    page_start: int = 239,
    page_end: int = 260,
    within_chapter_order: int = 1,
    visual_hint: str | None = None,
    parent_uid: str | None = None,
    children_uids: list[str] | None = None,
) -> ExtractionNode:
    return ExtractionNode(
        uid=uid,
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=ResolutionLevel.CONCEPT,
        section_number=section_number,
        summary=summary,
        source_text="Source text.",
        page_start=page_start,
        page_end=page_end,
        chapter_order=3,
        within_chapter_order=within_chapter_order,
        difficulty=Difficulty.INTERMEDIATE,
        visual_hint=visual_hint,
        parent_uid=parent_uid,
        children_uids=children_uids or [],
    )


def _make_extraction(
    nodes: list[ExtractionNode],
    rels: list[ExtractionRelationship] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="Test Textbook",
        scope="chapter",
        chapter_title="Simple Harmonic Motion",
        source=ExtractionSource(
            textbook_title="Test Textbook",
            chapter_title="Simple Harmonic Motion",
            page_range="239-260",
            extractor_model="mock-model",
        ),
        nodes=nodes,
        relationships=rels or [],
    )


def _make_incomplete_extraction() -> CurriculumExtractionResult:
    """Extraction missing section 12.3, Figure 12.2, and Example 12.1."""
    nodes = [
        _make_node(
            uid="curriculum:physics:shm:shm",
            topic_name="Simple Harmonic Motion",
            section_number="12.1",
            within_chapter_order=1,
        ),
        _make_node(
            uid="curriculum:physics:shm:displacement",
            topic_name="Displacement in SHM (Eq. 12.1)",
            concept_type=ConceptType.FORMULA,
            section_number="12.1",
            summary="x = A sin(ωt + φ). Eq. 12.1.",
            within_chapter_order=2,
            visual_hint="Sine wave diagram",
        ),
        _make_node(
            uid="curriculum:physics:shm:shm_diagram",
            topic_name="SHM Displacement Diagram (Figure 12.1)",
            concept_type=ConceptType.VISUALIZATION,
            section_number="12.1",
            summary="Diagram of displacement. Figure 12.1.",
            within_chapter_order=3,
            visual_hint="Spring-mass diagram",
        ),
        _make_node(
            uid="curriculum:physics:shm:energy",
            topic_name="Energy in SHM",
            section_number="12.2",
            within_chapter_order=4,
        ),
    ]
    return _make_extraction(nodes)


def _gap_fill_response_12_3() -> str:
    """LLM response that fills section 12.3."""
    return json.dumps({
        "nodes": [
            {
                "topic_name": "Damped Oscillations",
                "concept_type": "topic",
                "resolution_level": "concept",
                "section_number": "12.3",
                "parent": None,
                "page_start": 253,
                "page_end": 258,
                "visual_hint": None,
                "estimated_duration_minutes": 5.0,
                "summary": "Real oscillations lose energy over time.",
                "source_text": "Real oscillations lose energy due to friction.",
                "difficulty": "intermediate",
            },
        ],
        "relationships": [
            {
                "from_node": "Energy in SHM",
                "to_node": "Damped Oscillations",
                "type": "leads_to",
                "label": "Energy concepts lead to damped oscillations",
            },
        ],
    })


def _gap_fill_response_fig_and_example() -> str:
    """LLM response that fills Figure 12.2 and Example 12.1."""
    return json.dumps({
        "nodes": [
            {
                "topic_name": "Energy Diagram (Figure 12.2)",
                "concept_type": "visualization",
                "resolution_level": "detail",
                "section_number": "12.2",
                "parent": "Energy in SHM",
                "page_start": 248,
                "page_end": 249,
                "visual_hint": "KE + PE energy curves",
                "estimated_duration_minutes": 2.0,
                "summary": "Combined energy diagram. Figure 12.2.",
                "source_text": "Figure 12.2 shows the energy diagram.",
                "difficulty": "intermediate",
            },
            {
                "topic_name": "Spring-Mass Calculation (Example 12.1)",
                "concept_type": "example",
                "resolution_level": "detail",
                "section_number": "12.1",
                "parent": "Simple Harmonic Motion",
                "page_start": 243,
                "page_end": 245,
                "visual_hint": "Spring-mass FBD",
                "estimated_duration_minutes": 4.0,
                "summary": "Worked example: spring-mass period. Example 12.1.",
                "source_text": "Example 12.1 demonstrates spring-mass calculation.",
                "difficulty": "beginner",
            },
        ],
        "relationships": [],
    })


# ---------------------------------------------------------------------------
# TestGapCollection
# ---------------------------------------------------------------------------


class TestGapCollection:

    def test_collects_missing_sections(self):
        report = ValidationReport()
        report.add_error(
            "MISSING_SECTIONS",
            "missing",
            details={"missing_sections": [{"section_number": "12.3", "title": "Damped"}]},
        )
        filler = GapFiller(MockLLMProvider(), StructuralValidator())
        gaps = filler._collect_gaps(report)

        assert "missing_sections" in gaps
        assert len(gaps["missing_sections"]) == 1

    def test_collects_missing_figures(self):
        report = ValidationReport()
        report.add_error(
            "MISSING_FIGURES",
            "missing",
            details={"missing_figures": ["Figure 12.2"]},
        )
        filler = GapFiller(MockLLMProvider(), StructuralValidator())
        gaps = filler._collect_gaps(report)

        assert "missing_figures" in gaps
        assert "Figure 12.2" in gaps["missing_figures"]

    def test_no_completeness_errors_empty_gaps(self):
        report = ValidationReport()
        report.add_error("DUPLICATE_UID", "structural only")
        filler = GapFiller(MockLLMProvider(), StructuralValidator())
        gaps = filler._collect_gaps(report)

        assert gaps == {}


# ---------------------------------------------------------------------------
# TestGapFillPrompt
# ---------------------------------------------------------------------------


class TestGapFillPrompt:

    def test_system_prompt_includes_schema(self):
        prompt = get_gap_fill_system_prompt()
        assert "Concept Types" in prompt
        assert "FORMULA" in prompt
        assert "gap-filling" in prompt.lower()

    def test_user_prompt_includes_existing_concepts(self):
        prompt = build_gap_fill_user_prompt(
            chapter_text="some text",
            existing_concept_names=["SHM", "Energy"],
            gaps={"missing_sections": [{"section_number": "12.3", "title": "Damped"}]},
        )
        assert "SHM" in prompt
        assert "Energy" in prompt
        assert "DO NOT re-extract" in prompt

    def test_user_prompt_includes_missing_items(self):
        prompt = build_gap_fill_user_prompt(
            chapter_text="some text",
            existing_concept_names=[],
            gaps={
                "missing_sections": [{"section_number": "12.3", "title": "Damped Oscillations"}],
                "missing_figures": ["Figure 12.2"],
                "missing_examples": ["Example 12.1"],
            },
        )
        assert "12.3" in prompt
        assert "Damped Oscillations" in prompt
        assert "Figure 12.2" in prompt
        assert "Example 12.1" in prompt

    def test_user_prompt_includes_chapter_text(self):
        prompt = build_gap_fill_user_prompt(
            chapter_text="The quick brown fox",
            existing_concept_names=[],
            gaps={},
        )
        assert "The quick brown fox" in prompt


# ---------------------------------------------------------------------------
# TestGapFillMerge
# ---------------------------------------------------------------------------


class TestGapFillMerge:

    def test_new_nodes_get_uids(self):
        extraction = _make_incomplete_extraction()
        filler = GapFiller(MockLLMProvider(), StructuralValidator())

        new_nodes = [
            {
                "topic_name": "Damped Oscillations",
                "concept_type": "topic",
                "section_number": "12.3",
                "page_start": 253,
                "page_end": 258,
                "summary": "Damped oscillations summary.",
                "source_text": "Source.",
                "difficulty": "intermediate",
            },
        ]
        updated = filler._merge_into_extraction(extraction, new_nodes, [])

        new_uids = updated.node_uids - extraction.node_uids
        assert len(new_uids) == 1
        new_uid = new_uids.pop()
        assert "curriculum:" in new_uid
        assert "damped" in new_uid.lower()

    def test_within_chapter_order_assigned(self):
        extraction = _make_incomplete_extraction()
        filler = GapFiller(MockLLMProvider(), StructuralValidator())

        max_existing = max(n.within_chapter_order for n in extraction.nodes)

        new_nodes = [
            {
                "topic_name": "New Concept A",
                "concept_type": "topic",
                "section_number": "12.3",
                "page_start": 253,
                "page_end": 258,
                "summary": "Summary A.",
                "source_text": "Source A.",
            },
            {
                "topic_name": "New Concept B",
                "concept_type": "definition",
                "section_number": "12.3",
                "page_start": 255,
                "page_end": 256,
                "summary": "Summary B.",
                "source_text": "Source B.",
            },
        ]
        updated = filler._merge_into_extraction(extraction, new_nodes, [])

        new_orders = sorted(
            n.within_chapter_order
            for n in updated.nodes
            if n.within_chapter_order > max_existing
        )
        assert new_orders == [max_existing + 1, max_existing + 2]

    def test_no_duplicate_uids_after_merge(self):
        extraction = _make_incomplete_extraction()
        filler = GapFiller(MockLLMProvider(), StructuralValidator())

        # Try to add a node that would generate same UID as existing
        new_nodes = [
            {
                "topic_name": "Simple Harmonic Motion",  # same name as existing
                "concept_type": "topic",
                "section_number": "12.1",
                "page_start": 239,
                "page_end": 245,
                "summary": "Duplicate.",
                "source_text": "Dup.",
            },
        ]
        updated = filler._merge_into_extraction(extraction, new_nodes, [])

        # Should not have added a duplicate
        assert len(updated.nodes) == len(extraction.nodes)

    def test_relationships_wired(self):
        extraction = _make_incomplete_extraction()
        filler = GapFiller(MockLLMProvider(), StructuralValidator())

        new_nodes = [
            {
                "topic_name": "Damped Oscillations",
                "concept_type": "topic",
                "section_number": "12.3",
                "page_start": 253,
                "page_end": 258,
                "summary": "Summary.",
                "source_text": "Source.",
            },
        ]
        new_rels = [
            {
                "from_node": "Energy in SHM",
                "to_node": "Damped Oscillations",
                "type": "leads_to",
                "label": "leads to",
            },
        ]
        updated = filler._merge_into_extraction(extraction, new_nodes, new_rels)

        assert len(updated.relationships) == 1
        rel = updated.relationships[0]
        assert rel.type == CurriculumRelationType.LEADS_TO


# ---------------------------------------------------------------------------
# TestGapFillLoop
# ---------------------------------------------------------------------------


class TestGapFillLoop:

    def test_fills_all_gaps_in_one_pass(self):
        """All gaps filled by one LLM call → no second retry."""
        # Build extraction that's only missing section 12.3
        nodes = [
            _make_node(
                uid="curriculum:physics:shm:shm",
                topic_name="Simple Harmonic Motion",
                section_number="12.1",
                within_chapter_order=1,
            ),
            _make_node(
                uid="curriculum:physics:shm:displacement",
                topic_name="Displacement (Eq. 12.1)",
                concept_type=ConceptType.FORMULA,
                section_number="12.1",
                summary="x = A sin(ωt + φ). Eq. 12.1.",
                within_chapter_order=2,
                visual_hint="Sine wave",
            ),
            _make_node(
                uid="curriculum:physics:shm:fig1",
                topic_name="SHM Diagram (Figure 12.1)",
                concept_type=ConceptType.VISUALIZATION,
                summary="Figure 12.1.",
                section_number="12.1",
                within_chapter_order=3,
                visual_hint="Diagram",
            ),
            _make_node(
                uid="curriculum:physics:shm:ex1",
                topic_name="Spring Example (Example 12.1)",
                concept_type=ConceptType.EXAMPLE,
                summary="Example 12.1.",
                section_number="12.1",
                within_chapter_order=4,
                visual_hint="FBD",
            ),
            _make_node(
                uid="curriculum:physics:shm:energy",
                topic_name="Energy in SHM",
                section_number="12.2",
                within_chapter_order=5,
            ),
            _make_node(
                uid="curriculum:physics:shm:fig2",
                topic_name="Energy Diagram (Figure 12.2)",
                concept_type=ConceptType.VISUALIZATION,
                summary="Figure 12.2.",
                section_number="12.2",
                within_chapter_order=6,
                visual_hint="Energy curves",
            ),
        ]
        extraction = _make_extraction(nodes)

        # LLM fills section 12.3
        llm = MockLLMProvider([_gap_fill_response_12_3()])
        filler = GapFiller(llm, StructuralValidator())
        result, report = filler.fill_gaps(extraction, ANCHORS_WITH_GAPS, CHAPTER_TEXT)

        # Section 12.3 should now be covered
        section_nums = {n.section_number for n in result.nodes if n.section_number}
        assert "12.3" in section_nums
        assert len(llm.calls) == 1  # only one gap-fill call

    def test_max_retries_downgrades(self):
        """After 2 retries with no progress, completeness errors → warnings."""
        extraction = _make_incomplete_extraction()

        # LLM returns empty both times
        llm = MockLLMProvider([
            '{"nodes": [], "relationships": []}',
            '{"nodes": [], "relationships": []}',
        ])
        filler = GapFiller(llm, StructuralValidator())
        result, report = filler.fill_gaps(extraction, ANCHORS_WITH_GAPS, CHAPTER_TEXT)

        # Completeness errors should be downgraded to warnings
        assert not report.has_completeness_errors()
        # But there should still be warnings
        assert report.warning_count > 0

    def test_no_gaps_no_llm_call(self):
        """If extraction is already complete, no LLM call is made."""
        # Build a complete extraction for ANCHORS_WITH_GAPS
        nodes = [
            _make_node(
                uid="curriculum:physics:shm:shm",
                topic_name="SHM",
                section_number="12.1",
                within_chapter_order=1,
            ),
            _make_node(
                uid="curriculum:physics:shm:eq1",
                topic_name="Eq. 12.1 formula",
                concept_type=ConceptType.FORMULA,
                section_number="12.1",
                summary="x = A sin(ωt + φ). Eq. 12.1.",
                within_chapter_order=2,
                visual_hint="Sine wave",
            ),
            _make_node(
                uid="curriculum:physics:shm:fig1",
                topic_name="Figure 12.1 diagram",
                concept_type=ConceptType.VISUALIZATION,
                section_number="12.1",
                summary="Figure 12.1.",
                within_chapter_order=3,
                visual_hint="Diagram",
            ),
            _make_node(
                uid="curriculum:physics:shm:ex1",
                topic_name="Example 12.1 worked",
                concept_type=ConceptType.EXAMPLE,
                section_number="12.1",
                summary="Example 12.1.",
                within_chapter_order=4,
                visual_hint="FBD",
            ),
            _make_node(
                uid="curriculum:physics:shm:energy",
                topic_name="Energy in SHM",
                section_number="12.2",
                within_chapter_order=5,
            ),
            _make_node(
                uid="curriculum:physics:shm:fig2",
                topic_name="Figure 12.2 energy",
                concept_type=ConceptType.VISUALIZATION,
                section_number="12.2",
                summary="Figure 12.2.",
                within_chapter_order=6,
                visual_hint="Energy",
            ),
            _make_node(
                uid="curriculum:physics:shm:damped",
                topic_name="Damped Oscillations",
                section_number="12.3",
                within_chapter_order=7,
            ),
        ]
        extraction = _make_extraction(nodes)

        llm = MockLLMProvider()
        filler = GapFiller(llm, StructuralValidator())
        result, report = filler.fill_gaps(extraction, ANCHORS_WITH_GAPS, CHAPTER_TEXT)

        assert len(llm.calls) == 0  # no LLM calls needed

    def test_two_passes_needed(self):
        """First pass fills section, second pass fills figure + example."""
        extraction = _make_incomplete_extraction()

        llm = MockLLMProvider([
            _gap_fill_response_12_3(),
            _gap_fill_response_fig_and_example(),
        ])
        filler = GapFiller(llm, StructuralValidator())
        result, report = filler.fill_gaps(extraction, ANCHORS_WITH_GAPS, CHAPTER_TEXT)

        # All sections should be covered
        section_nums = {n.section_number for n in result.nodes if n.section_number}
        assert "12.3" in section_nums

        # Should have called LLM twice
        assert len(llm.calls) == 2


# ---------------------------------------------------------------------------
# TestGapFillEdgeCases
# ---------------------------------------------------------------------------


class TestGapFillEdgeCases:

    def test_llm_invalid_json_graceful(self):
        """Invalid JSON from LLM → skip that round, still retry."""
        extraction = _make_incomplete_extraction()

        llm = MockLLMProvider([
            "this is not json",
            _gap_fill_response_12_3(),
        ])
        filler = GapFiller(llm, StructuralValidator())
        result, report = filler.fill_gaps(extraction, ANCHORS_WITH_GAPS, CHAPTER_TEXT)

        # Should have retried after bad JSON
        assert len(llm.calls) == 2

    def test_empty_llm_response(self):
        """LLM returns empty nodes list → no new nodes merged."""
        extraction = _make_incomplete_extraction()
        original_count = len(extraction.nodes)

        llm = MockLLMProvider(['{"nodes": [], "relationships": []}'])
        filler = GapFiller(llm, StructuralValidator())
        result, report = filler.fill_gaps(extraction, ANCHORS_WITH_GAPS, CHAPTER_TEXT)

        # No new nodes added (but may have retried)
        # After max retries, completeness errors downgraded
        assert not report.has_completeness_errors()

    def test_no_gappable_issues(self):
        """Report has errors but none are completeness — no gap-fill attempted."""
        n1 = _make_node(uid="a", within_chapter_order=1, page_start=260, page_end=239)
        extraction = _make_extraction([n1])

        llm = MockLLMProvider()
        filler = GapFiller(llm, StructuralValidator())
        # Use None anchors → no completeness checks → no gaps
        result, report = filler.fill_gaps(
            extraction, ExtractionAnchors(page_count=0), CHAPTER_TEXT
        )

        assert len(llm.calls) == 0

    def test_gap_filled_nodes_have_metadata_flag(self):
        """Gap-filled nodes get metadata={'gap_filled': True}."""
        extraction = _make_incomplete_extraction()

        llm = MockLLMProvider([_gap_fill_response_12_3()])
        filler = GapFiller(llm, StructuralValidator())
        result, report = filler.fill_gaps(extraction, ANCHORS_WITH_GAPS, CHAPTER_TEXT)

        gap_filled = [n for n in result.nodes if n.metadata.get("gap_filled")]
        assert len(gap_filled) >= 1
