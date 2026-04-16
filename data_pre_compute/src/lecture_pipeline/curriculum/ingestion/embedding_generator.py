"""Generate and store vector embeddings for curriculum graph nodes.

Uses OpenAI text-embedding-3-small (1536 dims) to embed node summaries,
then writes embeddings to Neo4j via batched UNWIND.

Supports incremental mode: only embeds nodes without existing embeddings.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lecture_pipeline.curriculum.models import (
    CurriculumExtractionResult,
    ExtractionNode,
    ResolutionLevel,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingReport:
    """Tracks embedding generation and storage results."""

    total_nodes: int = 0
    nodes_embedded: int = 0
    nodes_skipped: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0
    error_details: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "OK" if not self.error_details else f"ERRORS: {self.errors}"
        return (
            f"Embedding {status} — "
            f"{self.nodes_embedded}/{self.total_nodes} embedded, "
            f"{self.nodes_skipped} skipped, "
            f"{self.elapsed_seconds:.1f}s"
        )


class EmbeddingGenerator:
    """Generates embeddings via OpenAI and writes them to Neo4j.

    Usage:
        gen = EmbeddingGenerator(model="text-embedding-3-small")
        report = await gen.generate_and_store(driver, extraction)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 100,
    ) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY")
        )
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    @staticmethod
    def compose_embedding_text(node: ExtractionNode) -> str:
        """Compose the text to embed for a given node.

        Uses topic_name + summary (LLM-generated, teaching-focused).
        source_text is excluded — it's raw PDF and often noisy.
        """
        separator = ". " if node.resolution_level in (
            ResolutionLevel.SYLLABUS,
            ResolutionLevel.UNIT,
            ResolutionLevel.CHAPTER,
        ) else ": "
        return f"{node.topic_name}{separator}{node.summary}"

    async def generate_and_store(
        self,
        driver: AsyncDriver,
        extraction: CurriculumExtractionResult,
        *,
        database: str = "neo4j",
        force: bool = False,
    ) -> EmbeddingReport:
        """Generate embeddings for all nodes and write to Neo4j.

        Args:
            driver: Async Neo4j driver
            extraction: The unified extraction result
            database: Neo4j database name
            force: If True, re-embed nodes that already have embeddings

        Returns:
            EmbeddingReport with statistics
        """
        start = time.monotonic()
        report = EmbeddingReport(total_nodes=len(extraction.nodes))

        # Prepare texts and UIDs
        items: list[dict[str, Any]] = []
        for node in extraction.nodes:
            text = self.compose_embedding_text(node)
            items.append({"uid": node.uid, "text": text})

        if not items:
            report.elapsed_seconds = time.monotonic() - start
            return report

        # If not forcing, check which nodes already have embeddings
        if not force:
            existing_uids = await self._get_embedded_uids(driver, database)
            original_count = len(items)
            items = [item for item in items if item["uid"] not in existing_uids]
            report.nodes_skipped = original_count - len(items)

        # Process in batches
        for i in range(0, len(items), self._batch_size):
            batch = items[i : i + self._batch_size]
            try:
                texts = [item["text"] for item in batch]
                embeddings = await self._embed_batch(texts)

                # Build batch for UNWIND
                neo4j_batch = [
                    {"uid": item["uid"], "embedding": emb}
                    for item, emb in zip(batch, embeddings)
                ]

                await self._write_embeddings(driver, neo4j_batch, database)
                report.nodes_embedded += len(batch)

            except Exception as e:
                report.errors += len(batch)
                error_msg = f"Embedding batch {i}-{i + len(batch)} failed: {e}"
                report.error_details.append(error_msg)
                logger.error(error_msg)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI embeddings API for a batch of texts."""
        response = await self._client.embeddings.create(
            input=texts,
            model=self._model,
            dimensions=self._dimensions,
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    async def _write_embeddings(
        self,
        driver: AsyncDriver,
        batch: list[dict[str, Any]],
        database: str,
    ) -> None:
        """Write embeddings to Neo4j using UNWIND for batch efficiency."""
        query = (
            "UNWIND $batch AS item "
            "MATCH (n {uid: item.uid}) "
            "SET n.embedding = item.embedding"
        )
        async with driver.session(database=database) as session:
            await session.run(query, {"batch": batch})

    async def _get_embedded_uids(
        self, driver: AsyncDriver, database: str
    ) -> set[str]:
        """Query Neo4j for UIDs that already have embeddings."""
        query = "MATCH (n) WHERE n.embedding IS NOT NULL RETURN n.uid AS uid"
        async with driver.session(database=database) as session:
            result = await session.run(query)
            records = [r.data() async for r in result]
            return {r["uid"] for r in records}
