"""Unit tests for salience service orchestrator (no Neo4j required)."""

from __future__ import annotations

import pytest

from lecture_pipeline.config import SalienceConfig
from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.salience.salience_service import (
    SalienceReport,
    SalienceService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="Test", chapter_title="Ch1", page_range="1-10", extractor_model="test"
    )


def _node(
    uid: str,
    concept_type: ConceptType = ConceptType.DEFINITION,
    resolution_level: ResolutionLevel = ResolutionLevel.CONCEPT,
    topic_name: str | None = None,
    **kwargs,
) -> ExtractionNode:
    defaults = dict(
        uid=uid,
        topic_name=topic_name or uid,
        concept_type=concept_type,
        resolution_level=resolution_level,
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


service = SalienceService()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScoreCombination:
    def test_total_is_weighted_sum(self):
        """total ≈ α·static + β·structural for default config."""
        config = SalienceConfig()  # α=0.6, β=0.4
        nodes = [_node("a"), _node("b", within_chapter_order=2)]
        rels = [_rel("a", "b")]
        ext = _extraction(nodes, rels)

        scores = service.score(ext, config)
        for uid, s in scores.items():
            expected = config.alpha * s.static + config.beta * s.structural
            assert s.total == pytest.approx(expected, abs=1e-9)

    def test_alpha_one_beta_zero_equals_static(self):
        config = SalienceConfig(alpha=1.0, beta=0.0)
        nodes = [
            _node("a", concept_type=ConceptType.FORMULA),
            _node("b", concept_type=ConceptType.ANALOGY, within_chapter_order=2),
        ]
        ext = _extraction(nodes)
        scores = service.score(ext, config)

        assert scores["a"].total == pytest.approx(scores["a"].static)
        assert scores["b"].total == pytest.approx(scores["b"].static)

    def test_alpha_zero_beta_one_equals_structural(self):
        config = SalienceConfig(alpha=0.0, beta=1.0)
        nodes = [_node("a"), _node("b", within_chapter_order=2)]
        rels = [_rel("a", "b")]
        ext = _extraction(nodes, rels)
        scores = service.score(ext, config)

        assert scores["a"].total == pytest.approx(scores["a"].structural)
        assert scores["b"].total == pytest.approx(scores["b"].structural)


class TestExpectedRankings:
    def test_formula_with_high_pagerank_is_top(self):
        """A FORMULA node that's also a PageRank hub should score highest."""
        hub = _node("hub", concept_type=ConceptType.FORMULA)
        spokes = [
            _node(f"s{i}", concept_type=ConceptType.ANALOGY, within_chapter_order=i + 1)
            for i in range(5)
        ]
        rels = [_rel(f"s{i}", "hub") for i in range(5)]
        ext = _extraction([hub] + spokes, rels)

        config = SalienceConfig()
        scores = service.score(ext, config)

        hub_score = scores["hub"].total
        for spoke_uid in [f"s{i}" for i in range(5)]:
            assert hub_score > scores[spoke_uid].total

    def test_analogy_with_low_pagerank_is_bottom(self):
        """An ANALOGY node with no incoming edges should score lowest."""
        important = _node("imp", concept_type=ConceptType.FORMULA)
        low = _node("low", concept_type=ConceptType.ANALOGY, within_chapter_order=2)
        rels = [_rel("low", "imp")]  # low points to imp, not the other way
        ext = _extraction([important, low], rels)

        config = SalienceConfig()
        scores = service.score(ext, config)
        assert scores["low"].total < scores["imp"].total


class TestRealisticExtraction:
    def _build_realistic(self) -> CurriculumExtractionResult:
        """20 nodes, 30 relationships mimicking a real chapter."""
        nodes = []
        # Chapter node
        nodes.append(_node("ch", concept_type=ConceptType.TOPIC, resolution_level=ResolutionLevel.CHAPTER, within_chapter_order=0))
        # 5 key concepts
        for i in range(5):
            nodes.append(_node(f"c{i}", concept_type=ConceptType.DEFINITION, within_chapter_order=i + 1))
        # 3 formulas
        for i in range(3):
            nodes.append(_node(f"f{i}", concept_type=ConceptType.FORMULA, within_chapter_order=i + 6))
        # 5 examples
        for i in range(5):
            nodes.append(_node(f"e{i}", concept_type=ConceptType.EXAMPLE, within_chapter_order=i + 9))
        # 3 analogies
        for i in range(3):
            nodes.append(_node(f"a{i}", concept_type=ConceptType.ANALOGY, within_chapter_order=i + 14))
        # 3 details
        for i in range(3):
            nodes.append(_node(f"d{i}", concept_type=ConceptType.DEFINITION, resolution_level=ResolutionLevel.DETAIL, within_chapter_order=i + 17))

        rels = []
        # Chain: c0→c1→c2→c3→c4 (prerequisite chain)
        for i in range(4):
            rels.append(_rel(f"c{i}", f"c{i+1}"))
        # Formulas derive from concepts
        rels.append(_rel("c1", "f0", CurriculumRelationType.LEADS_TO))
        rels.append(_rel("c2", "f1", CurriculumRelationType.LEADS_TO))
        rels.append(_rel("c3", "f2", CurriculumRelationType.LEADS_TO))
        # Examples of concepts (should NOT affect PageRank)
        for i in range(5):
            rels.append(_rel(f"e{i}", f"c{i}", CurriculumRelationType.EXAMPLE_OF))
        # Cross-references
        rels.append(_rel("f0", "f1", CurriculumRelationType.LEADS_TO))
        rels.append(_rel("c0", "f2", CurriculumRelationType.PREREQUISITE))
        # Hierarchy (should NOT affect PageRank)
        for i in range(5):
            rels.append(_rel("ch", f"c{i}", CurriculumRelationType.CONTAINS))

        return _extraction(nodes, rels)

    def test_report_has_correct_count(self):
        ext = self._build_realistic()
        config = SalienceConfig()
        scores = service.score(ext, config)
        assert len(scores) == 20

    def test_all_scores_in_range(self):
        ext = self._build_realistic()
        config = SalienceConfig()
        scores = service.score(ext, config)
        for uid, s in scores.items():
            assert 0.0 <= s.total <= 10.0, f"{uid} total {s.total} out of range"
            assert 0.0 <= s.static <= 10.0, f"{uid} static {s.static} out of range"
            assert 0.0 <= s.structural <= 10.0, f"{uid} structural {s.structural} out of range"

    def test_formulas_rank_above_analogies(self):
        ext = self._build_realistic()
        config = SalienceConfig()
        scores = service.score(ext, config)

        formula_scores = [scores[f"f{i}"].total for i in range(3)]
        analogy_scores = [scores[f"a{i}"].total for i in range(3)]
        assert min(formula_scores) > max(analogy_scores)


class TestReportBuilding:
    def test_report_from_score(self):
        ext = _extraction([
            _node("a", concept_type=ConceptType.FORMULA, topic_name="Force"),
            _node("b", concept_type=ConceptType.ANALOGY, within_chapter_order=2, topic_name="Pushing"),
        ])
        config = SalienceConfig()
        scores = service.score(ext, config)

        # Build report manually using the private method
        uid_to_name = {n.uid: n.topic_name for n in ext.nodes}
        report = service._build_report(scores, uid_to_name, 0.01)

        assert report.nodes_scored == 2
        assert report.elapsed_seconds == pytest.approx(0.01)
        assert len(report.top_10) == 2
        # First entry should be highest scorer
        assert report.top_10[0][1] >= report.top_10[1][1]

    def test_report_summary_string(self):
        report = SalienceReport(
            nodes_scored=50,
            elapsed_seconds=0.5,
            total_range=(2.0, 9.5),
        )
        summary = report.summary()
        assert "50" in summary
        assert "2.0" in summary
        assert "9.5" in summary

    def test_empty_report(self):
        scores: dict = {}
        report = service._build_report(scores, {}, 0.0)
        assert report.nodes_scored == 0
