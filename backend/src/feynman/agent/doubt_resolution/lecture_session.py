"""LectureDoubtSession — per-lecture coordinator for the doubt pipeline.

One instance lives for the duration of a single LiveKit lecture session.
It owns:
- The loaded `ChapterContext` (topics + diagrams from Neo4j).
- Session-only `prior_doubts_in_session` history (drives planner context
  + classifier disambiguation).
- `shown_diagram_ids` (drives the matcher's recency penalty).

The pipeline is classifier → planner → matcher. Phase 5 takes the
returned `ResolutionPlan` and delivers it as live voice + visuals.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

from feynman.agent.doubt_resolution.diagram_fit_matcher import (
    match_diagrams_for_plan,
)
from feynman.agent.doubt_resolution.doubt_classifier import (
    DoubtType,
    classify_doubt,
)
from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    DoubtRecord,
    ResolutionPlan,
)
from feynman.agent.doubt_resolution.resolution_planner import plan_resolution

logger = structlog.get_logger()


@dataclass
class LectureDoubtSession:
    chapter_context: ChapterContext
    prior_doubts_in_session: list[DoubtRecord] = field(default_factory=list)
    shown_diagram_ids: set[str] = field(default_factory=set)

    async def resolve(
        self,
        *,
        doubt_text: str,
        current_topic_id: str | None = None,
        cursor: int | None = None,
        different_angle: bool = False,
        prior_resolution_summary: str = "",
    ) -> ResolutionPlan | None:
        """Run the full classify → plan → match pipeline for one doubt.

        Returns the plan (or None if the planner fails persistently). The
        caller — currently the worker in `_handle_doubt_intent` — is
        responsible for delivery (Phase 5).
        """
        t0 = time.monotonic()
        topic_meta = self.chapter_context.topic(current_topic_id)
        topic_summary = topic_meta.summary if topic_meta else ""

        classification = await classify_doubt(
            doubt_text=doubt_text,
            current_topic_id=current_topic_id,
            current_topic_context_snippet=topic_summary,
            prior_doubts_in_session=[r.doubt_text for r in self.prior_doubts_in_session],
            chapter_context=self.chapter_context,
        )
        logger.info(
            "lecture_session.classified",
            type=classification.type.value,
            related=classification.related_concept_ids,
            rationale=classification.rationale,
            cursor=cursor,
        )

        plan = await plan_resolution(
            doubt_text=doubt_text,
            classification=classification,
            chapter_context=self.chapter_context,
            current_topic_id=current_topic_id,
            prior_doubts=self.prior_doubts_in_session,
            different_angle=different_angle,
            prior_resolution_summary=prior_resolution_summary,
        )
        if plan is None:
            logger.error("lecture_session.planner_failed", cursor=cursor)
            return None

        # Phase 6 adaptive matcher: local clarifications are typically
        # small verbal explanations where a tangentially-related diagram
        # is acceptable. Skipping the Haiku verifier shaves ~1-2s off the
        # latency budget on the most-common doubt type.
        skip_stage2 = classification.type == DoubtType.LOCAL_CLARIFICATION

        await match_diagrams_for_plan(
            plan=plan,
            chapter_context=self.chapter_context,
            doubt_text=doubt_text,
            classification=classification,
            current_topic_id=current_topic_id,
            shown_diagram_ids=self.shown_diagram_ids,
            skip_stage2=skip_stage2,
        )

        matched_ids = [b.target_diagram_id for b in plan.beats if b.target_diagram_id]
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "lecture_session.plan_ready",
            beats=len(plan.beats),
            matched=matched_ids,
            narration_chars=sum(len(b.narration_text) for b in plan.beats),
        )
        logger.info(
            "phase6.doubt_pipeline_total_ms",
            ms=elapsed_ms,
            classification=classification.type.value,
            skip_stage2=skip_stage2,
        )

        # Update session history + shown set.
        plan_summary = " | ".join(b.narration_text[:80] for b in plan.beats)
        self.prior_doubts_in_session.append(
            DoubtRecord(
                doubt_text=doubt_text,
                classification=classification,
                plan_summary=plan_summary,
            )
        )
        self.shown_diagram_ids.update(matched_ids)
        return plan
