"""Tests for cross-chapter reference resolver."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    ChapterSummary,
    ConceptType,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ResolutionLevel,
    UnitGrouping,
)
from lecture_pipeline.curriculum.id_generator import generate_relationship_key
from lecture_pipeline.curriculum.unification.reference_resolver import (
    ReferenceResolver,
    ResolutionResult,
    _is_cross_chapter_ref,
    _parse_cross_chapter_ref,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_skeleton() -> BookSkeleton:
    """Build a minimal BookSkeleton with 3 chapters."""
    return BookSkeleton(
        textbook_title="HC Verma Physics",
        subject="physics",
        total_chapters=3,
        total_pages=300,
        chapters=[
            ChapterSummary(
                chapter_index=1,
                title="Newton's Laws of Motion",
                page_start=1,
                page_end=100,
                summary="Classical mechanics foundations.",
                key_concepts=["Force", "Inertia", "Momentum"],
            ),
            ChapterSummary(
                chapter_index=2,
                title="Work, Energy and Power",
                page_start=101,
                page_end=200,
                summary="Energy conservation and work-energy theorem.",
                key_concepts=["Kinetic Energy", "Potential Energy", "Conservation"],
            ),
            ChapterSummary(
                chapter_index=3,
                title="Simple Harmonic Motion",
                page_start=201,
                page_end=300,
                summary="Oscillatory motion and SHM.",
                key_concepts=["SHM", "Restoring Force", "Energy in SHM"],
            ),
        ],
        units=[],
        subject_overview="A complete physics course.",
    )


def _make_node(
    topic_name: str,
    chapter_order: int,
    uid: str | None = None,
    concept_type: ConceptType = ConceptType.TOPIC,
) -> ExtractionNode:
    """Build a minimal ExtractionNode for testing."""
    return ExtractionNode(
        uid=uid or f"curriculum:physics:ch{chapter_order}:{topic_name.lower().replace(' ', '_')}",
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=ResolutionLevel.CONCEPT,
        summary="A test summary.",
        source_text="Source text.",
        page_start=chapter_order * 100 - 99,
        page_end=chapter_order * 100,
        chapter_order=chapter_order,
        within_chapter_order=1,
        difficulty=Difficulty.INTERMEDIATE,
    )


def _make_rel(
    from_uid: str,
    to_uid: str,
    rel_type: CurriculumRelationType = CurriculumRelationType.PREREQUISITE,
) -> ExtractionRelationship:
    """Build a relationship with auto-generated key."""
    return ExtractionRelationship(
        relationship_key=generate_relationship_key(rel_type.value, from_uid, to_uid),
        type=rel_type,
        from_uid=from_uid,
        to_uid=to_uid,
        label="test",
    )


# ===========================================================================
# TestHelpers
# ===========================================================================


class TestHelpers:
    def test_is_cross_chapter_ref_true(self):
        assert _is_cross_chapter_ref("Newton's Laws::Force") is True

    def test_is_cross_chapter_ref_false(self):
        assert _is_cross_chapter_ref("curriculum:physics:ch1:force") is False

    def test_parse_cross_chapter_ref(self):
        chapter, concept = _parse_cross_chapter_ref("Work, Energy and Power::Kinetic Energy")
        assert chapter == "Work, Energy and Power"
        assert concept == "Kinetic Energy"

    def test_parse_with_extra_whitespace(self):
        chapter, concept = _parse_cross_chapter_ref("  Chapter Title  ::  Concept Name  ")
        assert chapter == "Chapter Title"
        assert concept == "Concept Name"


# ===========================================================================
# TestResolution
# ===========================================================================


class TestResolution:
    def test_resolve_known_cross_chapter_ref(self):
        """Resolve 'Work, Energy and Power::Kinetic Energy' to a real UID."""
        skeleton = _make_skeleton()
        nodes = [
            _make_node("Force", 1, uid="curriculum:physics:newton:force"),
            _make_node("Kinetic Energy", 2, uid="curriculum:physics:energy:kinetic_energy"),
            _make_node("SHM", 3, uid="curriculum:physics:shm:shm"),
        ]
        rels = [
            _make_rel(
                "curriculum:physics:shm:shm",
                "Work, Energy and Power::Kinetic Energy",
            )
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 1
        assert result.unresolved_count == 0
        assert result.resolved_relationships[0].to_uid == "curriculum:physics:energy:kinetic_energy"

    def test_fuzzy_chapter_title_match(self):
        """Case-insensitive chapter matching works."""
        skeleton = _make_skeleton()
        nodes = [
            _make_node("Force", 1, uid="curriculum:physics:newton:force"),
        ]
        rels = [
            _make_rel(
                "curriculum:physics:shm:shm",
                "newton's laws::Force",  # lowercase
            )
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 1
        assert result.resolved_relationships[0].to_uid == "curriculum:physics:newton:force"

    def test_fuzzy_concept_name_match(self):
        """Concept names are matched after normalization (stop words removed)."""
        skeleton = _make_skeleton()
        # Node has "Energy in SHM", reference says "Energy of SHM"
        nodes = [
            _make_node("Energy in SHM", 3, uid="curriculum:physics:shm:energy_in_shm"),
        ]
        rels = [
            _make_rel(
                "curriculum:physics:energy:ke",
                "Simple Harmonic Motion::Energy of SHM",  # "of" is stop word
            )
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 1
        assert result.resolved_relationships[0].to_uid == "curriculum:physics:shm:energy_in_shm"

    def test_unresolved_chapter_warning(self):
        """Unknown chapter title produces a warning."""
        skeleton = _make_skeleton()
        nodes = [_make_node("Force", 1)]
        rels = [
            _make_rel("curriculum:physics:ch1:force", "Nonexistent Chapter::Concept")
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 0
        assert result.unresolved_count == 1
        assert len(result.warnings) == 1
        assert "could not match chapter" in result.warnings[0]
        # Relationship kept with original placeholder
        assert "::" in result.resolved_relationships[0].to_uid

    def test_unresolved_concept_warning(self):
        """Known chapter but unknown concept produces a warning."""
        skeleton = _make_skeleton()
        nodes = [_make_node("Force", 1)]
        rels = [
            _make_rel(
                "curriculum:physics:ch1:force",
                "Newton's Laws of Motion::Nonexistent Concept",
            )
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 0
        assert result.unresolved_count == 1
        assert "not found in chapter" in result.warnings[0]

    def test_no_cross_chapter_refs_passthrough(self):
        """Relationships without '::' pass through unchanged."""
        skeleton = _make_skeleton()
        nodes = [_make_node("Force", 1, uid="uid_a"), _make_node("Inertia", 1, uid="uid_b")]
        rels = [_make_rel("uid_a", "uid_b")]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 0
        assert result.unresolved_count == 0
        assert len(result.warnings) == 0
        assert result.resolved_relationships[0].from_uid == "uid_a"
        assert result.resolved_relationships[0].to_uid == "uid_b"

    def test_multiple_refs_resolved(self):
        """Multiple cross-chapter refs resolved in one pass."""
        skeleton = _make_skeleton()
        nodes = [
            _make_node("Force", 1, uid="uid_force"),
            _make_node("Kinetic Energy", 2, uid="uid_ke"),
            _make_node("SHM", 3, uid="uid_shm"),
        ]
        rels = [
            _make_rel("uid_shm", "Newton's Laws of Motion::Force"),
            _make_rel("uid_shm", "Work, Energy and Power::Kinetic Energy"),
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 2
        assert result.unresolved_count == 0
        assert result.resolved_relationships[0].to_uid == "uid_force"
        assert result.resolved_relationships[1].to_uid == "uid_ke"

    def test_from_uid_with_cross_ref_also_resolved(self):
        """from_uid containing '::' is also resolved."""
        skeleton = _make_skeleton()
        nodes = [
            _make_node("Force", 1, uid="uid_force"),
            _make_node("SHM", 3, uid="uid_shm"),
        ]
        rels = [
            _make_rel("Newton's Laws of Motion::Force", "uid_shm")
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        assert result.resolved_count == 1
        assert result.resolved_relationships[0].from_uid == "uid_force"

    def test_relationship_key_regenerated(self):
        """After resolution, the relationship_key uses the resolved UIDs."""
        skeleton = _make_skeleton()
        nodes = [
            _make_node("Force", 1, uid="uid_force"),
            _make_node("SHM", 3, uid="uid_shm"),
        ]
        rels = [
            _make_rel("uid_shm", "Newton's Laws of Motion::Force")
        ]

        resolver = ReferenceResolver(skeleton)
        result = resolver.resolve(rels, nodes)

        expected_key = generate_relationship_key("prerequisite", "uid_shm", "uid_force")
        assert result.resolved_relationships[0].relationship_key == expected_key
