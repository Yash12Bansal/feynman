"""Tests for curriculum graph models — round-trip serialization, counts, accessors."""

import json

import pytest

from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    ChapterSummary,
    ConceptType,
    CrossChapterPrerequisite,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
    UnitGrouping,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_node(
    uid: str = "curriculum:physics:shm:energy_in_shm",
    topic_name: str = "Energy in SHM",
    concept_type: ConceptType = ConceptType.FORMULA,
    resolution_level: ResolutionLevel = ResolutionLevel.CONCEPT,
    chapter_order: int = 10,
    within_chapter_order: int = 6,
    **kwargs,
) -> ExtractionNode:
    return ExtractionNode(
        uid=uid,
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=resolution_level,
        summary="Energy analysis reveals U = 1/2 kx^2, K = 1/2 mv^2",
        source_text="The potential energy of a spring...",
        page_start=245,
        page_end=246,
        chapter_order=chapter_order,
        within_chapter_order=within_chapter_order,
        visual_hint="Spring-mass energy diagram with KE/PE curves overlaid",
        **kwargs,
    )


def _make_relationship(
    from_uid: str = "curriculum:physics:shm:energy_in_shm",
    to_uid: str = "curriculum:physics:shm:mathematical_description",
    rel_type: CurriculumRelationType = CurriculumRelationType.PREREQUISITE,
) -> ExtractionRelationship:
    return ExtractionRelationship(
        relationship_key=f"rel:{rel_type.value}:{from_uid}:{to_uid}",
        type=rel_type,
        from_uid=from_uid,
        to_uid=to_uid,
        label="Mathematical description must be understood first",
    )


def _make_source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="HC Verma - Concepts of Physics",
        chapter_title="Simple Harmonic Motion",
        page_range="239-252",
        extractor_model="claude-sonnet-4",
        confidence=0.92,
    )


def _make_extraction() -> CurriculumExtractionResult:
    nodes = [
        _make_node(
            uid="curriculum:physics:shm:energy_in_shm",
            topic_name="Energy in SHM",
            concept_type=ConceptType.FORMULA,
            within_chapter_order=6,
        ),
        _make_node(
            uid="curriculum:physics:shm:mathematical_description",
            topic_name="Mathematical Description of SHM",
            concept_type=ConceptType.TOPIC,
            within_chapter_order=3,
        ),
        _make_node(
            uid="curriculum:physics:shm:example_spring_mass",
            topic_name="Example: Spring-Mass System",
            concept_type=ConceptType.EXAMPLE,
            within_chapter_order=7,
        ),
    ]
    rels = [
        _make_relationship(
            from_uid="curriculum:physics:shm:energy_in_shm",
            to_uid="curriculum:physics:shm:mathematical_description",
            rel_type=CurriculumRelationType.PREREQUISITE,
        ),
        _make_relationship(
            from_uid="curriculum:physics:shm:example_spring_mass",
            to_uid="curriculum:physics:shm:energy_in_shm",
            rel_type=CurriculumRelationType.EXAMPLE_OF,
        ),
    ]
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="HC Verma - Concepts of Physics",
        chapter_title="Simple Harmonic Motion",
        source=_make_source(),
        nodes=nodes,
        relationships=rels,
    )


def _make_skeleton() -> BookSkeleton:
    return BookSkeleton(
        textbook_title="HC Verma - Concepts of Physics",
        subject="physics",
        total_chapters=3,
        total_pages=400,
        chapters=[
            ChapterSummary(
                chapter_index=5,
                title="Work, Energy and Power",
                page_start=80,
                page_end=100,
                summary="Covers work-energy theorem and conservation of energy.",
                key_concepts=["work", "kinetic energy", "potential energy"],
            ),
            ChapterSummary(
                chapter_index=7,
                title="Circular Motion",
                page_start=120,
                page_end=145,
                summary="Covers uniform and non-uniform circular motion.",
                key_concepts=["centripetal force", "angular velocity"],
                leads_to=["Simple Harmonic Motion"],
            ),
            ChapterSummary(
                chapter_index=10,
                title="Simple Harmonic Motion",
                page_start=239,
                page_end=260,
                summary="Covers SHM, energy analysis, damped and forced oscillations.",
                key_concepts=["SHM", "energy in SHM", "damped oscillations"],
                prerequisites_from=["Work, Energy and Power", "Circular Motion"],
            ),
        ],
        units=[
            UnitGrouping(
                unit_name="Oscillations & Waves",
                chapter_indices=[10, 11, 12],
                theme="Periodic motion and wave phenomena",
            ),
        ],
        cross_chapter_prerequisites=[
            CrossChapterPrerequisite(
                from_chapter="Work, Energy and Power",
                to_chapter="Simple Harmonic Motion",
                reason="Energy conservation is used to derive SHM energy formulas",
            ),
        ],
        subject_overview="Classical mechanics from kinematics through oscillations.",
    )


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_concept_type_values(self):
        assert ConceptType.FORMULA.value == "formula"
        assert ConceptType.MISCONCEPTION.value == "misconception"
        assert len(ConceptType) == 10

    def test_resolution_level_ordering(self):
        levels = list(ResolutionLevel)
        assert levels[0] == ResolutionLevel.SYLLABUS
        assert levels[-1] == ResolutionLevel.DETAIL

    def test_relationship_type_values(self):
        assert CurriculumRelationType.PREREQUISITE.value == "prerequisite"
        assert CurriculumRelationType.HAS_VISUAL.value == "has_visual"


# ---------------------------------------------------------------------------
# Tests: ExtractionNode
# ---------------------------------------------------------------------------


class TestExtractionNode:
    def test_global_teaching_order_auto_computed(self):
        node = _make_node(chapter_order=10, within_chapter_order=6)
        assert node.global_teaching_order == 10006

    def test_global_teaching_order_explicit(self):
        node = _make_node(
            chapter_order=10,
            within_chapter_order=6,
            global_teaching_order=99999,
        )
        assert node.global_teaching_order == 99999

    def test_default_difficulty(self):
        node = _make_node()
        assert node.difficulty == Difficulty.INTERMEDIATE

    def test_visual_hint_present(self):
        node = _make_node()
        assert "KE/PE" in node.visual_hint


# ---------------------------------------------------------------------------
# Tests: BookSkeleton
# ---------------------------------------------------------------------------


class TestBookSkeleton:
    def test_chapter_by_index(self):
        skeleton = _make_skeleton()
        ch = skeleton.chapter_by_index(10)
        assert ch is not None
        assert ch.title == "Simple Harmonic Motion"

    def test_chapter_by_index_missing(self):
        skeleton = _make_skeleton()
        assert skeleton.chapter_by_index(999) is None

    def test_chapter_by_title(self):
        skeleton = _make_skeleton()
        ch = skeleton.chapter_by_title("harmonic motion")
        assert ch is not None
        assert ch.chapter_index == 10

    def test_chapter_by_title_missing(self):
        skeleton = _make_skeleton()
        assert skeleton.chapter_by_title("quantum mechanics") is None

    def test_round_trip_json(self):
        skeleton = _make_skeleton()
        json_str = skeleton.model_dump_json(indent=2)
        restored = BookSkeleton.model_validate_json(json_str)
        assert restored.textbook_title == skeleton.textbook_title
        assert len(restored.chapters) == len(skeleton.chapters)
        assert restored.chapters[2].title == "Simple Harmonic Motion"


# ---------------------------------------------------------------------------
# Tests: CurriculumExtractionResult
# ---------------------------------------------------------------------------


class TestExtractionResult:
    def test_node_uids(self):
        ext = _make_extraction()
        uids = ext.node_uids
        assert len(uids) == 3
        assert "curriculum:physics:shm:energy_in_shm" in uids

    def test_node_by_uid(self):
        ext = _make_extraction()
        node = ext.node_by_uid("curriculum:physics:shm:energy_in_shm")
        assert node is not None
        assert node.concept_type == ConceptType.FORMULA

    def test_node_by_uid_missing(self):
        ext = _make_extraction()
        assert ext.node_by_uid("nonexistent") is None

    def test_nodes_by_type(self):
        ext = _make_extraction()
        formulas = ext.nodes_by_type(ConceptType.FORMULA)
        assert len(formulas) == 1
        assert formulas[0].topic_name == "Energy in SHM"

    def test_nodes_by_resolution(self):
        ext = _make_extraction()
        concepts = ext.nodes_by_resolution(ResolutionLevel.CONCEPT)
        assert len(concepts) == 3

    def test_relationships_by_type(self):
        ext = _make_extraction()
        prereqs = ext.relationships_by_type(CurriculumRelationType.PREREQUISITE)
        assert len(prereqs) == 1

    def test_compute_counts(self):
        ext = _make_extraction()
        counts = ext.compute_counts()
        assert counts["nodes"]["formula"] == 1
        assert counts["nodes"]["topic"] == 1
        assert counts["nodes"]["example"] == 1
        assert counts["relationships"]["prerequisite"] == 1
        assert counts["relationships"]["example_of"] == 1

    def test_round_trip_json(self):
        ext = _make_extraction()
        json_str = ext.to_json()
        restored = CurriculumExtractionResult.from_json(json_str)

        assert restored.subject == "physics"
        assert restored.textbook_title == ext.textbook_title
        assert len(restored.nodes) == 3
        assert len(restored.relationships) == 2
        assert restored.node_by_uid("curriculum:physics:shm:energy_in_shm") is not None

    def test_round_trip_preserves_types(self):
        ext = _make_extraction()
        json_str = ext.to_json()
        restored = CurriculumExtractionResult.from_json(json_str)

        node = restored.node_by_uid("curriculum:physics:shm:energy_in_shm")
        assert isinstance(node.concept_type, ConceptType)
        assert isinstance(node.resolution_level, ResolutionLevel)

    def test_save_and_load(self, tmp_path):
        ext = _make_extraction()
        path = tmp_path / "extraction.json"
        ext.save(path)
        restored = CurriculumExtractionResult.load(path)
        assert restored.subject == "physics"
        assert len(restored.nodes) == 3

    def test_with_book_skeleton(self):
        ext = _make_extraction()
        ext.book_skeleton = _make_skeleton()
        json_str = ext.to_json()
        restored = CurriculumExtractionResult.from_json(json_str)
        assert restored.book_skeleton is not None
        assert restored.book_skeleton.total_chapters == 3

    def test_scope_default(self):
        ext = _make_extraction()
        assert ext.scope == "chapter"

    def test_warnings(self):
        ext = _make_extraction()
        ext.warnings.append("Missing section 12.3")
        json_str = ext.to_json()
        restored = CurriculumExtractionResult.from_json(json_str)
        assert len(restored.warnings) == 1
