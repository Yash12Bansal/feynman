"""Doubt classifier — Phase 4 real Anthropic tool-use call.

Phase 3 was a stub that always returned `local_clarification`. This
replacement keeps the exact same signature so callers don't have to
change, but routes through a Claude Sonnet tool-use call that returns a
real classification.

Retry pattern mirrors `data_pre_compute_v2/.../lesson_planner.py`:
two attempts max, attempt 2 includes the prior ValidationError so the
LLM can self-correct. On final failure we fall back to
`local_clarification` so the downstream planner can still proceed.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING

import anthropic
import structlog
from pydantic import BaseModel, Field, ValidationError

from feynman.agent.doubt_resolution.prompts import CLASSIFIER_SYSTEM
from feynman.config import settings

if TYPE_CHECKING:
    from feynman.agent.doubt_resolution.models import ChapterContext

logger = structlog.get_logger()

_MODEL = "claude-sonnet-4-20250514"
_TOOL_NAME = "emit_classification"
_TOOL_DESCRIPTION = "Emit the DoubtClassification for the supplied student doubt."
_MAX_TOKENS = 1024
_MAX_ATTEMPTS = 2


class DoubtType(StrEnum):
    """The three doubt categories Feynman distinguishes."""

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
    chapter_context: ChapterContext | None = None,
) -> DoubtClassification:
    """Classify a doubt into one of `DoubtType`.

    Falls back to `LOCAL_CLARIFICATION` if both retries fail — the planner
    can still produce a reasonable resolution under that assumption.
    """
    text = (doubt_text or "").strip()
    if not text:
        return DoubtClassification(
            type=DoubtType.LOCAL_CLARIFICATION,
            rationale="empty doubt text — defaulted",
        )

    last_error: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = await _call_once(
                doubt_text=text,
                current_topic_id=current_topic_id,
                current_topic_context_snippet=current_topic_context_snippet,
                prior_doubts_in_session=prior_doubts_in_session or [],
                chapter_context=chapter_context,
                prior_validation_error=last_error,
            )
        except ValidationError as exc:
            last_error = str(exc)
            logger.warning(
                "doubt_classifier.validation_error",
                attempt=attempt,
                error=last_error,
            )
            result = None
        except Exception as exc:
            logger.warning(
                "doubt_classifier.unexpected_exception",
                attempt=attempt,
                error=str(exc),
            )
            result = None

        if result is not None:
            if attempt > 0:
                logger.info("doubt_classifier.recovered_on_retry")
            return result

    logger.error("doubt_classifier.final_failure", last_error=last_error)
    return DoubtClassification(
        type=DoubtType.LOCAL_CLARIFICATION,
        rationale=f"classifier_failed: {last_error or 'unknown'}",
    )


async def _call_once(
    *,
    doubt_text: str,
    current_topic_id: str | None,
    current_topic_context_snippet: str,
    prior_doubts_in_session: list[str],
    chapter_context: ChapterContext | None,
    prior_validation_error: str | None,
) -> DoubtClassification | None:
    user_message = _build_user_message(
        doubt_text=doubt_text,
        current_topic_id=current_topic_id,
        current_topic_context_snippet=current_topic_context_snippet,
        prior_doubts_in_session=prior_doubts_in_session,
        chapter_context=chapter_context,
        prior_validation_error=prior_validation_error,
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "")
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=CLASSIFIER_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        tools=[
            {
                "name": _TOOL_NAME,
                "description": _TOOL_DESCRIPTION,
                "input_schema": DoubtClassification.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
    )

    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == _TOOL_NAME
        ):
            payload = block.input
            if not isinstance(payload, dict):
                logger.warning("doubt_classifier.tool_input_not_dict")
                return None
            return DoubtClassification.model_validate(payload)

    logger.warning("doubt_classifier.no_tool_use_block")
    return None


def _build_user_message(
    *,
    doubt_text: str,
    current_topic_id: str | None,
    current_topic_context_snippet: str,
    prior_doubts_in_session: list[str],
    chapter_context: ChapterContext | None,
    prior_validation_error: str | None,
) -> str:
    parts: list[str] = []
    if prior_validation_error:
        parts.append(
            "Your previous response failed validation:\n"
            f"  {prior_validation_error}\n"
            "Fix the offending field and emit a valid tool call."
        )

    parts.append(f"STUDENT DOUBT:\n{doubt_text}\n")

    if current_topic_id:
        parts.append(f"CURRENT_TOPIC_ID: {current_topic_id}")
    if current_topic_context_snippet:
        parts.append(f"WHAT FEYNMAN WAS JUST SAYING:\n{current_topic_context_snippet}")

    if chapter_context:
        topic_lines = [
            f"- {t.topic_id} ({t.section_number}): {t.topic_name}"
            for t in chapter_context.topics.values()
        ]
        if topic_lines:
            parts.append("CHAPTER TOPICS (for related_concept_ids):\n" + "\n".join(topic_lines))

    if prior_doubts_in_session:
        parts.append(
            "PRIOR DOUBTS THIS SESSION:\n" + "\n".join(f"- {d}" for d in prior_doubts_in_session)
        )

    parts.append(
        "Emit the classification via the `emit_classification` tool. "
        "JSON example: "
        + json.dumps(
            {
                "type": "local_clarification",
                "related_concept_ids": [],
                "rationale": "one-sentence reason",
            }
        )
    )
    return "\n\n".join(parts)
