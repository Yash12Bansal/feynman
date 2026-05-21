"""Deterministic semantic ID generation for v2 nodes.

IDs are human-readable and stable across pipeline re-runs — the runtime
agent, dashboard state, and per-student knowledge graphs all reference
these UIDs without surprises.

Formats:
    chapter:{subject}:{chapter_slug}
    topic:{subject}:{chapter_slug}:{section_slug}
    diagram:{subject}:{chapter_slug}:{section_slug}:{diagram_slug}
    question:{subject}:{chapter_slug}:{section_slug}:{question_slug}

Section slug uses underscores instead of dots (12.1.1 → 12_1_1) so the
colon-separated UID stays unambiguous.
"""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if len(text) > 80:
        text = text[:80].rsplit("_", 1)[0]
    return text


def section_slug(section_number: str) -> str:
    """Convert a section number like '12.1.1' to '12_1_1' for safe embedding in UIDs."""
    return section_number.replace(".", "_")


def generate_chapter_uid(subject: str, chapter_title: str) -> str:
    return f"chapter:{slugify(subject)}:{slugify(chapter_title)}"


def generate_topic_uid(
    subject: str,
    chapter_title: str,
    section_number: str,
) -> str:
    return (
        f"topic:{slugify(subject)}:{slugify(chapter_title)}:"
        f"{section_slug(section_number)}"
    )


def generate_diagram_uid(topic_uid: str, diagram_name: str) -> str:
    if topic_uid.startswith("topic:"):
        suffix = topic_uid[len("topic:"):]
    else:
        suffix = topic_uid
    return f"diagram:{suffix}:{slugify(diagram_name)}"


def generate_question_uid(topic_uid: str, question_name: str) -> str:
    if topic_uid.startswith("topic:"):
        suffix = topic_uid[len("topic:"):]
    else:
        suffix = topic_uid
    return f"question:{suffix}:{slugify(question_name)}"
