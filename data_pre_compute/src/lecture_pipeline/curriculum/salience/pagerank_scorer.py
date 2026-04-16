"""Structural salience via iterative PageRank on the curriculum graph.

Runs PageRank on PREREQUISITE and LEADS_TO edges only — structural
hierarchy (CONTAINS, SUMMARIZES) and examples/analogies are excluded.

Pure Python, no Neo4j GDS dependency. Practical for curriculum graphs
(hundreds to low thousands of nodes per book).

Scores normalized to [0, 10] via min-max scaling.
"""

from __future__ import annotations

from collections import defaultdict

from lecture_pipeline.curriculum.models import (
    CurriculumExtractionResult,
    CurriculumRelationType,
)

# Relationship types that define the PageRank subgraph
_PAGERANK_TYPES = {
    CurriculumRelationType.PREREQUISITE,
    CurriculumRelationType.LEADS_TO,
}


class PageRankScorer:
    """Compute structural salience via iterative PageRank."""

    def __init__(
        self,
        *,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
    ) -> None:
        self._damping = damping
        self._max_iterations = max_iterations
        self._tolerance = tolerance

    def score(self, extraction: CurriculumExtractionResult) -> dict[str, float]:
        """Compute PageRank for all nodes, normalized to [0, 10].

        Returns:
            Mapping of uid → structural salience score in [0, 10].
        """
        if not extraction.nodes:
            return {}

        node_uids = {node.uid for node in extraction.nodes}
        n = len(node_uids)

        if n == 1:
            uid = next(iter(node_uids))
            return {uid: 5.0}

        # Build adjacency: outgoing[u] = list of nodes u points to
        # incoming[v] = list of nodes pointing to v
        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming: dict[str, list[str]] = defaultdict(list)

        for rel in extraction.relationships:
            if rel.type not in _PAGERANK_TYPES:
                continue
            if rel.from_uid not in node_uids or rel.to_uid not in node_uids:
                continue
            outgoing[rel.from_uid].append(rel.to_uid)
            incoming[rel.to_uid].append(rel.from_uid)

        # Initialize scores uniformly
        d = self._damping
        base = (1.0 - d) / n
        scores = {uid: 1.0 / n for uid in node_uids}

        # Iterate until convergence
        for _ in range(self._max_iterations):
            new_scores: dict[str, float] = {}
            for uid in node_uids:
                rank = base
                for src in incoming.get(uid, []):
                    out_deg = len(outgoing[src])
                    if out_deg > 0:
                        rank += d * scores[src] / out_deg
                new_scores[uid] = rank

            # Check convergence
            max_delta = max(
                abs(new_scores[uid] - scores[uid]) for uid in node_uids
            )
            scores = new_scores
            if max_delta < self._tolerance:
                break

        # Normalize to [0, 10]
        return self._normalize(scores)

    @staticmethod
    def _normalize(scores: dict[str, float]) -> dict[str, float]:
        """Min-max normalize scores to [0, 10]."""
        if not scores:
            return {}
        min_s = min(scores.values())
        max_s = max(scores.values())
        if max_s - min_s < 1e-12:
            return {uid: 5.0 for uid in scores}
        scale = 10.0 / (max_s - min_s)
        return {uid: (s - min_s) * scale for uid, s in scores.items()}
