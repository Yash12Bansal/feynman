"""BookExampleWeaver — owns the book-coverage USP at the lecture-plan level.

LessonPlanner produces a concept-only choreography (hook, intuition,
derivation of the formula, summary). The weaver runs AFTER, and for each
Topic.book_examples[i] produces a small sequence of ChoreographyStep
entries that solve that example faithfully. The new steps get inserted
into the existing choreography between the conceptual teaching and the
summary, with `is_book_example=True` and `book_example_ref=i` set on
every weaver-generated step.

A hard structural validator runs after weaving — every book_example MUST
have at least one tagged step. Missing examples trigger a retry-with-
feedback prompt that names the specific example the LLM dropped. After
two retries any persistent gap is logged loudly so the chapter-level
pipeline gate can fail the build.

Cost: ~1 Sonnet call per book_example. On HC Verma physics_and_mathematics
that's ~36 calls per chapter, ~$1 total. Same order as one LessonPlanner
run for the chapter — and unlike LessonPlanner, every call has a single
small concern (one example) so the LLM struggles less.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic
import structlog
from pydantic import BaseModel, Field, ValidationError

from ...config import PipelineConfig
from ..models import BookExample, Diagram, Topic
from .book_example_prompts import (
    BOOK_EXAMPLE_WEAVER_SYSTEM_PROMPT,
    build_book_example_user_prompt,
)
from .lesson_plan_models import ChoreographyStep, LessonPlan

logger = structlog.get_logger(__name__)

_TOOL_NAME = "emit_book_example_choreography"
_TOOL_DESCRIPTION = (
    "Emit the ChoreographyStep list for ONE book example. 3-6 steps. "
    "Faithful to setup_facts. Final step holds the answer."
)
_MAX_TOKENS = 4096
_MAX_ATTEMPTS_PER_EXAMPLE = 2  # initial + 1 retry with feedback


# Terminal beat types — insertion point sits BEFORE the first of these.
_TRAILING_TYPES_HINT = frozenset({"summarize", "transition"})


class _WeaverOutput(BaseModel):
    """The tool's expected output shape. Wrapper around list[ChoreographyStep]
    so Anthropic's `input_schema` lands as a JSON object, not a bare array."""

    steps: list[ChoreographyStep] = Field(min_length=3, max_length=6)


class WeaverReport(BaseModel):
    """Per-chapter telemetry — coverage stats + failures."""

    topics_processed: int = 0
    book_examples_total: int = 0
    book_examples_woven: int = 0
    retries_used: int = 0
    permanent_failures: list[str] = Field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.book_examples_total == 0:
            return 1.0
        return self.book_examples_woven / self.book_examples_total

    def summary(self) -> str:
        return (
            f"BookExampleWeaver — {self.book_examples_woven}/"
            f"{self.book_examples_total} examples woven "
            f"({self.coverage_pct:.0%}); topics={self.topics_processed}; "
            f"retries={self.retries_used}; "
            f"permanent_failures={len(self.permanent_failures)}"
        )


class BookExampleWeaver:
    """Per-example LLM render + structural validation + retry loop."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._client = anthropic.AsyncAnthropic(api_key=config.llm.api_key or "")

    async def weave_for_chapter(
        self,
        chapter_lesson_plans: dict[str, LessonPlan],
        topics_by_id: dict[str, Topic],
        diagrams_by_id: dict[str, Diagram],
    ) -> WeaverReport:
        """Walk every topic's LessonPlan; weave book examples in place.

        `chapter_lesson_plans` is updated IN PLACE — the caller (pipeline.py)
        re-reads `chapter.lesson_plans` after this returns.
        """
        report = WeaverReport()
        for topic_id, plan in chapter_lesson_plans.items():
            topic = topics_by_id.get(topic_id)
            if topic is None or not topic.book_examples:
                continue
            report.topics_processed += 1
            new_plan = await self.weave_for_topic(
                lesson_plan=plan,
                topic=topic,
                diagrams_by_id=diagrams_by_id,
                report=report,
            )
            chapter_lesson_plans[topic_id] = new_plan
        logger.info("book_example_weaver.summary", summary=report.summary())
        return report

    async def weave_for_topic(
        self,
        *,
        lesson_plan: LessonPlan,
        topic: Topic,
        diagrams_by_id: dict[str, Diagram],
        report: WeaverReport,
    ) -> LessonPlan:
        """Produce ChoreographyStep blocks for each book example, insert
        them into the lesson plan at the right slot, return the new plan.

        Idempotent: any existing is_book_example=True steps in the input
        plan are stripped before re-weaving, so running the weaver twice
        on the same plan doesn't duplicate example beats.

        Retries-with-feedback on any example the structural validator misses.
        """
        # Strip any existing weaver-tagged steps from the input plan first.
        # Without this, re-running the weaver on an already-woven plan
        # appends a SECOND copy of every example block.
        original_count = len(lesson_plan.choreography)
        stripped = [
            s for s in lesson_plan.choreography if not s.is_book_example
        ]
        if len(stripped) < original_count:
            logger.info(
                "book_example_weaver.stripped_existing",
                topic_id=topic.topic_id,
                removed=original_count - len(stripped),
            )
            data = lesson_plan.model_dump()
            data["choreography"] = [s.model_dump() for s in stripped]
            try:
                lesson_plan = LessonPlan.model_validate(data)
            except ValidationError as exc:
                logger.warning(
                    "book_example_weaver.strip_validation_failed",
                    topic_id=topic.topic_id,
                    error=str(exc)[:200],
                )
                # Bail out without modifying — better to return the original
                # plan than a half-stripped one.
                return lesson_plan

        woven_blocks: list[list[ChoreographyStep]] = []
        for ref_idx, book_ex in enumerate(topic.book_examples):
            report.book_examples_total += 1
            steps = await self._weave_one_example_with_retry(
                topic=topic,
                book_ex=book_ex,
                ref_idx=ref_idx,
                diagrams_by_id=diagrams_by_id,
                report=report,
            )
            if steps is None:
                report.permanent_failures.append(
                    f"{topic.topic_id}::book_example[{ref_idx}]"
                )
                continue
            # Tag every step with the ref so the validator can attribute it.
            for s in steps:
                s.is_book_example = True
                s.book_example_ref = ref_idx
            woven_blocks.append(steps)
            report.book_examples_woven += 1

        if not woven_blocks:
            return lesson_plan

        flat_new_steps: list[ChoreographyStep] = []
        for block in woven_blocks:
            flat_new_steps.extend(block)

        insertion_idx = _trailing_insertion_index(lesson_plan.choreography)
        merged = (
            lesson_plan.choreography[:insertion_idx]
            + flat_new_steps
            + lesson_plan.choreography[insertion_idx:]
        )
        # Build a new LessonPlan (model_copy mutates, but Pydantic validators
        # would re-run; we just replace choreography in a dict-roundtrip).
        data = lesson_plan.model_dump()
        data["choreography"] = [s.model_dump() for s in merged]
        try:
            return LessonPlan.model_validate(data)
        except ValidationError as exc:
            # If validators reject the post-merge plan (e.g., element_ids
            # reference something not declared, or a crucial_fact press
            # count gets miscounted), log and return the ORIGINAL plan
            # rather than a broken one. The structural validator on the
            # pipeline side will surface this as a permanent failure.
            logger.warning(
                "book_example_weaver.post_merge_validation_failed",
                topic_id=topic.topic_id,
                error=str(exc)[:400],
            )
            for ref_idx, _ in enumerate(topic.book_examples):
                if ref_idx not in {
                    s.book_example_ref for s in flat_new_steps if s.book_example_ref is not None
                }:
                    continue
                # All weaver steps drop on the floor; mark all as failures.
                report.permanent_failures.append(
                    f"{topic.topic_id}::book_example[{ref_idx}]::post_merge_validation"
                )
            report.book_examples_woven -= len(woven_blocks)
            return lesson_plan

    async def _weave_one_example_with_retry(
        self,
        *,
        topic: Topic,
        book_ex: BookExample,
        ref_idx: int,
        diagrams_by_id: dict[str, Diagram],
        report: WeaverReport,
    ) -> list[ChoreographyStep] | None:
        active_diagram_id, active_roles = _resolve_active_diagram(
            lesson_plan_diagrams=[],  # NOTE: we don't introspect declared diagrams here;
            diagrams_by_id=diagrams_by_id,
            topic=topic,
        )

        last_error: str = ""
        for attempt in range(_MAX_ATTEMPTS_PER_EXAMPLE):
            user_msg = build_book_example_user_prompt(
                topic_id=topic.topic_id,
                topic_name=topic.topic_name,
                section_number=topic.section_number,
                book_example_index=ref_idx,
                verbatim_text=book_ex.verbatim_text,
                lesson_focus=book_ex.lesson_focus,
                kind=book_ex.kind,
                setup_facts=list(book_ex.setup_facts),
                has_derivation=book_ex.has_derivation,
                active_diagram_id=active_diagram_id,
                active_diagram_roles=active_roles,
                prior_attempt_feedback=last_error if attempt > 0 else "",
            )
            try:
                steps = await self._call_anthropic(user_msg)
            except ValidationError as exc:
                last_error = (
                    f"Pydantic rejected your output: {exc}. The steps list must "
                    f"have 3-6 entries with non-empty narration. Try again."
                )
                report.retries_used += 1
                logger.warning(
                    "book_example_weaver.validation_error",
                    topic_id=topic.topic_id,
                    ref_idx=ref_idx,
                    attempt=attempt,
                )
                continue
            except Exception as exc:
                last_error = f"Unexpected error: {exc}. Try again."
                report.retries_used += 1
                logger.warning(
                    "book_example_weaver.unexpected_exception",
                    topic_id=topic.topic_id,
                    ref_idx=ref_idx,
                    attempt=attempt,
                    error=str(exc)[:200],
                )
                continue

            if steps is None or not steps:
                last_error = "Your response had no tool_use block or the steps list was empty. Try again."
                report.retries_used += 1
                continue

            # Defense-in-depth: force every weaver-produced step's
            # diagram-side fields to safe defaults. The post-merge
            # validator on LessonPlan rejects any choreography step whose
            # target_element_id references an undeclared element — and
            # the LLM keeps inventing element ids despite the prompt
            # telling it not to. Strip these unconditionally so the merge
            # always succeeds; example beats live on the notebook side
            # via inline markers in `narration`, not on the slide diagram.
            for s in steps:
                s.actions = []
                s.target_element_id = None
                s.target_diagram_id = None
                s.is_question = False
                s.is_payoff = False
                s.presses_crucial_fact = False

            if attempt > 0:
                logger.info(
                    "book_example_weaver.recovered_on_retry",
                    topic_id=topic.topic_id,
                    ref_idx=ref_idx,
                )
            return steps

        logger.error(
            "book_example_weaver.permanent_failure",
            topic_id=topic.topic_id,
            ref_idx=ref_idx,
            last_error=last_error[:200],
        )
        return None

    async def _call_anthropic(self, user_msg: str) -> list[ChoreographyStep] | None:
        response = await self._client.messages.create(
            model=self.config.llm.model,
            max_tokens=_MAX_TOKENS,
            system=BOOK_EXAMPLE_WEAVER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": _TOOL_DESCRIPTION,
                    "input_schema": _WeaverOutput.model_json_schema(),
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
                    return None
                parsed = _WeaverOutput.model_validate(payload)
                return parsed.steps
        return None


def _trailing_insertion_index(choreography: list[ChoreographyStep]) -> int:
    """Find the index BEFORE the first summarize/transition step. If no
    obvious trailing step exists, insert before the last 2 entries so the
    weaver block doesn't accidentally appear AFTER the lesson's wrap-up.
    """
    for i, step in enumerate(choreography):
        # Lesson plans don't carry beat_type per step, but the narration
        # often signals the wrap. Heuristic: look for narrations that read
        # like a summary close — fallback handled below.
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


def _resolve_active_diagram(
    *,
    lesson_plan_diagrams: list[Any],
    diagrams_by_id: dict[str, Diagram],
    topic: Topic,
) -> tuple[str | None, list[str] | None]:
    """Best-effort: pick the first diagram linked to this topic if any.
    Returns (diagram_id, role_vocab) or (None, None) when no diagram is
    available — the LLM is then told to leave actions empty.
    """
    candidate = next(
        (
            d
            for d in diagrams_by_id.values()
            if topic.topic_id in d.linked_topic_ids
        ),
        None,
    )
    if candidate is None:
        return None, None
    rd = getattr(candidate, "render_data", None) or {}
    dictionary = rd.get("dictionary", {}) if isinstance(rd, dict) else {}
    roles: set[str] = set()
    if isinstance(dictionary, dict):
        for entry in dictionary.values():
            if isinstance(entry, dict):
                role = entry.get("role")
                if isinstance(role, str) and role:
                    roles.add(role)
    return candidate.diagram_id, sorted(roles) if roles else []


# Re-export logging at module level for callers that prefer std logging.
_std_logger = logging.getLogger(__name__)
