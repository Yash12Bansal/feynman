"""NarrationJudge — Phase 2 LLM rubric over topic narration."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.models import Topic
from lecture_pipeline_v2.llm.base import LLMProvider
from lecture_pipeline_v2.llm.factory import create_llm_provider

logger = logging.getLogger(__name__)

_SYSTEM = """You score AI-generated classroom narration for a single topic.

Return scores 0–100 via the tool:
- domain_fit_score: sounds native to the subject (finance lesson sounds like finance, not physics)
- analogy_leakage_score: 0 = no wrong-domain metaphors; 100 = heavy physics/relativity/etc. on non-physics topics
- clarity_score: a sharp 13–15 year old would follow easily
- engagement_score: would students stay curious through the excerpt
- factual_grounding_score: claims traceable to the source excerpt (no invented numbers/facts)

Be strict on analogy_leakage for cross-domain teaching (e.g. Feynman voice on finance).
issue: one concrete sentence if any score < 60, else empty string."""

_TOOL = "emit_narration_judgement"


class NarrationJudgement(BaseModel):
    domain_fit_score: int = Field(ge=0, le=100)
    analogy_leakage_score: int = Field(ge=0, le=100)
    clarity_score: int = Field(ge=0, le=100)
    engagement_score: int = Field(ge=0, le=100)
    factual_grounding_score: int = Field(ge=0, le=100)
    issue: str = ""

    @classmethod
    def skipped(cls, reason: str) -> NarrationJudgement:
        return cls(issue=reason)


class NarrationJudge:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider(config.llm)

    async def judge_topic(
        self,
        *,
        subject: str,
        topic: Topic,
        narration_excerpt: str,
        persona_id: str | None = None,
    ) -> NarrationJudgement:
        if not narration_excerpt.strip():
            return NarrationJudgement.skipped("empty_narration")

        user = (
            f"Subject: {subject}\n"
            f"Persona: {persona_id or 'default'}\n"
            f"Topic: {topic.topic_name} ({topic.section_number})\n\n"
            f"## Source (textbook)\n{topic.orig_book_content[:3000]}\n\n"
            f"## Narration excerpt\n{narration_excerpt[:4000]}\n\n"
            "Score the narration excerpt."
        )
        try:
            payload = await self._provider.agenerate_tool_use(
                _SYSTEM,
                user,
                tool_name=_TOOL,
                tool_description="Emit narration quality scores.",
                input_schema=NarrationJudgement.model_json_schema(),
                max_tokens=1024,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("narration_judge.api_error topic=%s err=%s", topic.topic_id, exc)
            return NarrationJudgement.skipped(f"api_error: {exc}")

        if not isinstance(payload, dict):
            return NarrationJudgement.skipped("no_tool_payload")
        try:
            return NarrationJudgement.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            return NarrationJudgement.skipped(f"parse_error: {exc}")
