"""ResolutionPlanner — Phase 4 LLM call that turns a classified doubt into a
list of `ResolutionBeat`s ready for Phase 5 delivery.

The planner doesn't pick a diagram — `target_diagram_id` stays `None` on
every beat. `DiagramFitMatcher` fills it in a downstream step.
"""

from __future__ import annotations

import json

import anthropic
import structlog
from pydantic import ValidationError

from feynman.agent.doubt_resolution.doubt_classifier import DoubtClassification
from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    DoubtRecord,
    ResolutionPlan,
)
from feynman.agent.doubt_resolution.prompts import PLANNER_SYSTEM
from feynman.config import settings

logger = structlog.get_logger()

_MODEL = "claude-sonnet-4-20250514"
_TOOL_NAME = "emit_resolution_plan"
_TOOL_DESCRIPTION = (
    "Emit the ResolutionPlan as a structured list of beats. "
    "Field constraints (1-6 beats, non-empty narration) are enforced."
)
_MAX_TOKENS = 4096
_MAX_ATTEMPTS = 2


async def plan_resolution(
    *,
    doubt_text: str,
    classification: DoubtClassification,
    chapter_context: ChapterContext,
    current_topic_id: str | None = None,
    prior_doubts: list[DoubtRecord] | None = None,
    different_angle: bool = False,
    prior_resolution_summary: str = "",
) -> ResolutionPlan | None:
    """Plan a doubt resolution as 3-5 beats.

    Returns None on persistent failure — caller (LectureDoubtSession) is
    responsible for the fallback path. Most callers should treat None as
    "skip this doubt with a graceful 'let me think about that' message."
    """
    last_error: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            plan = await _call_once(
                doubt_text=doubt_text,
                classification=classification,
                chapter_context=chapter_context,
                current_topic_id=current_topic_id,
                prior_doubts=prior_doubts or [],
                different_angle=different_angle,
                prior_resolution_summary=prior_resolution_summary,
                prior_validation_error=last_error,
            )
        except ValidationError as exc:
            last_error = str(exc)
            logger.warning(
                "resolution_planner.validation_error",
                attempt=attempt,
                error=last_error,
            )
            plan = None
        except Exception as exc:
            logger.warning(
                "resolution_planner.unexpected_exception",
                attempt=attempt,
                error=str(exc),
            )
            plan = None

        if plan is not None:
            if attempt > 0:
                logger.info("resolution_planner.recovered_on_retry")
            return plan

    logger.error("resolution_planner.final_failure", last_error=last_error)
    return None


async def _call_once(
    *,
    doubt_text: str,
    classification: DoubtClassification,
    chapter_context: ChapterContext,
    current_topic_id: str | None,
    prior_doubts: list[DoubtRecord],
    different_angle: bool,
    prior_resolution_summary: str,
    prior_validation_error: str | None,
) -> ResolutionPlan | None:
    user_message = _build_user_message(
        doubt_text=doubt_text,
        classification=classification,
        chapter_context=chapter_context,
        current_topic_id=current_topic_id,
        prior_doubts=prior_doubts,
        different_angle=different_angle,
        prior_resolution_summary=prior_resolution_summary,
        prior_validation_error=prior_validation_error,
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "")
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=PLANNER_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        tools=[
            {
                "name": _TOOL_NAME,
                "description": _TOOL_DESCRIPTION,
                "input_schema": ResolutionPlan.model_json_schema(),
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
                logger.warning("resolution_planner.tool_input_not_dict")
                return None
            return ResolutionPlan.model_validate(payload)

    logger.warning("resolution_planner.no_tool_use_block")
    return None


def _build_user_message(
    *,
    doubt_text: str,
    classification: DoubtClassification,
    chapter_context: ChapterContext,
    current_topic_id: str | None,
    prior_doubts: list[DoubtRecord],
    different_angle: bool,
    prior_resolution_summary: str,
    prior_validation_error: str | None,
) -> str:
    parts: list[str] = []

    if prior_validation_error:
        parts.append(
            "Your previous response failed validation:\n"
            f"  {prior_validation_error}\n"
            "Fix the offending field and emit a valid tool call."
        )

    parts.append(f"STUDENT DOUBT:\n{doubt_text}")

    parts.append(
        "CLASSIFICATION:\n"
        f"  type: {classification.type.value}\n"
        f"  related_concept_ids: {classification.related_concept_ids}\n"
        f"  rationale: {classification.rationale}"
    )

    current_topic = chapter_context.topic(current_topic_id)
    if current_topic:
        parts.append(
            "CURRENT TOPIC:\n"
            f"  topic_id: {current_topic.topic_id}\n"
            f"  section: {current_topic.section_number}\n"
            f"  name: {current_topic.topic_name}\n"
            f"  summary: {current_topic.summary or '(no summary available)'}"
        )

    adjacent = chapter_context.adjacent_topics(current_topic_id, radius=1)
    if adjacent:
        adj_lines = [
            f"  - {t.section_number} {t.topic_name}: {t.summary or '(no summary)'}"
            for t in adjacent
        ]
        parts.append("ADJACENT TOPICS:\n" + "\n".join(adj_lines))

    if chapter_context.diagrams:
        diagram_lines = []
        for d in list(chapter_context.diagrams.values())[:12]:
            roles = ", ".join(
                sorted(
                    {
                        (entry or {}).get("role", "")
                        for entry in d.dictionary.values()
                        if isinstance(entry, dict)
                    }
                    - {""}
                )
            )
            diagram_lines.append(
                f"  - {d.diagram_id}: {d.description[:160]}"
                + (f" — elements: {roles}" if roles else "")
            )
        parts.append(
            "AVAILABLE DIAGRAMS (the matcher will pick one — describe the "
            "visual intent in plain English):\n" + "\n".join(diagram_lines)
        )

    if prior_doubts:
        prior_lines = [
            f"  - [{r.classification.type.value}] {r.doubt_text}" for r in prior_doubts[-3:]
        ]
        parts.append("PRIOR DOUBTS THIS SESSION:\n" + "\n".join(prior_lines))

    if different_angle:
        parts.append(
            "RE-PLAN: the student was not satisfied with the previous "
            "framing. Pick a different angle, a different analogy, or "
            "attack the concept from the opposite side. Do not repeat:\n"
            f"  {prior_resolution_summary or '(no prior summary captured)'}"
        )

    parts.append(
        "Emit the plan via `emit_resolution_plan`. JSON example shape:\n"
        + json.dumps(
            {
                "beats": [
                    {
                        "narration_text": "Here's what's happening: …",
                        "visual_intent_description": "a side-by-side …",
                        "annotation_actions": [
                            {
                                "action": "focus",
                                "target_role": "trajectory",
                                "text": "look here",
                            }
                        ],
                        "target_diagram_id": None,
                    }
                ]
            },
            indent=2,
        )
    )

    return "\n\n".join(parts)
