"""Deterministic semantic ID generation for curriculum graph nodes.

IDs are human-readable, stable across re-runs, and serve as the primary
key for cross-graph references (dashboard state, student knowledge).

Format:
    curriculum:{subject}:{chapter_slug}:{concept_slug}
    curriculum:{subject}:{chapter_slug}:{concept_slug}:{sub_concept_slug}

Examples:
    curriculum:physics:simple_harmonic_motion
    curriculum:physics:simple_harmonic_motion:energy_in_shm
    curriculum:physics:simple_harmonic_motion:energy_in_shm:potential_energy_formula
"""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    """Convert arbitrary text to a stable, URL-safe slug.

    - Unicode normalized (NFD → ASCII)
    - Lowercased
    - Non-alphanumeric characters replaced with underscores
    - Consecutive underscores collapsed
    - Leading/trailing underscores stripped
    - Truncated to 80 chars (preserving word boundaries where possible)
    """
    # Normalize unicode → ASCII approximation
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()

    # Replace non-alphanumeric with underscore
    text = re.sub(r"[^a-z0-9]+", "_", text)

    # Collapse consecutive underscores and strip edges
    text = re.sub(r"_+", "_", text).strip("_")

    # Truncate to 80 chars at a word boundary
    if len(text) > 80:
        text = text[:80].rsplit("_", 1)[0]

    return text


def generate_concept_uid(
    subject: str,
    chapter_title: str,
    concept_name: str,
    parent_concept_name: str | None = None,
) -> str:
    """Generate a deterministic, human-readable UID for a concept node.

    Same inputs always produce the same UID — critical for idempotent
    re-ingestion and cross-graph references.

    Args:
        subject: e.g. "physics"
        chapter_title: e.g. "Simple Harmonic Motion"
        concept_name: e.g. "Energy in SHM"
        parent_concept_name: e.g. "Energy in SHM" (for sub-concepts)

    Returns:
        Stable semantic ID like "curriculum:physics:simple_harmonic_motion:energy_in_shm"
    """
    parts = [
        "curriculum",
        slugify(subject),
        slugify(chapter_title),
    ]

    if parent_concept_name:
        parts.append(slugify(parent_concept_name))

    parts.append(slugify(concept_name))

    return ":".join(parts)


def generate_chapter_uid(subject: str, chapter_title: str) -> str:
    """Generate UID for a Chapter node."""
    return f"curriculum:{slugify(subject)}:{slugify(chapter_title)}"


def generate_unit_uid(subject: str, unit_name: str) -> str:
    """Generate UID for a Unit node."""
    return f"unit:{slugify(subject)}:{slugify(unit_name)}"


def generate_subject_uid(subject: str) -> str:
    """Generate UID for a Subject node."""
    return f"subject:{slugify(subject)}"


def generate_visual_uid(concept_uid: str) -> str:
    """Generate UID for a Visual node linked to a concept.

    Mirrors the concept UID with a 'visual:' prefix instead of 'curriculum:'.
    """
    if concept_uid.startswith("curriculum:"):
        return "visual:" + concept_uid[len("curriculum:"):]
    return f"visual:{concept_uid}"


def generate_relationship_key(
    rel_type: str, from_uid: str, to_uid: str
) -> str:
    """Generate a deterministic key for relationship deduplication.

    Format: rel:{type}:{from_uid}:{to_uid}
    """
    return f"rel:{rel_type}:{from_uid}:{to_uid}"
