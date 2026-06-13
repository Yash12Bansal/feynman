"""Models for the per-student knowledge (memory) layer.

This graph is INDEPENDENT of the shared curriculum graph. It links to
curriculum only by id strings (`chapter_id`, `topic_id`, `question_id`).
Each memory denormalises the small bit of text the memory card needs
(`q_text`, `doubt_text`, `response`) so the card is a pure student-graph
query with no runtime join back to curriculum.

Timestamps are epoch milliseconds, supplied by the caller — the store
holds no clock, which keeps it deterministic under test.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AttemptMemory(BaseModel):
    """One question the student attempted during a lecture checkpoint."""

    question_id: str
    topic_id: str
    chapter_id: str = ""  # denormalised from the session → labels the global card
    q_text: str
    options: list[str] = Field(default_factory=list)  # collapsible on the card
    solution: str = ""  # the correct answer (an MCQ letter)
    explanation: str = ""  # why it's correct — collapsible on the card
    correct: bool
    mode: Literal["mcq", "subjective"]
    created_at: int  # epoch ms


class DoubtMemory(BaseModel):
    """One doubt the student raised mid-lecture, with the answer they got."""

    topic_id: str
    chapter_id: str = ""  # denormalised from the session → labels the global card
    doubt_text: str
    response: str
    created_at: int  # epoch ms


class MemoryCard(BaseModel):
    """What to surface as a revision card: the questions the student got wrong
    and the doubts they raised.

    Used for all three surfaces — the per-chapter auto-pop (last N study-days),
    the full-chapter "weakness" view (all study-days), and the user-level global
    card (every chapter). For the global card `chapter_id` is "" and each item
    carries its own `chapter_id`.
    """

    student_id: str
    chapter_id: str = ""
    incorrect_attempts: list[AttemptMemory] = Field(default_factory=list)
    doubts: list[DoubtMemory] = Field(default_factory=list)
    sessions_covered: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.incorrect_attempts and not self.doubts
