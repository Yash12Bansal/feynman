"""Tests for structural validation of curriculum extraction results."""

from __future__ import annotations

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
from lecture_pipeline.curriculum.validation.models import (
    COMPLETENESS_ISSUE_CODES,
    ValidationReport,
)
from lecture_pipeline.curriculum.validation.structural import StructuralValidator


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_node(
    uid: str = "curriculum:physics:shm:test_concept",
    topic_name: str = "Test Concept",
    concept_type: ConceptType = ConceptType.TOPIC,
    section_number: str | None = "12.1",
    summary: str = "A test concept summary.",
    page_start: int = 239,
    page_end: int = 245,
    chapter_order: int = 3,
    within_chapter_order: int = 1,
    visual_hint: str | None = None,
    parent_uid: str | None = None,
    children_uids: list[str] | None = None,
    **kwargs,
) -> ExtractionNode:
    return ExtractionNode(
        uid=uid,
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=ResolutionLevel.CONCEPT,
        section_number=section_number,
        summary=summary,
        source_text="Some source text.",
        page_start=page_start,
        page_end=page_end,
        chapter_order=chapter_order,
        within_chapter_order=within_chapter_order,
        difficulty=Difficulty.INTERMEDIATE,
        visual_hint=visual_hint,
        parent_uid=parent_uid,
        children_uids=children_uids or [],
        **kwargs,
    )


def _make_rel(
    from_uid: str,
    to_uid: str,
    rel_type: CurriculumRelationType = CurriculumRelationType.LEADS_TO,
    key: str | None = None,
) -> ExtractionRelationship:
    key = key or f"rel:{rel_type.value}:{from_uid}:{to_uid}"
    return ExtractionRelationship(
        relationship_key=key,
        type=rel_type,
        from_uid=from_uid,
        to_uid=to_uid,
        label="test",
    )


def _make_extraction(
    nodes: list[ExtractionNode] | None = None,
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
        nodes=nodes or [],
        relationships=rels or [],
    )


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


def _make_valid_extraction() -> CurriculumExtractionResult:
    """Build a valid extraction that passes all checks against SHM_ANCHORS."""
    nodes = [
        _make_node(
            uid="curriculum:physics:shm:shm",
            topic_name="Simple Harmonic Motion",
            section_number="12.1",
            page_start=239, page_end=245,
            within_chapter_order=1,
            children_uids=[
                "curriculum:physics:shm:displacement",
                "curriculum:physics:shm:shm_diagram",
                "curriculum:physics:shm:spring_example",
            ],
        ),
        _make_node(
            uid="curriculum:physics:shm:displacement",
            topic_name="Displacement in SHM (Eq. 12.1)",
            concept_type=ConceptType.FORMULA,
            section_number="12.1",
            summary="x = A sin(ωt + φ) where A is amplitude, ω is angular frequency. Eq. 12.1.",
            page_start=240, page_end=242,
            within_chapter_order=2,
            visual_hint="Sine wave with amplitude marked",
            parent_uid="curriculum:physics:shm:shm",
        ),
        _make_node(
            uid="curriculum:physics:shm:shm_diagram",
            topic_name="SHM Displacement Diagram (Figure 12.1)",
            concept_type=ConceptType.VISUALIZATION,
            section_number="12.1",
            summary="Diagram showing spring-mass system displacement. Figure 12.1.",
            page_start=242, page_end=243,
            within_chapter_order=3,
            visual_hint="Spring-mass system diagram",
            parent_uid="curriculum:physics:shm:shm",
        ),
        _make_node(
            uid="curriculum:physics:shm:spring_example",
            topic_name="Spring-Mass Example (Example 12.1)",
            concept_type=ConceptType.EXAMPLE,
            section_number="12.1",
            summary="Worked example calculating period of spring-mass. Example 12.1.",
            page_start=243, page_end=245,
            within_chapter_order=4,
            visual_hint="Free body diagram of mass on spring",
            parent_uid="curriculum:physics:shm:shm",
        ),
        _make_node(
            uid="curriculum:physics:shm:energy",
            topic_name="Energy in SHM",
            section_number="12.2",
            page_start=245, page_end=252,
            within_chapter_order=5,
            children_uids=[
                "curriculum:physics:shm:ke",
                "curriculum:physics:shm:pe",
                "curriculum:physics:shm:energy_diagram",
                "curriculum:physics:shm:derivation",
                "curriculum:physics:shm:pendulum",
            ],
        ),
        _make_node(
            uid="curriculum:physics:shm:ke",
            topic_name="Kinetic Energy in SHM (Eq. 12.2)",
            concept_type=ConceptType.FORMULA,
            section_number="12.2.1",
            summary="KE = ½mv² = ½mω²(A²-x²). Eq. 12.2.",
            page_start=246, page_end=248,
            within_chapter_order=6,
            visual_hint="KE curve vs displacement",
            parent_uid="curriculum:physics:shm:energy",
        ),
        _make_node(
            uid="curriculum:physics:shm:pe",
            topic_name="Potential Energy in SHM (Eq. 12.3)",
            concept_type=ConceptType.FORMULA,
            section_number="12.2.2",
            summary="PE = ½kx² = ½mω²x². Eq. 12.3.",
            page_start=248, page_end=250,
            within_chapter_order=7,
            visual_hint="PE curve vs displacement",
            parent_uid="curriculum:physics:shm:energy",
        ),
        _make_node(
            uid="curriculum:physics:shm:energy_diagram",
            topic_name="SHM Energy Diagram (Figure 12.2)",
            concept_type=ConceptType.VISUALIZATION,
            section_number="12.2",
            summary="Combined KE + PE + Total energy curves. Figure 12.2.",
            page_start=250, page_end=251,
            within_chapter_order=8,
            visual_hint="Combined energy curves",
            parent_uid="curriculum:physics:shm:energy",
        ),
        _make_node(
            uid="curriculum:physics:shm:derivation",
            topic_name="Energy Conservation in SHM",
            concept_type=ConceptType.DERIVATION,
            section_number="12.2",
            summary="Derivation: KE + PE = constant. E = ½mω²A².",
            page_start=250, page_end=252,
            within_chapter_order=9,
            visual_hint="Step-by-step derivation: KE + PE = constant",
            parent_uid="curriculum:physics:shm:energy",
        ),
        _make_node(
            uid="curriculum:physics:shm:pendulum",
            topic_name="Pendulum as SHM (Example 12.2)",
            concept_type=ConceptType.EXAMPLE,
            section_number="12.2",
            summary="Simple pendulum approximation. Example 12.2.",
            page_start=251, page_end=252,
            within_chapter_order=10,
            visual_hint="Simple pendulum with angle θ",
            parent_uid="curriculum:physics:shm:energy",
        ),
        _make_node(
            uid="curriculum:physics:shm:damped",
            topic_name="Damped Oscillations",
            section_number="12.3",
            page_start=253, page_end=258,
            within_chapter_order=11,
            children_uids=[
                "curriculum:physics:shm:damping_formula",
                "curriculum:physics:shm:damped_diagram",
            ],
        ),
        _make_node(
            uid="curriculum:physics:shm:damping_formula",
            topic_name="Damping Force Formula",
            concept_type=ConceptType.FORMULA,
            section_number="12.3",
            summary="F = -bv, leading to x = Ae^(-bt/2m)sin(ω't + φ).",
            page_start=254, page_end=255,
            within_chapter_order=12,
            visual_hint="Decaying sine wave with envelope",
            parent_uid="curriculum:physics:shm:damped",
        ),
        _make_node(
            uid="curriculum:physics:shm:damped_diagram",
            topic_name="Damped Oscillation Diagram (Figure 12.3)",
            concept_type=ConceptType.VISUALIZATION,
            section_number="12.3",
            summary="Amplitude decay over time. Figure 12.3.",
            page_start=255, page_end=257,
            within_chapter_order=13,
            visual_hint="Damped oscillation plot",
            parent_uid="curriculum:physics:shm:damped",
        ),
    ]

    rels = [
        _make_rel(
            "curriculum:physics:shm:shm",
            "curriculum:physics:shm:energy",
            CurriculumRelationType.LEADS_TO,
        ),
        _make_rel(
            "curriculum:physics:shm:energy",
            "curriculum:physics:shm:damped",
            CurriculumRelationType.LEADS_TO,
        ),
    ]

    return _make_extraction(nodes, rels)


# ---------------------------------------------------------------------------
# TestValidationReport
# ---------------------------------------------------------------------------


class TestValidationReport:

    def test_add_error_sets_valid_false(self):
        report = ValidationReport()
        assert report.valid is True
        report.add_error("TEST", "test error")
        assert report.valid is False
        assert report.error_count == 1

    def test_add_warning_keeps_valid(self):
        report = ValidationReport()
        report.add_warning("TEST", "test warning")
        assert report.valid is True
        assert report.warning_count == 1

    def test_summary_format(self):
        report = ValidationReport(node_count=10, relationship_count=5)
        report.add_error("ERR", "bad")
        report.add_warning("WARN", "meh")
        s = report.summary()
        assert "FAIL" in s
        assert "10 nodes" in s
        assert "1 errors" in s

    def test_has_completeness_errors(self):
        report = ValidationReport()
        report.add_error("DUPLICATE_UID", "not completeness")
        assert report.has_completeness_errors() is False
        report.add_error("MISSING_SECTIONS", "yes completeness")
        assert report.has_completeness_errors() is True

    def test_downgrade_completeness_errors(self):
        report = ValidationReport()
        report.add_error("MISSING_SECTIONS", "missing")
        report.add_error("DUPLICATE_UID", "structural")
        assert report.error_count == 2
        assert report.valid is False

        report.downgrade_completeness_errors()
        # MISSING_SECTIONS downgraded to warning, DUPLICATE_UID stays error
        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.valid is False  # still invalid due to DUPLICATE_UID

    def test_downgrade_makes_valid_if_only_completeness_errors(self):
        report = ValidationReport()
        report.add_error("MISSING_FIGURES", "missing figs")
        report.downgrade_completeness_errors()
        assert report.valid is True
        assert report.error_count == 0
        assert report.warning_count == 1


# ---------------------------------------------------------------------------
# TestDuplicateChecks
# ---------------------------------------------------------------------------


class TestDuplicateChecks:

    def test_duplicate_uids_flagged(self):
        n1 = _make_node(uid="dup:1", within_chapter_order=1)
        n2 = _make_node(uid="dup:1", topic_name="Another", within_chapter_order=2)
        extraction = _make_extraction([n1, n2])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("DUPLICATE_UID")
        assert len(errors) == 1
        assert "dup:1" in errors[0].message

    def test_duplicate_relationship_keys_flagged(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        n2 = _make_node(uid="b", within_chapter_order=2)
        r1 = _make_rel("a", "b", key="rel:leads_to:a:b")
        r2 = _make_rel("a", "b", key="rel:leads_to:a:b")
        extraction = _make_extraction([n1, n2], [r1, r2])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("DUPLICATE_RELATIONSHIP_KEY")
        assert len(errors) == 1

    def test_no_duplicates_clean(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        n2 = _make_node(uid="b", within_chapter_order=2)
        extraction = _make_extraction([n1, n2])

        report = StructuralValidator().validate(extraction)
        assert not report.errors_by_code("DUPLICATE_UID")
        assert not report.errors_by_code("DUPLICATE_RELATIONSHIP_KEY")


# ---------------------------------------------------------------------------
# TestReferentialIntegrity
# ---------------------------------------------------------------------------


class TestReferentialIntegrity:

    def test_dangling_from_uid(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        rel = _make_rel("nonexistent", "a")
        extraction = _make_extraction([n1], [rel])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("DANGLING_REFERENCE")
        assert len(errors) == 1
        assert "from_uid" in errors[0].message

    def test_dangling_to_uid(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        rel = _make_rel("a", "nonexistent")
        extraction = _make_extraction([n1], [rel])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("DANGLING_REFERENCE")
        assert len(errors) == 1
        assert "to_uid" in errors[0].message

    def test_cross_chapter_ref_not_flagged(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        rel = _make_rel("a", "Work, Energy and Power::Conservation of Energy")
        extraction = _make_extraction([n1], [rel])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("DANGLING_REFERENCE")
        assert len(errors) == 0

    def test_valid_references(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        n2 = _make_node(uid="b", within_chapter_order=2)
        rel = _make_rel("a", "b")
        extraction = _make_extraction([n1, n2], [rel])

        report = StructuralValidator().validate(extraction)
        assert not report.errors_by_code("DANGLING_REFERENCE")


# ---------------------------------------------------------------------------
# TestRequiredProperties
# ---------------------------------------------------------------------------


class TestRequiredProperties:

    def test_empty_topic_name_error(self):
        n = _make_node(topic_name="", within_chapter_order=1)
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)
        assert len(report.errors_by_code("EMPTY_TOPIC_NAME")) == 1

    def test_invalid_page_range_error(self):
        n = _make_node(page_start=260, page_end=239, within_chapter_order=1)
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)
        assert len(report.errors_by_code("INVALID_PAGE_RANGE")) == 1

    def test_empty_summary_warning(self):
        n = _make_node(summary="", within_chapter_order=1)
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)
        warnings = [i for i in report.issues if i.code == "EMPTY_SUMMARY"]
        assert len(warnings) == 1
        assert warnings[0].level == "warning"


# ---------------------------------------------------------------------------
# TestTypeConsistency
# ---------------------------------------------------------------------------


class TestTypeConsistency:

    def test_formula_without_equation_warns(self):
        n = _make_node(
            concept_type=ConceptType.FORMULA,
            topic_name="Something",
            summary="This concept has no mathematical content whatsoever",
            within_chapter_order=1,
        )
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)
        warnings = [i for i in report.issues if i.code == "FORMULA_NO_EQUATION"]
        assert len(warnings) == 1

    def test_formula_with_equation_clean(self):
        n = _make_node(
            concept_type=ConceptType.FORMULA,
            topic_name="F = ma",
            summary="Force equals mass times acceleration",
            within_chapter_order=1,
        )
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)
        warnings = [i for i in report.issues if i.code == "FORMULA_NO_EQUATION"]
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# TestHierarchyIntegrity
# ---------------------------------------------------------------------------


class TestHierarchyIntegrity:

    def test_parent_uid_not_found(self):
        n = _make_node(
            uid="child",
            parent_uid="nonexistent_parent",
            within_chapter_order=1,
        )
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("BROKEN_HIERARCHY")
        assert len(errors) >= 1
        assert "nonexistent_parent" in errors[0].message

    def test_children_uid_not_found(self):
        n = _make_node(
            uid="parent",
            children_uids=["nonexistent_child"],
            within_chapter_order=1,
        )
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("BROKEN_HIERARCHY")
        assert any("nonexistent_child" in e.message for e in errors)

    def test_valid_hierarchy(self):
        parent = _make_node(
            uid="parent",
            children_uids=["child"],
            within_chapter_order=1,
        )
        child = _make_node(
            uid="child",
            parent_uid="parent",
            within_chapter_order=2,
        )
        extraction = _make_extraction([parent, child])

        report = StructuralValidator().validate(extraction)
        assert not report.errors_by_code("BROKEN_HIERARCHY")


# ---------------------------------------------------------------------------
# TestTeachingOrder
# ---------------------------------------------------------------------------


class TestTeachingOrder:

    def test_gap_in_order_warns(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        n2 = _make_node(uid="b", within_chapter_order=3)  # gap: missing 2
        extraction = _make_extraction([n1, n2])

        report = StructuralValidator().validate(extraction)
        warnings = [i for i in report.issues if i.code == "TEACHING_ORDER_GAP"]
        assert len(warnings) == 1

    def test_sequential_order_clean(self):
        nodes = [
            _make_node(uid=f"n{i}", within_chapter_order=i)
            for i in range(1, 4)
        ]
        extraction = _make_extraction(nodes)

        report = StructuralValidator().validate(extraction)
        assert not [i for i in report.issues if i.code == "TEACHING_ORDER_GAP"]


# ---------------------------------------------------------------------------
# TestCircularDependencies
# ---------------------------------------------------------------------------


class TestCircularDependencies:

    def test_simple_cycle_detected(self):
        n1 = _make_node(uid="a", within_chapter_order=1)
        n2 = _make_node(uid="b", within_chapter_order=2)
        r1 = _make_rel("a", "b", CurriculumRelationType.PREREQUISITE, key="r1")
        r2 = _make_rel("b", "a", CurriculumRelationType.PREREQUISITE, key="r2")
        extraction = _make_extraction([n1, n2], [r1, r2])

        report = StructuralValidator().validate(extraction)
        errors = report.errors_by_code("CIRCULAR_PREREQUISITE")
        assert len(errors) == 1
        assert errors[0].details is not None
        assert "cycle" in errors[0].details

    def test_three_node_cycle_detected(self):
        nodes = [
            _make_node(uid="a", within_chapter_order=1),
            _make_node(uid="b", within_chapter_order=2),
            _make_node(uid="c", within_chapter_order=3),
        ]
        rels = [
            _make_rel("a", "b", CurriculumRelationType.PREREQUISITE, key="r1"),
            _make_rel("b", "c", CurriculumRelationType.PREREQUISITE, key="r2"),
            _make_rel("c", "a", CurriculumRelationType.PREREQUISITE, key="r3"),
        ]
        extraction = _make_extraction(nodes, rels)

        report = StructuralValidator().validate(extraction)
        assert len(report.errors_by_code("CIRCULAR_PREREQUISITE")) == 1

    def test_acyclic_graph_clean(self):
        nodes = [
            _make_node(uid="a", within_chapter_order=1),
            _make_node(uid="b", within_chapter_order=2),
            _make_node(uid="c", within_chapter_order=3),
        ]
        rels = [
            _make_rel("a", "b", CurriculumRelationType.PREREQUISITE, key="r1"),
            _make_rel("b", "c", CurriculumRelationType.PREREQUISITE, key="r2"),
        ]
        extraction = _make_extraction(nodes, rels)

        report = StructuralValidator().validate(extraction)
        assert not report.errors_by_code("CIRCULAR_PREREQUISITE")


# ---------------------------------------------------------------------------
# TestPageCoverage
# ---------------------------------------------------------------------------


class TestPageCoverage:

    def test_uncovered_pages_warned(self):
        # Node covers 239-241, then 244-245. Pages 242-243 uncovered.
        n1 = _make_node(uid="a", page_start=239, page_end=241, within_chapter_order=1)
        n2 = _make_node(uid="b", page_start=244, page_end=245, within_chapter_order=2)
        extraction = _make_extraction([n1, n2])

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        warnings = [i for i in report.issues if i.code == "UNCOVERED_PAGES"]
        assert len(warnings) == 1
        assert 242 in warnings[0].details["uncovered_pages"]

    def test_full_coverage_clean(self):
        n = _make_node(uid="a", page_start=239, page_end=260, within_chapter_order=1)
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        assert not [i for i in report.issues if i.code == "UNCOVERED_PAGES"]


# ---------------------------------------------------------------------------
# TestExtractionCompleteness
# ---------------------------------------------------------------------------


class TestExtractionCompleteness:

    def test_missing_section_error(self):
        """Node only covers 12.1 — sections 12.2, 12.2.1, 12.2.2, 12.3 missing."""
        n = _make_node(
            uid="a",
            section_number="12.1",
            page_start=239, page_end=260,
            within_chapter_order=1,
        )
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        errors = report.errors_by_code("MISSING_SECTIONS")
        assert len(errors) == 1
        missing = errors[0].details["missing_sections"]
        missing_nums = {s["section_number"] for s in missing}
        assert "12.2" in missing_nums
        assert "12.3" in missing_nums

    def test_all_sections_covered(self):
        extraction = _make_valid_extraction()
        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        assert not report.errors_by_code("MISSING_SECTIONS")

    def test_missing_formulas_error(self):
        """No FORMULA nodes, but anchors have 3 equations → coverage 0%."""
        n = _make_node(
            uid="a",
            section_number="12.1",
            page_start=239, page_end=260,
            within_chapter_order=1,
        )
        extraction = _make_extraction([n])

        # Need enough sections covered to not get MISSING_SECTIONS too
        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        errors = report.errors_by_code("MISSING_FORMULAS")
        assert len(errors) == 1

    def test_equation_coverage_above_threshold_clean(self):
        extraction = _make_valid_extraction()
        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        assert not report.errors_by_code("MISSING_FORMULAS")

    def test_missing_figures_error(self):
        """VISUALIZATION nodes exist but don't match all figure refs."""
        nodes = [
            _make_node(
                uid=f"n{i}",
                section_number=s.section_number,
                within_chapter_order=i + 1,
                page_start=239, page_end=260,
            )
            for i, s in enumerate(SHM_ANCHORS.section_numbers)
        ]
        # Only one viz node matching Figure 12.1
        nodes.append(_make_node(
            uid="viz1",
            topic_name="Diagram (Figure 12.1)",
            concept_type=ConceptType.VISUALIZATION,
            summary="Figure 12.1 diagram",
            within_chapter_order=len(nodes) + 1,
            visual_hint="A diagram",
            page_start=239, page_end=260,
        ))
        extraction = _make_extraction(nodes)

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        errors = report.errors_by_code("MISSING_FIGURES")
        assert len(errors) == 1
        # Figure 12.2 and 12.3 should be missing
        missing = errors[0].details["missing_figures"]
        assert len(missing) == 2

    def test_missing_examples_error(self):
        """No EXAMPLE nodes, but anchors have 2 example refs."""
        nodes = [
            _make_node(
                uid=f"n{i}",
                section_number=s.section_number,
                within_chapter_order=i + 1,
                page_start=239, page_end=260,
            )
            for i, s in enumerate(SHM_ANCHORS.section_numbers)
        ]
        extraction = _make_extraction(nodes)

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        errors = report.errors_by_code("MISSING_EXAMPLES")
        assert len(errors) == 1

    def test_missing_visual_hints_warning(self):
        """FORMULA node without visual_hint → warning."""
        n = _make_node(
            uid="formula",
            concept_type=ConceptType.FORMULA,
            topic_name="F = ma",
            summary="Force = mass × acceleration",
            visual_hint=None,  # missing!
            within_chapter_order=1,
        )
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        warnings = [i for i in report.issues if i.code == "MISSING_VISUAL_HINTS"]
        assert len(warnings) == 1

    def test_low_density_warning(self):
        """Only 1 node for 22 pages → 0.05 concepts/page."""
        n = _make_node(uid="a", page_start=239, page_end=260, within_chapter_order=1)
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        warnings = [i for i in report.issues if i.code == "LOW_CONCEPT_DENSITY"]
        assert len(warnings) == 1

    def test_no_anchors_skips_completeness(self):
        """validate(extraction, anchors=None) skips completeness checks."""
        n = _make_node(uid="a", within_chapter_order=1)
        extraction = _make_extraction([n])

        report = StructuralValidator().validate(extraction)  # no anchors
        # Should have no completeness-related issues at all
        completeness_issues = [
            i for i in report.issues if i.code in COMPLETENESS_ISSUE_CODES
        ]
        assert len(completeness_issues) == 0


# ---------------------------------------------------------------------------
# TestFullValidation
# ---------------------------------------------------------------------------


class TestFullValidation:

    def test_valid_extraction_passes(self):
        extraction = _make_valid_extraction()
        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        # Should have no errors (may have warnings)
        assert report.error_count == 0, (
            f"Expected no errors, got: "
            f"{[i.message for i in report.issues if i.level == 'error']}"
        )

    def test_mixed_issues(self):
        """Extraction with both structural and completeness issues."""
        n1 = _make_node(uid="a", topic_name="", within_chapter_order=1)  # empty name
        n2 = _make_node(uid="a", within_chapter_order=2)  # duplicate UID
        extraction = _make_extraction([n1, n2])

        report = StructuralValidator().validate(extraction, SHM_ANCHORS)
        assert report.valid is False
        assert report.error_count >= 2  # at least dup UID + empty name

    def test_empty_extraction(self):
        extraction = _make_extraction()
        report = StructuralValidator().validate(extraction)
        # Empty extraction is structurally valid (no nodes = no issues to find)
        assert report.node_count == 0
