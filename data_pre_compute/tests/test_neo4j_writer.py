"""Integration tests for Neo4jWriter — require a running Neo4j instance.

Run with: pytest tests/test_neo4j_writer.py -v -m integration
Skip if Neo4j is not available.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from lecture_pipeline.config import Neo4jConfig
from lecture_pipeline.curriculum.ingestion.cypher_generator import CypherGenerator
from lecture_pipeline.curriculum.ingestion.neo4j_writer import IngestionReport, Neo4jWriter
from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.schema import drop_all_data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="HC Verma",
        chapter_title="SHM",
        page_range="1-20",
        extractor_model="test",
    )


def _make_node(
    uid: str = "curriculum:physics:shm:test",
    topic_name: str = "Test Concept",
    concept_type: ConceptType = ConceptType.DEFINITION,
    resolution_level: ResolutionLevel = ResolutionLevel.CONCEPT,
    **kwargs,
) -> ExtractionNode:
    defaults = dict(
        uid=uid,
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=resolution_level,
        summary="A test summary for this concept.",
        source_text="Verbatim from PDF.",
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=1,
    )
    defaults.update(kwargs)
    return ExtractionNode(**defaults)


def _make_extraction(
    nodes: list[ExtractionNode] | None = None,
    relationships: list[ExtractionRelationship] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="HC Verma",
        scope="book",
        source=_make_source(),
        nodes=nodes or [],
        relationships=relationships or [],
    )


@pytest_asyncio.fixture
async def writer():
    """Create a writer connected to local Neo4j, clean up after test."""
    config = Neo4jConfig()
    try:
        w = Neo4jWriter(config)
        await w.connect()
    except Exception:
        pytest.skip("Neo4j not available at bolt://localhost:7687")
        return

    # Clean before test
    await drop_all_data(w.driver)

    yield w

    # Clean after test
    await drop_all_data(w.driver)
    await w.close()


# ---------------------------------------------------------------------------
# Mark all tests as integration
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSchemaInitialization:
    @pytest.mark.asyncio
    async def test_schema_creates_constraints_and_indexes(self, writer):
        gen = CypherGenerator()
        # Ingest nothing but with schema init
        report = await writer.ingest([], initialize=True)
        assert report.statements_succeeded == 0

        info = await writer.verify_ingestion()
        # At minimum, no errors
        assert isinstance(info, dict)


class TestSingleNodeIngestion:
    @pytest.mark.asyncio
    async def test_write_and_query_single_concept(self, writer):
        node = _make_node()
        extraction = _make_extraction(nodes=[node])

        gen = CypherGenerator()
        stmts = gen.generate(extraction)
        report = await writer.ingest(stmts)

        assert report.statements_succeeded == 1
        assert report.statements_failed == 0
        assert report.nodes_created == 1

        # Query it back
        async with writer.driver.session() as session:
            result = await session.run(
                "MATCH (n:Concept {uid: $uid}) RETURN n",
                {"uid": node.uid},
            )
            record = await result.single()
            assert record is not None
            n = record["n"]
            assert n["topic_name"] == "Test Concept"
            assert n["concept_type"] == "definition"
            assert n["summary"] == "A test summary for this concept."


class TestRelationshipIngestion:
    @pytest.mark.asyncio
    async def test_write_relationship(self, writer):
        node_a = _make_node(uid="curriculum:physics:shm:a", topic_name="Concept A")
        node_b = _make_node(uid="curriculum:physics:shm:b", topic_name="Concept B")
        rel = ExtractionRelationship(
            relationship_key="rel:prerequisite:a:b",
            type=CurriculumRelationType.PREREQUISITE,
            from_uid=node_a.uid,
            to_uid=node_b.uid,
            label="A before B",
        )
        extraction = _make_extraction(nodes=[node_a, node_b], relationships=[rel])

        gen = CypherGenerator()
        stmts = gen.generate(extraction)
        report = await writer.ingest(stmts)

        assert report.statements_succeeded == 3  # 2 nodes + 1 rel
        assert report.relationships_created == 1

        # Query relationship
        async with writer.driver.session() as session:
            result = await session.run(
                "MATCH (a:Concept)-[r:PREREQUISITE]->(b:Concept) "
                "RETURN a.uid AS from_uid, b.uid AS to_uid, r.label AS label"
            )
            record = await result.single()
            assert record is not None
            assert record["from_uid"] == node_a.uid
            assert record["to_uid"] == node_b.uid
            assert record["label"] == "A before B"


class TestBatchIngestion:
    @pytest.mark.asyncio
    async def test_100_nodes_in_batches(self, writer):
        nodes = [
            _make_node(
                uid=f"curriculum:physics:shm:concept_{i}",
                topic_name=f"Concept {i}",
                within_chapter_order=i,
            )
            for i in range(100)
        ]
        extraction = _make_extraction(nodes=nodes)

        gen = CypherGenerator()
        stmts = gen.generate(extraction)
        report = await writer.ingest(stmts, batch_size=25)

        assert report.statements_succeeded == 100
        assert report.nodes_created == 100

        # Verify count
        async with writer.driver.session() as session:
            result = await session.run("MATCH (n:Concept) RETURN count(n) AS cnt")
            record = await result.single()
            assert record["cnt"] == 100


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_re_ingestion_no_duplicates(self, writer):
        """MERGE ensures re-ingesting same data creates no duplicates."""
        nodes = [
            _make_node(uid="curriculum:physics:shm:a", topic_name="A"),
            _make_node(uid="curriculum:physics:shm:b", topic_name="B"),
        ]
        rel = ExtractionRelationship(
            relationship_key="rel:leads_to:a:b",
            type=CurriculumRelationType.LEADS_TO,
            from_uid=nodes[0].uid,
            to_uid=nodes[1].uid,
        )
        extraction = _make_extraction(nodes=nodes, relationships=[rel])

        gen = CypherGenerator()
        stmts = gen.generate(extraction)

        # First ingestion
        report1 = await writer.ingest(stmts)
        info1 = await writer.verify_ingestion()

        # Second ingestion (same data)
        report2 = await writer.ingest(stmts, initialize=False)
        info2 = await writer.verify_ingestion()

        # Counts must be identical
        assert info1["nodes_by_label"] == info2["nodes_by_label"]
        assert info1["relationships_by_type"] == info2["relationships_by_type"]

        # Second run should create 0 new nodes (MERGE finds existing)
        assert report2.nodes_created == 0
        assert report2.relationships_created == 0

    @pytest.mark.asyncio
    async def test_property_update_on_re_ingestion(self, writer):
        """MERGE + SET updates properties on existing nodes."""
        node_v1 = _make_node(uid="curriculum:physics:shm:x", summary="Version 1")
        extraction_v1 = _make_extraction(nodes=[node_v1])

        gen = CypherGenerator()
        stmts_v1 = gen.generate(extraction_v1)
        await writer.ingest(stmts_v1)

        # Re-ingest with updated summary
        node_v2 = _make_node(uid="curriculum:physics:shm:x", summary="Version 2")
        extraction_v2 = _make_extraction(nodes=[node_v2])
        stmts_v2 = gen.generate(extraction_v2)
        await writer.ingest(stmts_v2, initialize=False)

        # Query — should have updated summary
        async with writer.driver.session() as session:
            result = await session.run(
                "MATCH (n:Concept {uid: $uid}) RETURN n.summary AS summary",
                {"uid": "curriculum:physics:shm:x"},
            )
            record = await result.single()
            assert record["summary"] == "Version 2"


class TestCrossChapterTraversal:
    @pytest.mark.asyncio
    async def test_cross_chapter_prerequisite_traversal(self, writer):
        ch1_concept = _make_node(
            uid="curriculum:physics:ch1:force",
            topic_name="Force",
            chapter_order=1,
        )
        ch2_concept = _make_node(
            uid="curriculum:physics:ch2:friction",
            topic_name="Friction",
            chapter_order=2,
        )
        rel = ExtractionRelationship(
            relationship_key="rel:prerequisite:force:friction",
            type=CurriculumRelationType.PREREQUISITE,
            from_uid=ch1_concept.uid,
            to_uid=ch2_concept.uid,
            label="Force needed before friction",
        )
        extraction = _make_extraction(
            nodes=[ch1_concept, ch2_concept],
            relationships=[rel],
        )

        gen = CypherGenerator()
        stmts = gen.generate(extraction)
        await writer.ingest(stmts)

        # Traverse cross-chapter prereqs
        async with writer.driver.session() as session:
            result = await session.run(
                "MATCH (a:Concept)-[:PREREQUISITE]->(b:Concept) "
                "WHERE a.chapter_order <> b.chapter_order "
                "RETURN a.topic_name AS from_name, b.topic_name AS to_name"
            )
            record = await result.single()
            assert record is not None
            assert record["from_name"] == "Force"
            assert record["to_name"] == "Friction"


class TestVerifyIngestion:
    @pytest.mark.asyncio
    async def test_verify_returns_correct_counts(self, writer):
        chapter = _make_node(
            uid="curriculum:physics:shm",
            resolution_level=ResolutionLevel.CHAPTER,
        )
        concept = _make_node(
            uid="curriculum:physics:shm:energy",
            resolution_level=ResolutionLevel.CONCEPT,
        )
        rel = ExtractionRelationship(
            relationship_key="rel:contains:shm:energy",
            type=CurriculumRelationType.CONTAINS,
            from_uid=chapter.uid,
            to_uid=concept.uid,
        )
        extraction = _make_extraction(
            nodes=[chapter, concept],
            relationships=[rel],
        )

        gen = CypherGenerator()
        stmts = gen.generate(extraction)
        await writer.ingest(stmts)

        info = await writer.verify_ingestion()
        assert info["nodes_by_label"]["Chapter"] == 1
        assert info["nodes_by_label"]["Concept"] == 1
        assert info["relationships_by_type"]["CONTAINS"] == 1


class TestIngestionReport:
    @pytest.mark.asyncio
    async def test_report_accuracy(self, writer):
        nodes = [
            _make_node(uid="curriculum:physics:shm:a"),
            _make_node(uid="curriculum:physics:shm:b"),
        ]
        rel = ExtractionRelationship(
            relationship_key="rel:leads_to:a:b",
            type=CurriculumRelationType.LEADS_TO,
            from_uid=nodes[0].uid,
            to_uid=nodes[1].uid,
        )
        extraction = _make_extraction(nodes=nodes, relationships=[rel])

        gen = CypherGenerator()
        stmts = gen.generate(extraction)
        report = await writer.ingest(stmts)

        assert report.total_statements == 3
        assert report.node_statements == 2
        assert report.relationship_statements == 1
        assert report.statements_succeeded == 3
        assert report.statements_failed == 0
        assert report.nodes_created == 2
        assert report.relationships_created == 1
        assert report.elapsed_seconds > 0
        assert not report.errors

    def test_report_summary_string(self):
        report = IngestionReport(
            total_statements=10,
            statements_succeeded=9,
            statements_failed=1,
            nodes_created=5,
            relationships_created=3,
            properties_set=50,
            elapsed_seconds=1.5,
            errors=["one error"],
        )
        summary = report.summary()
        assert "ERRORS: 1" in summary
        assert "9/10" in summary
