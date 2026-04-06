"""Within-chapter chunk merging for curriculum extraction."""

from .entity_resolver import (
    IdentityKey,
    compute_identity_key,
    compute_node_identity,
    group_by_identity,
    normalize_topic_name,
)
from .extraction_merger import ExtractionMerger, MergeReport
from .text_chunker import TextChunk, chunk_text, needs_chunking

__all__ = [
    "ExtractionMerger",
    "IdentityKey",
    "MergeReport",
    "TextChunk",
    "chunk_text",
    "compute_identity_key",
    "compute_node_identity",
    "group_by_identity",
    "needs_chunking",
    "normalize_topic_name",
]
