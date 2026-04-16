"""Tests for book-aware chapter extraction — mocked LLM, no API calls."""

from __future__ import annotations

import json

import pytest

from lecture_pipeline.curriculum.anchors.models import (
    ExtractionAnchors,
    SectionAnchor,
)
from lecture_pipeline.curriculum.chapter_extractor import (
    ChapterExtractionError,
    ChapterExtractor,
)
from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    ChapterSummary,
    ConceptType,
    CrossChapterPrerequisite,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ResolutionLevel,
    UnitGrouping,
)
from lecture_pipeline.curriculum.prompts import (
    CURRICULUM_SCHEMA_CONTEXT,
    build_chapter_content_user_prompt,
    build_chapter_structure_user_prompt,
    get_chapter_content_system_prompt,
    get_chapter_structure_system_prompt,
)
from lecture_pipeline.llm.base import LLMProvider, LLMResponse
from lecture_pipeline.pdf.parser import PageContent, PDFContent
from lecture_pipeline.pdf.toc import Chapter


# ---------------------------------------------------------------------------
# Mock LLM provider
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
# Fixtures — BookSkeleton
# ---------------------------------------------------------------------------


SIMPLE_SKELETON = BookSkeleton(
    textbook_title="HC Verma - Concepts of Physics",
    subject="physics",
    total_chapters=3,
    total_pages=400,
    chapters=[
        ChapterSummary(
            chapter_index=1,
            title="Work, Energy and Power",
            page_start=80,
            page_end=100,
            summary="Covers work-energy theorem and conservation of energy.",
            key_concepts=["work", "kinetic energy", "potential energy", "conservation of energy"],
            prerequisites_from=[],
            leads_to=["Simple Harmonic Motion"],
        ),
        ChapterSummary(
            chapter_index=2,
            title="Circular Motion",
            page_start=120,
            page_end=145,
            summary="Covers uniform and non-uniform circular motion.",
            key_concepts=["centripetal force", "angular velocity", "centripetal acceleration"],
            prerequisites_from=[],
            leads_to=["Simple Harmonic Motion"],
        ),
        ChapterSummary(
            chapter_index=3,
            title="Simple Harmonic Motion",
            page_start=239,
            page_end=260,
            summary="Covers SHM, energy analysis, damped and forced oscillations.",
            key_concepts=["SHM", "energy in SHM", "damped oscillations"],
            prerequisites_from=["Work, Energy and Power", "Circular Motion"],
            leads_to=[],
        ),
    ],
    units=[
        UnitGrouping(
            unit_name="Mechanics",
            chapter_indices=[1, 2],
            theme="Forces, motion, energy, and work.",
        ),
        UnitGrouping(
            unit_name="Oscillations",
            chapter_indices=[3],
            theme="Periodic motion and harmonic oscillations.",
        ),
    ],
    cross_chapter_prerequisites=[
        CrossChapterPrerequisite(
            from_chapter="Work, Energy and Power",
            to_chapter="Simple Harmonic Motion",
            reason="Energy conservation is used to derive SHM energy formulas.",
        ),
    ],
    subject_overview="Classical mechanics from kinematics through oscillations.",
)


# ---------------------------------------------------------------------------
# Fixtures — ExtractionAnchors
# ---------------------------------------------------------------------------

SHM_ANCHORS = ExtractionAnchors(
    section_numbers=[
        SectionAnchor(section_number="12.1", title="Simple Harmonic Motion", depth=2),
        SectionAnchor(section_number="12.2", title="Energy in SHM", depth=2),
        SectionAnchor(section_number="12.2.1", title="Kinetic Energy", depth=3),
        SectionAnchor(section_number="12.2.2", title="Potential Energy", depth=3),
        SectionAnchor(section_number="12.3", title="Damped Oscillations", depth=2),
    ],
    equations=["Eq. (12.1)", "Eq. (12.2)", "Eq. (12.3)"],
    figure_refs=["Figure 12.1", "Figure 12.2", "Figure 12.3"],
    example_refs=["Example 12.1", "Example 12.2"],
    defined_terms=["amplitude", "angular frequency"],
    page_count=22,
)


# ---------------------------------------------------------------------------
# Fixtures — Pass A / Pass B JSON responses
# ---------------------------------------------------------------------------

PASS_A_NODES = [
    {
        "topic_name": "Simple Harmonic Motion",
        "concept_type": "topic",
        "resolution_level": "concept",
        "section_number": "12.1",
        "parent": None,
        "page_start": 239,
        "page_end": 245,
        "visual_hint": None,
        "estimated_duration_minutes": 5.0,
    },
    {
        "topic_name": "Displacement in SHM",
        "concept_type": "formula",
        "resolution_level": "detail",
        "section_number": "12.1",
        "parent": "Simple Harmonic Motion",
        "page_start": 240,
        "page_end": 242,
        "visual_hint": "Sine wave showing x = A sin(ωt + φ) with amplitude and phase marked",
        "estimated_duration_minutes": 3.0,
    },
    {
        "topic_name": "Amplitude",
        "concept_type": "definition",
        "resolution_level": "detail",
        "section_number": "12.1",
        "parent": "Simple Harmonic Motion",
        "page_start": 240,
        "page_end": 241,
        "visual_hint": "Sine wave with amplitude A labeled at peak",
        "estimated_duration_minutes": 2.0,
    },
    {
        "topic_name": "Angular Frequency",
        "concept_type": "definition",
        "resolution_level": "detail",
        "section_number": "12.1",
        "parent": "Simple Harmonic Motion",
        "page_start": 241,
        "page_end": 242,
        "visual_hint": None,
        "estimated_duration_minutes": 2.0,
    },
    {
        "topic_name": "Energy in SHM",
        "concept_type": "topic",
        "resolution_level": "concept",
        "section_number": "12.2",
        "parent": None,
        "page_start": 245,
        "page_end": 252,
        "visual_hint": None,
        "estimated_duration_minutes": 5.0,
    },
    {
        "topic_name": "Kinetic Energy in SHM",
        "concept_type": "formula",
        "resolution_level": "detail",
        "section_number": "12.2.1",
        "parent": "Energy in SHM",
        "page_start": 246,
        "page_end": 248,
        "visual_hint": "KE curve as function of displacement, parabolic shape",
        "estimated_duration_minutes": 3.0,
    },
    {
        "topic_name": "Potential Energy in SHM",
        "concept_type": "formula",
        "resolution_level": "detail",
        "section_number": "12.2.2",
        "parent": "Energy in SHM",
        "page_start": 248,
        "page_end": 250,
        "visual_hint": "PE curve as function of displacement, parabolic shape",
        "estimated_duration_minutes": 3.0,
    },
    {
        "topic_name": "SHM Energy Diagram",
        "concept_type": "visualization",
        "resolution_level": "detail",
        "section_number": "12.2",
        "parent": "Energy in SHM",
        "page_start": 250,
        "page_end": 251,
        "visual_hint": "Combined KE + PE + Total energy curves vs displacement",
        "estimated_duration_minutes": 2.0,
    },
    {
        "topic_name": "SHM Displacement Diagram",
        "concept_type": "visualization",
        "resolution_level": "detail",
        "section_number": "12.1",
        "parent": "Simple Harmonic Motion",
        "page_start": 242,
        "page_end": 243,
        "visual_hint": "Spring-mass system showing displacement x from equilibrium",
        "estimated_duration_minutes": 2.0,
    },
    {
        "topic_name": "Energy Conservation in SHM",
        "concept_type": "derivation",
        "resolution_level": "detail",
        "section_number": "12.2",
        "parent": "Energy in SHM",
        "page_start": 250,
        "page_end": 252,
        "visual_hint": "Step-by-step derivation: KE + PE = constant",
        "estimated_duration_minutes": 4.0,
    },
    {
        "topic_name": "Spring-Mass Example",
        "concept_type": "example",
        "resolution_level": "detail",
        "section_number": "12.1",
        "parent": "Simple Harmonic Motion",
        "page_start": 243,
        "page_end": 245,
        "visual_hint": "Free body diagram of mass on spring, forces labeled",
        "estimated_duration_minutes": 4.0,
    },
    {
        "topic_name": "Pendulum as SHM",
        "concept_type": "example",
        "resolution_level": "detail",
        "section_number": "12.2",
        "parent": "Energy in SHM",
        "page_start": 251,
        "page_end": 252,
        "visual_hint": "Simple pendulum with angle θ, forces, and arc length",
        "estimated_duration_minutes": 3.0,
    },
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
    },
    {
        "topic_name": "Damping Force Formula",
        "concept_type": "formula",
        "resolution_level": "detail",
        "section_number": "12.3",
        "parent": "Damped Oscillations",
        "page_start": 254,
        "page_end": 255,
        "visual_hint": "Decaying sine wave with envelope curves showing e^(-bt/2m)",
        "estimated_duration_minutes": 3.0,
    },
    {
        "topic_name": "Car Suspension System",
        "concept_type": "application",
        "resolution_level": "detail",
        "section_number": "12.3",
        "parent": "Damped Oscillations",
        "page_start": 257,
        "page_end": 258,
        "visual_hint": "Spring-damper diagram of car suspension",
        "estimated_duration_minutes": 2.0,
    },
]

PASS_A_RELATIONSHIPS = [
    {
        "from_node": "Simple Harmonic Motion",
        "to_node": "Energy in SHM",
        "type": "leads_to",
        "label": "SHM concepts lead to energy analysis",
    },
    {
        "from_node": "Energy in SHM",
        "to_node": "Damped Oscillations",
        "type": "leads_to",
        "label": "Energy analysis precedes damped systems",
    },
    {
        "from_node": "Displacement in SHM",
        "to_node": "Kinetic Energy in SHM",
        "type": "prerequisite",
        "label": "Must know displacement to derive KE",
    },
    {
        "from_node": "Kinetic Energy in SHM",
        "to_node": "Energy Conservation in SHM",
        "type": "derived_from",
        "label": "Conservation derived from KE + PE",
    },
    {
        "from_node": "Spring-Mass Example",
        "to_node": "Simple Harmonic Motion",
        "type": "example_of",
        "label": "Classic SHM example",
    },
    {
        "from_node": "Car Suspension System",
        "to_node": "Damped Oscillations",
        "type": "application_of",
        "label": "Real-world damped oscillation",
    },
    {
        "from_node": "Simple Harmonic Motion",
        "to_node": "Work, Energy and Power::Conservation of Energy",
        "type": "prerequisite",
        "label": "Uses energy conservation from earlier chapter",
    },
]

VALID_PASS_A_JSON = json.dumps({
    "nodes": PASS_A_NODES,
    "relationships": PASS_A_RELATIONSHIPS,
})


def _make_pass_b_json(node_names: list[str]) -> str:
    """Generate a Pass B response with summaries for the given node names."""
    nodes = []
    for name in node_names:
        nodes.append({
            "topic_name": name,
            "summary": f"Exhaustive teaching summary for {name}. "
                       f"Contains all formulas, derivation steps, and key insights.",
            "source_text": f"Verbatim text from the textbook about {name}.",
            "difficulty": "intermediate",
        })
    return json.dumps({"nodes": nodes})


# Default Pass B covers all nodes from Pass A
VALID_PASS_B_JSON = _make_pass_b_json([n["topic_name"] for n in PASS_A_NODES])


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_mock_llm(*responses: str) -> MockLLMProvider:
    """Create a MockLLMProvider with the given response sequence."""
    return MockLLMProvider(responses=list(responses))


def _make_pdf_content(
    start_page: int = 239,
    end_page: int = 260,
) -> PDFContent:
    """Create a PDFContent with pages covering the SHM chapter."""
    pages = []
    for i in range(1, end_page + 10):
        if start_page <= i <= end_page:
            text = (
                f"Page {i}: This page covers Simple Harmonic Motion concepts. "
                f"12.1 Simple Harmonic Motion\n"
                f"The displacement of a particle in SHM is given by x = A sin(ωt + φ). "
                f"Amplitude is defined as the maximum displacement from equilibrium. "
                f"Figure 12.1 shows the spring-mass system.\n"
                f"Example 12.1: A spring with k=200 N/m...\n"
                f"Eq. (12.1): x = A sin(ωt + φ)\n"
            )
        else:
            text = f"Page {i}: Other content."
        pages.append(PageContent(page_number=i, text=text))
    return PDFContent(
        pages=pages,
        toc_raw=[],
        total_pages=end_page + 10,
        metadata={},
    )


def _make_chapter(
    title: str = "Simple Harmonic Motion",
    start_page: int = 239,
    end_page: int = 260,
) -> Chapter:
    return Chapter(title=title, level=1, start_page=start_page, end_page=end_page)


# ---------------------------------------------------------------------------
# Tests: Chapter Structure Prompts (Pass A)
# ---------------------------------------------------------------------------


class TestChapterStructurePrompts:
    def test_system_prompt_contains_schema_context(self):
        prompt = get_chapter_structure_system_prompt()
        assert "Concept Types" in prompt
        assert "FORMULA" in prompt
        assert "DEFINITION" in prompt
        assert "Relationship Types" in prompt
        assert "PREREQUISITE" in prompt

    def test_system_prompt_contains_output_format(self):
        prompt = get_chapter_structure_system_prompt()
        assert "topic_name" in prompt
        assert "concept_type" in prompt
        assert "section_number" in prompt
        assert "visual_hint" in prompt

    def test_user_prompt_includes_book_skeleton(self):
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=3,
            chapter_text="Some chapter text.",
            anchors=SHM_ANCHORS,
        )
        assert "HC Verma" in prompt
        assert "Simple Harmonic Motion" in prompt
        assert "THIS CHAPTER" in prompt

    def test_user_prompt_includes_anchor_checklist(self):
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=3,
            chapter_text="Some chapter text.",
            anchors=SHM_ANCHORS,
        )
        # Section anchors
        assert "12.1" in prompt
        assert "12.2" in prompt
        assert "12.2.1" in prompt
        assert "extraction floor" in prompt.lower()
        # Figure anchors
        assert "Figure 12.1" in prompt
        assert "VISUALIZATION" in prompt
        # Example anchors
        assert "Example 12.1" in prompt
        # Equation anchors
        assert "Eq. (12.1)" in prompt

    def test_user_prompt_includes_previous_chapter_concepts(self):
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=3,
            chapter_text="Some chapter text.",
            anchors=SHM_ANCHORS,
        )
        # Chapter 2 (Circular Motion) is previous — its key_concepts should appear
        assert "centripetal force" in prompt
        assert "angular velocity" in prompt

    def test_user_prompt_includes_next_chapter_summary(self):
        # Chapter 2 has chapter 3 as next
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=2,
            chapter_text="Some chapter text.",
            anchors=ExtractionAnchors(page_count=10),
        )
        assert "SHM" in prompt or "damped" in prompt.lower()

    def test_user_prompt_first_chapter_no_previous(self):
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=1,
            chapter_text="Some chapter text.",
            anchors=ExtractionAnchors(page_count=10),
        )
        assert "first chapter" in prompt.lower()

    def test_user_prompt_last_chapter_no_next(self):
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=3,
            chapter_text="Some chapter text.",
            anchors=SHM_ANCHORS,
        )
        assert "last chapter" in prompt.lower()

    def test_user_prompt_includes_chapter_text(self):
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=3,
            chapter_text="The displacement is x = A sin(wt).",
            anchors=SHM_ANCHORS,
        )
        assert "x = A sin(wt)" in prompt

    def test_user_prompt_empty_anchors(self):
        prompt = build_chapter_structure_user_prompt(
            skeleton=SIMPLE_SKELETON,
            chapter_index=1,
            chapter_text="Some text.",
            anchors=ExtractionAnchors(page_count=5),
        )
        assert "No structural anchors" in prompt


# ---------------------------------------------------------------------------
# Tests: Chapter Content Prompts (Pass B)
# ---------------------------------------------------------------------------


class TestChapterContentPrompts:
    def test_system_prompt_contains_schema_context(self):
        prompt = get_chapter_content_system_prompt()
        assert "Concept Types" in prompt
        assert "summary" in prompt
        assert "source_text" in prompt

    def test_user_prompt_lists_concepts(self):
        nodes = [
            {"topic_name": "Displacement in SHM", "concept_type": "formula"},
            {"topic_name": "Amplitude", "concept_type": "definition"},
        ]
        prompt = build_chapter_content_user_prompt(
            chapter_text="Chapter text here.",
            nodes_to_enrich=nodes,
            page_start=239,
            page_end=245,
        )
        assert "Displacement in SHM" in prompt
        assert "formula" in prompt
        assert "Amplitude" in prompt
        assert "definition" in prompt
        assert "239" in prompt
        assert "245" in prompt

    def test_user_prompt_includes_chapter_text(self):
        prompt = build_chapter_content_user_prompt(
            chapter_text="The KE of SHM is (1/2)mv².",
            nodes_to_enrich=[{"topic_name": "KE", "concept_type": "formula"}],
            page_start=246,
            page_end=248,
        )
        assert "(1/2)mv²" in prompt

    def test_user_prompt_empty_node_list(self):
        prompt = build_chapter_content_user_prompt(
            chapter_text="Some text.",
            nodes_to_enrich=[],
            page_start=1,
            page_end=5,
        )
        assert "Concepts to Summarize" in prompt


# ---------------------------------------------------------------------------
# Tests: Pass A Extraction
# ---------------------------------------------------------------------------


class TestPassAExtraction:
    def test_extracts_nodes_with_correct_types(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        types = {n.concept_type for n in result.nodes}
        assert ConceptType.TOPIC in types
        assert ConceptType.FORMULA in types
        assert ConceptType.DEFINITION in types
        assert ConceptType.EXAMPLE in types

    def test_extracts_relationships(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert len(result.relationships) > 0
        rel_types = {r.type for r in result.relationships}
        assert CurriculumRelationType.LEADS_TO in rel_types

    def test_invalid_json_retries_then_raises(self):
        llm = _make_mock_llm("not json", "still not json")
        extractor = ChapterExtractor(llm)
        with pytest.raises(ChapterExtractionError, match="invalid JSON"):
            extractor.extract_chapter(
                _make_pdf_content(), _make_chapter(), 3,
                SIMPLE_SKELETON, SHM_ANCHORS, "physics",
            )

    def test_invalid_json_retry_succeeds(self):
        """First attempt fails, second succeeds."""
        llm = _make_mock_llm("not json", VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert len(result.nodes) == len(PASS_A_NODES)

    def test_empty_chapter_text_raises(self):
        pages = [PageContent(page_number=i, text="") for i in range(239, 261)]
        pdf = PDFContent(pages=pages, toc_raw=[], total_pages=260, metadata={})
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        with pytest.raises(ChapterExtractionError, match="Empty text"):
            extractor.extract_chapter(
                pdf, _make_chapter(), 3,
                SIMPLE_SKELETON, SHM_ANCHORS, "physics",
            )

    def test_cross_chapter_references_preserved(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        cross_refs = [
            r for r in result.relationships
            if "::" in r.to_uid
        ]
        assert len(cross_refs) > 0
        assert "Work, Energy and Power::Conservation of Energy" in [
            r.to_uid for r in cross_refs
        ]

    def test_visual_hint_on_formula_nodes(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        formula_nodes = result.nodes_by_type(ConceptType.FORMULA)
        for node in formula_nodes:
            assert node.visual_hint is not None, (
                f"FORMULA node '{node.topic_name}' missing visual_hint"
            )

    def test_section_number_populated(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        nodes_with_section = [n for n in result.nodes if n.section_number]
        assert len(nodes_with_section) > 0
        section_numbers = {n.section_number for n in nodes_with_section}
        assert "12.1" in section_numbers
        assert "12.2" in section_numbers


# ---------------------------------------------------------------------------
# Tests: Pass B Extraction
# ---------------------------------------------------------------------------


class TestPassBExtraction:
    def test_nodes_enriched_with_summaries(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        for node in result.nodes:
            assert node.summary != "", f"Node '{node.topic_name}' has empty summary"

    def test_nodes_enriched_with_source_text(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        for node in result.nodes:
            assert node.source_text != "", f"Node '{node.topic_name}' has empty source_text"

    def test_nodes_enriched_with_difficulty(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        for node in result.nodes:
            assert node.difficulty in (
                Difficulty.BEGINNER,
                Difficulty.INTERMEDIATE,
                Difficulty.ADVANCED,
            )

    def test_batches_nodes_by_page_range(self):
        extractor = ChapterExtractor(_make_mock_llm())
        nodes = [
            {"topic_name": f"Node {i}", "page_start": 240 + i}
            for i in range(20)
        ]
        batches = extractor._batch_nodes_by_page_range(nodes, batch_size=8)
        assert len(batches) == 3  # 20 / 8 = 2.5 → 3 batches
        assert len(batches[0]) == 8
        assert len(batches[1]) == 8
        assert len(batches[2]) == 4

    def test_missing_node_in_pass_b_gets_defaults(self):
        """If Pass B doesn't return a node, it gets empty summary."""
        partial_pass_b = json.dumps({
            "nodes": [
                {
                    "topic_name": "Simple Harmonic Motion",
                    "summary": "SHM summary.",
                    "source_text": "SHM source.",
                    "difficulty": "beginner",
                },
            ]
        })
        llm = _make_mock_llm(VALID_PASS_A_JSON, partial_pass_b)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        shm_node = next(n for n in result.nodes if n.topic_name == "Simple Harmonic Motion")
        assert shm_node.summary == "SHM summary."
        # Other nodes should have empty summary (defaults)
        other = next(n for n in result.nodes if n.topic_name == "Displacement in SHM")
        assert other.summary == ""

    def test_pass_b_invalid_json_raises(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, "not json", "still not json")
        extractor = ChapterExtractor(llm)
        with pytest.raises(ChapterExtractionError, match="invalid JSON"):
            extractor.extract_chapter(
                _make_pdf_content(), _make_chapter(), 3,
                SIMPLE_SKELETON, SHM_ANCHORS, "physics",
            )


# ---------------------------------------------------------------------------
# Tests: Assembly
# ---------------------------------------------------------------------------


class TestAssembly:
    def _extract_result(self) -> CurriculumExtractionResult:
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        return extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )

    def test_generates_stable_uids(self):
        result = self._extract_result()
        for node in result.nodes:
            assert node.uid.startswith("curriculum:physics:simple_harmonic_motion:")

    def test_uid_is_deterministic(self):
        """Same inputs produce same UIDs."""
        result1 = self._extract_result()
        result2 = self._extract_result()
        uids1 = [n.uid for n in result1.nodes]
        uids2 = [n.uid for n in result2.nodes]
        assert uids1 == uids2

    def test_within_chapter_order_sequential(self):
        result = self._extract_result()
        orders = [n.within_chapter_order for n in result.nodes]
        assert orders == list(range(1, len(result.nodes) + 1))

    def test_chapter_order_set(self):
        result = self._extract_result()
        for node in result.nodes:
            assert node.chapter_order == 3

    def test_global_teaching_order_computed(self):
        result = self._extract_result()
        for node in result.nodes:
            expected = 3 * 1000 + node.within_chapter_order
            assert node.global_teaching_order == expected

    def test_relationships_use_uids(self):
        result = self._extract_result()
        node_uids = result.node_uids
        for rel in result.relationships:
            # from_uid should always be a real UID
            assert rel.from_uid in node_uids
            # to_uid is either a real UID or a cross-chapter ref
            if "::" not in rel.to_uid:
                assert rel.to_uid in node_uids

    def test_parent_uid_and_children_uids_wired(self):
        result = self._extract_result()
        # "Displacement in SHM" should have parent = "Simple Harmonic Motion"
        displacement = next(
            n for n in result.nodes if n.topic_name == "Displacement in SHM"
        )
        shm = next(
            n for n in result.nodes if n.topic_name == "Simple Harmonic Motion"
        )
        assert displacement.parent_uid == shm.uid
        assert displacement.uid in shm.children_uids

    def test_produces_valid_extraction_result(self):
        result = self._extract_result()
        assert isinstance(result, CurriculumExtractionResult)
        assert result.scope == "chapter"
        assert result.chapter_title == "Simple Harmonic Motion"
        assert result.subject == "physics"
        assert result.textbook_title == "HC Verma - Concepts of Physics"
        assert len(result.nodes) == len(PASS_A_NODES)
        assert len(result.relationships) > 0

    def test_relationship_dedup(self):
        """Duplicate relationships should not appear."""
        result = self._extract_result()
        keys = [r.relationship_key for r in result.relationships]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Tests: Full Integration
# ---------------------------------------------------------------------------


class TestExtractChapterIntegration:
    def test_full_pipeline(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert result.scope == "chapter"
        assert result.chapter_title == "Simple Harmonic Motion"
        assert len(result.nodes) == 15
        assert len(result.relationships) > 0

    def test_source_metadata(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert result.source.textbook_title == "HC Verma - Concepts of Physics"
        assert result.source.chapter_title == "Simple Harmonic Motion"
        assert result.source.page_range == "239-260"
        assert result.source.extractor_model == "mock-model"
        assert result.source.extraction_timestamp  # non-empty

    def test_llm_call_count(self):
        """1 call for Pass A + ceil(15/8) = 2 calls for Pass B = 3 total."""
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        # 1 (Pass A) + 2 (Pass B: 15 nodes / 8 per batch = 2 batches)
        assert len(llm.calls) == 3

    def test_book_skeleton_attached(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert result.book_skeleton is not None
        assert result.book_skeleton.textbook_title == "HC Verma - Concepts of Physics"

    def test_json_serialization_roundtrip(self):
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        json_str = result.to_json()
        loaded = CurriculumExtractionResult.from_json(json_str)
        assert len(loaded.nodes) == len(result.nodes)
        assert len(loaded.relationships) == len(result.relationships)


# ---------------------------------------------------------------------------
# Tests: Edge Cases & Parsing
# ---------------------------------------------------------------------------


class TestParsingHelpers:
    def test_parse_unknown_concept_type_defaults_to_topic(self):
        assert ChapterExtractor._parse_concept_type("unknown") == ConceptType.TOPIC

    def test_parse_valid_concept_types(self):
        assert ChapterExtractor._parse_concept_type("formula") == ConceptType.FORMULA
        assert ChapterExtractor._parse_concept_type("DEFINITION") == ConceptType.DEFINITION

    def test_parse_unknown_resolution_defaults_to_concept(self):
        assert ChapterExtractor._parse_resolution_level("x") == ResolutionLevel.CONCEPT

    def test_parse_valid_resolution_levels(self):
        assert ChapterExtractor._parse_resolution_level("detail") == ResolutionLevel.DETAIL
        assert ChapterExtractor._parse_resolution_level("CONCEPT") == ResolutionLevel.CONCEPT

    def test_parse_unknown_difficulty_defaults_to_intermediate(self):
        assert ChapterExtractor._parse_difficulty("x") == Difficulty.INTERMEDIATE

    def test_parse_valid_difficulties(self):
        assert ChapterExtractor._parse_difficulty("beginner") == Difficulty.BEGINNER
        assert ChapterExtractor._parse_difficulty("ADVANCED") == Difficulty.ADVANCED

    def test_parse_unknown_relationship_returns_none(self):
        assert ChapterExtractor._parse_relationship_type("fake") is None

    def test_parse_valid_relationship_types(self):
        assert (
            ChapterExtractor._parse_relationship_type("prerequisite")
            == CurriculumRelationType.PREREQUISITE
        )
        assert (
            ChapterExtractor._parse_relationship_type("LEADS_TO")
            == CurriculumRelationType.LEADS_TO
        )


class TestEdgeCases:
    def test_pass_a_nodes_not_a_list_raises(self):
        bad_json = json.dumps({"nodes": "not a list", "relationships": []})
        llm = _make_mock_llm(bad_json)
        extractor = ChapterExtractor(llm)
        with pytest.raises(ChapterExtractionError, match="not a list"):
            extractor.extract_chapter(
                _make_pdf_content(), _make_chapter(), 3,
                SIMPLE_SKELETON, SHM_ANCHORS, "physics",
            )

    def test_empty_nodes_produces_empty_result(self):
        empty = json.dumps({"nodes": [], "relationships": []})
        llm = _make_mock_llm(empty)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert len(result.nodes) == 0
        assert len(result.relationships) == 0

    def test_relationship_with_missing_from_node_skipped(self):
        """If from_node doesn't match any node, relationship is dropped."""
        pass_a = json.dumps({
            "nodes": [{"topic_name": "NodeA", "concept_type": "topic",
                        "resolution_level": "concept", "page_start": 240,
                        "page_end": 245}],
            "relationships": [{
                "from_node": "NonExistent",
                "to_node": "NodeA",
                "type": "leads_to",
                "label": "test",
            }],
        })
        llm = _make_mock_llm(pass_a, '{"nodes": []}')
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert len(result.relationships) == 0

    def test_invalid_relationship_type_skipped(self):
        pass_a = json.dumps({
            "nodes": [
                {"topic_name": "A", "concept_type": "topic",
                 "resolution_level": "concept", "page_start": 240, "page_end": 245},
                {"topic_name": "B", "concept_type": "topic",
                 "resolution_level": "concept", "page_start": 245, "page_end": 250},
            ],
            "relationships": [{
                "from_node": "A",
                "to_node": "B",
                "type": "INVALID_TYPE",
                "label": "test",
            }],
        })
        llm = _make_mock_llm(pass_a, '{"nodes": []}')
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        assert len(result.relationships) == 0

    def test_model_name_from_llm_config(self):
        """When LLM has a config, model name is captured in source metadata."""
        llm = _make_mock_llm(VALID_PASS_A_JSON, VALID_PASS_B_JSON)
        extractor = ChapterExtractor(llm)
        result = extractor.extract_chapter(
            _make_pdf_content(), _make_chapter(), 3,
            SIMPLE_SKELETON, SHM_ANCHORS, "physics",
        )
        # MockLLMProvider has no config, so model_name = "unknown"
        # but the LLMResponse model is "mock-model"
        assert result.source.extractor_model is not None
