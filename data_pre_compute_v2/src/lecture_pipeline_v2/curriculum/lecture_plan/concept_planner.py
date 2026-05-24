"""ConceptPlanner — per-topic ConceptTeachingPlan via the shared kernel.

Async because the kernel's `plan_concept` is async (uses AsyncAnthropic).
One retry on failure: the kernel swallows ValidationError / API errors and
returns None, so the retry condition is `result is None`. Second failure
logs and proceeds with no plan for that topic (the chapter still gets
ingested; downstream stages tolerate missing plans).

Doc 18 §5.2 enforcement: after the kernel returns, walk the beats and
rewrite any concept-style beat whose `visual.tool` falls outside the
whitelist to `draw_design_diagram`. This guarantees that §47.1-style
"dead slide" failures don't slip past planning into the manifest.
"""

from __future__ import annotations

import structlog
from feynman_teaching_kernel import ConceptTeachingPlan, plan_concept

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.curriculum_adapter import (
    CurriculumAdapter,
    _LessonPlanShim,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Chapter, Diagram, Topic

logger = structlog.get_logger()


# The precompute pipeline's whitelist for `visual.tool`. Slide-side: the two
# design_agent renderers. Notebook-side: the seven write_* tools the
# composer's chunker recognizes. Anything else (draw_scene, draw_diagram,
# show_equation, step_equation, show_graph, highlight_*, annotate, etc.)
# is silently unsupported by precompute — we pass this list to the kernel so
# the LLM never picks an unsupported tool in the first place.
#
# Doc 19 §10 rolled back the post-plan rewrite from doc 18 §5.2: forcing
# every concept beat to carry a design diagram produced *more* diagrams, not
# *better* teaching. The kernel constraint (passed below) is enough — the
# planner has the freedom to pick text-only when that's the right move.
PRECOMPUTE_ALLOWED_VISUAL_TOOLS: list[str] = [
    "draw_design_diagram",
    "modify_design_diagram",
    "write_section",
    "write_equation",
    "write_step",
    "write_key_point",
    "write_text",
    "write_answer",
]


class ConceptPlanner:
    """Plans every topic in every chapter via kernel.plan_concept."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    async def plan_for_all(
        self,
        chapters: list[Chapter],
        topics_by_chapter: dict[str, list[Topic]],
        lecture_plans: dict[str, ChapterLecturePlan],
        diagrams_by_topic: dict[str, list[Diagram]],
    ) -> dict[str, list[ConceptTeachingPlan]]:
        """For each chapter that has a lecture plan, plan each topic in
        concept_sequence order. Returns chapter_id → list of plans.
        """
        result: dict[str, list[ConceptTeachingPlan]] = {}
        for chapter in chapters:
            lecture_plan = lecture_plans.get(chapter.chapter_id)
            if lecture_plan is None:
                logger.warning(
                    "concept_planner.no_chapter_plan",
                    chapter_id=chapter.chapter_id,
                )
                continue

            topics = topics_by_chapter.get(chapter.chapter_id, [])
            adapter = CurriculumAdapter(
                chapter, topics, lecture_plan, diagrams_by_topic
            )
            plan_shim = _LessonPlanShim(
                total_concepts=len(lecture_plan.concept_sequence)
            )

            concept_plans: list[ConceptTeachingPlan] = []
            prev_plan: ConceptTeachingPlan | None = None
            for idx, topic_id in enumerate(lecture_plan.concept_sequence):
                cp = await self._plan_one_with_retry(
                    idx,
                    adapter,
                    plan_shim,
                    prev_plan=prev_plan,
                    topic_id=topic_id,
                    chapter_id=chapter.chapter_id,
                )
                if cp is not None:
                    concept_plans.append(cp)
                    prev_plan = cp
            result[chapter.chapter_id] = concept_plans
        return result

    async def _plan_one_with_retry(
        self,
        concept_index: int,
        curriculum: CurriculumAdapter,
        plan: _LessonPlanShim,
        *,
        prev_plan: ConceptTeachingPlan | None,
        topic_id: str,
        chapter_id: str,
    ) -> ConceptTeachingPlan | None:
        """Call kernel.plan_concept; retry once if it returns None.

        The kernel returns None on ValidationError, API errors, or no
        tool_use block found in the response. Single retry is cheap
        insurance against transient failures; persistent failures log and
        proceed with no plan for this concept.
        """
        for attempt in range(2):
            try:
                cp = await plan_concept(
                    concept_index,
                    curriculum,
                    plan,
                    board_summary="",  # no live board in precompute
                    audit=None,
                    prev_plan=prev_plan,
                    allowed_visual_tools=PRECOMPUTE_ALLOWED_VISUAL_TOOLS,
                    api_key=self.config.llm.api_key or "",
                    model=self.config.llm.model,
                )
            except Exception as exc:  # noqa: BLE001 — defensive at boundary
                logger.warning(
                    "concept_planner.unexpected_exception",
                    chapter_id=chapter_id,
                    topic_id=topic_id,
                    concept_index=concept_index,
                    attempt=attempt,
                    error=str(exc),
                )
                cp = None

            if cp is not None:
                return cp

            logger.warning(
                "concept_planner.plan_returned_none",
                chapter_id=chapter_id,
                topic_id=topic_id,
                concept_index=concept_index,
                attempt=attempt,
            )

        logger.error(
            "concept_planner.final_failure",
            chapter_id=chapter_id,
            topic_id=topic_id,
            concept_index=concept_index,
        )
        return None
