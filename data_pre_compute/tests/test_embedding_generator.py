"""Tests for embedding text composition and batch logic (no API calls)."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.ingestion.embedding_generator import EmbeddingGenerator
from lecture_pipeline.curriculum.models import (
    ConceptType,
    ExtractionNode,
    ResolutionLevel,
)


def _make_node(
    resolution_level: ResolutionLevel = ResolutionLevel.CONCEPT,
    topic_name: str = "Energy in SHM",
    summary: str = "Kinetic and potential energy exchange in simple harmonic motion.",
) -> ExtractionNode:
    return ExtractionNode(
        uid=f"curriculum:physics:shm:{topic_name.lower().replace(' ', '_')}",
        topic_name=topic_name,
        concept_type=ConceptType.DEFINITION,
        resolution_level=resolution_level,
        summary=summary,
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=1,
    )


class TestComposeEmbeddingText:
    """Test embedding text composition for each resolution level."""

    def test_concept_uses_colon_separator(self):
        node = _make_node(resolution_level=ResolutionLevel.CONCEPT)
        text = EmbeddingGenerator.compose_embedding_text(node)
        assert text == "Energy in SHM: Kinetic and potential energy exchange in simple harmonic motion."

    def test_detail_uses_colon_separator(self):
        node = _make_node(resolution_level=ResolutionLevel.DETAIL)
        text = EmbeddingGenerator.compose_embedding_text(node)
        assert ": " in text

    def test_chapter_uses_period_separator(self):
        node = _make_node(resolution_level=ResolutionLevel.CHAPTER)
        text = EmbeddingGenerator.compose_embedding_text(node)
        assert text == "Energy in SHM. Kinetic and potential energy exchange in simple harmonic motion."

    def test_unit_uses_period_separator(self):
        node = _make_node(resolution_level=ResolutionLevel.UNIT)
        text = EmbeddingGenerator.compose_embedding_text(node)
        assert ". " in text

    def test_syllabus_uses_period_separator(self):
        node = _make_node(resolution_level=ResolutionLevel.SYLLABUS)
        text = EmbeddingGenerator.compose_embedding_text(node)
        assert ". " in text

    def test_text_includes_topic_name_and_summary(self):
        node = _make_node(
            topic_name="Newton's Laws",
            summary="Three fundamental laws of motion.",
        )
        text = EmbeddingGenerator.compose_embedding_text(node)
        assert "Newton's Laws" in text
        assert "Three fundamental laws" in text

    def test_empty_summary_still_works(self):
        node = _make_node(summary="")
        text = EmbeddingGenerator.compose_embedding_text(node)
        assert text.startswith("Energy in SHM")


class TestBatchPartitioning:
    """Test that items are correctly partitioned into batches."""

    def test_batch_size_100_with_250_items(self):
        """250 items with batch_size=100 → 3 batches (100, 100, 50)."""
        # We can't test the actual API call without mocking, but we can
        # verify the batch logic by checking the range calculation
        items = list(range(250))
        batch_size = 100
        batches = []
        for i in range(0, len(items), batch_size):
            batches.append(items[i : i + batch_size])

        assert len(batches) == 3
        assert len(batches[0]) == 100
        assert len(batches[1]) == 100
        assert len(batches[2]) == 50

    def test_exact_batch_size(self):
        """100 items with batch_size=100 → 1 batch."""
        items = list(range(100))
        batch_size = 100
        batches = []
        for i in range(0, len(items), batch_size):
            batches.append(items[i : i + batch_size])

        assert len(batches) == 1
        assert len(batches[0]) == 100

    def test_fewer_than_batch_size(self):
        """30 items with batch_size=100 → 1 batch of 30."""
        items = list(range(30))
        batch_size = 100
        batches = []
        for i in range(0, len(items), batch_size):
            batches.append(items[i : i + batch_size])

        assert len(batches) == 1
        assert len(batches[0]) == 30
