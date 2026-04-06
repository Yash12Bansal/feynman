"""Neo4j writer for Visual nodes and HAS_VISUAL edges.

Stores pre-generated DiagramSpec JSON as (:Visual) nodes linked to their
(:Concept) nodes via [:HAS_VISUAL] relationships. All writes use MERGE
for idempotent re-runs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .models import DiagramSpec

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class VisualWriteReport:
    """Tracks Visual node writes to Neo4j."""

    visuals_written: int = 0
    edges_written: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "OK" if not self.errors else f"ERRORS: {len(self.errors)}"
        return (
            f"Visual write {status} — "
            f"{self.visuals_written} visuals, "
            f"{self.edges_written} edges, "
            f"{self.elapsed_seconds:.1f}s"
        )


# ---------------------------------------------------------------------------
# Cypher templates
# ---------------------------------------------------------------------------

# Single statement: create Visual node + HAS_VISUAL edge in one query
_MERGE_VISUAL_CYPHER = """
MERGE (v:Visual {uid: $visual_uid})
SET v.diagram_spec = $diagram_spec,
    v.spec_version = $spec_version,
    v.generation_model = $generation_model,
    v.generated_at = datetime(),
    v.element_count = $element_count,
    v.has_interactive_params = $has_params,
    v.width = $width,
    v.height = $height,
    v.title = $title
WITH v
MERGE (c {uid: $concept_uid})
MERGE (c)-[:HAS_VISUAL]->(v)
"""


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class Neo4jVisualWriter:
    """Writes Visual nodes and HAS_VISUAL edges to Neo4j."""

    async def write_visuals(
        self,
        driver: AsyncDriver,
        visuals: list[tuple[str, DiagramSpec]],
        *,
        generation_model: str,
        database: str = "neo4j",
        batch_size: int = 50,
    ) -> VisualWriteReport:
        """Write Visual nodes and link them to Concept nodes.

        Args:
            driver: Active Neo4j async driver.
            visuals: List of (concept_uid, DiagramSpec) pairs. The visual UID
                is derived internally from the concept UID.
            generation_model: Model name that generated the specs (stored as metadata).
            database: Neo4j database name.
            batch_size: Statements per transaction.

        Returns:
            VisualWriteReport with write statistics.
        """
        start = time.monotonic()
        report = VisualWriteReport()

        if not visuals:
            report.elapsed_seconds = time.monotonic() - start
            return report

        # Build parameter dicts for each visual
        param_sets = [
            self._build_params(concept_uid, spec, generation_model)
            for concept_uid, spec in visuals
        ]

        # Batch execute
        for i in range(0, len(param_sets), batch_size):
            batch = param_sets[i : i + batch_size]
            try:
                await self._execute_batch(driver, batch, database, report)
            except Exception as e:
                logger.warning(
                    "Batch %d-%d failed (%s), falling back to per-statement",
                    i,
                    i + len(batch),
                    e,
                )
                for params in batch:
                    await self._execute_single(driver, params, database, report)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    def _build_params(
        self,
        concept_uid: str,
        spec: DiagramSpec,
        generation_model: str,
    ) -> dict[str, Any]:
        """Build Cypher parameter dict for a single visual."""
        # Derive visual UID from concept UID
        if concept_uid.startswith("curriculum:"):
            visual_uid = "visual:" + concept_uid[len("curriculum:"):]
        else:
            visual_uid = "visual:" + concept_uid

        return {
            "visual_uid": visual_uid,
            "concept_uid": concept_uid,
            "diagram_spec": spec.model_dump_json(),
            "spec_version": "1.0",
            "generation_model": generation_model,
            "element_count": len(spec.elements),
            "has_params": len(spec.parameters) > 0,
            "width": spec.width,
            "height": spec.height,
            "title": spec.title,
        }

    async def _execute_batch(
        self,
        driver: AsyncDriver,
        batch: list[dict[str, Any]],
        database: str,
        report: VisualWriteReport,
    ) -> None:
        """Execute a batch of visual writes in a single transaction."""
        async with driver.session(database=database) as session:
            async with session.begin_transaction() as tx:
                for params in batch:
                    await tx.run(_MERGE_VISUAL_CYPHER, params)
                    report.visuals_written += 1
                    report.edges_written += 1
                await tx.commit()

    async def _execute_single(
        self,
        driver: AsyncDriver,
        params: dict[str, Any],
        database: str,
        report: VisualWriteReport,
    ) -> None:
        """Execute a single visual write with error handling."""
        try:
            async with driver.session(database=database) as session:
                await session.run(_MERGE_VISUAL_CYPHER, params)
                report.visuals_written += 1
                report.edges_written += 1
        except Exception as e:
            error_msg = (
                f"Failed to write visual {params['visual_uid']!r}: {e}"
            )
            report.errors.append(error_msg)
            logger.error(error_msg)
