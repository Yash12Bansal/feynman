"""Load a `ChapterContext` from Neo4j given a `chapter_id`.

Schema (per `data_pre_compute_v2/.../schema.py`):
  (:Chapter {chapter_id, title, chapter_index})
       -[:CONTAINS]-> (:Topic {topic_id, topic_name, section_number, ...})
                      -[:HAS_DIAGRAM]-> (:Diagram {diagram_id, description,
                                                   dictionary (json), ...})

One round-trip with `OPTIONAL MATCH`es fetches everything we need. Diagram
nodes may store `dictionary` as a JSON-encoded string (depending on ingest
version) — we attempt `json.loads` defensively.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase

from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    DiagramData,
    TopicMeta,
)
from feynman.config import settings

logger = structlog.get_logger()


_LOAD_CHAPTER_CYPHER = """
MATCH (c:Chapter {chapter_id: $chapter_id})
OPTIONAL MATCH (c)-[:CONTAINS]->(t:Topic)
OPTIONAL MATCH (t)-[:HAS_DIAGRAM]->(d:Diagram)
RETURN
    c.chapter_id AS chapter_id,
    c.title      AS title,
    collect(DISTINCT {
        topic_id:       t.topic_id,
        topic_name:     t.topic_name,
        section_number: t.section_number,
        summary:        t.our_understanding
    }) AS topics,
    collect(DISTINCT {
        diagram_id:        d.diagram_id,
        description:       d.description,
        dictionary:        d.dictionary,
        linked_topic_ids:  d.linked_topic_ids
    }) AS diagrams
"""


def _parse_dictionary(value: Any) -> dict[str, dict[str, Any]]:
    """`dictionary` may arrive as a JSON string, a dict, or None."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def load_chapter_by_id(chapter_id: str) -> ChapterContext | None:
    """Hydrate a ChapterContext from Neo4j. Returns None when no rows match."""
    uri = settings.neo4j_uri
    auth = (settings.neo4j_user, settings.neo4j_password)
    database = settings.neo4j_database

    driver = AsyncGraphDatabase.driver(uri, auth=auth)
    try:
        async with driver.session(database=database) as session:
            result = await session.run(_LOAD_CHAPTER_CYPHER, {"chapter_id": chapter_id})
            record = await result.single()
    finally:
        await driver.close()

    if record is None or not record["chapter_id"]:
        logger.warning("chapter_loader.not_found", chapter_id=chapter_id)
        return None

    topics: dict[str, TopicMeta] = {}
    for raw in record["topics"] or []:
        tid = raw.get("topic_id") if isinstance(raw, dict) else None
        if not tid:
            continue
        topics[tid] = TopicMeta(
            topic_id=tid,
            topic_name=raw.get("topic_name") or tid,
            section_number=raw.get("section_number") or "",
            summary=raw.get("summary") or "",
        )

    diagrams: dict[str, DiagramData] = {}
    for raw in record["diagrams"] or []:
        did = raw.get("diagram_id") if isinstance(raw, dict) else None
        if not did:
            continue
        diagrams[did] = DiagramData(
            diagram_id=did,
            description=raw.get("description") or "",
            dictionary=_parse_dictionary(raw.get("dictionary")),
            linked_topic_ids=list(raw.get("linked_topic_ids") or []),
        )

    ctx = ChapterContext(
        chapter_id=record["chapter_id"],
        title=record["title"] or "",
        topics=topics,
        diagrams=diagrams,
    )
    logger.info(
        "chapter_loader.loaded",
        chapter_id=chapter_id,
        topics=len(topics),
        diagrams=len(diagrams),
    )
    return ctx


def chapter_context_from_extraction(
    extraction: dict[str, Any], chapter_id: str
) -> ChapterContext | None:
    """Build a ChapterContext directly from an extraction.json payload.

    Used by tests (hermetic, no Neo4j). The Phase H extraction shape has
    `topics: list[Topic]` and `diagrams: list[Diagram]` at the root, with
    each topic carrying chapter_id.
    """
    chapters = extraction.get("chapters") or []
    chapter = next(
        (c for c in chapters if c.get("chapter_id") == chapter_id),
        None,
    )
    if chapter is None:
        return None

    topic_ids = set(chapter.get("topic_ids") or [])
    topics: dict[str, TopicMeta] = {}
    for t in extraction.get("topics") or []:
        tid = t.get("topic_id")
        if not tid or (topic_ids and tid not in topic_ids):
            continue
        topics[tid] = TopicMeta(
            topic_id=tid,
            topic_name=t.get("topic_name") or tid,
            section_number=t.get("section_number") or "",
            summary=t.get("our_understanding") or "",
        )

    diagrams: dict[str, DiagramData] = {}
    for d in extraction.get("diagrams") or []:
        did = d.get("diagram_id")
        if not did:
            continue
        linked = d.get("linked_topic_ids") or []
        if topics and not any(tid in topics for tid in linked):
            # Diagram is for a different chapter — skip.
            continue
        diagrams[did] = DiagramData(
            diagram_id=did,
            description=d.get("description") or "",
            dictionary=_parse_dictionary(d.get("dictionary")),
            linked_topic_ids=list(linked),
        )

    return ChapterContext(
        chapter_id=chapter_id,
        title=chapter.get("title") or "",
        topics=topics,
        diagrams=diagrams,
    )
