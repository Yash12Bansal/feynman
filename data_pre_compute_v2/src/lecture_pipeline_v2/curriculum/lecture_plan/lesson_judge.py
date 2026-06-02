"""PlanJudge — doc 19 Phase F. LLM-as-judge over a LessonPlan.

Asks: would the greatest teacher on this planet be proud to put their name
on this lesson? Returns a 1–5 score + concrete issue + suggestion the
orchestrator uses for regen feedback.

Graceful-degradation philosophy mirrors `DiagramQA` (`enrichment/diagram_qa.py`):
on ANY failure (API error, empty response, malformed tool input) the judge
returns `PlanJudgement.skipped()` — score=3, passed=True. We never block the
pipeline on judge infrastructure drift. A lesson that the judge couldn't
score gets through; humans can review later via `needs_review`.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, Field, model_validator

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.llm.base import LLMProvider
from lecture_pipeline_v2.llm.factory import create_llm_provider
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge_prompts import (
    LESSON_JUDGE_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import LessonPlan

logger = structlog.get_logger()


_TOOL_NAME = "emit_plan_judgement"
_TOOL_DESCRIPTION = (
    "Emit your PlanJudgement for this LessonPlan. Score 1-5; passed iff "
    "score >= the threshold described in the system prompt. issue and "
    "suggestion are mandatory."
)
_MAX_TOKENS = 1024
_DEFAULT_MIN_SCORE = 3


# ─────────────────────────────────────────────────────────────────────────────
# Output model
# ─────────────────────────────────────────────────────────────────────────────


class PlanJudgement(BaseModel):
    """One judge result. Mirrors `QAResult` shape from DiagramQA for symmetry
    with the orchestrator's per-diagram + per-plan judgement history.
    """

    passed: bool
    score: int = Field(ge=1, le=5)
    issue: str
    suggestion: str

    @model_validator(mode="after")
    def passed_consistent_with_score(self) -> PlanJudgement:
        # We don't reject — the LLM may have a slightly different threshold
        # than ours — but we log if it's wildly off so we can spot prompt
        # drift in telemetry.
        if self.passed and self.score < _DEFAULT_MIN_SCORE:
            logger.warning(
                "plan_judge.passed_with_low_score",
                score=self.score,
                threshold=_DEFAULT_MIN_SCORE,
            )
        return self

    @classmethod
    def skipped(cls, reason: str) -> PlanJudgement:
        """Graceful pass-through when the judge couldn't score. Pipeline
        consumers should NOT regen on a skipped() result."""
        return cls(
            passed=True,
            score=_DEFAULT_MIN_SCORE,
            issue=reason,
            suggestion="",
        )


# ─────────────────────────────────────────────────────────────────────────────
# PlanJudge
# ─────────────────────────────────────────────────────────────────────────────


class PlanJudge:
    """Async judge. One LLM round-trip (configured provider) per `judge()` call.

    `min_score` is the pass threshold applied DETERMINISTICALLY on our side
    after the LLM emits a score, so config-level threshold tweaks don't
    require re-prompting the LLM with a new rubric.
    """

    def __init__(
        self,
        config: PipelineConfig,
        *,
        provider: LLMProvider | None = None,
        provider_override: str | None = None,
        model_override: str | None = None,
        min_score: int = _DEFAULT_MIN_SCORE,
    ) -> None:
        self.config = config
        self.min_score = max(1, min(5, min_score))
        # The judge follows the main `llm` switch unless an override is set.
        # Pinning a DIFFERENT model/provider than the author is good practice:
        # a model is a poor judge of its own blind spots.
        self._provider = provider or create_llm_provider(
            config.llm.for_override(provider_override, model_override)
        )

    async def judge(
        self,
        plan: LessonPlan,
        *,
        topic_name: str,
    ) -> PlanJudgement:
        """Score the plan against doc 19's quality rubric.

        Never raises. On any error path (API down, malformed response,
        unexpected exception) returns `PlanJudgement.skipped()` so the
        pipeline never blocks on judge infrastructure.
        """
        user_message = _build_user_message(plan, topic_name=topic_name)

        try:
            payload = await self._provider.agenerate_tool_use(
                LESSON_JUDGE_SYSTEM_PROMPT,
                user_message,
                tool_name=_TOOL_NAME,
                tool_description=_TOOL_DESCRIPTION,
                input_schema=PlanJudgement.model_json_schema(),
                max_tokens=_MAX_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001 — judge must never bubble
            logger.warning(
                "lesson_judge.api_error",
                topic_name=topic_name,
                error=str(exc),
            )
            return PlanJudgement.skipped(f"api_error: {exc}")

        return self._build_judgement(payload, topic_name=topic_name)

    def _build_judgement(
        self, payload: dict[str, Any] | None, *, topic_name: str
    ) -> PlanJudgement:
        """Validate the tool payload into a PlanJudgement.

        Any structural mismatch (no payload, validator failure) returns
        skipped() so the orchestrator passes the plan through with
        `needs_review` set elsewhere.
        """
        if not isinstance(payload, dict):
            logger.warning(
                "lesson_judge.no_tool_use_block",
                topic_name=topic_name,
            )
            return PlanJudgement.skipped("no_tool_use_block")
        try:
            judgement = PlanJudgement.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 — boundary
            logger.warning(
                "lesson_judge.pydantic_error",
                topic_name=topic_name,
                error=str(exc),
            )
            return PlanJudgement.skipped(f"pydantic_error: {exc}")

        # Deterministic threshold override: don't trust the LLM's `passed`
        # if it disagrees with our configured threshold.
        final_passed = judgement.score >= self.min_score
        if final_passed != judgement.passed:
            judgement = judgement.model_copy(update={"passed": final_passed})
        return judgement


# ─────────────────────────────────────────────────────────────────────────────
# User-message composer
# ─────────────────────────────────────────────────────────────────────────────


def _build_user_message(plan: LessonPlan, *, topic_name: str) -> str:
    """Serialize the LessonPlan into the user message the judge reads.

    Includes hook text, crucial_facts, every choreography step narration
    plus its actions and target_element_id (so the LLM can spot
    choreography-narration sync issues), and the DiagramRequirement
    summaries (so the LLM understands what's on the board — without
    requiring the DiagramSpec internals, which DiagramQA handles).
    """
    parts: list[str] = []
    parts.append(f"# Lesson to judge: {topic_name} (topic_id={plan.topic_id})")
    parts.append(f"Title: {plan.title}")

    parts.append("")
    parts.append(f"## Hook ({plan.hook.type.value})")
    parts.append(plan.hook.text)

    parts.append("")
    parts.append("## Crucial facts (each must be pressed in ≥2 choreography steps)")
    for i, fact in enumerate(plan.crucial_facts):
        parts.append(f"- {fact}")

    parts.append("")
    parts.append("## Diagrams declared")
    if not plan.diagrams:
        parts.append("(none)")
    else:
        for d in plan.diagrams:
            parts.append(f"- `{d.diagram_id}` — {d.purpose}")
            for el in d.required_elements:
                parts.append(
                    f"    * {el.element_id} (role={el.role}): {el.description}"
                )

    parts.append("")
    parts.append("## Choreography (the spine)")
    for idx, step in enumerate(plan.choreography):
        flags: list[str] = []
        if step.is_question:
            flags.append("QUESTION")
        if step.is_payoff:
            flags.append("PAYOFF")
        if step.presses_crucial_fact:
            flags.append("PRESSES_CRUCIAL_FACT")
        flag_str = f" [{' | '.join(flags)}]" if flags else ""
        actions_str = (
            ", ".join(a.value for a in step.actions) if step.actions else "(none)"
        )
        target = step.target_element_id or "(no target)"
        parts.append(
            f"{idx}. {step.narration}{flag_str}\n   actions: {actions_str} → {target}"
        )

    if plan.equations:
        parts.append("")
        parts.append("## Equations introduced")
        for eq in plan.equations:
            parts.append(
                f"- after step {eq.introduces_after_step_index}: "
                f'"{eq.explanation_in_words}" → `{eq.latex}`'
            )

    parts.append("")
    parts.append(
        "Now score this lesson 1–5 against the rubric in your system "
        "prompt. Emit ONE PlanJudgement via the tool. Be concrete in "
        "`issue` and `suggestion` — the planner will use `suggestion` "
        "verbatim on the next attempt, so name steps and exact changes."
    )
    return "\n".join(parts)
