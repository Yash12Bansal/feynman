"""Neo4j schema initialization for the v2 curriculum graph.

Labels: Chapter, Topic, Diagram, Question, LectureVariant.
Edges:  CONTAINS, NEXT, PREREQ, HAS_DIAGRAM, HAS_QUESTION, HAS_VARIANT.

All DDL is idempotent (IF NOT EXISTS). Existence constraints require
Neo4j Enterprise — they fail silently on Community and verify_ingestion()
catches the same issues programmatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Uniqueness constraints
# ---------------------------------------------------------------------------

CONSTRAINT_QUERIES = [
    "CREATE CONSTRAINT chapter_uid IF NOT EXISTS FOR (n:Chapter) REQUIRE n.chapter_id IS UNIQUE",
    "CREATE CONSTRAINT topic_uid IF NOT EXISTS FOR (n:Topic) REQUIRE n.topic_id IS UNIQUE",
    "CREATE CONSTRAINT diagram_uid IF NOT EXISTS FOR (n:Diagram) REQUIRE n.diagram_id IS UNIQUE",
    "CREATE CONSTRAINT question_uid IF NOT EXISTS FOR (n:Question) REQUIRE n.question_id IS UNIQUE",
    "CREATE CONSTRAINT lecture_variant_uid IF NOT EXISTS FOR (n:LectureVariant) REQUIRE n.variant_id IS UNIQUE",
]


# Existence constraints — Enterprise only
EXISTENCE_CONSTRAINT_QUERIES = [
    "CREATE CONSTRAINT chapter_title_exists IF NOT EXISTS FOR (n:Chapter) REQUIRE n.title IS NOT NULL",
    "CREATE CONSTRAINT chapter_order_exists IF NOT EXISTS FOR (n:Chapter) REQUIRE n.chapter_index IS NOT NULL",

    "CREATE CONSTRAINT topic_name_exists IF NOT EXISTS FOR (n:Topic) REQUIRE n.topic_name IS NOT NULL",
    "CREATE CONSTRAINT topic_chapter_exists IF NOT EXISTS FOR (n:Topic) REQUIRE n.chapter_id IS NOT NULL",
    "CREATE CONSTRAINT topic_section_exists IF NOT EXISTS FOR (n:Topic) REQUIRE n.section_number IS NOT NULL",

    "CREATE CONSTRAINT diagram_renderer_exists IF NOT EXISTS FOR (n:Diagram) REQUIRE n.renderer IS NOT NULL",

    "CREATE CONSTRAINT question_text_exists IF NOT EXISTS FOR (n:Question) REQUIRE n.q_text IS NOT NULL",
    "CREATE CONSTRAINT question_type_exists IF NOT EXISTS FOR (n:Question) REQUIRE n.type IS NOT NULL",
]


# ---------------------------------------------------------------------------
# Range / composite indexes — driven by runtime query patterns
# ---------------------------------------------------------------------------

INDEX_QUERIES = [
    # Chapter lookups
    "CREATE INDEX chapter_index_idx IF NOT EXISTS FOR (n:Chapter) ON (n.chapter_index)",
    "CREATE INDEX chapter_language IF NOT EXISTS FOR (n:Chapter) ON (n.language)",

    # LectureVariant — persona-specific playback manifests
    "CREATE INDEX lecture_variant_chapter IF NOT EXISTS FOR (n:LectureVariant) ON (n.chapter_id)",
    "CREATE INDEX lecture_variant_persona IF NOT EXISTS FOR (n:LectureVariant) ON (n.persona_id)",
    "CREATE INDEX lecture_variant_chapter_persona IF NOT EXISTS FOR (n:LectureVariant) ON (n.chapter_id, n.persona_id)",

    # Topic — the bread-and-butter teaching queries
    "CREATE INDEX topic_section IF NOT EXISTS FOR (n:Topic) ON (n.section_number)",
    "CREATE INDEX topic_chapter IF NOT EXISTS FOR (n:Topic) ON (n.chapter_id)",
    "CREATE INDEX topic_order IF NOT EXISTS FOR (n:Topic) ON (n.within_chapter_order)",
    "CREATE INDEX topic_needs_review IF NOT EXISTS FOR (n:Topic) ON (n.needs_review)",
    "CREATE INDEX topic_language IF NOT EXISTS FOR (n:Topic) ON (n.language)",

    # Topic composite — "all topics in chapter, ordered" runs constantly at runtime
    "CREATE INDEX topic_chapter_order IF NOT EXISTS FOR (n:Topic) ON (n.chapter_id, n.within_chapter_order)",

    # Diagram lookups
    "CREATE INDEX diagram_renderer IF NOT EXISTS FOR (n:Diagram) ON (n.renderer)",

    # Question lookups
    "CREATE INDEX question_type IF NOT EXISTS FOR (n:Question) ON (n.type)",
    "CREATE INDEX question_source IF NOT EXISTS FOR (n:Question) ON (n.source)",
    "CREATE INDEX question_confidence IF NOT EXISTS FOR (n:Question) ON (n.solution_confidence)",
    "CREATE INDEX question_needs_review IF NOT EXISTS FOR (n:Question) ON (n.needs_review)",
]


# ---------------------------------------------------------------------------
# Full-text indexes — for searching topic content and questions
# ---------------------------------------------------------------------------

FULLTEXT_QUERIES = [
    """CREATE FULLTEXT INDEX topic_search IF NOT EXISTS
       FOR (n:Topic)
       ON EACH [n.topic_name, n.our_understanding, n.orig_book_content]""",

    """CREATE FULLTEXT INDEX chapter_search IF NOT EXISTS
       FOR (n:Chapter)
       ON EACH [n.title, n.summary]""",

    """CREATE FULLTEXT INDEX question_search IF NOT EXISTS
       FOR (n:Question)
       ON EACH [n.q_text, n.answer]""",
]


# ---------------------------------------------------------------------------
# Vector indexes — for semantic search
# ---------------------------------------------------------------------------

def _vector_index_query(label: str, property_name: str, dimensions: int) -> str:
    index_name = f"{label.lower()}_{property_name}_vector"
    return (
        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
        f"FOR (n:{label}) ON (n.{property_name}) "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dimensions}, "
        f"`vector.similarity_function`: 'cosine'}}}}"
    )


def get_vector_index_queries(embedding_dimensions: int = 1536) -> list[str]:
    return [
        _vector_index_query("Topic", "embedding", embedding_dimensions),
        _vector_index_query("Chapter", "embedding", embedding_dimensions),
    ]


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------


async def initialize_schema(
    driver: AsyncDriver,
    database: str = "neo4j",
    embedding_dimensions: int = 1536,
) -> dict[str, int]:
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
                msg = str(e).lower()
                if "already exists" in msg or "equivalent" in msg:
                    results["skipped"] += 1
                elif "enterprise edition" in msg:
                    results["enterprise_only"] += 1
                else:
                    results["failed"] += 1
                    logger.error("Schema query failed: %s — %s", query[:80], e)

    logger.info(
        "Schema initialized: %d created, %d skipped, %d enterprise-only, %d failed",
        results["success"], results["skipped"], results["enterprise_only"], results["failed"],
    )
    return results


async def drop_all_data(driver: AsyncDriver, database: str = "neo4j") -> int:
    logger.warning("Dropping ALL data from database '%s'", database)
    async with driver.session(database=database) as session:
        result = await session.run("MATCH (n) DETACH DELETE n RETURN count(n) as deleted")
        record = await result.single()
        count = record["deleted"] if record else 0
        logger.info("Deleted %d nodes", count)
        return count


# ---------------------------------------------------------------------------
# Post-ingestion verification
# ---------------------------------------------------------------------------


@dataclass
class VerificationIssue:
    severity: str
    category: str
    message: str


@dataclass
class VerificationReport:
    nodes_by_label: dict[str, int] = field(default_factory=dict)
    relationships_by_type: dict[str, int] = field(default_factory=dict)
    expected_nodes: int = 0
    expected_relationships: int = 0
    actual_nodes: int = 0
    actual_relationships: int = 0
    issues: list[VerificationIssue] = field(default_factory=list)
    missing_node_ids: list[str] = field(default_factory=list)
    orphan_node_ids: list[str] = field(default_factory=list)
    null_property_violations: list[dict[str, str]] = field(default_factory=list)
    needs_review_counts: dict[str, int] = field(default_factory=dict)

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
        if self.orphan_node_ids:
            parts.append(f"  Orphans (no relationships): {len(self.orphan_node_ids)}")
        if self.missing_node_ids:
            parts.append(f"  Missing from Neo4j: {len(self.missing_node_ids)}")
        if self.null_property_violations:
            parts.append(f"  Null required properties: {len(self.null_property_violations)}")
        if self.needs_review_counts:
            review_str = ", ".join(f"{k}={v}" for k, v in self.needs_review_counts.items())
            parts.append(f"  needs_review: {review_str}")
        return "\n".join(parts)


_REQUIRED_PROPERTIES: dict[str, list[str]] = {
    "Chapter":  ["chapter_id", "title", "chapter_index"],
    "Topic":    ["topic_id", "topic_name", "section_number", "chapter_id"],
    "Diagram":  ["diagram_id", "renderer"],
    "Question": ["question_id", "q_text", "type"],
    "LectureVariant": ["variant_id", "chapter_id", "persona_id"],
}

_UID_KEY: dict[str, str] = {
    "Chapter":  "chapter_id",
    "Topic":    "topic_id",
    "Diagram":  "diagram_id",
    "Question": "question_id",
    "LectureVariant": "variant_id",
}


async def verify_ingestion(
    driver: AsyncDriver,
    expected_node_ids: set[str],
    expected_rel_count: int,
    database: str = "neo4j",
) -> VerificationReport:
    """Verify the Neo4j graph matches what we expected to ingest."""
    report = VerificationReport(
        expected_nodes=len(expected_node_ids),
        expected_relationships=expected_rel_count,
    )

    async with driver.session(database=database) as session:
        # Node counts by label
        result = await session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY label"
        )
        async for record in result:
            report.nodes_by_label[record["label"]] = record["cnt"]
        report.actual_nodes = sum(report.nodes_by_label.values())

        # Relationship counts by type
        result = await session.run(
            "MATCH ()-[r]->() RETURN type(r) AS rtype, count(r) AS cnt ORDER BY rtype"
        )
        async for record in result:
            report.relationships_by_type[record["rtype"]] = record["cnt"]
        report.actual_relationships = sum(report.relationships_by_type.values())

        # Missing UIDs
        actual_ids: set[str] = set()
        for label, key in _UID_KEY.items():
            result = await session.run(
                f"MATCH (n:{label}) RETURN n.{key} AS id"
            )
            async for record in result:
                if record["id"]:
                    actual_ids.add(record["id"])
        report.missing_node_ids = sorted(expected_node_ids - actual_ids)

        # Orphan Topic nodes (no relationships at all)
        result = await session.run(
            "MATCH (n:Topic) WHERE NOT (n)--() RETURN n.topic_id AS id LIMIT 50"
        )
        async for record in result:
            report.orphan_node_ids.append(record["id"])

        # Required property null checks
        for label, required_props in _REQUIRED_PROPERTIES.items():
            uid_key = _UID_KEY[label]
            for prop in required_props:
                result = await session.run(
                    f"MATCH (n:{label}) WHERE n.{prop} IS NULL "
                    f"RETURN n.{uid_key} AS id LIMIT 10"
                )
                async for record in result:
                    report.null_property_violations.append({
                        "label": label, "property": prop, "id": record["id"] or "(no id)"
                    })

        # needs_review counts per label
        for label in ("Topic", "Question"):
            result = await session.run(
                f"MATCH (n:{label}) WHERE n.needs_review = true RETURN count(n) AS cnt"
            )
            record = await result.single()
            report.needs_review_counts[label] = record["cnt"] if record else 0

    # Build issues
    if report.missing_node_ids:
        report.issues.append(VerificationIssue(
            severity="error", category="count_mismatch",
            message=f"{len(report.missing_node_ids)} nodes missing "
                    f"(first 5: {report.missing_node_ids[:5]})",
        ))

    if report.actual_relationships < expected_rel_count * 0.9:
        report.issues.append(VerificationIssue(
            severity="error", category="count_mismatch",
            message=f"Relationship count low: {report.actual_relationships} actual "
                    f"vs {expected_rel_count} expected (>10% loss)",
        ))
    elif report.actual_relationships < expected_rel_count:
        report.issues.append(VerificationIssue(
            severity="warning", category="count_mismatch",
            message=f"Relationship count slightly low: {report.actual_relationships} "
                    f"vs {expected_rel_count} (MERGE dedup likely)",
        ))

    if report.orphan_node_ids:
        report.issues.append(VerificationIssue(
            severity="warning", category="orphan",
            message=f"{len(report.orphan_node_ids)} Topic nodes have zero relationships "
                    f"(first 5: {report.orphan_node_ids[:5]})",
        ))

    if report.null_property_violations:
        report.issues.append(VerificationIssue(
            severity="error", category="missing_property",
            message=f"{len(report.null_property_violations)} null required properties "
                    f"(e.g. {report.null_property_violations[0]})",
        ))

    return report
