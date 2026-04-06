"""Neo4j schema initialization for the curriculum graph.

Creates constraints, indexes, and vector indexes. All queries use IF NOT EXISTS
for idempotent re-runs. Adapted from PMG's schema.py pattern.

Usage:
    from neo4j import AsyncGraphDatabase
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    await initialize_schema(driver)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Uniqueness constraints — enforce stable UIDs as primary keys
# ---------------------------------------------------------------------------

CONSTRAINT_QUERIES = [
    # Core curriculum nodes
    "CREATE CONSTRAINT subject_uid IF NOT EXISTS FOR (n:Subject) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT unit_uid IF NOT EXISTS FOR (n:Unit) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT chapter_uid IF NOT EXISTS FOR (n:Chapter) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT concept_uid IF NOT EXISTS FOR (n:Concept) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT detail_uid IF NOT EXISTS FOR (n:Detail) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT visual_uid IF NOT EXISTS FOR (n:Visual) REQUIRE n.uid IS UNIQUE",
    # Future: cross-subject shared concepts
    "CREATE CONSTRAINT ontology_uid IF NOT EXISTS FOR (n:OntologyConcept) REQUIRE n.uid IS UNIQUE",
]


# ---------------------------------------------------------------------------
# Performance indexes — common query patterns
# ---------------------------------------------------------------------------

INDEX_QUERIES = [
    # Concept lookups by type, resolution, chapter
    "CREATE INDEX concept_type IF NOT EXISTS FOR (n:Concept) ON (n.concept_type)",
    "CREATE INDEX concept_resolution IF NOT EXISTS FOR (n:Concept) ON (n.resolution_level)",
    "CREATE INDEX concept_chapter_order IF NOT EXISTS FOR (n:Concept) ON (n.chapter_order)",
    "CREATE INDEX concept_global_order IF NOT EXISTS FOR (n:Concept) ON (n.global_teaching_order)",
    "CREATE INDEX concept_section_number IF NOT EXISTS FOR (n:Concept) ON (n.section_number)",

    # Detail lookups
    "CREATE INDEX detail_type IF NOT EXISTS FOR (n:Detail) ON (n.concept_type)",
    "CREATE INDEX detail_chapter_order IF NOT EXISTS FOR (n:Detail) ON (n.chapter_order)",

    # Chapter lookups
    "CREATE INDEX chapter_order IF NOT EXISTS FOR (n:Chapter) ON (n.chapter_order)",
    "CREATE INDEX chapter_subject IF NOT EXISTS FOR (n:Chapter) ON (n.subject)",

    # Visual lookups
    "CREATE INDEX visual_spec_version IF NOT EXISTS FOR (n:Visual) ON (n.spec_version)",

    # Salience-based queries (teaching agent fetches most important concepts)
    "CREATE INDEX concept_salience IF NOT EXISTS FOR (n:Concept) ON (n.salience_total)",
]


# ---------------------------------------------------------------------------
# Full-text indexes — for searching concept summaries and names
# ---------------------------------------------------------------------------

FULLTEXT_QUERIES = [
    # Search across concept names and summaries
    """CREATE FULLTEXT INDEX concept_search IF NOT EXISTS
       FOR (n:Concept)
       ON EACH [n.topic_name, n.summary, n.source_text]""",

    # Search across detail nodes
    """CREATE FULLTEXT INDEX detail_search IF NOT EXISTS
       FOR (n:Detail)
       ON EACH [n.topic_name, n.summary, n.source_text]""",

    # Chapter search
    """CREATE FULLTEXT INDEX chapter_search IF NOT EXISTS
       FOR (n:Chapter)
       ON EACH [n.title, n.summary]""",
]


# ---------------------------------------------------------------------------
# Vector indexes — for semantic search via embeddings
# ---------------------------------------------------------------------------

def _vector_index_query(label: str, property_name: str, dimensions: int) -> str:
    """Generate a vector index creation query."""
    index_name = f"{label.lower()}_{property_name}_vector"
    return (
        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
        f"FOR (n:{label}) ON (n.{property_name}) "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dimensions}, "
        f"`vector.similarity_function`: 'cosine'}}}}"
    )


def get_vector_index_queries(embedding_dimensions: int = 1536) -> list[str]:
    """Generate vector index queries for the configured embedding dimensions."""
    return [
        _vector_index_query("Concept", "embedding", embedding_dimensions),
        _vector_index_query("Detail", "embedding", embedding_dimensions),
        _vector_index_query("Chapter", "embedding", embedding_dimensions),
        _vector_index_query("Visual", "embedding", embedding_dimensions),
    ]


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

async def initialize_schema(
    driver: AsyncDriver,
    database: str = "neo4j",
    embedding_dimensions: int = 1536,
) -> dict[str, int]:
    """Initialize the curriculum graph schema in Neo4j.

    Idempotent — safe to run multiple times. Uses IF NOT EXISTS for all
    constraints and indexes.

    Returns:
        Dict with counts of created constraints, indexes, etc.
    """
    all_queries = (
        CONSTRAINT_QUERIES
        + INDEX_QUERIES
        + FULLTEXT_QUERIES
        + get_vector_index_queries(embedding_dimensions)
    )

    results = {"success": 0, "skipped": 0, "failed": 0}

    async with driver.session(database=database) as session:
        for query in all_queries:
            try:
                await session.run(query)
                results["success"] += 1
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "equivalent" in error_msg:
                    results["skipped"] += 1
                else:
                    results["failed"] += 1
                    logger.error("Schema query failed: %s — %s", query[:80], e)

    logger.info(
        "Schema initialized: %d created, %d skipped, %d failed",
        results["success"],
        results["skipped"],
        results["failed"],
    )
    return results


async def drop_all_data(
    driver: AsyncDriver,
    database: str = "neo4j",
) -> int:
    """Delete all nodes and relationships. Use with caution.

    Returns:
        Count of deleted nodes.
    """
    logger.warning("Dropping ALL data from database '%s'", database)
    async with driver.session(database=database) as session:
        result = await session.run("MATCH (n) DETACH DELETE n RETURN count(n) as deleted")
        record = await result.single()
        count = record["deleted"] if record else 0
        logger.info("Deleted %d nodes", count)
        return count


async def get_schema_info(
    driver: AsyncDriver,
    database: str = "neo4j",
) -> dict[str, list[str]]:
    """Return current schema info (labels, relationship types, indexes, constraints)."""
    info: dict[str, list[str]] = {}
    async with driver.session(database=database) as session:
        for key, query in [
            ("labels", "CALL db.labels()"),
            ("relationship_types", "CALL db.relationshipTypes()"),
        ]:
            result = await session.run(query)
            records = [r.data() async for r in result]
            info[key] = [list(r.values())[0] for r in records]

        for key, query in [
            ("indexes", "SHOW INDEXES YIELD name RETURN name"),
            ("constraints", "SHOW CONSTRAINTS YIELD name RETURN name"),
        ]:
            result = await session.run(query)
            records = [r.data() async for r in result]
            info[key] = [r["name"] for r in records]

    return info
