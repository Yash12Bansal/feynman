"""LessonQualityGate — doc 19 Phase F orchestrator.

Wires Phase C (LessonPlanner), Phase D (LessonDiagramGenerator), Phase E
(LessonNarrator), and Phase F's judges into one synchronous per-topic gate:

    plan → PlanJudge → (regen plan once if score < threshold)
         → diagrams → DiagramQA per diagram → (regen offending diagrams once)
         → narrate → return GateResult

Quality retries are CAPPED to `max_quality_retries` per stage (default 1).
The planner/generator each have their own internal 2-attempt Pydantic retry;
Phase F sits on top with the quality layer. Worst-case total LLM calls per
topic: 2 planner × (1 + max_quality_retries) + 2 diag-gen × (1 + max_quality_retries)
per diagram + 1 judge + 1 QA per diagram.

Failed-to-pass topics are NOT dropped — they ship with `needs_review=True`.
This mirrors DiagramQA's existing graceful-degradation philosophy: a flagged
lesson is better than a missing lesson.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge import (
    PlanJudge,
    PlanJudgement,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (
    LessonNarrator,
    TopicNarration,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    DiagramRequirement,
    LessonPlan,
)
from lecture_pipeline_v2.curriculum.models import Diagram

if TYPE_CHECKING:
    from lecture_pipeline_v2.curriculum.enrichment.diagram_qa import DiagramQA
    from lecture_pipeline_v2.curriculum.lecture_plan.curriculum_adapter import (
        CurriculumAdapter,
    )
    from lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_generator import (
        LessonDiagramGenerator,
    )
    from lecture_pipeline_v2.curriculum.lecture_plan.lesson_planner import (
        LessonPlanner,
    )

logger = structlog.get_logger()


_DEFAULT_MAX_QUALITY_RETRIES = 1


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


class GateResult(BaseModel):
    """One topic's quality-gate outcome.

    `needs_review=True` does NOT block — the topic still ships. Downstream
    consumers (Phase H pipeline, dashboards, etc.) use this flag to surface
    the topic for human review.
    """

    topic_id: str
    plan: LessonPlan | None = None
    diagrams: list[Diagram] = Field(default_factory=list)
    narration: TopicNarration | None = None
    plan_judgement: PlanJudgement | None = None
    diagram_judgements: dict[str, object] = Field(
        default_factory=dict,
        description="diagram_id → QAResult. Typed loosely because QAResult is "
        "a dataclass, not a BaseModel.",
    )
    plan_regen_attempts: int = 0
    diagram_regen_attempts: int = 0
    needs_review: bool = False


@dataclass
class GateReport:
    """Across-many-topics telemetry. Not in GateResult to keep that focused
    on one topic's artifacts."""

    topics_seen: int = 0
    topics_passed: int = 0
    topics_needing_review: int = 0
    plan_regens: int = 0
    diagram_regens: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"LessonQualityGate — {self.topics_passed}/{self.topics_seen} "
            f"passed, {self.topics_needing_review} need review, "
            f"{self.plan_regens} plan regens, {self.diagram_regens} diagram "
            f"regens, {len(self.warnings)} warnings"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────


class LessonQualityGate:
    """Composes Phase C-F into one per-topic gate. Phase H calls this; until
    then it's standalone-testable with mocked dependencies.
    """

    def __init__(
        self,
        config: PipelineConfig,
        *,
        planner: LessonPlanner,
        diagram_generator: LessonDiagramGenerator,
        narrator: LessonNarrator,
        plan_judge: PlanJudge,
        diagram_qa: DiagramQA | None = None,
        max_quality_retries: int = _DEFAULT_MAX_QUALITY_RETRIES,
    ) -> None:
        self.config = config
        self.planner = planner
        self.diagram_generator = diagram_generator
        self.narrator = narrator
        self.plan_judge = plan_judge
        self.diagram_qa = diagram_qa
        self.max_quality_retries = max(0, max_quality_retries)

    async def gate_one_topic(
        self,
        *,
        chapter_id: str,
        topic_id: str,
        topic_name: str,
        concept_index: int,
        curriculum: CurriculumAdapter,
        report: GateReport | None = None,
    ) -> GateResult:
        """Full Phase C-F pipeline for one topic.

        Returns a `GateResult` whose `plan`/`diagrams`/`narration` are the
        FINAL artifacts after any quality retries. `needs_review=True` if
        any stage ended with a sub-threshold score.
        """
        local_report = report or GateReport()
        local_report.topics_seen += 1
        needs_review = False

        # ─── Stage 1: Plan + judge + (maybe regen) ─────────────────────────
        plan, plan_judgement, plan_regens = await self._gate_plan(
            chapter_id=chapter_id,
            topic_id=topic_id,
            topic_name=topic_name,
            concept_index=concept_index,
            curriculum=curriculum,
            report=local_report,
        )
        if plan is None:
            # Planner gave up internally. Return an empty result flagged for
            # review; downstream can decide to skip the topic or hand-author.
            local_report.topics_needing_review += 1
            return GateResult(
                topic_id=topic_id,
                plan=None,
                diagrams=[],
                narration=None,
                plan_judgement=plan_judgement,
                diagram_judgements={},
                plan_regen_attempts=plan_regens,
                diagram_regen_attempts=0,
                needs_review=True,
            )
        if plan_judgement is not None and not plan_judgement.passed:
            needs_review = True

        # ─── Stage 2: Diagrams + QA + (maybe regen offending diagrams) ────
        diagrams, diagram_judgements, diagram_regens = await self._gate_diagrams(
            chapter_id=chapter_id,
            topic_id=topic_id,
            requirements=plan.diagrams,
            report=local_report,
        )
        if any(not getattr(j, "passed", True) for j in diagram_judgements.values()):
            needs_review = True

        # ─── Stage 3: Narration (deterministic; no judge) ─────────────────
        # Pass a diagram_id_resolver so the narrator emits SHOW_DIAGRAM
        # markers using the LONG generate_diagram_uid output (matching what
        # LessonDiagramGenerator pins on each Diagram), not the planner's
        # short id. Without this, the frontend can't resolve the manifest
        # event id back to a diagram and the slide stays "loading".
        short_to_long = _diagram_id_short_to_long(plan, topic_id)
        narration = self.narrator.render(
            topic_id=topic_id,
            plan=plan,
            diagram_id_resolver=lambda short_id: short_to_long.get(short_id, short_id),
        )

        if needs_review:
            local_report.topics_needing_review += 1
        else:
            local_report.topics_passed += 1

        return GateResult(
            topic_id=topic_id,
            plan=plan,
            diagrams=diagrams,
            narration=narration,
            plan_judgement=plan_judgement,
            diagram_judgements=diagram_judgements,
            plan_regen_attempts=plan_regens,
            diagram_regen_attempts=diagram_regens,
            needs_review=needs_review,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internal stage helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _gate_plan(
        self,
        *,
        chapter_id: str,
        topic_id: str,
        topic_name: str,
        concept_index: int,
        curriculum: CurriculumAdapter,
        report: GateReport,
    ) -> tuple[LessonPlan | None, PlanJudgement | None, int]:
        """Plan → judge → (re-plan with feedback at most max_quality_retries
        times) → final plan + final judgement.

        Returns (plan, judgement, regen_count). plan is None iff the planner
        gave up internally (both Pydantic attempts failed).
        """
        plan = await self.planner.plan_one_topic(
            concept_index=concept_index,
            curriculum=curriculum,
            topic_id=topic_id,
            chapter_id=chapter_id,
        )
        if plan is None:
            return None, None, 0

        best_plan = plan
        best_judgement = await self.plan_judge.judge(plan, topic_name=topic_name)
        regens = 0

        while not best_judgement.passed and regens < self.max_quality_retries:
            regens += 1
            report.plan_regens += 1
            feedback = _format_judge_feedback(best_judgement)
            logger.info(
                "lesson_quality_gate.plan_regen",
                topic_id=topic_id,
                attempt=regens,
                prior_score=best_judgement.score,
            )
            retry_plan = await self.planner.plan_one_topic(
                concept_index=concept_index,
                curriculum=curriculum,
                topic_id=topic_id,
                chapter_id=chapter_id,
                prior_quality_feedback=feedback,
            )
            if retry_plan is None:
                # Planner crashed on the regen — keep the best so far.
                break

            retry_judgement = await self.plan_judge.judge(
                retry_plan, topic_name=topic_name
            )
            # Take the higher-scoring attempt. This is "best", not "latest".
            if retry_judgement.score > best_judgement.score:
                best_plan = retry_plan
                best_judgement = retry_judgement

        return best_plan, best_judgement, regens

    async def _gate_diagrams(
        self,
        *,
        chapter_id: str,
        topic_id: str,
        requirements: list[DiagramRequirement],
        report: GateReport,
    ) -> tuple[list[Diagram], dict[str, object], int]:
        """Generate all diagrams, QA each, regen offending ones at most
        max_quality_retries times.

        Returns (final_diagrams, judgements_by_diagram_id, total_regens).
        """
        if not requirements:
            return [], {}, 0

        # Initial pass.
        initial_diagrams, _ = await self.diagram_generator.generate_for_requirements(
            [(chapter_id, topic_id, r) for r in requirements]
        )

        # Map back to (diagram, requirement) tuples for the QA pass.
        diagrams_by_diagram_id: dict[str, Diagram] = {
            d.diagram_id: d for d in initial_diagrams
        }
        # We need to know which requirement produced which diagram; the
        # generator pins requirement.diagram_id but the Diagram.diagram_id
        # is a UID via `generate_diagram_uid`. We match by ordering OR by
        # description (description == requirement.purpose).
        requirements_by_description: dict[str, DiagramRequirement] = {
            r.purpose: r for r in requirements
        }

        judgements: dict[str, object] = {}
        regens = 0

        if self.diagram_qa is None:
            # Visual QA disabled — pass everything through unjudged.
            return initial_diagrams, judgements, 0

        for diagram in list(initial_diagrams):
            requirement = requirements_by_description.get(diagram.description)
            if requirement is None:
                continue
            claim = _build_diagram_claim(requirement)
            qa = await self.diagram_qa.verify(diagram, claim)
            judgements[diagram.diagram_id] = qa

            quality_attempts = 0
            best_diagram = diagram
            best_qa = qa
            while not best_qa.passed and quality_attempts < self.max_quality_retries:
                quality_attempts += 1
                regens += 1
                report.diagram_regens += 1
                feedback = _format_qa_feedback(best_qa)
                logger.info(
                    "lesson_quality_gate.diagram_regen",
                    topic_id=topic_id,
                    diagram_id=requirement.diagram_id,
                    attempt=quality_attempts,
                    prior_score=best_qa.score,
                )
                retry_diagram = await self.diagram_generator.generate_one_requirement(
                    chapter_id=chapter_id,
                    topic_id=topic_id,
                    requirement=requirement,
                    prior_quality_feedback=feedback,
                )
                if retry_diagram is None:
                    break
                retry_qa = await self.diagram_qa.verify(retry_diagram, claim)
                if retry_qa.score > best_qa.score:
                    best_diagram = retry_diagram
                    best_qa = retry_qa

            # Replace in the final list with the best-scoring version.
            diagrams_by_diagram_id[best_diagram.diagram_id] = best_diagram
            judgements[best_diagram.diagram_id] = best_qa

        return list(diagrams_by_diagram_id.values()), judgements, regens


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────


def _diagram_id_short_to_long(plan: LessonPlan, topic_id: str) -> dict[str, str]:
    """Map each `DiagramRequirement.diagram_id` (the planner's short id used in
    `choreography.target_diagram_id` and emitted by `LessonNarrator` as a
    `<<SHOW_DIAGRAM:short>>` marker by default) to the long runtime UID that
    `LessonDiagramGenerator._build_diagram` pins via `generate_diagram_uid`.

    Used by the gate to give `LessonNarrator` a resolver so the manifest's
    `show_diagram` events carry the SAME id the actual `Diagram` object has —
    otherwise the frontend can't look up the diagram by id and the slide
    stays stuck on "loading".
    """
    from lecture_pipeline_v2.curriculum.id_generator import generate_diagram_uid

    return {
        req.diagram_id: generate_diagram_uid(topic_id, req.diagram_id)
        for req in plan.diagrams
    }


def _build_diagram_claim(requirement: DiagramRequirement) -> str:
    """Synthesize a plain-language claim from a DiagramRequirement.

    The DiagramQA vision pass expects a single claim string describing what
    the diagram should depict. We compose: purpose + the role/description of
    every required element so the vision model can confirm presence.
    """
    parts: list[str] = []
    parts.append(requirement.purpose.strip())
    if requirement.required_elements:
        parts.append("")
        parts.append("Elements that MUST appear:")
        for el in requirement.required_elements:
            parts.append(f"- {el.role}: {el.description.strip()}")
    return "\n".join(parts)


def _format_judge_feedback(judgement: PlanJudgement) -> str:
    """Format a PlanJudgement for the planner's `prior_quality_feedback`."""
    return (
        f"Issue: {judgement.issue}\n"
        f"Suggestion: {judgement.suggestion}\n"
        f"(Prior judge score: {judgement.score}/5)"
    )


def _format_qa_feedback(qa: object) -> str:
    """Format a DiagramQA QAResult for the generator's `prior_quality_feedback`.

    QAResult is a dataclass with `.issue`, `.suggestion`, `.score`. We avoid
    importing it at module top to keep the dependency tree shallow.
    """
    issue = getattr(qa, "issue", "")
    suggestion = getattr(qa, "suggestion", "")
    score = getattr(qa, "score", 0)
    return f"Issue: {issue}\nSuggestion: {suggestion}\n(Prior QA score: {score}/5)"
