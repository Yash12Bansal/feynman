"""Stable identifiers for per-persona lecture variants."""

from __future__ import annotations


def variant_id(chapter_id: str, persona_id: str) -> str:
    """``{chapter_id}::persona:{persona_id}`` — design doc 21."""
    return f"{chapter_id}::persona:{persona_id}"


def parse_variant_id(variant_id_str: str) -> tuple[str, str] | None:
    marker = "::persona:"
    if marker not in variant_id_str:
        return None
    chapter_id, persona_id = variant_id_str.split(marker, 1)
    if not chapter_id or not persona_id:
        return None
    return chapter_id, persona_id
