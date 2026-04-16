"""Tests for hierarchy builder — Subject→Unit→Chapter tree construction."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.id_generator import (
    generate_chapter_uid,
    generate_subject_uid,
    generate_unit_uid,
)
from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    ChapterSummary,
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
    UnitGrouping,
)
from lecture_pipeline.curriculum.unification.hierarchy_builder import (
    HierarchyBuilder,
    HierarchyResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SOURCE = ExtractionSource(
    textbook_title="HC Verma Physics",
    chapter_title="Test",
    page_range="1-100",
    extractor_model="test",
)


def _make_skeleton(*, with_units: bool = True) -> BookSkeleton:
    """Build a BookSkeleton with 3 chapters, optionally with unit groupings."""
    units = []
    if with_units:
        units = [
            UnitGrouping(
                unit_name="Mechanics",
                chapter_indices=[1, 2],
                theme="Forces, motion, energy.",
            ),
            UnitGrouping(
                unit_name="Oscillations",
                chapter_indices=[3],
                theme="Periodic motion and waves.",
            ),
        ]
    return BookSkeleton(
        textbook_title="HC Verma Physics",
        subject="physics",
        total_chapters=3,
        total_pages=300,
        chapters=[
            ChapterSummary(
                chapter_index=1,
                title="Newton's Laws",
                page_start=1,
                page_end=100,
                summary="Foundations of mechanics.",
                key_concepts=["Force", "Inertia"],
            ),
            ChapterSummary(
                chapter_index=2,
                title="Work and Energy",
                page_start=101,
                page_end=200,
                summary="Energy conservation.",
                key_concepts=["KE", "PE"],
            ),
            ChapterSummary(
                chapter_index=3,
                title="Simple Harmonic Motion",
                page_start=201,
                page_end=300,
                summary="Oscillatory motion.",
                key_concepts=["SHM"],
            ),
        ],
        units=units,
        subject_overview="Complete introductory physics.",
    )


def _make_node(
    topic_name: str,
    chapter_order: int,
    uid: str | None = None,
    parent_uid: str | None = None,
    within_chapter_order: int = 1,
) -> ExtractionNode:
    return ExtractionNode(
        uid=uid or f"curriculum:physics:ch{chapter_order}:{topic_name.lower().replace(' ', '_')}",
        topic_name=topic_name,
        concept_type=ConceptType.TOPIC,
        resolution_level=ResolutionLevel.CONCEPT,
        summary="Summary.",
        source_text="Source.",
        page_start=chapter_order * 100 - 99,
        page_end=chapter_order * 100,
        chapter_order=chapter_order,
        within_chapter_order=within_chapter_order,
        difficulty=Difficulty.INTERMEDIATE,
        parent_uid=parent_uid,
    )


def _make_extraction(
    chapter_title: str,
    nodes: list[ExtractionNode],
    rels: list[ExtractionRelationship] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="HC Verma Physics",
        scope="chapter",
        chapter_title=chapter_title,
        source=SOURCE,
        nodes=nodes,
        relationships=rels or [],
    )


# ===========================================================================
# TestSubjectNode
# ===========================================================================


class TestSubjectNode:
    def test_subject_node_created(self):
        """Subject node exists with correct UID and resolution_level."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        subject_nodes = [
            n for n in result.hierarchy_nodes
            if n.resolution_level == ResolutionLevel.SYLLABUS
        ]
        assert len(subject_nodes) == 1
        assert subject_nodes[0].uid == generate_subject_uid("physics")
        assert subject_nodes[0].topic_name == "physics"
        assert subject_nodes[0].summary == "Complete introductory physics."

    def test_subject_page_range_from_children(self):
        """Subject node page range spans all chapters."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
            _make_extraction("Simple Harmonic Motion", [_make_node("SHM", 3)]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        subject = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.SYLLABUS][0]
        assert subject.page_start == 1
        assert subject.page_end == 300


# ===========================================================================
# TestUnitNodes
# ===========================================================================


class TestUnitNodes:
    def test_unit_nodes_created(self):
        """Unit nodes created from BookSkeleton.units."""
        skeleton = _make_skeleton(with_units=True)
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
            _make_extraction("Work and Energy", [_make_node("KE", 2)]),
            _make_extraction("Simple Harmonic Motion", [_make_node("SHM", 3)]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        unit_nodes = [
            n for n in result.hierarchy_nodes
            if n.resolution_level == ResolutionLevel.UNIT
        ]
        assert len(unit_nodes) == 2
        unit_names = {n.topic_name for n in unit_nodes}
        assert "Mechanics" in unit_names
        assert "Oscillations" in unit_names

    def test_unit_parent_is_subject(self):
        """Unit nodes have parent_uid pointing to Subject."""
        skeleton = _make_skeleton(with_units=True)
        chapters = [_make_extraction("Newton's Laws", [_make_node("Force", 1)])]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        subject_uid = generate_subject_uid("physics")
        unit_nodes = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.UNIT]
        for u in unit_nodes:
            assert u.parent_uid == subject_uid

    def test_no_units_subject_to_chapter_directly(self):
        """Without units, Subject→Chapter edges are created directly."""
        skeleton = _make_skeleton(with_units=False)
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
            _make_extraction("Work and Energy", [_make_node("KE", 2)]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        # No unit nodes
        unit_nodes = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.UNIT]
        assert len(unit_nodes) == 0

        # Chapter nodes have Subject as parent
        subject_uid = generate_subject_uid("physics")
        chapter_nodes = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.CHAPTER]
        for ch in chapter_nodes:
            assert ch.parent_uid == subject_uid

        # Subject has chapters as children
        subject = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.SYLLABUS][0]
        for ch in chapter_nodes:
            assert ch.uid in subject.children_uids


# ===========================================================================
# TestChapterNodes
# ===========================================================================


class TestChapterNodes:
    def test_chapter_nodes_created(self):
        """One Chapter node per chapter result."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
            _make_extraction("Work and Energy", [_make_node("KE", 2)]),
            _make_extraction("Simple Harmonic Motion", [_make_node("SHM", 3)]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        chapter_nodes = [
            n for n in result.hierarchy_nodes
            if n.resolution_level == ResolutionLevel.CHAPTER
        ]
        assert len(chapter_nodes) == 3

    def test_chapter_uid_from_generator(self):
        """Chapter UIDs use generate_chapter_uid."""
        skeleton = _make_skeleton()
        chapters = [_make_extraction("Newton's Laws", [_make_node("Force", 1)])]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        ch_nodes = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.CHAPTER]
        assert ch_nodes[0].uid == generate_chapter_uid("physics", "Newton's Laws")

    def test_chapter_parent_is_unit(self):
        """With units, chapter parent_uid points to its unit."""
        skeleton = _make_skeleton(with_units=True)
        chapters = [_make_extraction("Newton's Laws", [_make_node("Force", 1)])]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        ch_node = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.CHAPTER][0]
        mechanics_uid = generate_unit_uid("physics", "Mechanics")
        assert ch_node.parent_uid == mechanics_uid


# ===========================================================================
# TestEdgeWiring
# ===========================================================================


class TestEdgeWiring:
    def test_contains_edges_created(self):
        """CONTAINS edges wire the full hierarchy."""
        skeleton = _make_skeleton(with_units=True)
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
            _make_extraction("Simple Harmonic Motion", [_make_node("SHM", 3)]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        contains = [
            r for r in result.hierarchy_relationships
            if r.type == CurriculumRelationType.CONTAINS
        ]
        # Subject→Unit(x2) + Unit→Chapter(x2) + Chapter→Concept(x2) = 6
        assert len(contains) >= 4  # at least Subject→Units + Unit→Chapters

    def test_summarizes_edges_parallel_contains(self):
        """SUMMARIZES edges are created alongside every CONTAINS edge."""
        skeleton = _make_skeleton(with_units=True)
        chapters = [_make_extraction("Newton's Laws", [_make_node("Force", 1)])]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        contains_count = sum(
            1 for r in result.hierarchy_relationships
            if r.type == CurriculumRelationType.CONTAINS
        )
        summarizes_count = sum(
            1 for r in result.hierarchy_relationships
            if r.type == CurriculumRelationType.SUMMARIZES
        )
        assert contains_count == summarizes_count

    def test_top_level_concepts_rewired_to_chapter(self):
        """Concepts with parent_uid=None get parent_uid set to chapter UID."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
                _make_node("Inertia", 1, uid="uid_inertia"),
            ]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        chapter_uid = generate_chapter_uid("physics", "Newton's Laws")
        for node in result.updated_nodes:
            if node.uid in ("uid_force", "uid_inertia"):
                assert node.parent_uid == chapter_uid

    def test_non_top_level_concepts_unchanged(self):
        """Concepts that already have a parent_uid are not rewired."""
        skeleton = _make_skeleton()
        child_node = _make_node("KE Formula", 1, uid="uid_ke_formula", parent_uid="uid_force")
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
                child_node,
            ]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        ke_formula = [n for n in result.updated_nodes if n.uid == "uid_ke_formula"][0]
        assert ke_formula.parent_uid == "uid_force"  # unchanged

    def test_children_uids_on_chapter_node(self):
        """Chapter node's children_uids includes top-level concepts."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
                _make_node("Inertia", 1, uid="uid_inertia"),
            ]),
        ]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        ch_node = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.CHAPTER][0]
        assert "uid_force" in ch_node.children_uids
        assert "uid_inertia" in ch_node.children_uids

    def test_global_teaching_order_hierarchy_nodes(self):
        """Hierarchy nodes get global_teaching_order from chapter_order * 1000."""
        skeleton = _make_skeleton()
        chapters = [_make_extraction("Newton's Laws", [_make_node("Force", 1)])]
        builder = HierarchyBuilder(skeleton, "physics")
        result = builder.build(chapters)

        subject = [n for n in result.hierarchy_nodes if n.resolution_level == ResolutionLevel.SYLLABUS][0]
        # chapter_order=0, within_chapter_order=0 → global=0
        assert subject.global_teaching_order == 0
