"""LessonPlanner — per-topic LessonPlan generation (doc 19 Phase C).

Async because Anthropic's AsyncAnthropic client is async. Sits ALONGSIDE
ConceptPlanner — does not replace it. Phase H is where the flip happens; until
then, both planners can run and the pipeline consumes whichever is wired in.

Tool-use pattern (mirrors `plan_concept` in the kernel):
- Tool input_schema = `LessonPlan.model_json_schema()` — the API enforces the
  shape of the LLM's output.
- Pydantic `model_validate()` enforces the cross-field validators
  (forbidden openers, crucial-fact press-twice, Q→P pairs, declared-before-
  used element_ids).
- ValidationError on first attempt → second attempt is told what failed so it
  can self-correct.
- Second failure → log + return None. Downstream tolerates missing plans.
"""

from __future__ import annotations

from typing import Any

import structlog
from feynman_teaching_kernel.persona import TeacherPersona, format_style_for_planner
from pydantic import ValidationError

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.llm.base import LLMProvider
from lecture_pipeline_v2.llm.factory import create_llm_provider
from lecture_pipeline_v2.curriculum.lecture_plan.curriculum_adapter import (
    CurriculumAdapter,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    LessonPlan,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_prompts import (
    LESSON_PLANNING_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.template_catalog import (
    match_template,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Chapter, Diagram, Topic

logger = structlog.get_logger()

# Tool name the LLM is forced to call (gives us a structured output via the
# tool-use schema rather than free-form JSON in a text block).
_LESSON_TOOL_NAME = "emit_lesson_plan"
_LESSON_TOOL_DESCRIPTION = (
    "Emit the LessonPlan for the requested topic. "
    "All field constraints listed in the system prompt are enforced by "
    "Pydantic and will cause a retry if violated."
)

# Per-call Anthropic limits.
_MAX_TOKENS = 8192
_MAX_ATTEMPTS = 2


class LessonPlanner:
    """Plans every topic via Anthropic tool-use against the LessonPlan schema."""

    def __init__(
        self,
        config: PipelineConfig,
        *,
        provider: LLMProvider | None = None,
        persona: TeacherPersona | None = None,
        style_context: str | None = None,
    ) -> None:
        self.config = config
        self._provider = provider or create_llm_provider(config.llm)
        self._persona = persona
        # Persona YAML (--persona) or legacy CLI --style-source markdown.
        if persona is not None:
            self._style_context = format_style_for_planner(persona)
        else:
            self._style_context = style_context

    async def plan_for_all(
        self,
        chapters: list[Chapter],
        topics_by_chapter: dict[str, list[Topic]],
        lecture_plans: dict[str, ChapterLecturePlan],
        diagrams_by_topic: dict[str, list[Diagram]],
    ) -> dict[str, list[LessonPlan]]:
        """For each chapter with a ChapterLecturePlan, plan each topic in
        concept_sequence order. Returns chapter_id → list of LessonPlans.

        Topics that fail the planner end up MISSING from the returned list,
        not as None entries — downstream code can `len(plans) ==
        len(concept_sequence)` to detect partial failures.
        """
        result: dict[str, list[LessonPlan]] = {}
        for chapter in chapters:
            lecture_plan = lecture_plans.get(chapter.chapter_id)
            if lecture_plan is None:
                logger.warning(
                    "lesson_planner.no_chapter_plan",
                    chapter_id=chapter.chapter_id,
                )
                continue

            topics = topics_by_chapter.get(chapter.chapter_id, [])
            adapter = CurriculumAdapter(
                chapter, topics, lecture_plan, diagrams_by_topic
            )

            plans: list[LessonPlan] = []
            for idx, topic_id in enumerate(lecture_plan.concept_sequence):
                lp = await self._plan_one_with_retry(
                    idx,
                    adapter,
                    topic_id=topic_id,
                    chapter_id=chapter.chapter_id,
                )
                if lp is not None:
                    plans.append(lp)
            result[chapter.chapter_id] = plans
        return result

    async def plan_one_topic(
        self,
        *,
        concept_index: int,
        curriculum: CurriculumAdapter,
        topic_id: str,
        chapter_id: str,
        prior_quality_feedback: str | None = None,
    ) -> LessonPlan | None:
        """Public single-topic entrypoint. Used by the Phase F quality gate
        to re-plan one topic with judge feedback baked into the user message.

        `prior_quality_feedback` is appended to the prompt under a "QUALITY
        RETRY" section when provided. The internal 2-attempt Pydantic retry
        budget still applies.
        """
        return await self._plan_one_with_retry(
            concept_index,
            curriculum,
            topic_id=topic_id,
            chapter_id=chapter_id,
            prior_quality_feedback=prior_quality_feedback,
        )

    async def _plan_one_with_retry(
        self,
        concept_index: int,
        curriculum: CurriculumAdapter,
        *,
        topic_id: str,
        chapter_id: str,
        prior_quality_feedback: str | None = None,
    ) -> LessonPlan | None:
        """Call Anthropic; on ValidationError, retry once with feedback.

        First attempt: clean prompt, no failure context.
        Second attempt: prompt augmented with the Pydantic error message from
        the first failure so the LLM can self-correct.

        Any non-ValidationError exception (API failure, JSON shape mismatch)
        also triggers a retry but without specific feedback.

        `prior_quality_feedback` (Phase F) is independent of the Pydantic
        retry — it's the judge's notes from a prior attempt at an EARLIER
        plan that was syntactically fine but below the quality bar. It
        sits in EVERY attempt's user message (not just retries).
        """
        last_validation_error: str | None = None

        for attempt in range(_MAX_ATTEMPTS):
            try:
                lp = await self._call_llm(
                    concept_index=concept_index,
                    curriculum=curriculum,
                    topic_id=topic_id,
                    chapter_id=chapter_id,
                    prior_validation_error=last_validation_error,
                    prior_quality_feedback=prior_quality_feedback,
                )
            except ValidationError as exc:
                last_validation_error = str(exc)
                logger.warning(
                    "lesson_planner.validation_error",
                    chapter_id=chapter_id,
                    topic_id=topic_id,
                    concept_index=concept_index,
                    attempt=attempt,
                    error=last_validation_error,
                )
                lp = None
            except Exception as exc:  # noqa: BLE001 — defensive at boundary
                logger.warning(
                    "lesson_planner.unexpected_exception",
                    chapter_id=chapter_id,
                    topic_id=topic_id,
                    concept_index=concept_index,
                    attempt=attempt,
                    error=str(exc),
                )
                lp = None

            if lp is not None:
                if attempt > 0:
                    logger.info(
                        "lesson_planner.recovered_on_retry",
                        chapter_id=chapter_id,
                        topic_id=topic_id,
                        concept_index=concept_index,
                    )
                return lp

        logger.error(
            "lesson_planner.final_failure",
            chapter_id=chapter_id,
            topic_id=topic_id,
            concept_index=concept_index,
        )
        return None

    async def _call_llm(
        self,
        *,
        concept_index: int,
        curriculum: CurriculumAdapter,
        topic_id: str,
        chapter_id: str,
        prior_validation_error: str | None,
        prior_quality_feedback: str | None = None,
    ) -> LessonPlan | None:
        """One LLM round-trip via the configured provider's tool-use surface.

        Returns the validated LessonPlan, or None if the model emitted no tool
        call. Raises ValidationError when Pydantic rejects the tool input —
        the caller catches it for the retry-with-feedback loop.
        """
        user_message = _build_user_message(
            concept_index=concept_index,
            curriculum=curriculum,
            topic_id=topic_id,
            prior_validation_error=prior_validation_error,
            prior_quality_feedback=prior_quality_feedback,
            style_context=self._style_context,
        )

        payload = await self._provider.agenerate_tool_use(
            LESSON_PLANNING_SYSTEM_PROMPT,
            user_message,
            tool_name=_LESSON_TOOL_NAME,
            tool_description=_LESSON_TOOL_DESCRIPTION,
            input_schema=LessonPlan.model_json_schema(),
            max_tokens=_MAX_TOKENS,
        )

        if not isinstance(payload, dict):
            logger.warning(
                "lesson_planner.no_tool_use_block",
                chapter_id=chapter_id,
                topic_id=topic_id,
                concept_index=concept_index,
            )
            return None
        # Pin topic_id so the LLM cannot rename it; the LessonPlan MUST be
        # keyed against the curriculum topic, not whatever the LLM invented.
        payload = {**payload, "topic_id": topic_id}
        # Raises ValidationError if any validator fails; caller handles retry.
        return LessonPlan.model_validate(payload)


def _build_user_message(
    *,
    concept_index: int,
    curriculum: CurriculumAdapter,
    topic_id: str,
    prior_validation_error: str | None,
    prior_quality_feedback: str | None = None,
    style_context: str | None = None,
) -> str:
    """Compose the topic-specific user message.

    Includes the topic name, its position in the chapter sequence, summaries
    of the surrounding topics, prerequisite hints from the curriculum graph,
    and (on retry) the Pydantic error message from the previous attempt so
    the LLM knows what to fix.
    """
    teaching_order = curriculum.get_teaching_order()
    concept_level = [c for c in teaching_order if c.level == 0]
    concept = _find_concept(concept_level, topic_id)

    parts: list[str] = []

    # Run-scoped style directive (CLI --style-source). Placed FIRST so it frames
    # the whole lesson — the voice, the order of ideas, and which figures to
    # declare as diagrams. None for ordinary runs (back-compat: no-op).
    if style_context:
        parts.append("## Master-teacher style & source for THIS lesson")
        parts.append(
            "Channel the master teacher described below: adopt the VOICE, the "
            "order of ideas, and the analogies, and REPRODUCE the key figures "
            "named (declare them as DiagramRequirements with stable element_ids "
            "the choreography points at). Keep the existing audience level and "
            "every system-prompt rule. Emulate the spirit — never copy sentences "
            "verbatim."
        )
        parts.append("")
        parts.append(_clip(style_context, 6000))
        parts.append("")

    if concept is None:
        parts.append(f"# Topic to plan (concept_index={concept_index})")
        parts.append(f"topic_id: {topic_id}")
        parts.append(
            "(No CurriculumAdapter concept found for this topic_id; plan "
            "from the topic_id alone as best you can.)"
        )
    else:
        parts.append(f"# Topic to plan (concept_index={concept_index})")
        parts.append(f"topic_id: {topic_id}")
        parts.append(f"name: {concept.topic_name}")
        if getattr(concept, "summary", None):
            parts.append("")
            parts.append("## Our textbook-derived understanding")
            parts.append(_clip(str(concept.summary), 800))
        if getattr(concept, "source_text", None):
            parts.append("")
            parts.append("## Raw source text (textbook excerpt)")
            parts.append(_clip(str(concept.source_text), 1500))
        if getattr(concept, "visual_hint", None):
            parts.append("")
            parts.append("## Visual hint (from the curriculum graph)")
            parts.append(str(concept.visual_hint))

        # Canonical-template hint: if the topic name/summary keyword-matches a
        # hand-built figure, surface it so the planner prefers the instant
        # template. Advisory only — the planner still decides whether the figure
        # genuinely IS that template, and authors required_elements against the
        # template's real ids (see the prompt's "Available canonical templates").
        template_hint = match_template(
            topic=str(getattr(concept, "topic_name", "") or ""),
            purpose=str(getattr(concept, "summary", "") or ""),
        )
        if template_hint is not None:
            parts.append("")
            parts.append("## Canonical figure hint")
            parts.append(
                f"This topic resembles the `{template_hint}` canonical template. "
                f"If the diagram you need genuinely IS that figure, template it "
                f"(set template_concept_id to {template_hint!r} and declare "
                f"required_elements with that template's element ids). If it only "
                f"superficially matches, ignore this hint."
            )

        # NOTE: book_examples are NOT injected here anymore. The
        # BookExampleWeaver (separate stage, after this planner) owns
        # the book-coverage USP. Your job is concept teaching only — the
        # weaver inserts faithful example beats into the choreography
        # afterwards. See lesson_prompts.LESSON_PLANNING_SYSTEM_PROMPT
        # "Your scope" section for the contract.

    # Surrounding topics for narrative continuity.
    prev_title = ""
    next_title = ""
    for i, c in enumerate(concept_level):
        if getattr(c, "uid", None) == topic_id:
            if i > 0:
                prev_title = concept_level[i - 1].topic_name
            if i + 1 < len(concept_level):
                next_title = concept_level[i + 1].topic_name
            break
    if prev_title or next_title:
        parts.append("")
        parts.append("## Surrounding topics")
        if prev_title:
            parts.append(f"Previous topic: {prev_title}")
        if next_title:
            parts.append(f"Next topic: {next_title}")

    # Prerequisites — what the student already knows.
    if concept is not None:
        try:
            prereqs = curriculum.get_prerequisites(getattr(concept, "uid", ""))
        except Exception:  # noqa: BLE001 — adapter shape variance
            prereqs = []
        if prereqs:
            parts.append("")
            parts.append("## Prerequisites the student already knows")
            for p in prereqs[:6]:
                parts.append(f"- {getattr(p, 'topic_name', '?')}")

    # Retry feedback — let the LLM see what failed last time.
    if prior_validation_error:
        parts.append("")
        parts.append("## RETRY — your previous LessonPlan failed validation")
        parts.append(
            "Read the Pydantic error below carefully and fix EXACTLY what it "
            "describes. Do not change anything else."
        )
        parts.append("")
        parts.append("```")
        parts.append(_clip(prior_validation_error, 2000))
        parts.append("```")

    # Phase F — quality-gate retry feedback from the judge.
    if prior_quality_feedback:
        parts.append("")
        parts.append(
            "## QUALITY RETRY — judge said the previous plan was below the bar"
        )
        parts.append(
            "A prior version of this LessonPlan passed Pydantic validation "
            "but scored below the quality threshold. The judge's specific "
            "suggestion is below. Address it directly; keep everything else "
            "that was working."
        )
        parts.append("")
        parts.append("```")
        parts.append(_clip(prior_quality_feedback, 2000))
        parts.append("```")

    return "\n".join(parts)


def _find_concept(concept_level: list[Any], topic_id: str) -> Any:
    """Locate the concept whose `uid` matches the given topic_id."""
    for c in concept_level:
        if getattr(c, "uid", None) == topic_id:
            return c
    return None


def _clip(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "…"
    return text
