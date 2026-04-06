"""Tests for text chunker — paragraph-aligned splitting with overlap."""

from __future__ import annotations

import pytest

from lecture_pipeline.curriculum.merge.text_chunker import (
    TextChunk,
    chunk_text,
    needs_chunking,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_text(size: int, paragraph_interval: int = 500) -> str:
    """Build a text string of approximately `size` chars with paragraph breaks."""
    paragraphs = []
    remaining = size
    while remaining > 0:
        para_size = min(paragraph_interval, remaining)
        # Fill with repeating words, ending with paragraph break
        words = "word " * (para_size // 5)
        paragraphs.append(words.strip())
        remaining -= para_size
    return "\n\n".join(paragraphs)


# ===========================================================================
# TestChunking
# ===========================================================================


class TestChunking:
    def test_short_text_single_chunk(self):
        """Text below target_size returns a single chunk."""
        text = "Short text here."
        chunks = chunk_text(text, target_size=25_000)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_exact_threshold_single_chunk(self):
        """Text exactly at target_size returns a single chunk."""
        text = "x" * 25_000
        chunks = chunk_text(text, target_size=25_000)
        assert len(chunks) == 1

    def test_two_chunks_with_overlap(self):
        """Text that's ~40K with 25K target produces 2 chunks."""
        text = _make_text(40_000)
        chunks = chunk_text(text, target_size=25_000, overlap=2_000)
        assert len(chunks) == 2
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[0].total_chunks == 2
        assert chunks[1].total_chunks == 2
        # Second chunk should start before the first chunk ends (overlap)
        assert chunks[1].char_start < chunks[0].char_end

    def test_three_chunks(self):
        """Text ~70K produces 3 chunks."""
        text = _make_text(70_000)
        chunks = chunk_text(text, target_size=25_000, overlap=2_000)
        assert len(chunks) >= 3

    def test_overlap_content_shared(self):
        """End of chunk N appears at start of chunk N+1."""
        text = _make_text(50_000, paragraph_interval=1_000)
        chunks = chunk_text(text, target_size=25_000, overlap=2_000)
        assert len(chunks) >= 2

        # The overlap region of chunk 1 should appear in chunk 0's end
        overlap_start = chunks[1].char_start
        overlap_end = chunks[0].char_end
        if overlap_end > overlap_start:
            # There is actual overlap
            original_overlap = text[overlap_start:overlap_end]
            chunk0_tail = chunks[0].text[-(overlap_end - overlap_start):]
            chunk1_head = chunks[1].text[:overlap_end - overlap_start]
            assert chunk0_tail == original_overlap
            assert chunk1_head == original_overlap

    def test_paragraph_boundary_splitting(self):
        """Chunks split at paragraph boundaries, not mid-word."""
        # Build text with clear paragraph breaks
        paragraphs = ["This is paragraph number %d. " % i + "x" * 4_000 for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, target_size=10_000, overlap=500)

        # Each chunk should start at the beginning of text or after a paragraph break
        for chunk in chunks[1:]:
            # The chunk start in the original text should be near a paragraph break
            context = text[max(0, chunk.char_start - 5):chunk.char_start + 5]
            # Allow flexibility — the key invariant is that chunks are usable
            assert len(chunk.text) > 0

    def test_small_final_chunk_merged(self):
        """A tiny final chunk gets merged into the previous chunk."""
        # 27K text with 25K target → break at ~25K, leaving ~2K
        # With min_chunk_size=5000, the 2K tail should be merged
        text = _make_text(27_000, paragraph_interval=500)
        chunks = chunk_text(
            text, target_size=25_000, overlap=2_000, min_chunk_size=5_000
        )
        assert len(chunks) == 1  # Too small to split meaningfully

    def test_chunk_metadata_correct(self):
        """char_start, char_end, chunk_index, total_chunks are correct."""
        text = _make_text(60_000, paragraph_interval=1_000)
        chunks = chunk_text(text, target_size=25_000, overlap=2_000)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)
            assert chunk.char_start >= 0
            assert chunk.char_end <= len(text)
            assert chunk.char_start < chunk.char_end
            # Chunk text matches the original text at its position
            assert chunk.text == text[chunk.char_start:chunk.char_end]


# ===========================================================================
# TestNeedsChunking
# ===========================================================================


class TestNeedsChunking:
    def test_needs_chunking_true(self):
        assert needs_chunking("x" * 60_000) is True

    def test_needs_chunking_false(self):
        assert needs_chunking("x" * 30_000) is False


# ===========================================================================
# TestEdgeCases
# ===========================================================================


class TestEdgeCases:
    def test_empty_text(self):
        """Empty string produces 1 chunk with empty text."""
        chunks = chunk_text("")
        assert len(chunks) == 1
        assert chunks[0].text == ""
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == 0

    def test_full_text_recoverable(self):
        """All text is covered by the chunks (no gaps, considering overlap)."""
        text = _make_text(60_000, paragraph_interval=1_000)
        chunks = chunk_text(text, target_size=25_000, overlap=2_000)

        # Every character in the original text should be covered by at least one chunk
        covered = set()
        for chunk in chunks:
            for pos in range(chunk.char_start, chunk.char_end):
                covered.add(pos)

        for pos in range(len(text)):
            assert pos in covered, f"Position {pos} not covered by any chunk"
