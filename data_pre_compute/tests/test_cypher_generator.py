"""Tests for deterministic Cypher generation from CurriculumExtractionResult."""

from __future__ import annotations

import json

import pytest

from lecture_pipeline.curriculum.ingestion.cypher_generator import (
    RESOLUTION_TO_LABEL,
    CypherGenerator,
    CypherStatement,
)
from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="HC Verma",
        chapter_title="SHM",
        page_range="1-20",
        extractor_model="test",
    )


def _make_node(
    uid: str = "curriculum:physics:shm:test_concept",
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
        summary="A test summary.",
        source_text="Raw text here.",
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=1,
    )
    defaults.update(kwargs)
    return ExtractionNode(**defaults)


def _make_rel(
    from_uid: str = "curriculum:physics:shm:a",
    to_uid: str = "curriculum:physics:shm:b",
    rel_type: CurriculumRelationType = CurriculumRelationType.PREREQUISITE,
) -> ExtractionRelationship:
    return ExtractionRelationship(
        relationship_key=f"rel:{rel_type.value}:{from_uid}:{to_uid}",
        type=rel_type,
        from_uid=from_uid,
        to_uid=to_uid,
        label="test relationship",
    )


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNodeToCypher:
    """Test node → Cypher generation."""

    def test_concept_node_produces_merge(self):
        node = _make_node()
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))

        assert len(stmts) == 1
        stmt = stmts[0]
        assert stmt.category == "node"
        assert stmt.label_or_type == "Concept"
        assert "MERGE (n:Concept {uid: $uid})" in stmt.query
        assert "SET" in stmt.query
        assert stmt.params["uid"] == node.uid
        assert stmt.params["topic_name"] == "Test Concept"
        assert stmt.params["concept_type"] == "definition"
        assert stmt.params["resolution_level"] == "concept"

    @pytest.mark.parametrize(
        "resolution,expected_label",
        [
            (ResolutionLevel.SYLLABUS, "Subject"),
            (ResolutionLevel.UNIT, "Unit"),
            (ResolutionLevel.CHAPTER, "Chapter"),
            (ResolutionLevel.CONCEPT, "Concept"),
            (ResolutionLevel.DETAIL, "Detail"),
        ],
    )
    def test_resolution_level_to_label_mapping(self, resolution, expected_label):
        node = _make_node(
            uid=f"test:{resolution.value}",
            resolution_level=resolution,
        )
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))

        assert len(stmts) == 1
        assert stmts[0].label_or_type == expected_label
        assert f"MERGE (n:{expected_label}" in stmts[0].query

    def test_optional_fields_excluded_when_none(self):
        node = _make_node(
            section_number=None,
            visual_hint=None,
            parent_uid=None,
        )
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))
        stmt = stmts[0]

        assert "section_number" not in stmt.params
        assert "visual_hint" not in stmt.params
        assert "parent_uid" not in stmt.params

    def test_optional_fields_included_when_present(self):
        node = _make_node(
            section_number="12.1.3",
            visual_hint="Draw a spring-mass system",
            parent_uid="curriculum:physics:shm",
        )
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))
        stmt = stmts[0]

        assert stmt.params["section_number"] == "12.1.3"
        assert stmt.params["visual_hint"] == "Draw a spring-mass system"
        assert stmt.params["parent_uid"] == "curriculum:physics:shm"

    def test_children_uids_as_list(self):
        node = _make_node(children_uids=["child:a", "child:b"])
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))

        assert stmts[0].params["children_uids"] == ["child:a", "child:b"]

    def test_metadata_serialized_as_json(self):
        node = _make_node(metadata={"hierarchy_node": True, "extra": "data"})
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))
        stmt = stmts[0]

        assert "metadata_json" in stmt.params
        parsed = json.loads(stmt.params["metadata_json"])
        assert parsed["hierarchy_node"] is True
        assert parsed["extra"] == "data"

    def test_empty_metadata_excluded(self):
        node = _make_node(metadata={})
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))

        assert "metadata_json" not in stmts[0].params

    def test_updated_at_in_set_clause(self):
        node = _make_node()
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))

        assert "n.updated_at = datetime()" in stmts[0].query

    def test_special_characters_in_properties(self):
        """Parameterized queries handle special characters safely."""
        node = _make_node(
            summary="Einstein's formula: E=mc² includes 'quotes' and \\backslashes",
            source_text='Line1\nLine2\t"Tab"',
        )
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=[node]))
        stmt = stmts[0]

        # Values pass through as-is in params (Neo4j driver handles escaping)
        assert "Einstein's" in stmt.params["summary"]
        assert "\\backslashes" in stmt.params["summary"]
        assert "\n" in stmt.params["source_text"]

    def test_difficulty_enum_serialized(self):
        for diff in Difficulty:
            node = _make_node(difficulty=diff)
            gen = CypherGenerator()
            stmts = gen.generate(_make_extraction(nodes=[node]))
            assert stmts[0].params["difficulty"] == diff.value


class TestRelationshipToCypher:
    """Test relationship → Cypher generation."""

    def test_basic_relationship(self):
        node_a = _make_node(uid="curriculum:physics:shm:a")
        node_b = _make_node(uid="curriculum:physics:shm:b")
        rel = _make_rel(from_uid=node_a.uid, to_uid=node_b.uid)

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(
            nodes=[node_a, node_b],
            relationships=[rel],
        ))

        rel_stmts = [s for s in stmts if s.category == "relationship"]
        assert len(rel_stmts) == 1

        stmt = rel_stmts[0]
        assert "MATCH (a:Concept {uid: $from_uid})" in stmt.query
        assert "MATCH (b:Concept {uid: $to_uid})" in stmt.query
        assert "MERGE (a)-[r:PREREQUISITE]->(b)" in stmt.query
        assert stmt.params["from_uid"] == node_a.uid
        assert stmt.params["to_uid"] == node_b.uid

    def test_cross_label_relationship(self):
        """Relationship between nodes of different labels."""
        chapter = _make_node(
            uid="curriculum:physics:shm",
            resolution_level=ResolutionLevel.CHAPTER,
        )
        concept = _make_node(
            uid="curriculum:physics:shm:energy",
            resolution_level=ResolutionLevel.CONCEPT,
        )
        rel = _make_rel(
            from_uid=chapter.uid,
            to_uid=concept.uid,
            rel_type=CurriculumRelationType.CONTAINS,
        )

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(
            nodes=[chapter, concept],
            relationships=[rel],
        ))

        rel_stmts = [s for s in stmts if s.category == "relationship"]
        assert len(rel_stmts) == 1
        assert "MATCH (a:Chapter {uid: $from_uid})" in rel_stmts[0].query
        assert "MATCH (b:Concept {uid: $to_uid})" in rel_stmts[0].query
        assert "MERGE (a)-[r:CONTAINS]->(b)" in rel_stmts[0].query

    def test_dangling_from_uid_skipped(self):
        node_b = _make_node(uid="curriculum:physics:shm:b")
        rel = _make_rel(
            from_uid="curriculum:physics:shm:nonexistent",
            to_uid=node_b.uid,
        )

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(
            nodes=[node_b],
            relationships=[rel],
        ))

        rel_stmts = [s for s in stmts if s.category == "relationship"]
        assert len(rel_stmts) == 0

    def test_dangling_to_uid_skipped(self):
        node_a = _make_node(uid="curriculum:physics:shm:a")
        rel = _make_rel(
            from_uid=node_a.uid,
            to_uid="curriculum:physics:shm:nonexistent",
        )

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(
            nodes=[node_a],
            relationships=[rel],
        ))

        rel_stmts = [s for s in stmts if s.category == "relationship"]
        assert len(rel_stmts) == 0

    def test_relationship_label_and_properties(self):
        node_a = _make_node(uid="curriculum:physics:shm:a")
        node_b = _make_node(uid="curriculum:physics:shm:b")
        rel = ExtractionRelationship(
            relationship_key="rel:prerequisite:a:b",
            type=CurriculumRelationType.PREREQUISITE,
            from_uid=node_a.uid,
            to_uid=node_b.uid,
            label="Needs understanding of oscillations first",
            properties={"strength": 0.9, "source": "skeleton"},
        )

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(
            nodes=[node_a, node_b],
            relationships=[rel],
        ))

        rel_stmts = [s for s in stmts if s.category == "relationship"]
        stmt = rel_stmts[0]
        assert stmt.params["label"] == "Needs understanding of oscillations first"
        assert "properties_json" in stmt.params
        parsed = json.loads(stmt.params["properties_json"])
        assert parsed["strength"] == 0.9

    def test_all_relationship_types_produce_valid_cypher(self):
        """Every CurriculumRelationType generates a valid MERGE statement."""
        node_a = _make_node(uid="curriculum:physics:shm:a")
        node_b = _make_node(uid="curriculum:physics:shm:b")

        for rel_type in CurriculumRelationType:
            rel = _make_rel(
                from_uid=node_a.uid,
                to_uid=node_b.uid,
                rel_type=rel_type,
            )
            gen = CypherGenerator()
            stmts = gen.generate(_make_extraction(
                nodes=[node_a, node_b],
                relationships=[rel],
            ))

            rel_stmts = [s for s in stmts if s.category == "relationship"]
            assert len(rel_stmts) == 1
            assert f"MERGE (a)-[r:{rel_type.value.upper()}]->(b)" in rel_stmts[0].query


class TestOrdering:
    """Test deterministic ordering of generated statements."""

    def test_hierarchy_first_ordering(self):
        """Subject → Unit → Chapter → Concept → Detail."""
        nodes = [
            _make_node(uid="d", resolution_level=ResolutionLevel.DETAIL),
            _make_node(uid="s", resolution_level=ResolutionLevel.SYLLABUS),
            _make_node(uid="ch", resolution_level=ResolutionLevel.CHAPTER),
            _make_node(uid="u", resolution_level=ResolutionLevel.UNIT),
            _make_node(uid="c", resolution_level=ResolutionLevel.CONCEPT),
        ]

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=nodes))

        labels = [s.label_or_type for s in stmts]
        assert labels == ["Subject", "Unit", "Chapter", "Concept", "Detail"]

    def test_nodes_before_relationships(self):
        node_a = _make_node(uid="curriculum:physics:shm:a")
        node_b = _make_node(uid="curriculum:physics:shm:b")
        rel = _make_rel(from_uid=node_a.uid, to_uid=node_b.uid)

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(
            nodes=[node_a, node_b],
            relationships=[rel],
        ))

        categories = [s.category for s in stmts]
        # All nodes must come before any relationship
        node_indices = [i for i, c in enumerate(categories) if c == "node"]
        rel_indices = [i for i, c in enumerate(categories) if c == "relationship"]
        if node_indices and rel_indices:
            assert max(node_indices) < min(rel_indices)

    def test_deterministic_output(self):
        """Same input always produces identical output."""
        nodes = [
            _make_node(uid="curriculum:physics:shm:b", within_chapter_order=2),
            _make_node(uid="curriculum:physics:shm:a", within_chapter_order=1),
        ]
        rel = _make_rel(from_uid=nodes[0].uid, to_uid=nodes[1].uid)
        extraction = _make_extraction(nodes=nodes, relationships=[rel])

        gen = CypherGenerator()
        run1 = gen.generate(extraction)
        run2 = gen.generate(extraction)

        assert len(run1) == len(run2)
        for s1, s2 in zip(run1, run2):
            assert s1.query == s2.query
            assert s1.params == s2.params
            assert s1.category == s2.category
            assert s1.uid_hint == s2.uid_hint

    def test_same_label_sorted_by_uid(self):
        nodes = [
            _make_node(uid="curriculum:physics:z_concept"),
            _make_node(uid="curriculum:physics:a_concept"),
            _make_node(uid="curriculum:physics:m_concept"),
        ]

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=nodes))

        uids = [s.uid_hint for s in stmts]
        assert uids == sorted(uids)

    def test_relationships_sorted_structural_first(self):
        node_a = _make_node(uid="curriculum:physics:shm:a")
        node_b = _make_node(uid="curriculum:physics:shm:b")
        rels = [
            _make_rel(from_uid=node_a.uid, to_uid=node_b.uid,
                      rel_type=CurriculumRelationType.PREREQUISITE),
            _make_rel(from_uid=node_a.uid, to_uid=node_b.uid,
                      rel_type=CurriculumRelationType.CONTAINS),
            _make_rel(from_uid=node_a.uid, to_uid=node_b.uid,
                      rel_type=CurriculumRelationType.SHARED_FOUNDATION),
        ]

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(
            nodes=[node_a, node_b],
            relationships=rels,
        ))

        rel_stmts = [s for s in stmts if s.category == "relationship"]
        types = [s.label_or_type for s in rel_stmts]
        assert types == ["CONTAINS", "PREREQUISITE", "SHARED_FOUNDATION"]


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_extraction(self):
        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction())
        assert stmts == []

    def test_full_scale_generation(self):
        """Realistic book-scale extraction generates valid statements."""
        nodes = []
        rels = []

        # 1 subject + 2 units + 5 chapters + 40 concepts + 20 details = 68 nodes
        nodes.append(_make_node(
            uid="subject:physics",
            resolution_level=ResolutionLevel.SYLLABUS,
        ))

        for u in range(2):
            nodes.append(_make_node(
                uid=f"unit:physics:unit_{u}",
                resolution_level=ResolutionLevel.UNIT,
            ))

        for ch in range(5):
            ch_uid = f"curriculum:physics:ch{ch}"
            nodes.append(_make_node(
                uid=ch_uid,
                resolution_level=ResolutionLevel.CHAPTER,
                chapter_order=ch + 1,
            ))

            for c in range(8):
                c_uid = f"curriculum:physics:ch{ch}:concept_{c}"
                nodes.append(_make_node(
                    uid=c_uid,
                    resolution_level=ResolutionLevel.CONCEPT,
                    chapter_order=ch + 1,
                    within_chapter_order=c + 1,
                ))
                rels.append(_make_rel(
                    from_uid=ch_uid,
                    to_uid=c_uid,
                    rel_type=CurriculumRelationType.CONTAINS,
                ))

                if c > 0:
                    prev_uid = f"curriculum:physics:ch{ch}:concept_{c - 1}"
                    rels.append(_make_rel(
                        from_uid=prev_uid,
                        to_uid=c_uid,
                        rel_type=CurriculumRelationType.LEADS_TO,
                    ))

            for d in range(4):
                d_uid = f"curriculum:physics:ch{ch}:concept_0:detail_{d}"
                nodes.append(_make_node(
                    uid=d_uid,
                    resolution_level=ResolutionLevel.DETAIL,
                    chapter_order=ch + 1,
                    within_chapter_order=1,
                ))

        gen = CypherGenerator()
        stmts = gen.generate(_make_extraction(nodes=nodes, relationships=rels))

        node_stmts = [s for s in stmts if s.category == "node"]
        rel_stmts = [s for s in stmts if s.category == "relationship"]

        assert len(node_stmts) == len(nodes)
        assert len(rel_stmts) == len(rels)

        # Verify ordering
        categories = [s.category for s in stmts]
        assert categories == ["node"] * len(nodes) + ["relationship"] * len(rels)

        # Verify all statements have queries and params
        for stmt in stmts:
            assert stmt.query
            assert stmt.params
            assert "uid" in stmt.params or "from_uid" in stmt.params


class TestGenerateText:
    """Test human-readable text output."""

    def test_text_output_includes_comments(self):
        node = _make_node()
        gen = CypherGenerator()
        text = gen.generate_text(_make_extraction(nodes=[node]))

        assert "// [node] Concept" in text
        assert "MERGE" in text
