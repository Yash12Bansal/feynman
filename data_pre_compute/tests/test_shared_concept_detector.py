"""Tests for cross-chapter shared concept detection."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.unification.shared_concept_detector import (
    SharedConceptDetector,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_node(
    topic_name: str,
    chapter_order: int,
    uid: str | None = None,
    concept_type: ConceptType = ConceptType.TOPIC,
    resolution_level: ResolutionLevel = ResolutionLevel.CONCEPT,
) -> ExtractionNode:
    return ExtractionNode(
        uid=uid or f"curriculum:physics:ch{chapter_order}:{topic_name.lower().replace(' ', '_')}",
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=resolution_level,
        summary="Summary.",
        source_text="Source.",
        page_start=chapter_order * 100,
        page_end=chapter_order * 100 + 50,
        chapter_order=chapter_order,
        within_chapter_order=1,
        difficulty=Difficulty.INTERMEDIATE,
    )


# ===========================================================================
# TestSharedConceptDetection
# ===========================================================================


class TestSharedConceptDetection:
    def test_same_name_across_chapters(self):
        """Identical normalized names in different chapters → SHARED_FOUNDATION."""
        nodes = [
            _make_node("Force", 1, uid="uid_force_ch1"),
            _make_node("Force", 3, uid="uid_force_ch3"),
        ]
        detector = SharedConceptDetector()
        result = detector.detect(nodes)

        assert result.shared_pairs_count == 1
        assert len(result.new_relationships) == 1
        rel = result.new_relationships[0]
        assert rel.type == CurriculumRelationType.SHARED_FOUNDATION
        assert rel.from_uid == "uid_force_ch1"  # earlier chapter
        assert rel.to_uid == "uid_force_ch3"

    def test_case_and_stop_word_invariance(self):
        """'Energy in SHM' and 'energy shm' match after normalization."""
        nodes = [
            _make_node("Energy in SHM", 2, uid="uid_energy_ch2"),
            _make_node("energy shm", 5, uid="uid_energy_ch5"),
        ]
        detector = SharedConceptDetector()
        result = detector.detect(nodes)

        assert result.shared_pairs_count == 1

    def test_same_chapter_not_flagged(self):
        """Nodes in the same chapter are never matched."""
        nodes = [
            _make_node("Force", 1, uid="uid_force_a"),
            _make_node("Force", 1, uid="uid_force_b"),
        ]
        detector = SharedConceptDetector()
        result = detector.detect(nodes)

        assert result.shared_pairs_count == 0
        assert len(result.new_relationships) == 0

    def test_different_concept_types_not_matched(self):
        """Same name but different concept_type → no match."""
        nodes = [
            _make_node("Energy", 1, uid="uid_topic", concept_type=ConceptType.TOPIC),
            _make_node("Energy", 3, uid="uid_formula", concept_type=ConceptType.FORMULA),
        ]
        detector = SharedConceptDetector()
        result = detector.detect(nodes)

        assert result.shared_pairs_count == 0

    def test_no_matches_empty_result(self):
        """All unique concepts → no shared pairs."""
        nodes = [
            _make_node("Force", 1),
            _make_node("Energy", 2),
            _make_node("SHM", 3),
        ]
        detector = SharedConceptDetector()
        result = detector.detect(nodes)

        assert result.shared_pairs_count == 0
        assert len(result.new_relationships) == 0

    def test_dedup_same_pair(self):
        """Same pair from multiple path traversals is only flagged once."""
        # Three chapters each with "Force" — should produce 3 pairs (1-2, 1-3, 2-3)
        nodes = [
            _make_node("Force", 1, uid="uid_1"),
            _make_node("Force", 2, uid="uid_2"),
            _make_node("Force", 3, uid="uid_3"),
        ]
        detector = SharedConceptDetector()
        result = detector.detect(nodes)

        assert result.shared_pairs_count == 3
        # Verify no duplicate relationship keys
        keys = [r.relationship_key for r in result.new_relationships]
        assert len(keys) == len(set(keys))

    def test_detail_nodes_excluded(self):
        """DETAIL resolution_level nodes are not matched."""
        nodes = [
            _make_node("Force", 1, uid="uid_detail_1", resolution_level=ResolutionLevel.DETAIL),
            _make_node("Force", 3, uid="uid_detail_3", resolution_level=ResolutionLevel.DETAIL),
        ]
        detector = SharedConceptDetector()
        result = detector.detect(nodes)

        assert result.shared_pairs_count == 0
