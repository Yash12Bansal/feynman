"""Deterministic concept identity for within-chapter chunk merging.

Computes identity keys so that the same concept extracted from
different chunks of the same chapter can be recognized and merged.

Identity = SHA-256(normalized_name + concept_type + parent_slug)[:16]

The normalization is stricter than id_generator.slugify():
  - lowercase
  - strip whitespace
  - remove stop words: "of", "the", "in", "a", "an", "for"
  - collapse whitespace

This catches cases like "Energy in SHM" vs "Energy SHM" across chunks.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass

from ..models import ConceptType, ExtractionNode

# Stop words removed during normalization
_STOP_WORDS: frozenset[str] = frozenset({"of", "the", "in", "a", "an", "for"})


@dataclass(frozen=True)
class IdentityKey:
    """A 16-char hex identity key with its source components for debugging."""

    key: str  # 16-char hex SHA-256 prefix
    normalized_name: str
    concept_type: str
    parent_slug: str  # "" if no parent


def normalize_topic_name(name: str) -> str:
    """Normalize a topic name for identity matching.

    Steps:
      1. Lowercase
      2. Strip leading/trailing whitespace
      3. Remove stop words (whole-word only)
      4. Collapse runs of whitespace to single space
      5. Strip again after stop-word removal
    """
    text = name.lower().strip()
    # Remove stop words as whole words
    words = text.split()
    words = [w for w in words if w not in _STOP_WORDS]
    return " ".join(words)


def compute_identity_key(
    topic_name: str,
    concept_type: ConceptType | str,
    parent_name: str | None = None,
) -> IdentityKey:
    """Compute a deterministic 16-char identity key for a concept.

    Args:
        topic_name: The raw topic name from extraction.
        concept_type: ConceptType enum or its string value.
        parent_name: Raw parent topic name (None if top-level).

    Returns:
        IdentityKey with the hex digest and source components.
    """
    normalized = normalize_topic_name(topic_name)
    type_val = (
        concept_type.value
        if isinstance(concept_type, ConceptType)
        else concept_type.lower()
    )
    parent_slug = normalize_topic_name(parent_name) if parent_name else ""

    raw = f"{normalized}|{type_val}|{parent_slug}"
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    return IdentityKey(
        key=key,
        normalized_name=normalized,
        concept_type=type_val,
        parent_slug=parent_slug,
    )


def compute_node_identity(node: ExtractionNode) -> IdentityKey:
    """Compute identity key for an ExtractionNode.

    Reads parent name from node.metadata["raw_parent_name"] since
    parent_uid is a generated UID (not suitable for cross-chunk matching).
    """
    parent_name = node.metadata.get("raw_parent_name")
    return compute_identity_key(
        topic_name=node.topic_name,
        concept_type=node.concept_type,
        parent_name=parent_name,
    )


def group_by_identity(
    nodes: list[ExtractionNode],
) -> dict[str, list[ExtractionNode]]:
    """Group nodes by their identity key.

    Returns:
        Dict mapping identity_key hex → list of nodes sharing that identity.
        Nodes with unique keys appear as single-element lists.
        Order within each group follows the input order.
    """
    groups: dict[str, list[ExtractionNode]] = defaultdict(list)
    for node in nodes:
        identity = compute_node_identity(node)
        groups[identity.key].append(node)
    return dict(groups)
