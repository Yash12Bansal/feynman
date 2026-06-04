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

from feynman.agent.doubt_resolution.diagram_templates import is_known
from feynman.agent.doubt_resolution.doubt_classifier import classify_doubt
from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    DoubtRecord,
    NoDiagram,
    ResolutionPlan,
    ReuseDiagram,
    TemplateDiagram,
)
from feynman.agent.doubt_resolution.resolution_planner import plan_resolution

logger = structlog.get_logger()


@dataclass
class LectureDoubtSession:
    chapter_context: ChapterContext
    prior_doubts_in_session: list[DoubtRecord] = field(default_factory=list)
    shown_diagram_ids: set[str] = field(default_factory=set)
    # Per-session cache of generated doubt-diagram specs, keyed by the
    # generation brief. Lets a `start_over`/re-resolve reuse a spec instead of
    # paying the generation latency + cost again. Ephemeral — never persisted.
    generated_specs: dict[str, dict] = field(default_factory=dict)

    async def resolve(
        self,
        *,
        doubt_text: str,
        current_topic_id: str | None = None,
        cursor: int | None = None,
        different_angle: bool = False,
        prior_resolution_summary: str = "",
        board_snapshot: dict | None = None,
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
            board_snapshot=board_snapshot,
        )
        if plan is None:
            logger.error("lecture_session.planner_failed", cursor=cursor)
            return None

        # The planner now decides each beat's diagram directly — it sees the
        # full diagram catalog with element semantics and chooses reuse /
        # generate / keep / none. Validate its reuse picks against the real
        # chapter diagrams: an id the planner invented degrades to "no diagram"
        # rather than dangling. `target_diagram_id` is mirrored from a valid
        # reuse for telemetry + the recency set (delivery reads the directive).
        valid_ids = set(self.chapter_context.diagrams.keys())
        for beat in plan.beats:
            directive = beat.diagram
            if isinstance(directive, ReuseDiagram):
                if directive.diagram_id in valid_ids:
                    beat.target_diagram_id = directive.diagram_id
                else:
                    logger.warning(
                        "lecture_session.reuse_id_invalid",
                        diagram_id=directive.diagram_id,
                    )
                    beat.diagram = NoDiagram()
            elif isinstance(directive, TemplateDiagram) and not is_known(directive.concept_id):
                # An invented template id would render a blank slide — degrade
                # to no-diagram (narration still answers the student).
                logger.warning(
                    "lecture_session.template_concept_invalid",
                    concept_id=directive.concept_id,
                )
                beat.diagram = NoDiagram()

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
