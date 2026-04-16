"""Tests for extraction merger — within-chapter chunk merging."""

from __future__ import annotations

import json

import pytest

from lecture_pipeline.curriculum.merge.extraction_merger import (
    ExtractionMerger,
    MergeReport,
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
from lecture_pipeline.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """LLM provider that returns preconfigured responses."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, str]] = []
        self._call_index = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self._call_index < len(self.responses):
            content = self.responses[self._call_index]
            self._call_index += 1
        else:
            content = "Merged summary fallback."
        return LLMResponse(content=content, model="mock-model", usage=None)

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return self.generate(system_prompt, user_prompt)


class FailingLLMProvider(LLMProvider):
    """LLM provider that always raises."""

    def __init__(self):
        pass  # Skip LLMProvider.__init__ which requires config

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        raise RuntimeError("LLM unavailable")

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        raise RuntimeError("LLM unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SOURCE = ExtractionSource(
    textbook_title="HC Verma Vol 1",
    chapter_title="Simple Harmonic Motion",
    page_range="245-270",
    extractor_model="mock-model",
)


def _make_node(
    topic_name: str,
    concept_type: ConceptType = ConceptType.TOPIC,
    uid: str | None = None,
    parent_name: str | None = None,
    parent_uid: str | None = None,
    within_chapter_order: int = 1,
    page_start: int = 1,
    page_end: int = 5,
    summary: str = "A summary.",
    source_text: str = "Source text.",
    difficulty: Difficulty = Difficulty.INTERMEDIATE,
    visual_hint: str | None = None,
    children_uids: list[str] | None = None,
    **extra_metadata,
) -> ExtractionNode:
    metadata = {}
    if parent_name:
        metadata["raw_parent_name"] = parent_name
    metadata.update(extra_metadata)

    return ExtractionNode(
        uid=uid or f"curriculum:physics:shm:{topic_name.lower().replace(' ', '_')}",
        topic_name=topic_name,
        concept_type=concept_type,
        resolution_level=ResolutionLevel.CONCEPT,
        summary=summary,
        source_text=source_text,
        page_start=page_start,
        page_end=page_end,
        chapter_order=12,
        within_chapter_order=within_chapter_order,
        difficulty=difficulty,
        visual_hint=visual_hint,
        parent_uid=parent_uid,
        children_uids=children_uids or [],
        metadata=metadata,
    )


def _make_rel(
    from_uid: str,
    to_uid: str,
    rel_type: CurriculumRelationType = CurriculumRelationType.PREREQUISITE,
    label: str = "",
) -> ExtractionRelationship:
    return ExtractionRelationship(
        relationship_key=f"rel:{rel_type.value}:{from_uid}:{to_uid}",
        type=rel_type,
        from_uid=from_uid,
        to_uid=to_uid,
        label=label,
    )


def _make_extraction(
    nodes: list[ExtractionNode],
    rels: list[ExtractionRelationship] | None = None,
    warnings: list[str] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="HC Verma Vol 1",
        chapter_title="Simple Harmonic Motion",
        source=SOURCE,
        nodes=nodes,
        relationships=rels or [],
        warnings=warnings or [],
    )


# ===========================================================================
# TestMergeValidation
# ===========================================================================


class TestMergeValidation:
    def test_single_chunk_passthrough(self):
        """Single chunk returns identical result."""
        node = _make_node("SHM")
        extraction = _make_extraction([node])
        merger = ExtractionMerger()

        result, report = merger.merge_chunks([extraction])

        assert len(result.nodes) == 1
        assert result.nodes[0].topic_name == "SHM"
        assert report.total_input_nodes == 1
        assert report.singleton_node_count == 1
        assert report.merged_node_count == 0

    def test_empty_chunks_raises(self):
        merger = ExtractionMerger()
        with pytest.raises(ValueError, match="must not be empty"):
            merger.merge_chunks([])

    def test_mismatched_chapters_raises(self):
        chunk1 = _make_extraction([_make_node("SHM")])
        chunk2 = CurriculumExtractionResult(
            subject="physics",
            textbook_title="HC Verma Vol 1",
            chapter_title="Wave Motion",  # Different chapter
            source=SOURCE,
            nodes=[_make_node("Waves")],
            relationships=[],
        )
        merger = ExtractionMerger()
        with pytest.raises(ValueError, match="chapter_title"):
            merger.merge_chunks([chunk1, chunk2])


# ===========================================================================
# TestNodeMerging
# ===========================================================================


class TestNodeMerging:
    def test_no_overlap(self):
        """Disjoint concepts from 2 chunks are all preserved."""
        chunk1 = _make_extraction([
            _make_node("SHM", within_chapter_order=1),
            _make_node("Energy", within_chapter_order=2),
        ])
        chunk2 = _make_extraction([
            _make_node("Damping", within_chapter_order=1),
            _make_node("Resonance", within_chapter_order=2),
        ])
        merger = ExtractionMerger()
        result, report = merger.merge_chunks([chunk1, chunk2])

        assert report.total_output_nodes == 4
        assert report.merged_node_count == 0
        assert report.singleton_node_count == 4

    def test_with_overlap(self):
        """Two chunks sharing a concept merge it."""
        # Both chunks have "Energy in SHM" — should merge to 1
        chunk1 = _make_extraction([
            _make_node("SHM", uid="uid_shm", within_chapter_order=1),
            _make_node("Energy in SHM", uid="uid_energy1", within_chapter_order=2,
                       summary="Chunk 1 energy summary.", page_start=1, page_end=10),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_energy2", within_chapter_order=1,
                       summary="Chunk 2 energy summary.", page_start=8, page_end=15),
            _make_node("Damping", uid="uid_damp", within_chapter_order=2),
        ])
        merger = ExtractionMerger()
        result, report = merger.merge_chunks([chunk1, chunk2])

        assert report.total_output_nodes == 3  # SHM + merged Energy + Damping
        assert report.merged_node_count == 1

    def test_three_chunks(self):
        """Concept appearing in 3 chunks merges correctly."""
        chunks = []
        for i in range(3):
            chunks.append(_make_extraction([
                _make_node("Energy in SHM", uid=f"uid_e{i}",
                           within_chapter_order=1,
                           summary=f"Summary from chunk {i}."),
                _make_node(f"Unique_{i}", uid=f"uid_u{i}", within_chapter_order=2),
            ]))
        merger = ExtractionMerger()
        result, report = merger.merge_chunks(chunks)

        # 1 merged Energy + 3 unique = 4
        assert report.total_output_nodes == 4
        assert report.merged_node_count == 1

    def test_summary_concatenated_no_llm(self):
        """Without LLM, summaries are concatenated."""
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_e1", summary="KE is ½mv².",
                       within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", summary="PE is ½kx².",
                       within_chapter_order=1),
        ])
        merger = ExtractionMerger(llm=None)
        result, _ = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert "KE is ½mv²." in energy_node.summary
        assert "PE is ½kx²." in energy_node.summary
        assert ExtractionMerger.SUMMARY_SEPARATOR in energy_node.summary

    def test_summary_with_llm(self):
        """With LLM, summaries are reconciled via LLM call."""
        llm = MockLLMProvider(responses=["Complete energy summary with KE and PE."])
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_e1", summary="KE is ½mv².",
                       within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", summary="PE is ½kx².",
                       within_chapter_order=1),
        ])
        merger = ExtractionMerger(llm=llm)
        result, report = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert energy_node.summary == "Complete energy summary with KE and PE."
        assert report.llm_reconciliations == 1
        assert len(llm.calls) == 1

    def test_source_text_concatenated(self):
        """source_text is always concatenated."""
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_e1", source_text="Source A.",
                       within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", source_text="Source B.",
                       within_chapter_order=1),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert "Source A." in energy_node.source_text
        assert "Source B." in energy_node.source_text

    def test_page_range_min_max(self):
        """page_start=min, page_end=max of all chunks."""
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_e1", page_start=5, page_end=10,
                       within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", page_start=8, page_end=15,
                       within_chapter_order=1),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert energy_node.page_start == 5
        assert energy_node.page_end == 15


# ===========================================================================
# TestRelationshipMerging
# ===========================================================================


class TestRelationshipMerging:
    def test_union(self):
        """All unique relationships are preserved."""
        rel1 = _make_rel("uid_a", "uid_b")
        rel2 = _make_rel("uid_c", "uid_d", CurriculumRelationType.LEADS_TO)
        chunk1 = _make_extraction(
            [_make_node("A", uid="uid_a"), _make_node("B", uid="uid_b", within_chapter_order=2)],
            rels=[rel1],
        )
        chunk2 = _make_extraction(
            [_make_node("C", uid="uid_c"), _make_node("D", uid="uid_d", within_chapter_order=2)],
            rels=[rel2],
        )
        merger = ExtractionMerger()
        result, report = merger.merge_chunks([chunk1, chunk2])
        assert report.total_output_relationships == 2

    def test_dedup(self):
        """Duplicate relationship_keys are eliminated."""
        rel = _make_rel("uid_a", "uid_b")
        chunk1 = _make_extraction(
            [_make_node("A", uid="uid_a"), _make_node("B", uid="uid_b", within_chapter_order=2)],
            rels=[rel],
        )
        chunk2 = _make_extraction(
            [_make_node("C", uid="uid_c"), _make_node("D", uid="uid_d", within_chapter_order=2)],
            rels=[_make_rel("uid_a", "uid_b")],  # Same rel
        )
        merger = ExtractionMerger()
        result, report = merger.merge_chunks([chunk1, chunk2])
        assert report.total_output_relationships == 1

    def test_uid_rewrite(self):
        """Non-canonical UIDs in relationships get rewritten."""
        # Energy node appears in both chunks with different UIDs
        chunk1 = _make_extraction(
            nodes=[
                _make_node("SHM", uid="uid_shm", within_chapter_order=1),
                _make_node("Energy in SHM", uid="uid_e1", within_chapter_order=2),
            ],
            rels=[_make_rel("uid_shm", "uid_e1", CurriculumRelationType.CONTAINS)],
        )
        chunk2 = _make_extraction(
            nodes=[
                _make_node("Energy SHM", uid="uid_e2", within_chapter_order=1),
                _make_node("Damping", uid="uid_d", within_chapter_order=2),
            ],
            rels=[_make_rel("uid_e2", "uid_d", CurriculumRelationType.LEADS_TO)],
        )
        merger = ExtractionMerger()
        result, report = merger.merge_chunks([chunk1, chunk2])

        # uid_e2 should be remapped to uid_e1
        leads_to_rels = [
            r for r in result.relationships
            if r.type == CurriculumRelationType.LEADS_TO
        ]
        assert len(leads_to_rels) == 1
        assert leads_to_rels[0].from_uid == "uid_e1"  # Rewritten from uid_e2


# ===========================================================================
# TestOrderAndHierarchy
# ===========================================================================


class TestOrderAndHierarchy:
    def test_sequential_order(self):
        """After merge, within_chapter_order is 1..N with no gaps."""
        chunk1 = _make_extraction([
            _make_node("A", uid="uid_a", within_chapter_order=1),
            _make_node("B", uid="uid_b", within_chapter_order=2),
        ])
        chunk2 = _make_extraction([
            _make_node("C", uid="uid_c", within_chapter_order=1),
            _make_node("D", uid="uid_d", within_chapter_order=2),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        orders = sorted(n.within_chapter_order for n in result.nodes)
        assert orders == [1, 2, 3, 4]

    def test_global_order_recomputed(self):
        """global_teaching_order matches new within_chapter_order."""
        chunk1 = _make_extraction([
            _make_node("A", uid="uid_a", within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("B", uid="uid_b", within_chapter_order=1),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        for node in result.nodes:
            expected = node.chapter_order * 1000 + node.within_chapter_order
            assert node.global_teaching_order == expected

    def test_cross_chunk_parent_child(self):
        """Parent in chunk 1, child in chunk 2 are wired correctly."""
        parent = _make_node("Energy in SHM", uid="uid_parent", within_chapter_order=1,
                            children_uids=["uid_ke_c1"])
        child_c1 = _make_node("KE Formula", uid="uid_ke_c1", within_chapter_order=2,
                              concept_type=ConceptType.FORMULA,
                              parent_name="Energy in SHM", parent_uid="uid_parent")

        chunk1 = _make_extraction([parent, child_c1])

        # Chunk 2 has a new child of the same parent concept
        child_c2 = _make_node("PE Formula", uid="uid_pe_c2", within_chapter_order=1,
                              concept_type=ConceptType.FORMULA,
                              parent_name="Energy in SHM", parent_uid="uid_parent_c2")
        parent_c2 = _make_node("Energy SHM", uid="uid_parent_c2",
                               within_chapter_order=2,
                               children_uids=["uid_pe_c2"])

        chunk2 = _make_extraction([child_c2, parent_c2])

        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        # Find merged parent (canonical uid = uid_parent)
        merged_parent = result.node_by_uid("uid_parent")
        assert merged_parent is not None
        # PE Formula's parent_uid should be remapped to uid_parent
        pe_node = result.node_by_uid("uid_pe_c2")
        assert pe_node is not None
        assert pe_node.parent_uid == "uid_parent"

    def test_bidirectional_consistency(self):
        """parent_uid and children_uids are consistent after merge."""
        parent = _make_node("SHM", uid="uid_shm", within_chapter_order=1)
        child = _make_node("Energy", uid="uid_energy", within_chapter_order=2,
                           parent_name="SHM", parent_uid="uid_shm")

        chunk1 = _make_extraction([parent, child])
        chunk2 = _make_extraction([
            _make_node("Damping", uid="uid_damp", within_chapter_order=1),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        # Find parent and child
        shm = result.node_by_uid("uid_shm")
        energy = result.node_by_uid("uid_energy")
        assert energy.parent_uid == "uid_shm"
        assert energy.uid in shm.children_uids


# ===========================================================================
# TestEdgeCases
# ===========================================================================


class TestEdgeCases:
    def test_empty_summary_not_concatenated(self):
        """Empty summary is ignored; non-empty one is used."""
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_e1", summary="",
                       within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", summary="Real summary here.",
                       within_chapter_order=1),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert energy_node.summary == "Real summary here."
        assert ExtractionMerger.SUMMARY_SEPARATOR not in energy_node.summary

    def test_llm_failure_falls_back_to_concat(self):
        """LLM raising exception falls back to concatenation."""
        llm = FailingLLMProvider()
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_e1", summary="Summary A.",
                       within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", summary="Summary B.",
                       within_chapter_order=1),
        ])
        merger = ExtractionMerger(llm=llm)
        result, report = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert "Summary A." in energy_node.summary
        assert "Summary B." in energy_node.summary
        assert report.llm_reconciliations == 0

    def test_chunk_with_zero_nodes_skipped(self):
        """Chunk with no nodes is handled gracefully."""
        chunk1 = _make_extraction([
            _make_node("SHM", uid="uid_shm"),
        ])
        chunk2 = _make_extraction([])  # Empty chunk
        merger = ExtractionMerger()
        result, report = merger.merge_chunks([chunk1, chunk2])

        assert report.total_output_nodes == 1

    def test_merge_report_counts(self):
        """MergeReport has correct counts."""
        chunk1 = _make_extraction([
            _make_node("SHM", uid="uid_shm", within_chapter_order=1),
            _make_node("Energy in SHM", uid="uid_e1", within_chapter_order=2),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", within_chapter_order=1),
            _make_node("Damping", uid="uid_damp", within_chapter_order=2),
        ])
        merger = ExtractionMerger()
        _, report = merger.merge_chunks([chunk1, chunk2])

        assert report.total_input_nodes == 4
        assert report.merged_node_count == 1
        assert report.singleton_node_count == 2
        assert report.total_output_nodes == 3

    def test_cross_chapter_ref_preserved(self):
        """Relationships with '::' to_uid are preserved as-is."""
        cross_ref = ExtractionRelationship(
            relationship_key="rel:cross_references:uid_e:Chapter 5::Energy Conservation",
            type=CurriculumRelationType.CROSS_REFERENCES,
            from_uid="uid_e",
            to_uid="Chapter 5::Energy Conservation",
            label="Cross-chapter reference",
        )
        chunk1 = _make_extraction(
            [_make_node("Energy", uid="uid_e")],
            rels=[cross_ref],
        )
        chunk2 = _make_extraction([_make_node("Damping", uid="uid_d")])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        cross_rels = [
            r for r in result.relationships
            if "::" in r.to_uid
        ]
        assert len(cross_rels) == 1
        assert cross_rels[0].to_uid == "Chapter 5::Energy Conservation"


# ===========================================================================
# TestMergeMetadata
# ===========================================================================


class TestMergeMetadata:
    def test_provenance_metadata(self):
        """Merged nodes have chunk_merged and merge_sources metadata."""
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_e1", within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_e2", within_chapter_order=1),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert energy_node.metadata["chunk_merged"] is True
        assert energy_node.metadata["merge_sources"] == 2

    def test_uid_remap_canonical_is_first(self):
        """The canonical UID comes from the first (earliest) chunk."""
        chunk1 = _make_extraction([
            _make_node("Energy in SHM", uid="uid_first", within_chapter_order=1),
        ])
        chunk2 = _make_extraction([
            _make_node("Energy SHM", uid="uid_second", within_chapter_order=1),
        ])
        merger = ExtractionMerger()
        result, _ = merger.merge_chunks([chunk1, chunk2])

        energy_node = next(n for n in result.nodes if "energy" in n.topic_name.lower())
        assert energy_node.uid == "uid_first"
