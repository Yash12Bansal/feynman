"""Idempotency snapshot — one read of Neo4j, then phases skip what's done.

At pipeline start we capture which nodes are already in the graph and which
of those already have audio/embeddings. Each phase consults this snapshot
before launching its expensive work.

The user can pass --force on the CLI to ignore the snapshot and recompute
everything. Default behaviour: do the minimum work to fill what's missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


@dataclass
class IdempotencySnapshot:
    existing_chapter_ids: set[str] = field(default_factory=set)
    existing_topic_ids: set[str] = field(default_factory=set)
    existing_diagram_ids: set[str] = field(default_factory=set)
    existing_question_ids: set[str] = field(default_factory=set)
    chapter_ids_with_audio: set[str] = field(default_factory=set)
    topic_ids_with_audio: set[str] = field(default_factory=set)
    chapter_ids_with_embedding: set[str] = field(default_factory=set)
    topic_ids_with_embedding: set[str] = field(default_factory=set)
    diagram_ids_with_fallback: set[str] = field(default_factory=set)

    @classmethod
    def empty(cls) -> IdempotencySnapshot:
        return cls()

    def summary(self) -> str:
        return (
            f"Idempotency snapshot — "
            f"{len(self.existing_chapter_ids)} chapters, "
            f"{len(self.existing_topic_ids)} topics, "
            f"{len(self.existing_diagram_ids)} diagrams, "
            f"{len(self.existing_question_ids)} questions; "
            f"audio: {len(self.chapter_ids_with_audio)}+{len(self.topic_ids_with_audio)}, "
            f"embedded: {len(self.chapter_ids_with_embedding)}+{len(self.topic_ids_with_embedding)}, "
            f"diagrams w/ fallback: {len(self.diagram_ids_with_fallback)}"
        )


async def take_snapshot(driver: AsyncDriver, database: str = "neo4j") -> IdempotencySnapshot:
    snap = IdempotencySnapshot()
    async with driver.session(database=database) as session:
        result = await session.run("MATCH (c:Chapter) RETURN c.chapter_id AS id")
        async for r in result:
            if r["id"]:
                snap.existing_chapter_ids.add(r["id"])

        result = await session.run("MATCH (t:Topic) RETURN t.topic_id AS id")
        async for r in result:
            if r["id"]:
                snap.existing_topic_ids.add(r["id"])

        result = await session.run("MATCH (d:Diagram) RETURN d.diagram_id AS id, d.fallback_image_url AS f")
        async for r in result:
            if r["id"]:
                snap.existing_diagram_ids.add(r["id"])
                if r["f"]:
                    snap.diagram_ids_with_fallback.add(r["id"])

        result = await session.run("MATCH (q:Question) RETURN q.question_id AS id")
        async for r in result:
            if r["id"]:
                snap.existing_question_ids.add(r["id"])

        result = await session.run(
            "MATCH (c:Chapter) WHERE c.chapter_manifest IS NOT NULL "
            "RETURN c.chapter_id AS id"
        )
        async for r in result:
            if r["id"]:
                snap.chapter_ids_with_audio.add(r["id"])

        result = await session.run(
            "MATCH (t:Topic) WHERE t.standalone_manifest IS NOT NULL "
            "RETURN t.topic_id AS id"
        )
        async for r in result:
            if r["id"]:
                snap.topic_ids_with_audio.add(r["id"])

        result = await session.run(
            "MATCH (c:Chapter) WHERE c.embedding IS NOT NULL RETURN c.chapter_id AS id"
        )
        async for r in result:
            if r["id"]:
                snap.chapter_ids_with_embedding.add(r["id"])

        result = await session.run(
            "MATCH (t:Topic) WHERE t.embedding IS NOT NULL RETURN t.topic_id AS id"
        )
        async for r in result:
            if r["id"]:
                snap.topic_ids_with_embedding.add(r["id"])

    logger.info(snap.summary())
    return snap
