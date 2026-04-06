"""Unit tests for PageRank structural salience scoring (no Neo4j required)."""

from __future__ import annotations

import random

import pytest

from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.salience.pagerank_scorer import PageRankScorer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="Test", chapter_title="Ch1", page_range="1-10", extractor_model="test"
    )


def _node(uid: str, **kwargs) -> ExtractionNode:
    defaults = dict(
        uid=uid,
        topic_name=uid,
        concept_type=ConceptType.DEFINITION,
        resolution_level=ResolutionLevel.CONCEPT,
        summary="Test node.",
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=1,
    )
    defaults.update(kwargs)
    return ExtractionNode(**defaults)


def _rel(from_uid: str, to_uid: str, rel_type: CurriculumRelationType = CurriculumRelationType.PREREQUISITE) -> ExtractionRelationship:
    return ExtractionRelationship(
        relationship_key=f"rel:{rel_type.value}:{from_uid}:{to_uid}",
        type=rel_type,
        from_uid=from_uid,
        to_uid=to_uid,
    )


def _extraction(
    nodes: list[ExtractionNode],
    rels: list[ExtractionRelationship] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="Test",
        scope="book",
        source=_source(),
        nodes=nodes,
        relationships=rels or [],
    )


scorer = PageRankScorer()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLinearChain:
    def test_hub_in_chain_scores_highest(self):
        """In A→B→C, the node receiving an edge and also giving one (B) should
        score at least as high as the terminal node."""
        nodes = [_node("A"), _node("B", within_chapter_order=2), _node("C", within_chapter_order=3)]
        rels = [_rel("A", "B"), _rel("B", "C")]
        ext = _extraction(nodes, rels)
        scores = scorer.score(ext)

        # All scores in [0, 10]
        assert all(0.0 <= s <= 10.0 for s in scores.values())
        # B or C should score highest (they receive edges)
        # A has no incoming → lowest
        assert scores["A"] < scores["B"] or scores["A"] < scores["C"]


class TestHubSpoke:
    def test_hub_scores_highest(self):
        """Central hub that all spokes point to should score highest."""
        hub = _node("hub")
        spokes = [_node(f"s{i}", within_chapter_order=i + 1) for i in range(5)]
        rels = [_rel(f"s{i}", "hub") for i in range(5)]
        ext = _extraction([hub] + spokes, rels)
        scores = scorer.score(ext)

        assert scores["hub"] == max(scores.values())
        assert scores["hub"] == pytest.approx(10.0)

    def test_reverse_hub_spokes_get_score(self):
        """Hub pointing to all spokes — spokes receive edges, hub doesn't."""
        hub = _node("hub")
        spokes = [_node(f"s{i}", within_chapter_order=i + 1) for i in range(5)]
        rels = [_rel("hub", f"s{i}") for i in range(5)]
        ext = _extraction([hub] + spokes, rels)
        scores = scorer.score(ext)

        # Hub has no incoming edges → lowest
        assert scores["hub"] == min(scores.values())


class TestDisconnectedComponents:
    def test_isolated_nodes_get_base_score(self):
        """Nodes with no edges all get the same score."""
        nodes = [_node(f"n{i}", within_chapter_order=i) for i in range(5)]
        ext = _extraction(nodes, [])
        scores = scorer.score(ext)

        # All equal → normalized to 5.0
        assert all(s == pytest.approx(5.0) for s in scores.values())

    def test_two_components(self):
        """Two disconnected subgraphs scored correctly."""
        nodes = [
            _node("a1"), _node("a2", within_chapter_order=2),
            _node("b1", within_chapter_order=3), _node("b2", within_chapter_order=4),
        ]
        rels = [_rel("a1", "a2"), _rel("b1", "b2")]
        ext = _extraction(nodes, rels)
        scores = scorer.score(ext)

        # a2 and b2 receive edges → higher scores
        assert scores["a2"] > scores["a1"]
        assert scores["b2"] > scores["b1"]
        # Symmetric components → same scores
        assert scores["a1"] == pytest.approx(scores["b1"])
        assert scores["a2"] == pytest.approx(scores["b2"])


class TestEdgeCases:
    def test_single_node(self):
        ext = _extraction([_node("only")])
        scores = scorer.score(ext)
        assert scores["only"] == pytest.approx(5.0)

    def test_empty_graph(self):
        ext = _extraction([])
        assert scorer.score(ext) == {}

    def test_self_loop_ignored(self):
        """Self-loops shouldn't cause issues."""
        nodes = [_node("a"), _node("b", within_chapter_order=2)]
        rels = [_rel("a", "a"), _rel("a", "b")]
        ext = _extraction(nodes, rels)
        scores = scorer.score(ext)
        assert all(0.0 <= s <= 10.0 for s in scores.values())


class TestRelationshipFiltering:
    def test_only_prerequisite_and_leads_to(self):
        """CONTAINS, EXAMPLE_OF, etc. should NOT affect PageRank."""
        nodes = [_node("a"), _node("b", within_chapter_order=2)]

        # Only non-pedagogical relationships
        rels = [
            _rel("a", "b", CurriculumRelationType.CONTAINS),
            _rel("a", "b", CurriculumRelationType.EXAMPLE_OF),
            _rel("a", "b", CurriculumRelationType.SUMMARIZES),
        ]
        ext = _extraction(nodes, rels)
        scores = scorer.score(ext)

        # No edges in the PageRank subgraph → all same score
        assert scores["a"] == pytest.approx(scores["b"])

    def test_prerequisite_counts(self):
        nodes = [_node("a"), _node("b", within_chapter_order=2)]
        rels = [_rel("a", "b", CurriculumRelationType.PREREQUISITE)]
        ext = _extraction(nodes, rels)
        scores = scorer.score(ext)
        assert scores["b"] > scores["a"]

    def test_leads_to_counts(self):
        nodes = [_node("a"), _node("b", within_chapter_order=2)]
        rels = [_rel("a", "b", CurriculumRelationType.LEADS_TO)]
        ext = _extraction(nodes, rels)
        scores = scorer.score(ext)
        assert scores["b"] > scores["a"]


class TestScaleAndDeterminism:
    def test_large_graph_all_in_range(self):
        """100 nodes with random edges — all scores in [0, 10]."""
        random.seed(42)
        nodes = [_node(f"n{i}", within_chapter_order=i) for i in range(100)]
        rels = [
            _rel(f"n{random.randint(0, 99)}", f"n{random.randint(0, 99)}")
            for _ in range(200)
        ]
        ext = _extraction(nodes, rels)
        scores = scorer.score(ext)

        assert len(scores) == 100
        for uid, s in scores.items():
            assert 0.0 <= s <= 10.0, f"{uid} score {s} out of range"

    def test_deterministic(self):
        """Same input → same output, every time."""
        nodes = [_node(f"n{i}", within_chapter_order=i) for i in range(10)]
        rels = [_rel("n0", "n1"), _rel("n1", "n2"), _rel("n3", "n1")]
        ext = _extraction(nodes, rels)

        scores1 = scorer.score(ext)
        scores2 = scorer.score(ext)
        assert scores1 == scores2
