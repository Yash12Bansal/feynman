"""Unit tests for static salience scoring (no Neo4j required)."""

from __future__ import annotations

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
from lecture_pipeline.curriculum.salience.static_scorer import (
    CONCEPT_TYPE_SCORES,
    RESOLUTION_BOOST,
    StaticScorer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="Test", chapter_title="Ch1", page_range="1-10", extractor_model="test"
    )


def _node(
    uid: str = "curriculum:physics:ch1:test",
    concept_type: ConceptType = ConceptType.DEFINITION,
    resolution_level: ResolutionLevel = ResolutionLevel.CONCEPT,
    **kwargs,
) -> ExtractionNode:
    defaults = dict(
        uid=uid,
        topic_name="Test",
        concept_type=concept_type,
        resolution_level=resolution_level,
        summary="A test node.",
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=1,
    )
    defaults.update(kwargs)
    return ExtractionNode(**defaults)


def _extraction(
    nodes: list[ExtractionNode] | None = None,
    rels: list[ExtractionRelationship] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="Test",
        scope="book",
        source=_source(),
        nodes=nodes or [],
        relationships=rels or [],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

scorer = StaticScorer()


class TestConceptTypeScoring:
    def test_formula_higher_than_example(self):
        ext = _extraction(nodes=[
            _node(uid="a", concept_type=ConceptType.FORMULA),
            _node(uid="b", concept_type=ConceptType.EXAMPLE),
        ])
        scores = scorer.score(ext)
        assert scores["a"] > scores["b"]

    def test_definition_higher_than_analogy(self):
        ext = _extraction(nodes=[
            _node(uid="a", concept_type=ConceptType.DEFINITION),
            _node(uid="b", concept_type=ConceptType.ANALOGY),
        ])
        scores = scorer.score(ext)
        assert scores["a"] > scores["b"]

    def test_misconception_higher_than_application(self):
        ext = _extraction(nodes=[
            _node(uid="a", concept_type=ConceptType.MISCONCEPTION),
            _node(uid="b", concept_type=ConceptType.APPLICATION),
        ])
        scores = scorer.score(ext)
        assert scores["a"] > scores["b"]

    def test_full_ordering(self):
        """FORMULA > MISCONCEPTION > DEFINITION > TOPIC = DERIVATION > APPLICATION > EXAMPLE = EXPERIMENT > VISUALIZATION = ANALOGY."""
        types = list(ConceptType)
        nodes = [_node(uid=f"n:{t.value}", concept_type=t) for t in types]
        ext = _extraction(nodes=nodes)
        scores = scorer.score(ext)

        def s(ct: ConceptType) -> float:
            return scores[f"n:{ct.value}"]

        assert s(ConceptType.FORMULA) > s(ConceptType.MISCONCEPTION)
        assert s(ConceptType.MISCONCEPTION) > s(ConceptType.DEFINITION)
        assert s(ConceptType.DEFINITION) > s(ConceptType.TOPIC)
        assert s(ConceptType.TOPIC) == s(ConceptType.DERIVATION)
        assert s(ConceptType.DERIVATION) > s(ConceptType.APPLICATION)
        assert s(ConceptType.APPLICATION) > s(ConceptType.EXAMPLE)
        assert s(ConceptType.EXAMPLE) == s(ConceptType.EXPERIMENT)
        assert s(ConceptType.EXPERIMENT) > s(ConceptType.VISUALIZATION)
        assert s(ConceptType.VISUALIZATION) == s(ConceptType.ANALOGY)

    def test_all_concept_types_covered(self):
        """Every ConceptType has an explicit score."""
        for ct in ConceptType:
            assert ct in CONCEPT_TYPE_SCORES


class TestResolutionBoost:
    def test_chapter_higher_than_concept(self):
        ext = _extraction(nodes=[
            _node(uid="ch", concept_type=ConceptType.DEFINITION, resolution_level=ResolutionLevel.CHAPTER),
            _node(uid="co", concept_type=ConceptType.DEFINITION, resolution_level=ResolutionLevel.CONCEPT),
        ])
        scores = scorer.score(ext)
        assert scores["ch"] > scores["co"]

    def test_concept_higher_than_detail(self):
        ext = _extraction(nodes=[
            _node(uid="co", concept_type=ConceptType.DEFINITION, resolution_level=ResolutionLevel.CONCEPT),
            _node(uid="de", concept_type=ConceptType.DEFINITION, resolution_level=ResolutionLevel.DETAIL),
        ])
        scores = scorer.score(ext)
        assert scores["co"] > scores["de"]

    def test_syllabus_highest_boost(self):
        ext = _extraction(nodes=[
            _node(uid="sy", concept_type=ConceptType.TOPIC, resolution_level=ResolutionLevel.SYLLABUS),
            _node(uid="un", concept_type=ConceptType.TOPIC, resolution_level=ResolutionLevel.UNIT),
            _node(uid="ch", concept_type=ConceptType.TOPIC, resolution_level=ResolutionLevel.CHAPTER),
        ])
        scores = scorer.score(ext)
        assert scores["sy"] > scores["un"] > scores["ch"]

    def test_all_resolution_levels_covered(self):
        for rl in ResolutionLevel:
            assert rl in RESOLUTION_BOOST


class TestInDegreeBoost:
    def test_node_with_prereqs_scores_higher(self):
        """Node with 4 PREREQUISITE edges pointing to it scores higher than isolated node."""
        target = _node(uid="target")
        sources = [_node(uid=f"src_{i}", within_chapter_order=i + 2) for i in range(4)]
        rels = [
            ExtractionRelationship(
                relationship_key=f"rel:prereq:{i}",
                type=CurriculumRelationType.PREREQUISITE,
                from_uid=f"src_{i}",
                to_uid="target",
            )
            for i in range(4)
        ]
        isolated = _node(uid="isolated", within_chapter_order=10)
        ext = _extraction(nodes=[target, isolated] + sources, rels=rels)
        scores = scorer.score(ext)
        assert scores["target"] > scores["isolated"]

    def test_in_degree_capped(self):
        """In-degree boost capped at 2.0 even with 10 incoming edges."""
        target = _node(uid="target")
        sources = [_node(uid=f"src_{i}", within_chapter_order=i + 2) for i in range(10)]
        rels = [
            ExtractionRelationship(
                relationship_key=f"rel:prereq:{i}",
                type=CurriculumRelationType.PREREQUISITE,
                from_uid=f"src_{i}",
                to_uid="target",
            )
            for i in range(10)
        ]
        ext = _extraction(nodes=[target] + sources, rels=rels)
        scores = scorer.score(ext)

        # Base for DEFINITION + CONCEPT + cap = 8.0 + 0.0 + 2.0 = 10.0
        assert scores["target"] == pytest.approx(10.0)

    def test_leads_to_also_counts(self):
        """LEADS_TO edges also contribute to in-degree boost."""
        target = _node(uid="target")
        src = _node(uid="src", within_chapter_order=2)
        rel = ExtractionRelationship(
            relationship_key="rel:leads_to:src:target",
            type=CurriculumRelationType.LEADS_TO,
            from_uid="src",
            to_uid="target",
        )
        ext = _extraction(nodes=[target, src], rels=[rel])
        scores = scorer.score(ext)
        # target gets 0.5 boost, src gets 0
        assert scores["target"] > scores["src"]

    def test_contains_does_not_boost(self):
        """CONTAINS edges should NOT contribute to in-degree boost."""
        target = _node(uid="target")
        parent = _node(uid="parent", resolution_level=ResolutionLevel.CHAPTER, within_chapter_order=0)
        rel = ExtractionRelationship(
            relationship_key="rel:contains:parent:target",
            type=CurriculumRelationType.CONTAINS,
            from_uid="parent",
            to_uid="target",
        )
        ext_with = _extraction(nodes=[target, parent], rels=[rel])
        ext_without = _extraction(nodes=[target, parent], rels=[])
        # Same type → same score (CONTAINS doesn't boost)
        assert scorer.score(ext_with)["target"] == scorer.score(ext_without)["target"]


class TestEdgeCases:
    def test_empty_extraction(self):
        assert scorer.score(_extraction()) == {}

    def test_all_scores_in_range(self):
        """All scores must be in [0, 10]."""
        nodes = [
            _node(uid=f"n:{ct.value}:{rl.value}", concept_type=ct, resolution_level=rl, within_chapter_order=i)
            for i, (ct, rl) in enumerate(
                [(ct, rl) for ct in ConceptType for rl in ResolutionLevel]
            )
        ]
        ext = _extraction(nodes=nodes)
        scores = scorer.score(ext)
        for uid, s in scores.items():
            assert 0.0 <= s <= 10.0, f"{uid} score {s} out of range"

    def test_detail_analogy_does_not_go_below_zero(self):
        """ANALOGY (4.0) + DETAIL (-1.0) = 3.0, not negative."""
        ext = _extraction(nodes=[
            _node(uid="low", concept_type=ConceptType.ANALOGY, resolution_level=ResolutionLevel.DETAIL),
        ])
        scores = scorer.score(ext)
        assert scores["low"] == pytest.approx(3.0)
        assert scores["low"] >= 0.0
