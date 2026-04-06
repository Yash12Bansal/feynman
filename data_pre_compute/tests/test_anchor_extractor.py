"""Tests for deterministic anchor extraction — regex-based, no LLM calls."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.anchors.anchor_extractor import (
    DeterministicAnchorExtractor,
)
from lecture_pipeline.curriculum.anchors.models import (
    ExtractionAnchors,
    SectionAnchor,
)
from lecture_pipeline.pdf.parser import PageContent, PDFContent
from lecture_pipeline.pdf.toc import Chapter


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

PHYSICS_CHAPTER_TEXT = """\
12 SIMPLE HARMONIC MOTION

12.1 Introduction to Oscillations
Oscillatory motion is one of the most important types of motion in physics.
Any motion that repeats itself at regular intervals is called periodic motion.
Simple harmonic motion is defined as oscillatory motion in which the
restoring force is proportional to the displacement.

12.1.1 Terminology and Definitions
The amplitude A is defined as the maximum displacement from equilibrium.
Angular frequency is defined as the rate of change of phase angle.
The period T is called the time for one complete oscillation.

See Fig. 12.1 for a diagram of simple harmonic motion.

12.1.2 Mathematical Description
The displacement in SHM is given by x = A cos(wt + phi).
This is Eq. (12.1), the fundamental equation of SHM.
See also Equation 12.2 for the velocity equation.

Example 12.1 A spring with constant k = 200 N/m supports a 2 kg mass.
Find the period of oscillation.

12.2 Energy in Simple Harmonic Motion
The potential energy of a spring is given by Eq. (12.3).
Figure 12.2 shows the energy diagram for a spring-mass system.

12.2.1 Potential Energy in SHM
We define the elastic potential energy as U = 1/2 kx^2.

12.2.2 Kinetic Energy in SHM
The kinetic energy K = 1/2 mv^2 follows from Eq. (12.4).
Worked Example 3.2 demonstrates energy conservation in SHM.

FIGURE 12.3 Energy diagram for SHM showing KE and PE curves.

Sample Problem 5.3 A block oscillates on a spring with amplitude 0.1 m.
"""


def _make_pdf_content(texts: list[str] | None = None) -> PDFContent:
    """Create a minimal PDFContent from page text strings."""
    if texts is None:
        texts = [PHYSICS_CHAPTER_TEXT]
    pages = []
    for i, text in enumerate(texts, 1):
        pages.append(PageContent(page_number=i, text=text))
    return PDFContent(
        pages=pages,
        toc_raw=[],
        total_pages=len(pages),
        metadata={},
    )


def _make_chapter(start: int = 1, end: int = 1) -> Chapter:
    return Chapter(title="Test Chapter", level=1, start_page=start, end_page=end)


# ---------------------------------------------------------------------------
# Tests: SectionAnchor model
# ---------------------------------------------------------------------------


class TestSectionAnchorModel:
    def test_basic_fields(self):
        a = SectionAnchor(section_number="12.1", title="Energy Analysis", depth=2)
        assert a.section_number == "12.1"
        assert a.title == "Energy Analysis"
        assert a.depth == 2

    def test_depth_three_level(self):
        a = SectionAnchor(section_number="12.1.1", title="Sub", depth=3)
        assert a.depth == 3


# ---------------------------------------------------------------------------
# Tests: ExtractionAnchors model
# ---------------------------------------------------------------------------


class TestExtractionAnchorsModel:
    def test_smallest_section_depth_mixed(self):
        anchors = ExtractionAnchors(
            section_numbers=[
                SectionAnchor(section_number="12.1", title="A", depth=2),
                SectionAnchor(section_number="12.1.1", title="B", depth=3),
            ]
        )
        assert anchors.smallest_section_depth == 3

    def test_smallest_section_depth_empty(self):
        anchors = ExtractionAnchors()
        assert anchors.smallest_section_depth == 0

    def test_leaf_sections(self):
        anchors = ExtractionAnchors(
            section_numbers=[
                SectionAnchor(section_number="12.1", title="A", depth=2),
                SectionAnchor(section_number="12.1.1", title="B", depth=3),
                SectionAnchor(section_number="12.1.2", title="C", depth=3),
                SectionAnchor(section_number="12.2", title="D", depth=2),
            ]
        )
        leaves = anchors.leaf_sections
        leaf_nums = {s.section_number for s in leaves}
        # 12.1 is NOT a leaf (has 12.1.1 and 12.1.2 children)
        # 12.1.1, 12.1.2, 12.2 ARE leaves
        assert leaf_nums == {"12.1.1", "12.1.2", "12.2"}

    def test_leaf_sections_all_same_depth(self):
        anchors = ExtractionAnchors(
            section_numbers=[
                SectionAnchor(section_number="12.1", title="A", depth=2),
                SectionAnchor(section_number="12.2", title="B", depth=2),
            ]
        )
        assert len(anchors.leaf_sections) == 2

    def test_leaf_sections_empty(self):
        anchors = ExtractionAnchors()
        assert anchors.leaf_sections == []

    def test_is_empty_true(self):
        anchors = ExtractionAnchors()
        assert anchors.is_empty is True

    def test_is_empty_false(self):
        anchors = ExtractionAnchors(figure_refs=["Figure 1"])
        assert anchors.is_empty is False

    def test_total_anchor_count(self):
        anchors = ExtractionAnchors(
            section_numbers=[SectionAnchor(section_number="1.1", title="A", depth=2)],
            equations=["Eq. (1)", "Eq. (2)"],
            figure_refs=["Figure 1"],
            example_refs=["Example 1"],
            defined_terms=["amplitude"],
        )
        assert anchors.total_anchor_count == 6

    def test_summary_with_anchors(self):
        anchors = ExtractionAnchors(
            section_numbers=[SectionAnchor(section_number="1.1", title="A", depth=2)],
            figure_refs=["Figure 1"],
            page_count=5,
        )
        s = anchors.summary()
        assert "1 sections" in s
        assert "1 figures" in s
        assert "5 pages" in s

    def test_summary_empty(self):
        assert ExtractionAnchors().summary() == "No anchors found"

    def test_json_round_trip(self):
        anchors = ExtractionAnchors(
            section_numbers=[
                SectionAnchor(section_number="12.1", title="Energy", depth=2),
            ],
            equations=["Eq. (12.1)"],
            figure_refs=["Figure 12.1"],
            page_count=10,
        )
        json_str = anchors.model_dump_json()
        restored = ExtractionAnchors.model_validate_json(json_str)
        assert restored.section_numbers[0].section_number == "12.1"
        assert restored.equations == ["Eq. (12.1)"]
        assert restored.figure_refs == ["Figure 12.1"]


# ---------------------------------------------------------------------------
# Tests: _find_section_numbers
# ---------------------------------------------------------------------------


class TestFindSectionNumbers:
    def setup_method(self):
        self.extractor = DeterministicAnchorExtractor()

    def test_two_level_sections(self):
        text = "12.1 Energy Analysis\nSome content here.\n12.2 Force Analysis\n"
        sections = self.extractor._find_section_numbers(text)
        assert len(sections) == 2
        assert sections[0].section_number == "12.1"
        assert sections[0].title == "Energy Analysis"
        assert sections[0].depth == 2
        assert sections[1].section_number == "12.2"

    def test_three_level_sections(self):
        text = "12.1.1 Potential Energy in SHM\nContent.\n12.1.2 Kinetic Energy\n"
        sections = self.extractor._find_section_numbers(text)
        assert len(sections) == 2
        assert sections[0].section_number == "12.1.1"
        assert sections[0].depth == 3

    def test_mixed_depth(self):
        text = (
            "12.1 Energy in SHM\nContent.\n"
            "12.1.1 Potential Energy\nMore content.\n"
            "12.1.2 Kinetic Energy\nMore content.\n"
            "12.2 Damped Oscillations\n"
        )
        sections = self.extractor._find_section_numbers(text)
        nums = [s.section_number for s in sections]
        assert nums == ["12.1", "12.1.1", "12.1.2", "12.2"]

    def test_dedup_prevents_3level_as_2level(self):
        """'12.1.1 Title' should NOT produce a spurious '12.1' match."""
        text = "12.1.1 Potential Energy in SHM\n"
        sections = self.extractor._find_section_numbers(text)
        nums = [s.section_number for s in sections]
        assert "12.1" not in nums
        assert "12.1.1" in nums

    def test_sorting(self):
        text = (
            "12.2 Second Section\n"
            "12.1 First Section\n"
            "12.1.1 Sub Section\n"
        )
        sections = self.extractor._find_section_numbers(text)
        nums = [s.section_number for s in sections]
        assert nums == ["12.1", "12.1.1", "12.2"]

    def test_no_sections(self):
        text = "This is just body text with no section numbers at all."
        sections = self.extractor._find_section_numbers(text)
        assert sections == []

    def test_inline_reference_not_matched(self):
        """Mid-line 'see section 12.1 for details' should not match."""
        text = "Please see section 12.1 for more details on this topic."
        sections = self.extractor._find_section_numbers(text)
        assert sections == []

    def test_page_number_not_matched(self):
        """Bare '245' at start of line without uppercase title should not match."""
        text = "245\nSome content on the next line."
        sections = self.extractor._find_section_numbers(text)
        assert sections == []

    def test_title_must_start_uppercase(self):
        """'12.1 some lowercase thing' should not match."""
        text = "12.1 some lowercase heading\n"
        sections = self.extractor._find_section_numbers(text)
        assert sections == []

    def test_leading_whitespace_tolerated(self):
        text = "  12.1 Energy Analysis\n"
        sections = self.extractor._find_section_numbers(text)
        assert len(sections) == 1
        assert sections[0].section_number == "12.1"

    def test_letter_subsections(self):
        text = "12.1a Electric Potential Energy\nContent.\n12.1b Magnetic Energy\n"
        sections = self.extractor._find_section_numbers(text)
        assert len(sections) == 2
        assert sections[0].section_number == "12.1a"
        assert sections[1].section_number == "12.1b"

    def test_duplicate_section_number_kept_once(self):
        """Same section appearing twice (e.g. header + footer) -> only one anchor."""
        text = "12.1 Energy Analysis\nContent.\n12.1 Energy Analysis\n"
        sections = self.extractor._find_section_numbers(text)
        assert len(sections) == 1


# ---------------------------------------------------------------------------
# Tests: _find_figure_references
# ---------------------------------------------------------------------------


class TestFindFigureReferences:
    def setup_method(self):
        self.extractor = DeterministicAnchorExtractor()

    def test_fig_dot_number(self):
        text = "As shown in Fig. 12.3, the motion is periodic."
        refs = self.extractor._find_figure_references(text)
        assert refs == ["Figure 12.3"]

    def test_figure_spelled_out(self):
        text = "Figure 5 shows the energy diagram."
        refs = self.extractor._find_figure_references(text)
        assert refs == ["Figure 5"]

    def test_figure_all_caps(self):
        text = "FIGURE 12.3 Energy diagram for SHM."
        refs = self.extractor._find_figure_references(text)
        assert refs == ["Figure 12.3"]

    def test_subfigure(self):
        text = "See Fig. 5.2a for the potential energy curve."
        refs = self.extractor._find_figure_references(text)
        assert refs == ["Figure 5.2a"]

    def test_dedup(self):
        text = "See Fig. 12.1. Later, Figure 12.1 shows more detail."
        refs = self.extractor._find_figure_references(text)
        assert refs == ["Figure 12.1"]

    def test_no_figures(self):
        text = "This text has no figure references at all."
        refs = self.extractor._find_figure_references(text)
        assert refs == []

    def test_figure_word_in_prose(self):
        """'we figure out the answer' should not match (no digit follows)."""
        text = "We need to figure out the answer to this problem."
        refs = self.extractor._find_figure_references(text)
        assert refs == []

    def test_multiple_sorted(self):
        text = "See Fig. 12.3 and Fig. 12.1 and Fig. 2.1."
        refs = self.extractor._find_figure_references(text)
        assert refs == ["Figure 2.1", "Figure 12.1", "Figure 12.3"]


# ---------------------------------------------------------------------------
# Tests: _find_example_references
# ---------------------------------------------------------------------------


class TestFindExampleReferences:
    def setup_method(self):
        self.extractor = DeterministicAnchorExtractor()

    def test_example_basic(self):
        text = "Example 12.1 A spring supports a mass."
        refs = self.extractor._find_example_references(text)
        assert refs == ["Example 12.1"]

    def test_example_caps(self):
        text = "EXAMPLE 5 Find the velocity."
        refs = self.extractor._find_example_references(text)
        assert refs == ["Example 5"]

    def test_worked_example(self):
        text = "Worked Example 3.2 demonstrates conservation."
        refs = self.extractor._find_example_references(text)
        assert refs == ["Example 3.2"]

    def test_sample_problem(self):
        text = "Sample Problem 5.3 A block oscillates."
        refs = self.extractor._find_example_references(text)
        assert refs == ["Example 5.3"]

    def test_dedup(self):
        text = "See Example 12.1. In Example 12.1 we showed..."
        refs = self.extractor._find_example_references(text)
        assert refs == ["Example 12.1"]

    def test_no_examples(self):
        text = "No examples here, just theory."
        refs = self.extractor._find_example_references(text)
        assert refs == []


# ---------------------------------------------------------------------------
# Tests: _find_equations
# ---------------------------------------------------------------------------


class TestFindEquations:
    def setup_method(self):
        self.extractor = DeterministicAnchorExtractor()

    def test_eq_dot_with_parens(self):
        text = "From Eq. (3.5) we can derive the velocity."
        refs = self.extractor._find_equations(text)
        assert refs == ["Eq. (3.5)"]

    def test_eq_dot_no_parens(self):
        text = "Using Eq. 3.5 for the displacement."
        refs = self.extractor._find_equations(text)
        assert refs == ["Eq. (3.5)"]

    def test_equation_spelled_out(self):
        text = "Equation 12 gives us the general solution."
        refs = self.extractor._find_equations(text)
        assert refs == ["Eq. (12)"]

    def test_equation_with_parens(self):
        text = "See Equation (12.3) for the energy formula."
        refs = self.extractor._find_equations(text)
        assert refs == ["Eq. (12.3)"]

    def test_dedup(self):
        text = "From Eq. (12.1) and later Eq. (12.1) again."
        refs = self.extractor._find_equations(text)
        assert refs == ["Eq. (12.1)"]

    def test_no_equations(self):
        text = "This text discusses concepts without equation references."
        refs = self.extractor._find_equations(text)
        assert refs == []

    def test_multiple_sorted(self):
        text = "From Eq. (12.4) and Eq. (12.1) and Eq. (3.2)."
        refs = self.extractor._find_equations(text)
        assert refs == ["Eq. (3.2)", "Eq. (12.1)", "Eq. (12.4)"]


# ---------------------------------------------------------------------------
# Tests: _find_defined_terms
# ---------------------------------------------------------------------------


class TestFindDefinedTerms:
    def setup_method(self):
        self.extractor = DeterministicAnchorExtractor()

    def test_is_defined_as(self):
        text = "Simple harmonic motion is defined as oscillatory motion."
        terms = self.extractor._find_defined_terms(text)
        assert any("harmonic motion" in t.lower() for t in terms)

    def test_is_called(self):
        text = ". Angular frequency is called the natural frequency of the system."
        terms = self.extractor._find_defined_terms(text)
        assert any("angular frequency" in t.lower() for t in terms)

    def test_definition_header(self):
        text = "Definition: Simple Harmonic Motion is periodic motion."
        terms = self.extractor._find_defined_terms(text)
        assert len(terms) >= 1

    def test_we_define(self):
        text = "We define the period as the time for one complete cycle."
        terms = self.extractor._find_defined_terms(text)
        assert any("period" in t.lower() for t in terms)

    def test_too_short_filtered(self):
        text = "We define xy as something."
        terms = self.extractor._find_defined_terms(text)
        assert all(len(t) >= 3 for t in terms)

    def test_dedup_case_insensitive(self):
        text = (
            ". Amplitude is defined as the maximum displacement. "
            ". Amplitude is called the peak value."
        )
        terms = self.extractor._find_defined_terms(text)
        amp_count = sum(1 for t in terms if "amplitude" in t.lower())
        assert amp_count <= 1

    def test_no_definitions(self):
        text = "The block moves to the right and then returns."
        terms = self.extractor._find_defined_terms(text)
        assert terms == []


# ---------------------------------------------------------------------------
# Tests: extract_anchors (full integration)
# ---------------------------------------------------------------------------


class TestExtractAnchors:
    def setup_method(self):
        self.extractor = DeterministicAnchorExtractor()

    def test_physics_chapter_all_categories(self):
        anchors = self.extractor.extract_anchors(PHYSICS_CHAPTER_TEXT, [None] * 5)
        # Sections
        assert len(anchors.section_numbers) >= 4  # 12.1, 12.1.1, 12.1.2, 12.2, 12.2.1, 12.2.2
        nums = {s.section_number for s in anchors.section_numbers}
        assert "12.1" in nums
        assert "12.1.1" in nums
        assert "12.2" in nums
        # Figures
        assert len(anchors.figure_refs) >= 3  # Fig. 12.1, Figure 12.2, FIGURE 12.3
        assert "Figure 12.1" in anchors.figure_refs
        # Examples
        assert len(anchors.example_refs) >= 1  # Example 12.1
        assert "Example 12.1" in anchors.example_refs
        # Equations
        assert len(anchors.equations) >= 2  # Eq. (12.1), Equation 12.2, Eq. (12.3), Eq. (12.4)
        # Page count
        assert anchors.page_count == 5
        # Not empty
        assert not anchors.is_empty

    def test_empty_text(self):
        anchors = self.extractor.extract_anchors("", [])
        assert anchors.is_empty
        assert anchors.page_count == 0

    def test_whitespace_only(self):
        anchors = self.extractor.extract_anchors("   \n\n  ", [None])
        assert anchors.is_empty
        assert anchors.page_count == 1

    def test_text_with_no_structure(self):
        text = "This is just a paragraph of text about physics. Nothing structured."
        anchors = self.extractor.extract_anchors(text, [None])
        assert anchors.section_numbers == []
        assert anchors.figure_refs == []
        assert anchors.example_refs == []


# ---------------------------------------------------------------------------
# Tests: extract_for_chapter (convenience method)
# ---------------------------------------------------------------------------


class TestExtractForChapter:
    def test_wires_correctly(self):
        pdf = _make_pdf_content([PHYSICS_CHAPTER_TEXT])
        chapter = _make_chapter(start=1, end=1)
        extractor = DeterministicAnchorExtractor()
        anchors = extractor.extract_for_chapter(pdf, chapter)
        assert not anchors.is_empty
        assert anchors.page_count == 1
        assert len(anchors.section_numbers) >= 4

    def test_multi_page_chapter(self):
        page1 = "12.1 Introduction\nSome content about Fig. 12.1."
        page2 = "12.2 Energy Analysis\nSee Eq. (12.1) and Example 12.1."
        pdf = _make_pdf_content([page1, page2])
        chapter = _make_chapter(start=1, end=2)
        extractor = DeterministicAnchorExtractor()
        anchors = extractor.extract_for_chapter(pdf, chapter)
        assert anchors.page_count == 2
        nums = {s.section_number for s in anchors.section_numbers}
        assert "12.1" in nums
        assert "12.2" in nums

    def test_empty_pages(self):
        pdf = _make_pdf_content([""])
        chapter = _make_chapter(start=1, end=1)
        extractor = DeterministicAnchorExtractor()
        anchors = extractor.extract_for_chapter(pdf, chapter)
        assert anchors.is_empty
