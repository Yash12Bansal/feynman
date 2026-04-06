"""Deterministic text chunking for large chapters.

Splits chapter text into overlapping chunks at paragraph boundaries.
Used when chapter text exceeds the chunk threshold (default 50K chars).

The overlap ensures concepts that span chunk boundaries appear in
both adjacent chunks, so the EntityResolver can match and merge them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    """A chunk of text with its position metadata."""

    text: str
    chunk_index: int  # 0-based
    char_start: int  # start offset in original text
    char_end: int  # end offset in original text
    total_chunks: int


def needs_chunking(text: str, threshold: int = 50_000) -> bool:
    """Check if text exceeds the chunking threshold."""
    return len(text) > threshold


def chunk_text(
    text: str,
    target_size: int = 25_000,
    overlap: int = 2_000,
    min_chunk_size: int = 5_000,
) -> list[TextChunk]:
    """Split text into overlapping chunks at paragraph boundaries.

    Algorithm:
      1. Compute raw break points at every target_size chars.
      2. For each break point, search +/-500 chars for the nearest
         paragraph boundary (double newline) to avoid splitting mid-sentence.
      3. Apply overlap: each chunk starts `overlap` chars before its
         nominal start (except chunk 0).
      4. If the final chunk would be smaller than min_chunk_size,
         merge it into the previous chunk.

    Args:
        text: Full chapter text.
        target_size: Target chunk size in characters.
        overlap: Overlap between adjacent chunks in characters.
        min_chunk_size: Minimum chunk size; smaller final chunks get merged.

    Returns:
        List of TextChunk objects, ordered by position.
        Returns a single chunk if text is shorter than target_size.
    """
    if not text or len(text) <= target_size:
        return [
            TextChunk(
                text=text,
                chunk_index=0,
                char_start=0,
                char_end=len(text),
                total_chunks=1,
            )
        ]

    # Find paragraph-aligned break points
    break_points = _find_break_points(text, target_size)

    if not break_points:
        return [
            TextChunk(
                text=text,
                chunk_index=0,
                char_start=0,
                char_end=len(text),
                total_chunks=1,
            )
        ]

    # Build chunk boundaries from break points
    boundaries = _build_chunk_boundaries(text, break_points, overlap)

    # Merge small final chunk
    if len(boundaries) > 1:
        last_start, last_end = boundaries[-1]
        if (last_end - last_start) < min_chunk_size:
            # Extend the previous chunk to cover the final chunk
            prev_start, _ = boundaries[-2]
            boundaries[-2] = (prev_start, last_end)
            boundaries.pop()

    # Build TextChunk objects
    total = len(boundaries)
    chunks = []
    for i, (start, end) in enumerate(boundaries):
        chunks.append(
            TextChunk(
                text=text[start:end],
                chunk_index=i,
                char_start=start,
                char_end=end,
                total_chunks=total,
            )
        )

    return chunks


def _find_break_points(text: str, target_size: int) -> list[int]:
    """Find paragraph-aligned break points in text.

    Starts from raw positions at every target_size chars,
    then adjusts each to the nearest paragraph boundary (double newline)
    within a +/-500 char window.
    """
    break_points = []
    pos = target_size

    while pos < len(text):
        # Search for nearest paragraph boundary in window
        best = _find_nearest_paragraph_break(text, pos, window=500)
        if best is not None:
            break_points.append(best)
        else:
            # No paragraph break found — use target position
            break_points.append(pos)

        pos = break_points[-1] + target_size

    return break_points


def _find_nearest_paragraph_break(
    text: str, pos: int, window: int = 500
) -> int | None:
    """Find the nearest double-newline paragraph boundary near pos.

    Searches within [pos - window, pos + window]. Returns the position
    right after the paragraph break (start of next paragraph).
    Prefers breaks closest to pos.
    """
    search_start = max(0, pos - window)
    search_end = min(len(text), pos + window)
    region = text[search_start:search_end]

    # Find all double-newline positions in the region
    best_pos = None
    best_dist = window + 1
    offset = 0

    while True:
        idx = region.find("\n\n", offset)
        if idx == -1:
            break
        # Position in original text, right after the break
        abs_pos = search_start + idx + 2
        dist = abs(abs_pos - pos)
        if dist < best_dist:
            best_dist = dist
            best_pos = abs_pos
        offset = idx + 1

    return best_pos


def _build_chunk_boundaries(
    text: str,
    break_points: list[int],
    overlap: int,
) -> list[tuple[int, int]]:
    """Build (start, end) pairs for each chunk, applying overlap."""
    boundaries: list[tuple[int, int]] = []

    # First chunk: [0, first_break)
    boundaries.append((0, break_points[0]))

    # Middle chunks: [break[i-1] - overlap, break[i])
    for i in range(1, len(break_points)):
        start = max(0, break_points[i - 1] - overlap)
        end = break_points[i]
        boundaries.append((start, end))

    # Final chunk: [last_break - overlap, len(text))
    last_start = max(0, break_points[-1] - overlap)
    boundaries.append((last_start, len(text)))

    return boundaries
