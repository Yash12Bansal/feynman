"""Tests for entity resolver — deterministic concept identity for chunk merging."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.merge.entity_resolver import (
    IdentityKey,
    compute_identity_key,
    compute_node_identity,
    group_by_identity,
    normalize_topic_name,
)
from lecture_pipeline.curriculum.models import (
    ConceptType,
    Difficulty,
    ExtractionNode,
    ResolutionLevel,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_node(
    topic_name: str = "Simple Harmonic Motion",
    concept_type: ConceptType = ConceptType.TOPIC,
    parent_name: str | None = None,
    uid: str | None = None,
    within_chapter_order: int = 1,
    **overrides,
) -> ExtractionNode:
    """Build a minimal ExtractionNode for testing."""
    metadata = {"raw_parent_name": parent_name} if parent_name else {}
    if "metadata" in overrides:
        metadata.update(overrides.pop("metadata"))
    return ExtractionNode(
        uid=uid or f"curriculum:physics:shm:{topic_name.lower().replace(' ', '_')}",
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=ResolutionLevel.CONCEPT,
        summary="A test summary.",
        source_text="Source text here.",
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=within_chapter_order,
        difficulty=Difficulty.INTERMEDIATE,
        metadata=metadata,
        **overrides,
    )


# ===========================================================================
# TestNormalization
# ===========================================================================


class TestNormalization:
    def test_removes_stop_words(self):
        result = normalize_topic_name("Energy of the Particle")
        assert result == "energy particle"

    def test_lowercase_and_strip(self):
        result = normalize_topic_name("  Simple Harmonic Motion  ")
        assert result == "simple harmonic motion"

    def test_collapses_whitespace(self):
        result = normalize_topic_name("energy   in   shm")
        # "in" is a stop word, so removed; whitespace collapsed
        assert result == "energy shm"

    def test_empty_string(self):
        assert normalize_topic_name("") == ""

    def test_only_stop_words(self):
        assert normalize_topic_name("of the in a an for") == ""


# ===========================================================================
# TestIdentityKey
# ===========================================================================


class TestIdentityKey:
    def test_deterministic(self):
        """Same inputs always produce the same key."""
        key1 = compute_identity_key("Energy in SHM", ConceptType.TOPIC)
        key2 = compute_identity_key("Energy in SHM", ConceptType.TOPIC)
        assert key1.key == key2.key

    def test_different_names(self):
        """Different names produce different keys."""
        key1 = compute_identity_key("Energy in SHM", ConceptType.TOPIC)
        key2 = compute_identity_key("Kinetic Energy", ConceptType.TOPIC)
        assert key1.key != key2.key

    def test_different_types(self):
        """Same name, different concept_type produces different key."""
        key1 = compute_identity_key("Energy in SHM", ConceptType.TOPIC)
        key2 = compute_identity_key("Energy in SHM", ConceptType.FORMULA)
        assert key1.key != key2.key

    def test_with_parent(self):
        """Parent name affects the key."""
        key1 = compute_identity_key("KE Formula", ConceptType.FORMULA, parent_name="Energy")
        key2 = compute_identity_key("KE Formula", ConceptType.FORMULA, parent_name=None)
        assert key1.key != key2.key

    def test_none_parent_stable(self):
        """None parent produces a stable key."""
        key1 = compute_identity_key("SHM", ConceptType.TOPIC, parent_name=None)
        key2 = compute_identity_key("SHM", ConceptType.TOPIC, parent_name=None)
        assert key1.key == key2.key
        assert key1.parent_slug == ""

    def test_stop_word_invariance(self):
        """'Energy in SHM' and 'Energy SHM' produce the same key."""
        key1 = compute_identity_key("Energy in SHM", ConceptType.TOPIC)
        key2 = compute_identity_key("Energy SHM", ConceptType.TOPIC)
        assert key1.key == key2.key

    def test_case_invariance(self):
        """'KINETIC ENERGY' and 'kinetic energy' produce the same key."""
        key1 = compute_identity_key("KINETIC ENERGY", ConceptType.TOPIC)
        key2 = compute_identity_key("kinetic energy", ConceptType.TOPIC)
        assert key1.key == key2.key

    def test_whitespace_invariance(self):
        """Extra whitespace doesn't change the key."""
        key1 = compute_identity_key("  Kinetic  Energy ", ConceptType.TOPIC)
        key2 = compute_identity_key("Kinetic Energy", ConceptType.TOPIC)
        assert key1.key == key2.key


# ===========================================================================
# TestNodeIdentity
# ===========================================================================


class TestNodeIdentity:
    def test_reads_metadata_parent(self):
        """Uses raw_parent_name from metadata for identity."""
        node = _make_node("KE Formula", ConceptType.FORMULA, parent_name="Energy in SHM")
        identity = compute_node_identity(node)
        assert identity.parent_slug != ""
        # Should match a direct compute_identity_key call
        direct = compute_identity_key("KE Formula", ConceptType.FORMULA, "Energy in SHM")
        assert identity.key == direct.key

    def test_no_parent_fallback(self):
        """Works when no parent metadata exists."""
        node = _make_node("SHM", ConceptType.TOPIC)
        identity = compute_node_identity(node)
        direct = compute_identity_key("SHM", ConceptType.TOPIC, None)
        assert identity.key == direct.key


# ===========================================================================
# TestGroupByIdentity
# ===========================================================================


class TestGroupByIdentity:
    def test_all_unique(self):
        """N unique nodes produce N groups of 1."""
        nodes = [
            _make_node("SHM", ConceptType.TOPIC, within_chapter_order=1),
            _make_node("Energy", ConceptType.TOPIC, within_chapter_order=2),
            _make_node("Damping", ConceptType.TOPIC, within_chapter_order=3),
        ]
        groups = group_by_identity(nodes)
        assert len(groups) == 3
        for group in groups.values():
            assert len(group) == 1

    def test_with_matches(self):
        """Overlapping concepts from 2 chunks are grouped together."""
        # Chunk 1
        node1a = _make_node("Energy in SHM", ConceptType.TOPIC, uid="uid_a1", within_chapter_order=1)
        node1b = _make_node("Damping", ConceptType.TOPIC, uid="uid_b1", within_chapter_order=2)
        # Chunk 2 — "Energy SHM" matches "Energy in SHM" after normalization
        node2a = _make_node("Energy SHM", ConceptType.TOPIC, uid="uid_a2", within_chapter_order=1)
        node2b = _make_node("Resonance", ConceptType.TOPIC, uid="uid_c2", within_chapter_order=2)

        groups = group_by_identity([node1a, node1b, node2a, node2b])
        # Energy nodes should be grouped, others singleton
        assert len(groups) == 3

        # Find the group with 2 nodes
        merged_group = [g for g in groups.values() if len(g) == 2]
        assert len(merged_group) == 1
        assert merged_group[0][0].topic_name == "Energy in SHM"
        assert merged_group[0][1].topic_name == "Energy SHM"

    def test_preserves_order(self):
        """Within each group, nodes appear in input order."""
        node1 = _make_node("Energy in SHM", ConceptType.TOPIC, uid="uid_1", within_chapter_order=1)
        node2 = _make_node("Energy SHM", ConceptType.TOPIC, uid="uid_2", within_chapter_order=5)
        node3 = _make_node("Energy of SHM", ConceptType.TOPIC, uid="uid_3", within_chapter_order=10)

        groups = group_by_identity([node1, node2, node3])
        assert len(groups) == 1
        group = list(groups.values())[0]
        assert group[0].uid == "uid_1"
        assert group[1].uid == "uid_2"
        assert group[2].uid == "uid_3"
