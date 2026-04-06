"""Salience scoring orchestrator — combines static + structural scores.

Computes salience for all nodes in a CurriculumExtractionResult and
optionally writes the scores to Neo4j as a post-ingestion step.

Usage:
    service = SalienceService()
    # Pure computation (no IO)
    scores = service.score(extraction, config)
    # Compute + write to Neo4j
    report = await service.score_and_write(driver, extraction, config)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lecture_pipeline.config import SalienceConfig
from lecture_pipeline.curriculum.models import CurriculumExtractionResult

from .pagerank_scorer import PageRankScorer
from .static_scorer import StaticScorer

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


@dataclass
class SalienceScores:
    """Salience scores for a single node."""

    uid: str
    static: float
    structural: float
    total: float


@dataclass
class SalienceReport:
    """Results of a salience scoring run."""

    nodes_scored: int = 0
    elapsed_seconds: float = 0.0
    static_range: tuple[float, float] = (0.0, 0.0)
    structural_range: tuple[float, float] = (0.0, 0.0)
    total_range: tuple[float, float] = (0.0, 0.0)
    top_10: list[tuple[str, float]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Salience — {self.nodes_scored} nodes scored, "
            f"total range [{self.total_range[0]:.1f}, {self.total_range[1]:.1f}], "
            f"{self.elapsed_seconds:.1f}s"
        )


class SalienceService:
    """Orchestrates static + structural salience scoring."""

    def __init__(
        self,
        *,
        static_scorer: StaticScorer | None = None,
        pagerank_scorer: PageRankScorer | None = None,
    ) -> None:
        self._static = static_scorer or StaticScorer()
        self._pagerank = pagerank_scorer or PageRankScorer()

    def score(
        self,
        extraction: CurriculumExtractionResult,
        config: SalienceConfig,
    ) -> dict[str, SalienceScores]:
        """Compute salience scores for all nodes. Pure computation, no IO.

        Returns:
            Mapping of uid → SalienceScores.
        """
        static_scores = self._static.score(extraction)
        structural_scores = self._pagerank.score(extraction)

        uid_to_name = {node.uid: node.topic_name for node in extraction.nodes}

        result: dict[str, SalienceScores] = {}
        for node in extraction.nodes:
            s = static_scores.get(node.uid, 5.0)
            p = structural_scores.get(node.uid, 0.0)
            total = config.alpha * s + config.beta * p
            result[node.uid] = SalienceScores(
                uid=node.uid, static=s, structural=p, total=total,
            )

        return result

    def _build_report(
        self,
        scores: dict[str, SalienceScores],
        uid_to_name: dict[str, str],
        elapsed: float,
    ) -> SalienceReport:
        """Build a report from computed scores."""
        if not scores:
            return SalienceReport(elapsed_seconds=elapsed)

        statics = [s.static for s in scores.values()]
        structurals = [s.structural for s in scores.values()]
        totals = [s.total for s in scores.values()]

        # Top 10 by total score
        sorted_scores = sorted(scores.values(), key=lambda s: s.total, reverse=True)
        top_10 = [
            (uid_to_name.get(s.uid, s.uid), s.total)
            for s in sorted_scores[:10]
        ]

        return SalienceReport(
            nodes_scored=len(scores),
            elapsed_seconds=elapsed,
            static_range=(min(statics), max(statics)),
            structural_range=(min(structurals), max(structurals)),
            total_range=(min(totals), max(totals)),
            top_10=top_10,
        )

    async def score_and_write(
        self,
        driver: AsyncDriver,
        extraction: CurriculumExtractionResult,
        config: SalienceConfig,
        *,
        database: str = "neo4j",
        batch_size: int = 100,
    ) -> SalienceReport:
        """Compute salience scores and write them to Neo4j.

        Args:
            driver: Async Neo4j driver (must be connected)
            extraction: The unified extraction result
            config: Salience weights (alpha, beta)
            database: Neo4j database name
            batch_size: Nodes per UNWIND batch

        Returns:
            SalienceReport with statistics.
        """
        start = time.monotonic()

        scores = self.score(extraction, config)
        uid_to_name = {node.uid: node.topic_name for node in extraction.nodes}

        # Write to Neo4j in batches
        items = [
            {"uid": s.uid, "static": s.static, "structural": s.structural, "total": s.total}
            for s in scores.values()
        ]

        query = (
            "UNWIND $batch AS item "
            "MATCH (n {uid: item.uid}) "
            "SET n.salience_static = item.static, "
            "    n.salience_structural = item.structural, "
            "    n.salience_total = item.total"
        )

        async with driver.session(database=database) as session:
            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]
                await session.run(query, {"batch": batch})

        elapsed = time.monotonic() - start
        report = self._build_report(scores, uid_to_name, elapsed)
        logger.info(report.summary())
        return report
