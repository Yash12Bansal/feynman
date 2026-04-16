"""Tests for book unifier — full book unification orchestrator."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.id_generator import (
    generate_chapter_uid,
    generate_relationship_key,
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
from lecture_pipeline.curriculum.unification.book_unifier import (
    BookUnifier,
    UnificationReport,
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
    units = []
    if with_units:
        units = [
            UnitGrouping(
                unit_name="Mechanics",
                chapter_indices=[1, 2],
                theme="Forces and energy.",
            ),
            UnitGrouping(
                unit_name="Oscillations",
                chapter_indices=[3],
                theme="Periodic motion.",
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
                summary="Mechanics foundations.",
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
        subject_overview="Complete physics course.",
    )


def _make_node(
    topic_name: str,
    chapter_order: int,
    uid: str | None = None,
    concept_type: ConceptType = ConceptType.TOPIC,
    within_chapter_order: int = 1,
    parent_uid: str | None = None,
) -> ExtractionNode:
    return ExtractionNode(
        uid=uid or f"curriculum:physics:ch{chapter_order}:{topic_name.lower().replace(' ', '_')}",
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=ResolutionLevel.CONCEPT,
        summary=f"Summary of {topic_name}.",
        source_text="Source.",
        page_start=chapter_order * 100 - 99,
        page_end=chapter_order * 100,
        chapter_order=chapter_order,
        within_chapter_order=within_chapter_order,
        difficulty=Difficulty.INTERMEDIATE,
        parent_uid=parent_uid,
    )


def _make_rel(
    from_uid: str,
    to_uid: str,
    rel_type: CurriculumRelationType = CurriculumRelationType.PREREQUISITE,
) -> ExtractionRelationship:
    return ExtractionRelationship(
        relationship_key=generate_relationship_key(rel_type.value, from_uid, to_uid),
        type=rel_type,
        from_uid=from_uid,
        to_uid=to_uid,
        label="test",
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
# TestValidation
# ===========================================================================


class TestValidation:
    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="empty"):
            BookUnifier().unify([], _make_skeleton())

    def test_mismatched_subjects_raises(self):
        ch1 = _make_extraction("Newton's Laws", [_make_node("Force", 1)])
        ch2 = CurriculumExtractionResult(
            subject="chemistry",  # different subject
            textbook_title="HC Verma Physics",
            scope="chapter",
            chapter_title="Atoms",
            source=SOURCE,
            nodes=[],
            relationships=[],
        )
        with pytest.raises(ValueError, match="subject"):
            BookUnifier().unify([ch1, ch2], _make_skeleton())

    def test_mismatched_textbooks_raises(self):
        ch1 = _make_extraction("Newton's Laws", [_make_node("Force", 1)])
        ch2 = CurriculumExtractionResult(
            subject="physics",
            textbook_title="Different Book",  # different title
            scope="chapter",
            chapter_title="Energy",
            source=SOURCE,
            nodes=[],
            relationships=[],
        )
        with pytest.raises(ValueError, match="textbook_title"):
            BookUnifier().unify([ch1, ch2], _make_skeleton())


# ===========================================================================
# TestUnification
# ===========================================================================


class TestUnification:
    def test_scope_is_book(self):
        """Unified result has scope='book'."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
        ]
        result, _ = BookUnifier().unify(chapters, skeleton)
        assert result.scope == "book"

    def test_chapter_title_is_none(self):
        """Unified result has chapter_title=None."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
        ]
        result, _ = BookUnifier().unify(chapters, skeleton)
        assert result.chapter_title is None

    def test_all_nodes_collected(self):
        """All concept nodes from all chapters appear in the unified result."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
                _make_node("Inertia", 1, uid="uid_inertia"),
            ]),
            _make_extraction("Work and Energy", [
                _make_node("KE", 2, uid="uid_ke"),
            ]),
            _make_extraction("Simple Harmonic Motion", [
                _make_node("SHM", 3, uid="uid_shm"),
            ]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        concept_uids = {n.uid for n in result.nodes if n.resolution_level == ResolutionLevel.CONCEPT}
        assert "uid_force" in concept_uids
        assert "uid_inertia" in concept_uids
        assert "uid_ke" in concept_uids
        assert "uid_shm" in concept_uids
        assert report.total_input_nodes == 4

    def test_cross_chapter_refs_resolved(self):
        """Cross-chapter placeholder UIDs are resolved to real UIDs."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
            ]),
            _make_extraction("Simple Harmonic Motion", [
                _make_node("Restoring Force", 3, uid="uid_restoring"),
            ], rels=[
                _make_rel("uid_restoring", "Newton's Laws::Force"),
            ]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        assert report.cross_chapter_refs_resolved == 1
        # Find the prerequisite relationship
        prereqs = [r for r in result.relationships if r.type == CurriculumRelationType.PREREQUISITE]
        assert len(prereqs) == 1
        assert prereqs[0].to_uid == "uid_force"  # resolved from placeholder

    def test_hierarchy_nodes_present(self):
        """Subject, Unit, and Chapter nodes are in the unified result."""
        skeleton = _make_skeleton(with_units=True)
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
            _make_extraction("Work and Energy", [_make_node("KE", 2)]),
            _make_extraction("Simple Harmonic Motion", [_make_node("SHM", 3)]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        levels = {n.resolution_level for n in result.nodes}
        assert ResolutionLevel.SYLLABUS in levels
        assert ResolutionLevel.UNIT in levels
        assert ResolutionLevel.CHAPTER in levels
        # 1 Subject + 2 Units + 3 Chapters = 6 hierarchy nodes
        assert report.hierarchy_nodes_created == 6

    def test_global_teaching_order_monotonic(self):
        """global_teaching_order increases across chapters for concept nodes."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, within_chapter_order=1),
                _make_node("Inertia", 1, within_chapter_order=2),
            ]),
            _make_extraction("Work and Energy", [
                _make_node("KE", 2, within_chapter_order=1),
            ]),
            _make_extraction("Simple Harmonic Motion", [
                _make_node("SHM", 3, within_chapter_order=1),
            ]),
        ]
        result, _ = BookUnifier().unify(chapters, skeleton)

        concept_nodes = [
            n for n in result.nodes
            if n.resolution_level == ResolutionLevel.CONCEPT
        ]
        orders = sorted(n.global_teaching_order for n in concept_nodes)
        # Must be strictly increasing
        for i in range(1, len(orders)):
            assert orders[i] > orders[i - 1]

    def test_single_chapter_works(self):
        """Single chapter produces a valid unified result."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [_make_node("Force", 1)]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        assert result.scope == "book"
        assert report.total_chapters == 1
        assert report.total_output_nodes > 0

    def test_referential_integrity(self):
        """All from_uid/to_uid in relationships point to existing nodes."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
            ]),
            _make_extraction("Work and Energy", [
                _make_node("KE", 2, uid="uid_ke"),
            ], rels=[
                _make_rel("uid_ke", "uid_force", CurriculumRelationType.PREREQUISITE),
            ]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        node_uids = {n.uid for n in result.nodes}
        dangling_warnings = [w for w in report.warnings if "Dangling" in w]
        assert len(dangling_warnings) == 0

        # Spot-check: all relationship UIDs exist in nodes
        for rel in result.relationships:
            if "::" not in rel.from_uid:
                assert rel.from_uid in node_uids, f"from_uid {rel.from_uid} not in nodes"
            if "::" not in rel.to_uid:
                assert rel.to_uid in node_uids, f"to_uid {rel.to_uid} not in nodes"

    def test_report_counts_correct(self):
        """UnificationReport has accurate counts."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
            ], rels=[
                _make_rel("uid_force", "Work and Energy::KE"),
            ]),
            _make_extraction("Work and Energy", [
                _make_node("KE", 2, uid="uid_ke"),
            ]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        assert report.total_chapters == 2
        assert report.total_input_nodes == 2
        assert report.total_input_relationships == 1
        assert report.cross_chapter_refs_resolved == 1
        assert report.total_output_nodes > report.total_input_nodes  # hierarchy added
        assert report.total_output_relationships > report.total_input_relationships  # hierarchy + resolved

    def test_book_skeleton_attached(self):
        """Unified result has book_skeleton attached."""
        skeleton = _make_skeleton()
        chapters = [_make_extraction("Newton's Laws", [_make_node("Force", 1)])]
        result, _ = BookUnifier().unify(chapters, skeleton)

        assert result.book_skeleton is not None
        assert result.book_skeleton.textbook_title == "HC Verma Physics"

    def test_shared_concepts_detected(self):
        """Shared concepts across chapters produce SHARED_FOUNDATION edges."""
        skeleton = _make_skeleton()
        # "Force" appears in ch1 and ch3
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force_ch1"),
            ]),
            _make_extraction("Simple Harmonic Motion", [
                _make_node("Force", 3, uid="uid_force_ch3"),
            ]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        assert report.shared_concepts_detected >= 1
        shared_rels = [
            r for r in result.relationships
            if r.type == CurriculumRelationType.SHARED_FOUNDATION
        ]
        assert len(shared_rels) >= 1

    def test_unresolved_ref_warning(self):
        """Unresolved cross-chapter ref produces a warning, not an error."""
        skeleton = _make_skeleton()
        chapters = [
            _make_extraction("Newton's Laws", [
                _make_node("Force", 1, uid="uid_force"),
            ], rels=[
                _make_rel("uid_force", "Nonexistent Chapter::Concept"),
            ]),
        ]
        result, report = BookUnifier().unify(chapters, skeleton)

        assert report.cross_chapter_refs_unresolved == 1
        assert len(report.warnings) >= 1

    def test_report_summary_string(self):
        """UnificationReport.summary() returns a human-readable string."""
        report = UnificationReport(
            total_chapters=3,
            total_input_nodes=50,
            total_output_nodes=56,
        )
        s = report.summary()
        assert "3 chapters" in s
        assert "50 nodes" in s
