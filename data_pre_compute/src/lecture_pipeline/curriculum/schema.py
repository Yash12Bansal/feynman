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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
# Existence constraints — required properties that must never be null
# NOTE: These require Neo4j Enterprise Edition. On Community Edition they
# fail silently and the same checks run programmatically in verify_ingestion().
# ---------------------------------------------------------------------------

EXISTENCE_CONSTRAINT_QUERIES = [
    # Subject
    "CREATE CONSTRAINT subject_uid_exists IF NOT EXISTS FOR (n:Subject) REQUIRE n.uid IS NOT NULL",

    # Chapter — must have title and order
    "CREATE CONSTRAINT chapter_uid_exists IF NOT EXISTS FOR (n:Chapter) REQUIRE n.uid IS NOT NULL",
    "CREATE CONSTRAINT chapter_title_exists IF NOT EXISTS FOR (n:Chapter) REQUIRE n.topic_name IS NOT NULL",
    "CREATE CONSTRAINT chapter_order_exists IF NOT EXISTS FOR (n:Chapter) REQUIRE n.chapter_order IS NOT NULL",

    # Concept — the primary teaching node, needs all core fields
    "CREATE CONSTRAINT concept_uid_exists IF NOT EXISTS FOR (n:Concept) REQUIRE n.uid IS NOT NULL",
    "CREATE CONSTRAINT concept_name_exists IF NOT EXISTS FOR (n:Concept) REQUIRE n.topic_name IS NOT NULL",
    "CREATE CONSTRAINT concept_type_exists IF NOT EXISTS FOR (n:Concept) REQUIRE n.concept_type IS NOT NULL",
    "CREATE CONSTRAINT concept_resolution_exists IF NOT EXISTS FOR (n:Concept) REQUIRE n.resolution_level IS NOT NULL",
    "CREATE CONSTRAINT concept_chapter_exists IF NOT EXISTS FOR (n:Concept) REQUIRE n.chapter_order IS NOT NULL",
    "CREATE CONSTRAINT concept_summary_exists IF NOT EXISTS FOR (n:Concept) REQUIRE n.summary IS NOT NULL",

    # Detail
    "CREATE CONSTRAINT detail_uid_exists IF NOT EXISTS FOR (n:Detail) REQUIRE n.uid IS NOT NULL",
    "CREATE CONSTRAINT detail_name_exists IF NOT EXISTS FOR (n:Detail) REQUIRE n.topic_name IS NOT NULL",

    # Visual
    "CREATE CONSTRAINT visual_uid_exists IF NOT EXISTS FOR (n:Visual) REQUIRE n.uid IS NOT NULL",
]


# ---------------------------------------------------------------------------
# Performance indexes — common query patterns
# ---------------------------------------------------------------------------

INDEX_QUERIES = [
    # --- Single-property range indexes ---

    # Concept lookups by type, resolution, chapter
    "CREATE INDEX concept_type IF NOT EXISTS FOR (n:Concept) ON (n.concept_type)",
    "CREATE INDEX concept_resolution IF NOT EXISTS FOR (n:Concept) ON (n.resolution_level)",
    "CREATE INDEX concept_chapter_order IF NOT EXISTS FOR (n:Concept) ON (n.chapter_order)",
    "CREATE INDEX concept_global_order IF NOT EXISTS FOR (n:Concept) ON (n.global_teaching_order)",
    "CREATE INDEX concept_section_number IF NOT EXISTS FOR (n:Concept) ON (n.section_number)",
    "CREATE INDEX concept_difficulty IF NOT EXISTS FOR (n:Concept) ON (n.difficulty)",
    "CREATE INDEX concept_visual_hint IF NOT EXISTS FOR (n:Concept) ON (n.visual_hint)",

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
    "CREATE INDEX detail_salience IF NOT EXISTS FOR (n:Detail) ON (n.salience_total)",

    # --- Composite indexes — multi-property queries the teaching agent hits constantly ---

    # "All formulas in chapter 5 sorted by order" — the bread-and-butter teaching query
    "CREATE INDEX concept_type_chapter IF NOT EXISTS FOR (n:Concept) ON (n.concept_type, n.chapter_order)",

    # "Beginner concepts in chapter 3" — difficulty-based adaptive teaching
    "CREATE INDEX concept_difficulty_chapter IF NOT EXISTS FOR (n:Concept) ON (n.difficulty, n.chapter_order)",

    # "Get concepts in teaching order within a chapter" — sequential lesson flow
    "CREATE INDEX concept_chapter_within IF NOT EXISTS FOR (n:Concept) ON (n.chapter_order, n.within_chapter_order)",

    # "All chapter-level nodes for the syllabus view" — resolution zoom
    "CREATE INDEX concept_resolution_chapter IF NOT EXISTS FOR (n:Concept) ON (n.resolution_level, n.chapter_order)",

    # "High-salience concepts of a specific type" — lesson planning
    "CREATE INDEX concept_type_salience IF NOT EXISTS FOR (n:Concept) ON (n.concept_type, n.salience_total)",

    # "Concepts with visuals in a chapter" — pre-load board content
    "CREATE INDEX concept_chapter_visual IF NOT EXISTS FOR (n:Concept) ON (n.chapter_order, n.visual_hint)",

    # Chapter ordering within subject
    "CREATE INDEX chapter_subject_order IF NOT EXISTS FOR (n:Chapter) ON (n.subject, n.chapter_order)",

    # Detail ordering within chapter
    "CREATE INDEX detail_type_chapter IF NOT EXISTS FOR (n:Detail) ON (n.concept_type, n.chapter_order)",
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
        + EXISTENCE_CONSTRAINT_QUERIES
        + INDEX_QUERIES
        + FULLTEXT_QUERIES
        + get_vector_index_queries(embedding_dimensions)
    )

    results = {"success": 0, "skipped": 0, "failed": 0, "enterprise_only": 0}

    async with driver.session(database=database) as session:
        for query in all_queries:
            try:
                await session.run(query)
                results["success"] += 1
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "equivalent" in error_msg:
                    results["skipped"] += 1
                elif "enterprise edition" in error_msg:
                    # Existence constraints require Enterprise — not an error,
                    # verify_ingestion() covers this programmatically
                    results["enterprise_only"] += 1
                else:
                    results["failed"] += 1
                    logger.error("Schema query failed: %s — %s", query[:80], e)

    if results["enterprise_only"]:
        logger.info(
            "Schema initialized: %d created, %d skipped, %d enterprise-only, %d failed",
            results["success"],
            results["skipped"],
            results["enterprise_only"],
            results["failed"],
        )
    else:
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


# ---------------------------------------------------------------------------
# Post-ingestion verification — adapted from PMG's programmatic_validator
# ---------------------------------------------------------------------------


@dataclass
class VerificationIssue:
    """A single problem found during post-ingestion verification."""

    severity: str  # "error" or "warning"
    category: str  # "orphan", "missing_property", "count_mismatch", "connectivity"
    message: str


@dataclass
class VerificationReport:
    """Result of verifying the Neo4j graph against the extraction it came from."""

    # Counts from Neo4j
    nodes_by_label: dict[str, int] = field(default_factory=dict)
    relationships_by_type: dict[str, int] = field(default_factory=dict)

    # Expected counts (from extraction)
    expected_nodes: int = 0
    expected_relationships: int = 0

    # Actual counts
    actual_nodes: int = 0
    actual_relationships: int = 0

    # Issues found
    issues: list[VerificationIssue] = field(default_factory=list)

    # Detailed checks
    orphan_node_uids: list[str] = field(default_factory=list)
    missing_node_uids: list[str] = field(default_factory=list)
    null_property_violations: list[dict[str, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def summary(self) -> str:
        status = "PASSED" if self.passed else f"FAILED ({self.error_count} errors)"
        parts = [
            f"Verification {status}",
            f"  Neo4j: {self.actual_nodes} nodes, {self.actual_relationships} rels",
            f"  Expected: {self.expected_nodes} nodes, {self.expected_relationships} rels",
        ]
        if self.warning_count:
            parts.append(f"  Warnings: {self.warning_count}")
        if self.orphan_node_uids:
            parts.append(f"  Orphans (no relationships): {len(self.orphan_node_uids)}")
        if self.missing_node_uids:
            parts.append(f"  Missing from Neo4j: {len(self.missing_node_uids)}")
        if self.null_property_violations:
            parts.append(f"  Null required properties: {len(self.null_property_violations)}")
        return "\n".join(parts)


# Required properties per label that we verify post-ingestion.
# This is a defense layer ON TOP of existence constraints —
# constraints prevent bad writes, this catches silent failures.
_REQUIRED_PROPERTIES: dict[str, list[str]] = {
    "Subject": ["uid"],
    "Unit": ["uid"],
    "Chapter": ["uid", "topic_name", "chapter_order"],
    "Concept": ["uid", "topic_name", "concept_type", "resolution_level", "chapter_order", "summary"],
    "Detail": ["uid", "topic_name"],
    "Visual": ["uid"],
}


async def verify_ingestion(
    driver: AsyncDriver,
    expected_node_uids: set[str],
    expected_rel_count: int,
    database: str = "neo4j",
) -> VerificationReport:
    """Verify the Neo4j graph matches what we expected to ingest.

    Checks:
    1. Node count by label — did everything land?
    2. Missing UIDs — which specific nodes didn't make it?
    3. Orphan nodes — nodes with zero relationships (suspicious)
    4. Required property nulls — did any node get written with missing fields?
    5. Relationship count — did all edges get created?
    6. Dangling relationships — edges pointing to nonexistent nodes

    Args:
        driver: Async Neo4j driver.
        expected_node_uids: Set of UIDs we sent to Neo4j.
        expected_rel_count: How many relationships we tried to create.
        database: Neo4j database name.

    Returns:
        VerificationReport with all findings.
    """
    report = VerificationReport(
        expected_nodes=len(expected_node_uids),
        expected_relationships=expected_rel_count,
    )

    async with driver.session(database=database) as session:
        # 1. Node counts by label
        result = await session.run(
            "MATCH (n) WHERE n.uid IS NOT NULL "
            "RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY label"
        )
        async for record in result:
            report.nodes_by_label[record["label"]] = record["cnt"]
        report.actual_nodes = sum(report.nodes_by_label.values())

        # 2. Relationship counts by type
        result = await session.run(
            "MATCH ()-[r]->() RETURN type(r) AS rtype, count(r) AS cnt ORDER BY rtype"
        )
        async for record in result:
            report.relationships_by_type[record["rtype"]] = record["cnt"]
        report.actual_relationships = sum(report.relationships_by_type.values())

        # 3. Check which expected UIDs actually exist
        result = await session.run(
            "MATCH (n) WHERE n.uid IS NOT NULL RETURN n.uid AS uid"
        )
        actual_uids: set[str] = set()
        async for record in result:
            actual_uids.add(record["uid"])

        report.missing_node_uids = sorted(expected_node_uids - actual_uids)

        # 4. Orphan nodes — nodes with zero relationships (excluding Visual which
        # only has inbound HAS_VISUAL and may not be written yet)
        result = await session.run(
            "MATCH (n) WHERE n.uid IS NOT NULL "
            "AND NOT (n)--() "
            "AND NOT n:Visual AND NOT n:Subject "
            "RETURN n.uid AS uid, labels(n)[0] AS label LIMIT 50"
        )
        async for record in result:
            report.orphan_node_uids.append(record["uid"])

        # 5. Required property null checks
        for label, required_props in _REQUIRED_PROPERTIES.items():
            for prop in required_props:
                result = await session.run(
                    f"MATCH (n:{label}) WHERE n.{prop} IS NULL RETURN n.uid AS uid LIMIT 10"
                )
                async for record in result:
                    uid = record["uid"] or "(no uid)"
                    report.null_property_violations.append(
                        {"label": label, "property": prop, "uid": uid}
                    )

        # 6. Dangling relationship check — edges where one end has no uid
        result = await session.run(
            "MATCH (a)-[r]->(b) "
            "WHERE a.uid IS NULL OR b.uid IS NULL "
            "RETURN type(r) AS rtype, count(r) AS cnt"
        )
        dangling_count = 0
        async for record in result:
            dangling_count += record["cnt"]

    # --- Build issues list ---

    # Node count mismatch
    if report.missing_node_uids:
        report.issues.append(VerificationIssue(
            severity="error",
            category="count_mismatch",
            message=f"{len(report.missing_node_uids)} nodes missing from Neo4j "
                    f"(first 5: {report.missing_node_uids[:5]})",
        ))

    # Relationship count mismatch (allow some slack — MERGE may dedupe)
    if report.actual_relationships < expected_rel_count * 0.9:
        report.issues.append(VerificationIssue(
            severity="error",
            category="count_mismatch",
            message=f"Relationship count low: {report.actual_relationships} actual "
                    f"vs {expected_rel_count} expected (>10% loss)",
        ))
    elif report.actual_relationships < expected_rel_count:
        report.issues.append(VerificationIssue(
            severity="warning",
            category="count_mismatch",
            message=f"Relationship count slightly low: {report.actual_relationships} actual "
                    f"vs {expected_rel_count} expected (MERGE dedup likely)",
        ))

    # Orphans
    if report.orphan_node_uids:
        report.issues.append(VerificationIssue(
            severity="warning",
            category="orphan",
            message=f"{len(report.orphan_node_uids)} nodes have zero relationships "
                    f"(first 5: {report.orphan_node_uids[:5]})",
        ))

    # Null required properties
    if report.null_property_violations:
        report.issues.append(VerificationIssue(
            severity="error",
            category="missing_property",
            message=f"{len(report.null_property_violations)} null required properties "
                    f"(e.g. {report.null_property_violations[0]})",
        ))

    # Dangling relationships
    if dangling_count > 0:
        report.issues.append(VerificationIssue(
            severity="error",
            category="connectivity",
            message=f"{dangling_count} relationships point to nodes without UIDs",
        ))

    return report
