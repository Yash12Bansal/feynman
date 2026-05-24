"""Doubt classifier (Phase 3 stub).

Phase 3 returns `local_clarification` for every doubt so the rest of the
pipeline can be plumbed end-to-end. Phase 4 replaces the body with a Claude
tool-use call that returns a real classification based on the doubt text,
the current topic, and the chapter context.

The signature and return type are chosen now so Phase 4's swap is a body-
only change — callers (worker + downstream planner) won't need to change.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DoubtType(StrEnum):
    """The three doubt categories Feynman distinguishes.

    - `local_clarification`: a small clarification about what was just said.
    - `interconnected`: links an earlier-taught topic to the current one.
    - `new_angle`: a genuinely new question about the current topic.
    """

    LOCAL_CLARIFICATION = "local_clarification"
    INTERCONNECTED = "interconnected"
    NEW_ANGLE = "new_angle"


class DoubtClassification(BaseModel):
    """Result of classifying a single doubt."""

    type: DoubtType
    related_concept_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


async def classify_doubt(
    *,
    doubt_text: str,
    current_topic_id: str | None = None,
    current_topic_context_snippet: str = "",
    prior_doubts_in_session: list[str] | None = None,
) -> DoubtClassification:
    """Classify a doubt into one of the three types.

    Phase 3 stub: always returns `local_clarification`. The argument
    surface is the one Phase 4 will need so callers don't have to change.
    """
    _ = (doubt_text, current_topic_id, current_topic_context_snippet, prior_doubts_in_session)
    return DoubtClassification(
        type=DoubtType.LOCAL_CLARIFICATION,
        rationale="Phase 3 stub — always local_clarification.",
    )
