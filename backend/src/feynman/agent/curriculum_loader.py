"""Load curriculum data from Neo4j for the teaching agent.

Replaces the old JSON file loading (ConceptGraph from data_pre_compute/output/graphs/).
Queries Neo4j directly for chapters, concepts, relationships, and pre-generated visuals.

If no curriculum exists in Neo4j for the requested topic, raises CurriculumNotFoundError
with a clear message telling the user to run the ingestion pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase

from feynman.config import settings

logger = structlog.get_logger()


class CurriculumNotFoundError(Exception):
    """Raised when no curriculum exists in Neo4j for the requested topic.

    Fix: Run the curriculum pipeline first:
        cd data_pre_compute
        lecture-pipeline ingest-book <pdf> --subject <subject>
    """

    def __init__(self, topic: str, detail: str = "") -> None:
        msg = (
            f"No curriculum found in Neo4j for topic '{topic}'. "
            f"Run: lecture-pipeline ingest-book <pdf> --subject <subject>"
        )
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)
        self.topic = topic


# ── Data models ──────────────────────────────────────────


@dataclass
class CurriculumConcept:
    """A single concept from the Neo4j curriculum graph."""

    uid: str
    topic_name: str
    concept_type: str  # "topic", "definition", "formula", etc.
    resolution_level: str  # "concept" or "detail"
    summary: str
    source_text: str = ""
    difficulty: str = "intermediate"
    visual_hint: str | None = None
    salience_total: float = 0.0
    page_start: int = 0
    page_end: int = 0
    chapter_order: int = 0
    within_chapter_order: int = 0
    global_teaching_order: int = 0
    estimated_duration_minutes: float = 3.0

    @property
    def level(self) -> int:
        """0 for concept-level, 1 for detail-level."""
        return 0 if self.resolution_level == "concept" else 1


@dataclass
class CurriculumEdge:
    """A relationship between two concepts."""

    from_uid: str
    to_uid: str
    rel_type: str  # "PREREQUISITE", "LEADS_TO", "EXAMPLE_OF", etc.
    label: str = ""


@dataclass
class CurriculumData:
    """Complete curriculum data for a chapter, loaded from Neo4j."""

    chapter_uid: str
    chapter_title: str
    subject: str
    concepts: list[CurriculumConcept] = field(default_factory=list)
    relationships: list[CurriculumEdge] = field(default_factory=list)
    pre_generated_visuals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def concept_by_uid(self, uid: str) -> CurriculumConcept | None:
        for c in self.concepts:
            if c.uid == uid:
                return c
        return None

    def get_teaching_order(self) -> list[CurriculumConcept]:
        """Return concepts sorted by global teaching order."""
        return sorted(self.concepts, key=lambda c: c.global_teaching_order)

    def get_prerequisites(self, uid: str) -> list[CurriculumConcept]:
        """Get prerequisite concepts for a given concept UID."""
        prereq_uids = [
            e.from_uid for e in self.relationships
            if e.to_uid == uid and e.rel_type == "PREREQUISITE"
        ]
        return [c for c in self.concepts if c.uid in prereq_uids]


# ── Neo4j queries ────────────────────────────────────────


async def load_curriculum(
    topic: str,
    subject: str | None = None,
) -> CurriculumData:
    """Load curriculum from Neo4j for the given topic.

    Uses fulltext search to find the best matching chapter, then loads
    all its concepts, relationships, and pre-generated visuals.

    Raises:
        CurriculumNotFoundError: If no matching chapter exists in Neo4j.
    """
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        # 1. Find the best matching chapter via fulltext search
        chapter = await _find_chapter(driver, topic, subject)

        # 2. Load all concepts for this chapter (concepts + details)
        concepts = await _load_concepts(driver, chapter["uid"])

        if not concepts:
            raise CurriculumNotFoundError(
                topic, detail=f"Chapter '{chapter['topic_name']}' found but has no concepts"
            )

        # 3. Load relationships between these concepts
        concept_uids = [c.uid for c in concepts]
        relationships = await _load_relationships(driver, concept_uids)

        # 4. Load pre-generated visuals
        visuals = await _load_visuals(driver, concept_uids, concepts)

        curriculum = CurriculumData(
            chapter_uid=chapter["uid"],
            chapter_title=chapter["topic_name"],
            subject=chapter.get("subject", subject or ""),
            concepts=concepts,
            relationships=relationships,
            pre_generated_visuals=visuals,
        )

        logger.info(
            "curriculum.loaded_from_neo4j",
            topic=topic,
            chapter=curriculum.chapter_title,
            concepts=len(concepts),
            relationships=len(relationships),
            visuals=len(visuals),
        )

        return curriculum

    finally:
        await driver.close()


async def _find_chapter(
    driver: Any,
    topic: str,
    subject: str | None,
) -> dict[str, Any]:
    """Find the best matching chapter in Neo4j via fulltext search.

    Tries fulltext index first, falls back to CONTAINS matching on topic_name.
    """
    async with driver.session(database=settings.neo4j_database) as session:
        # Try fulltext search first (searches chapter title + summary)
        result = await session.run(
            "CALL db.index.fulltext.queryNodes('chapter_search', $topic) "
            "YIELD node, score "
            "WHERE score > 0.3 "
            "RETURN node.uid AS uid, node.topic_name AS topic_name, "
            "       node.subject AS subject, node.chapter_order AS chapter_order, "
            "       score "
            "ORDER BY score DESC LIMIT 1",
            {"topic": topic},
        )
        record = await result.single()

        if record:
            logger.info(
                "curriculum.chapter_found_fulltext",
                topic=topic,
                matched=record["topic_name"],
                score=record["score"],
            )
            return dict(record)

        # Fallback: case-insensitive CONTAINS on topic_name
        result = await session.run(
            "MATCH (c:Chapter) "
            "WHERE toLower(c.topic_name) CONTAINS toLower($topic) "
            "RETURN c.uid AS uid, c.topic_name AS topic_name, "
            "       c.subject AS subject, c.chapter_order AS chapter_order "
            "ORDER BY c.chapter_order LIMIT 1",
            {"topic": topic},
        )
        record = await result.single()

        if record:
            logger.info(
                "curriculum.chapter_found_contains",
                topic=topic,
                matched=record["topic_name"],
            )
            return dict(record)

        # Fallback: search in Concept nodes (user might say "Projectile Motion"
        # which is a concept, not a chapter title)
        result = await session.run(
            "CALL db.index.fulltext.queryNodes('concept_search', $topic) "
            "YIELD node, score "
            "WHERE score > 0.1 "
            "MATCH (ch:Chapter)-[:CONTAINS*1..3]->(node) "
            "RETURN ch.uid AS uid, ch.topic_name AS topic_name, "
            "       ch.subject AS subject, ch.chapter_order AS chapter_order, "
            "       score "
            "ORDER BY score DESC LIMIT 1",
            {"topic": topic},
        )
        record = await result.single()

        if record:
            logger.info(
                "curriculum.chapter_found_via_concept",
                topic=topic,
                matched_chapter=record["topic_name"],
            )
            return dict(record)

        # Last resort: tokenize topic, search concept topic_name/summary
        # with CONTAINS on each significant word, trace to parent chapter
        stop_words = {"and", "the", "with", "from", "that", "this", "for", "are", "was"}
        words = [
            w for w in topic.lower().split()
            if len(w) > 3 and w not in stop_words
        ]
        for word in words:
            result = await session.run(
                "MATCH (ch:Chapter)-[:CONTAINS]->(n) "
                "WHERE toLower(n.topic_name) CONTAINS $word "
                "   OR toLower(n.summary) CONTAINS $word "
                "RETURN DISTINCT ch.uid AS uid, ch.topic_name AS topic_name, "
                "       ch.subject AS subject, ch.chapter_order AS chapter_order "
                "ORDER BY ch.chapter_order LIMIT 1",
                {"word": word},
            )
            record = await result.single()
            if record:
                logger.info(
                    "curriculum.chapter_found_via_keyword",
                    topic=topic,
                    keyword=word,
                    matched_chapter=record["topic_name"],
                )
                return dict(record)

        raise CurriculumNotFoundError(topic)


async def _load_concepts(
    driver: Any,
    chapter_uid: str,
) -> list[CurriculumConcept]:
    """Load all concepts and details for a chapter, ordered by teaching sequence."""
    async with driver.session(database=settings.neo4j_database) as session:
        # Get concepts directly contained in this chapter, plus details
        # that are contained in those concepts
        result = await session.run(
            "MATCH (ch {uid: $uid})-[:CONTAINS]->(n) "
            "WHERE n:Concept OR n:Detail "
            "RETURN n "
            "ORDER BY n.global_teaching_order",
            {"uid": chapter_uid},
        )

        concepts = []
        async for record in result:
            node = record["n"]
            props = dict(node.items())

            # Convert Neo4j integer types
            for k, v in props.items():
                if hasattr(v, "to_py"):
                    props[k] = v.to_py()

            concepts.append(CurriculumConcept(
                uid=props.get("uid", ""),
                topic_name=props.get("topic_name", ""),
                concept_type=props.get("concept_type", "topic"),
                resolution_level=props.get("resolution_level", "concept"),
                summary=props.get("summary", ""),
                source_text=props.get("source_text", ""),
                difficulty=props.get("difficulty", "intermediate"),
                visual_hint=props.get("visual_hint"),
                salience_total=float(props.get("salience_total", 0) or 0),
                page_start=int(props.get("page_start", 0) or 0),
                page_end=int(props.get("page_end", 0) or 0),
                chapter_order=int(props.get("chapter_order", 0) or 0),
                within_chapter_order=int(props.get("within_chapter_order", 0) or 0),
                global_teaching_order=int(props.get("global_teaching_order", 0) or 0),
                estimated_duration_minutes=float(props.get("estimated_duration_minutes", 3) or 3),
            ))

        return concepts


async def _load_relationships(
    driver: Any,
    concept_uids: list[str],
) -> list[CurriculumEdge]:
    """Load all relationships between the given concept UIDs."""
    if not concept_uids:
        return []

    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (a)-[r]->(b) "
            "WHERE a.uid IN $uids AND b.uid IN $uids "
            "AND type(r) <> 'CONTAINS' "
            "RETURN a.uid AS from_uid, b.uid AS to_uid, "
            "       type(r) AS rel_type, r.label AS label",
            {"uids": concept_uids},
        )

        edges = []
        async for record in result:
            edges.append(CurriculumEdge(
                from_uid=record["from_uid"],
                to_uid=record["to_uid"],
                rel_type=record["rel_type"],
                label=record["label"] or "",
            ))

        return edges


async def _load_visuals(
    driver: Any,
    concept_uids: list[str],
    concepts: list[CurriculumConcept],
) -> dict[str, dict[str, Any]]:
    """Load pre-generated DiagramSpec visuals for concepts.

    The visual writer creates separate source nodes (visual:...) linked via HAS_VISUAL
    to Visual nodes. We match visuals to concepts by title similarity since the source
    nodes aren't the same as the concept nodes.

    Returns: {concept_uid: DiagramSpec dict}
    """
    if not concepts:
        return {}

    # Build topic name → concept UID lookup
    name_to_uid: dict[str, str] = {}
    for c in concepts:
        name_to_uid[c.topic_name.lower()] = c.uid

    async with driver.session(database=settings.neo4j_database) as session:
        # Get all visuals and match by title to concept topic_name
        result = await session.run(
            "MATCH ()-[:HAS_VISUAL]->(v:Visual) "
            "WHERE v.diagram_spec IS NOT NULL "
            "RETURN v.diagram_spec AS spec, v.title AS title",
        )

        visuals: dict[str, dict[str, Any]] = {}
        async for record in result:
            title = (record["title"] or "").lower()
            # Try exact match first, then containment
            matched_uid = None
            for name, uid in name_to_uid.items():
                if name in title or title in name:
                    matched_uid = uid
                    break

            if not matched_uid:
                continue

            try:
                spec = json.loads(record["spec"])
                # Only store first match per concept (avoid duplicates)
                if matched_uid not in visuals:
                    visuals[matched_uid] = spec
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "curriculum.visual_parse_failed",
                    title=record["title"],
                )

        return visuals
