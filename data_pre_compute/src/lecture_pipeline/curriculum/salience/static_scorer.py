"""Rule-based static salience scoring for curriculum nodes.

Scores are determined by concept type (FORMULA > DEFINITION > EXAMPLE > ...),
resolution level (CHAPTER > CONCEPT > DETAIL), and in-degree from pedagogical
relationships (nodes that many others depend on are more important).

All scores are clamped to [0, 10].
"""

from __future__ import annotations

from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    ResolutionLevel,
)

# ---------------------------------------------------------------------------
# Scoring tables (from design doc §5.6)
# ---------------------------------------------------------------------------

CONCEPT_TYPE_SCORES: dict[ConceptType, float] = {
    ConceptType.FORMULA: 9.0,
    ConceptType.MISCONCEPTION: 8.5,
    ConceptType.DEFINITION: 8.0,
    ConceptType.TOPIC: 7.0,
    ConceptType.DERIVATION: 7.0,
    ConceptType.APPLICATION: 6.0,
    ConceptType.EXAMPLE: 5.0,
    ConceptType.EXPERIMENT: 5.0,
    ConceptType.VISUALIZATION: 4.0,
    ConceptType.ANALOGY: 4.0,
}

RESOLUTION_BOOST: dict[ResolutionLevel, float] = {
    ResolutionLevel.SYLLABUS: 2.0,
    ResolutionLevel.UNIT: 1.5,
    ResolutionLevel.CHAPTER: 1.0,
    ResolutionLevel.CONCEPT: 0.0,
    ResolutionLevel.DETAIL: -1.0,
}

# Relationship types that count toward in-degree boost
_PEDAGOGICAL_TYPES = {
    CurriculumRelationType.PREREQUISITE,
    CurriculumRelationType.LEADS_TO,
}

# In-degree boost: 0.5 per incoming edge, capped at 2.0
_IN_DEGREE_FACTOR = 0.5
_IN_DEGREE_CAP = 2.0


class StaticScorer:
    """Compute static salience from concept type, resolution level, and in-degree."""

    def score(self, extraction: CurriculumExtractionResult) -> dict[str, float]:
        """Score all nodes in the extraction.

        Returns:
            Mapping of uid → static salience score in [0, 10].
        """
        if not extraction.nodes:
            return {}

        # Build in-degree map from pedagogical relationships
        in_degree: dict[str, int] = {}
        for rel in extraction.relationships:
            if rel.type in _PEDAGOGICAL_TYPES:
                in_degree[rel.to_uid] = in_degree.get(rel.to_uid, 0) + 1

        scores: dict[str, float] = {}
        for node in extraction.nodes:
            base = CONCEPT_TYPE_SCORES.get(node.concept_type, 5.0)
            base += RESOLUTION_BOOST.get(node.resolution_level, 0.0)
            base += min(in_degree.get(node.uid, 0) * _IN_DEGREE_FACTOR, _IN_DEGREE_CAP)
            scores[node.uid] = max(0.0, min(10.0, base))

        return scores
