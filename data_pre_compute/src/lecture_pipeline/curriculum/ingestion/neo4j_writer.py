"""Async Neo4j writer for curriculum graph ingestion.

Executes parameterized Cypher statements in batches with idempotent MERGE
semantics. Handles batch transaction failures with per-statement fallback.

Adapted from PMG's unified_pipeline.py batch execution pattern.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from neo4j import AsyncGraphDatabase

from lecture_pipeline.config import Neo4jConfig
from lecture_pipeline.curriculum.schema import initialize_schema

from .cypher_generator import CypherStatement

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    """Tracks what happened during Neo4j ingestion."""

    # Input counts
    total_statements: int = 0
    node_statements: int = 0
    relationship_statements: int = 0

    # Execution results
    statements_succeeded: int = 0
    statements_failed: int = 0

    # Neo4j counters
    nodes_created: int = 0
    relationships_created: int = 0
    properties_set: int = 0

    # Timing
    elapsed_seconds: float = 0.0

    # Diagnostics
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "OK" if not self.errors else f"ERRORS: {len(self.errors)}"
        return (
            f"Ingestion {status} — "
            f"{self.statements_succeeded}/{self.total_statements} statements, "
            f"{self.nodes_created} nodes created, "
            f"{self.relationships_created} rels created, "
            f"{self.properties_set} props set, "
            f"{self.elapsed_seconds:.1f}s"
        )


class Neo4jWriter:
    """Async Neo4j writer with batch execution and fallback error handling.

    Usage:
        async with Neo4jWriter(config) as writer:
            report = await writer.ingest(statements)
    """

    def __init__(self, config: Neo4jConfig) -> None:
        self._config = config
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Create the Neo4j driver and verify connectivity."""
        self._driver = AsyncGraphDatabase.driver(
            self._config.uri,
            auth=(self._config.username, self._config.password),
            max_connection_pool_size=50,
            connection_acquisition_timeout=30.0,
        )
        await self._driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", self._config.uri)

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> Neo4jWriter:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        await self.close()

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError(
                "Neo4jWriter not connected. Use 'async with' or call connect()."
            )
        return self._driver

    async def ingest(
        self,
        statements: list[CypherStatement],
        *,
        batch_size: int = 50,
        initialize: bool = True,
    ) -> IngestionReport:
        """Execute all Cypher statements: schema init → nodes → relationships.

        Args:
            statements: CypherStatements from CypherGenerator.generate()
            batch_size: Statements per transaction (default 50)
            initialize: Whether to initialize schema first (default True)

        Returns:
            IngestionReport with execution statistics
        """
        start = time.monotonic()
        report = IngestionReport()

        # Split nodes and relationships
        node_stmts = [s for s in statements if s.category == "node"]
        rel_stmts = [s for s in statements if s.category == "relationship"]

        report.total_statements = len(statements)
        report.node_statements = len(node_stmts)
        report.relationship_statements = len(rel_stmts)

        # Initialize schema (idempotent)
        if initialize:
            try:
                await initialize_schema(
                    self.driver,
                    database=self._config.database,
                    embedding_dimensions=self._config.embedding_dimensions,
                )
            except Exception as e:
                report.errors.append(f"Schema initialization failed: {e}")
                logger.error("Schema initialization failed: %s", e)

        # Execute nodes first, then relationships
        logger.info(
            "Ingesting %d nodes + %d relationships (batch_size=%d)",
            len(node_stmts),
            len(rel_stmts),
            batch_size,
        )

        await self._execute_batched(node_stmts, batch_size, report)
        await self._execute_batched(rel_stmts, batch_size, report)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    async def _execute_batched(
        self,
        statements: list[CypherStatement],
        batch_size: int,
        report: IngestionReport,
    ) -> None:
        """Execute statements in batched transactions with fallback."""
        for i in range(0, len(statements), batch_size):
            batch = statements[i : i + batch_size]
            try:
                await self._execute_batch_tx(batch, report)
            except Exception as e:
                logger.warning(
                    "Batch %d-%d failed (%s), falling back to per-statement",
                    i,
                    i + len(batch),
                    e,
                )
                # Fallback: execute each statement individually
                for stmt in batch:
                    await self._execute_single(stmt, report)

    async def _execute_batch_tx(
        self,
        batch: list[CypherStatement],
        report: IngestionReport,
    ) -> None:
        """Execute a batch of statements in a single transaction."""
        async with self.driver.session(database=self._config.database) as session:
            async with await session.begin_transaction() as tx:
                for stmt in batch:
                    result = await tx.run(stmt.query, stmt.params)
                    summary = await result.consume()
                    self._accumulate_counters(summary.counters, report)
                    report.statements_succeeded += 1
                await tx.commit()

    async def _execute_single(
        self,
        stmt: CypherStatement,
        report: IngestionReport,
    ) -> None:
        """Execute a single statement with error handling."""
        try:
            async with self.driver.session(database=self._config.database) as session:
                result = await session.run(stmt.query, stmt.params)
                summary = await result.consume()
                self._accumulate_counters(summary.counters, report)
                report.statements_succeeded += 1
        except Exception as e:
            report.statements_failed += 1
            error_msg = f"Failed [{stmt.category}] {stmt.uid_hint}: {e}"
            report.errors.append(error_msg)
            logger.error(error_msg)

    def _accumulate_counters(self, counters, report: IngestionReport) -> None:  # noqa: ANN001
        """Add Neo4j result counters to the report."""
        report.nodes_created += counters.nodes_created
        report.relationships_created += counters.relationships_created
        report.properties_set += counters.properties_set

    async def verify_ingestion(self) -> dict[str, Any]:
        """Post-ingestion verification: count nodes by label and relationships by type.

        Returns dict with 'nodes_by_label' and 'relationships_by_type'.
        """
        info: dict[str, Any] = {}

        async with self.driver.session(database=self._config.database) as session:
            # Count nodes by label
            result = await session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY label"
            )
            records = [r.data() async for r in result]
            info["nodes_by_label"] = {r["label"]: r["cnt"] for r in records}

            # Count relationships by type
            result = await session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt "
                "ORDER BY rel_type"
            )
            records = [r.data() async for r in result]
            info["relationships_by_type"] = {r["rel_type"]: r["cnt"] for r in records}

        return info
