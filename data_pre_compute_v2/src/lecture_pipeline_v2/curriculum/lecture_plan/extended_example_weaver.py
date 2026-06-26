"""ExtendedExampleWeaver — generates real-world anchors + fun facts and weaves
them into the lecture so it feels like a great teacher's, not just a correct
one.

Runs AFTER BookExampleWeaver. For each topic, `Topic.n_extended_examples()`
decides how many extras to add (the product rule locked 2026-05-27). Unlike
the book weaver, the examples don't exist yet — this stage GENERATES them in
one LLM call per topic, renders each into a short ChoreographyStep block,
tags the steps `is_extended_example=True` + `extended_example_ref=i`, and
persists the generated `ExtendedExample` metadata back onto the topic for
inspectability.

Mirrors BookExampleWeaver's safety properties:
  * Idempotent — strips prior is_extended_example steps before re-weaving.
  * Sanitized — every generated step's diagram-side fields are forced to safe
    defaults so the post-merge LessonPlan validator never rejects the merge
    (extended examples live on the notebook via inline markers, not the slide).
  * Retry-with-feedback on validation failure (initial + 1 retry).

Cost: ~1 Sonnet call per topic that qualifies for extras (0-3 examples each).
Topics with n_extended_examples()==0 are skipped entirely — no call.
"""

from __future__ import annotations

import logging

import structlog
from feynman_teaching_kernel.persona import TeacherPersona
from pydantic import BaseModel, Field, ValidationError

from ...config import PipelineConfig
from ...llm.base import LLMProvider
from ...llm.factory import create_llm_provider
from ..models import ExtendedExample, Topic
from .extended_example_prompts import (
    EXTENDED_EXAMPLE_WEAVER_SYSTEM_PROMPT,
    build_extended_example_user_prompt,
)
from .lesson_plan_models import ChoreographyStep, LessonPlan

logger = structlog.get_logger(__name__)

_TOOL_NAME = "emit_extended_examples"
_TOOL_DESCRIPTION = (
    "Emit the real-world anchors + fun facts for ONE topic, each rendered as "
    "1-3 narration-only ChoreographyStep entries. Produce EXACTLY the requested "
    "count."
)
_MAX_TOKENS = 4096
_MAX_ATTEMPTS_PER_TOPIC = 2  # initial + 1 retry with feedback


class _WovenExample(BaseModel):
    """One generated extended example + its rendered choreography."""

    kind: str = Field(pattern="^(real_world|fun_fact)$")
    hook_text: str = Field(min_length=1)
    concept_tie: str = Field(min_length=1)
    steps: list[ChoreographyStep] = Field(min_length=1, max_length=3)


class _WeaverOutput(BaseModel):
    """Tool output shape — a list wrapped in an object so the schema is a
    JSON object, not a bare array."""

    examples: list[_WovenExample] = Field(min_length=1, max_length=3)


class ExtendedWeaverReport(BaseModel):
    """Per-chapter telemetry."""

    topics_seen: int = 0
    topics_eligible: int = 0  # n_extended_examples() > 0
    topics_woven: int = 0
    examples_generated: int = 0
    retries_used: int = 0
    permanent_failures: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        return (
            f"ExtendedExampleWeaver — {self.examples_generated} examples across "
            f"{self.topics_woven}/{self.topics_eligible} eligible topics "
            f"(seen={self.topics_seen}); retries={self.retries_used}; "
            f"permanent_failures={len(self.permanent_failures)}"
        )


class ExtendedExampleWeaver:
    """Per-topic generate + weave + structural retry loop."""

    def __init__(
        self,
        config: PipelineConfig,
        *,
        provider: LLMProvider | None = None,
        persona: TeacherPersona | None = None,
    ) -> None:
        self.config = config
        self._provider = provider or create_llm_provider(config.llm)
        self._persona = persona

    async def weave_for_chapter(
        self,
        chapter_lesson_plans: dict[str, LessonPlan],
        topics_by_id: dict[str, Topic],
    ) -> ExtendedWeaverReport:
        """Walk every topic's LessonPlan; generate + weave extended examples
        in place. `chapter_lesson_plans` and the topics in `topics_by_id` are
        both updated in place (plan choreography + topic.extended_examples).
        """
        report = ExtendedWeaverReport()
        for topic_id, plan in chapter_lesson_plans.items():
            report.topics_seen += 1
            topic = topics_by_id.get(topic_id)
            if topic is None:
                continue
            n = topic.n_extended_examples()
            if n <= 0:
                continue
            report.topics_eligible += 1
            new_plan = await self.weave_for_topic(
                lesson_plan=plan,
                topic=topic,
                n_examples=n,
                report=report,
            )
            chapter_lesson_plans[topic_id] = new_plan
        logger.info("extended_example_weaver.summary", summary=report.summary())
        return report

    async def weave_for_topic(
        self,
        *,
        lesson_plan: LessonPlan,
        topic: Topic,
        n_examples: int,
        report: ExtendedWeaverReport,
    ) -> LessonPlan:
        """Generate `n_examples` extended examples, render + weave them into
        the lesson plan, persist metadata on the topic, return the new plan.

        Idempotent: existing is_extended_example=True steps are stripped before
        re-weaving, and topic.extended_examples is reset, so a re-run doesn't
        duplicate. Concept and book-example steps are untouched.
        """
        # Strip prior extended-example steps so a re-run doesn't append a
        # second copy. Book-example + concept steps are preserved.
        original_count = len(lesson_plan.choreography)
        stripped = [s for s in lesson_plan.choreography if not s.is_extended_example]
        if len(stripped) < original_count:
            logger.info(
                "extended_example_weaver.stripped_existing",
                topic_id=topic.topic_id,
                removed=original_count - len(stripped),
            )
            data = lesson_plan.model_dump()
            data["choreography"] = [s.model_dump() for s in stripped]
            try:
                lesson_plan = LessonPlan.model_validate(data)
            except ValidationError as exc:
                logger.warning(
                    "extended_example_weaver.strip_validation_failed",
                    topic_id=topic.topic_id,
                    error=str(exc)[:200],
                )
                return lesson_plan
        # Reset persisted metadata for idempotency.
        topic.extended_examples = []

        woven = await self._weave_with_retry(
            topic=topic, n_examples=n_examples, report=report
        )
        if not woven:
            report.permanent_failures.append(topic.topic_id)
            return lesson_plan

        flat_new_steps: list[ChoreographyStep] = []
        for ref_idx, ex in enumerate(woven):
            for s in ex.steps:
                s.is_extended_example = True
                s.extended_example_ref = ref_idx
            flat_new_steps.extend(ex.steps)
            topic.extended_examples.append(
                ExtendedExample(
                    kind=ex.kind,
                    hook_text=ex.hook_text,
                    concept_tie=ex.concept_tie,
                )
            )

        insertion_idx = _trailing_insertion_index(lesson_plan.choreography)
        merged = (
            lesson_plan.choreography[:insertion_idx]
            + flat_new_steps
            + lesson_plan.choreography[insertion_idx:]
        )
        data = lesson_plan.model_dump()
        data["choreography"] = [s.model_dump() for s in merged]
        try:
            new_plan = LessonPlan.model_validate(data)
        except ValidationError as exc:
            logger.warning(
                "extended_example_weaver.post_merge_validation_failed",
                topic_id=topic.topic_id,
                error=str(exc)[:400],
            )
            report.permanent_failures.append(f"{topic.topic_id}::post_merge")
            topic.extended_examples = []  # roll back persisted metadata
            return lesson_plan

        report.topics_woven += 1
        report.examples_generated += len(woven)
        return new_plan

    async def _weave_with_retry(
        self,
        *,
        topic: Topic,
        n_examples: int,
        report: ExtendedWeaverReport,
    ) -> list[_WovenExample] | None:
        last_error = ""
        for attempt in range(_MAX_ATTEMPTS_PER_TOPIC):
            user_msg = build_extended_example_user_prompt(
                topic_id=topic.topic_id,
                topic_name=topic.topic_name,
                section_number=topic.section_number,
                our_understanding=topic.our_understanding,
                n_examples=n_examples,
                prior_attempt_feedback=last_error if attempt > 0 else "",
                persona=self._persona,
            )
            try:
                examples = await self._call_llm(user_msg)
            except ValidationError as exc:
                last_error = (
                    f"Pydantic rejected your output: {exc}. Each example needs "
                    f"kind in (real_world|fun_fact), non-empty hook_text + "
                    f"concept_tie, and 1-3 steps with non-empty narration. "
                    f"Produce exactly {n_examples} example(s)."
                )
                report.retries_used += 1
                logger.warning(
                    "extended_example_weaver.validation_error",
                    topic_id=topic.topic_id,
                    attempt=attempt,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = f"Unexpected error: {exc}. Try again."
                report.retries_used += 1
                logger.warning(
                    "extended_example_weaver.unexpected_exception",
                    topic_id=topic.topic_id,
                    attempt=attempt,
                    error=str(exc)[:200],
                )
                continue

            if not examples:
                last_error = "Your response had no usable examples. Try again."
                report.retries_used += 1
                continue

            # Defense-in-depth: extended examples are notebook-only. Force
            # every step's diagram-side + pedagogy flags to safe defaults so
            # the post-merge LessonPlan validator never rejects the merge.
            for ex in examples:
                for s in ex.steps:
                    s.actions = []
                    s.target_element_id = None
                    s.target_diagram_id = None
                    s.is_question = False
                    s.is_payoff = False
                    s.presses_crucial_fact = False

            if attempt > 0:
                logger.info(
                    "extended_example_weaver.recovered_on_retry",
                    topic_id=topic.topic_id,
                )
            return examples

        logger.error(
            "extended_example_weaver.permanent_failure",
            topic_id=topic.topic_id,
            last_error=last_error[:200],
        )
        return None

    async def _call_llm(self, user_msg: str) -> list[_WovenExample] | None:
        payload = await self._provider.agenerate_tool_use(
            EXTENDED_EXAMPLE_WEAVER_SYSTEM_PROMPT,
            user_msg,
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=_WeaverOutput.model_json_schema(),
            max_tokens=_MAX_TOKENS,
        )
        if not isinstance(payload, dict):
            return None
        parsed = _WeaverOutput.model_validate(payload)
        return parsed.examples


def _trailing_insertion_index(choreography: list[ChoreographyStep]) -> int:
    """Index BEFORE the lesson's wrap-up, so extended examples land after the
    concept (and any book examples) but before the summary close. Mirrors the
    book weaver's heuristic.
    """
    for i, step in enumerate(choreography):
        nar = (step.narration or "").lower().strip()
        if any(
            nar.startswith(prefix)
            for prefix in (
                "to summarise",
                "to summarize",
                "putting it together",
                "stepping back",
                "let me wrap",
                "so the takeaway",
                "the takeaway",
                "the bottom line",
            )
        ):
            return i
    return max(0, len(choreography) - 2)


# std logging handle for callers that prefer it
_std_logger = logging.getLogger(__name__)
