"""Async Neo4j writer for v2 ingestion.

Executes Cypher statements in batches with per-statement fallback so one
bad row can't fail the batch. Pattern carried from v1 verbatim, simplified
to v2's flatter schema.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from neo4j import AsyncGraphDatabase

from ...config import Neo4jConfig
from ..schema import initialize_schema
from .cypher_generator import CypherStatement

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    total_statements: int = 0
    node_statements: int = 0
    edge_statements: int = 0
    statements_succeeded: int = 0
    statements_failed: int = 0
    nodes_created: int = 0
    relationships_created: int = 0
    properties_set: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

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
    def __init__(self, config: Neo4jConfig):
        self._config = config
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
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

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4jWriter not connected.")
        return self._driver

    async def ingest(
        self,
        statements: list[CypherStatement],
        *,
        batch_size: int = 50,
        initialize: bool = True,
        embedding_dimensions: int = 384,
    ) -> IngestionReport:
        start = time.monotonic()
        report = IngestionReport()

        node_stmts = [s for s in statements if s.category == "node"]
        edge_stmts = [s for s in statements if s.category == "edge"]

        report.total_statements = len(statements)
        report.node_statements = len(node_stmts)
        report.edge_statements = len(edge_stmts)

        if initialize:
            try:
                await initialize_schema(
                    self.driver,
                    database=self._config.database,
                    embedding_dimensions=embedding_dimensions,
                )
            except Exception as e:
                report.errors.append(f"Schema init failed: {e}")
                logger.error("Schema init failed: %s", e)

        logger.info(
            "Ingesting %d nodes + %d edges (batch_size=%d)",
            len(node_stmts), len(edge_stmts), batch_size,
        )

        await self._execute_batched(node_stmts, batch_size, report)
        await self._execute_batched(edge_stmts, batch_size, report)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    async def _execute_batched(
        self,
        statements: list[CypherStatement],
        batch_size: int,
        report: IngestionReport,
    ) -> None:
        for i in range(0, len(statements), batch_size):
            batch = statements[i : i + batch_size]
            try:
                await self._execute_batch_tx(batch, report)
            except Exception as e:
                logger.warning(
                    "Batch %d-%d failed (%s), falling back to per-statement",
                    i, i + len(batch), e,
                )
                for stmt in batch:
                    await self._execute_single(stmt, report)

    async def _execute_batch_tx(
        self, batch: list[CypherStatement], report: IngestionReport
    ) -> None:
        async with self.driver.session(database=self._config.database) as session:
            async with session.begin_transaction() as tx:
                for stmt in batch:
                    result = await tx.run(stmt.query, stmt.params)
                    summary = await result.consume()
                    self._accumulate_counters(summary.counters, report)
                    report.statements_succeeded += 1
                await tx.commit()

    async def _execute_single(
        self, stmt: CypherStatement, report: IngestionReport
    ) -> None:
        try:
            async with self.driver.session(database=self._config.database) as session:
                result = await session.run(stmt.query, stmt.params)
                summary = await result.consume()
                self._accumulate_counters(summary.counters, report)
                report.statements_succeeded += 1
        except Exception as e:
            report.statements_failed += 1
            error_msg = f"Failed [{stmt.category}] {stmt.uid}: {e}"
            report.errors.append(error_msg)
            logger.error(error_msg)

    def _accumulate_counters(self, counters, report: IngestionReport) -> None:
        report.nodes_created += counters.nodes_created
        report.relationships_created += counters.relationships_created
        report.properties_set += counters.properties_set
