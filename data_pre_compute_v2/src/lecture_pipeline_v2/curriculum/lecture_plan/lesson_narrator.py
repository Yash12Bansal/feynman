"""LessonNarrator — deterministic synthesizer from LessonPlan.choreography
to chunker-grammar narration text (doc 19 Phase E).

The choreography (Phase C output) ALREADY pre-decides what happens on the
board and what gets said per step. Phase E's job is plumbing: walk the
choreography and emit the chunker markers that the existing
`tts/chunker.py` consumes (SHOW_DIAGRAM, FOCUS, UNFOCUS, TRACE, POINT,
CLEAR_ANNOTATIONS, PAUSE, WRITE_EQUATION).

No LLM call. Pure function. Idempotent. The narrator does not move actions
or rewrite words — it just translates the locked plan into the audio
pipeline's input format.

Phase H is where this replaces BeatNarrationWriter in `pipeline.py`. Until
then it sits alongside.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import structlog
from pydantic import BaseModel, Field

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    ChoreographyAction,
    ChoreographyStep,
    DiagramRequirement,
    EquationIntroduction,
    LessonPlan,
)

logger = structlog.get_logger()


# Words per second for the duration estimate. Matches BeatNarrationConfig's
# `target_wps` default (`config.py`). Real timing comes from TTS; this is
# only useful for sanity checks at plan time.
_TARGET_WPS = 2.5


# ─────────────────────────────────────────────────────────────────────────────
# Output models
# ─────────────────────────────────────────────────────────────────────────────


class LessonNarrationSegment(BaseModel):
    """One ChoreographyStep rendered to text-with-markers.

    `raw_narration` is the plan's verbatim narration (for QA / inspection).
    `text_with_markers` is what gets joined into `full_text_with_markers`.
    The boolean flags propagate downstream so Phase G (prosody) can light
    crucial-fact lines and elongate question pauses.
    """

    step_index: int = Field(ge=0)
    raw_narration: str
    text_with_markers: str
    target_duration_seconds: float = Field(default=0.0, ge=0.0)
    is_question: bool = False
    is_payoff: bool = False
    presses_crucial_fact: bool = False


class TopicNarration(BaseModel):
    """Per-LessonPlan output. `full_text_with_markers` is the canonical
    artifact fed to `tts/chunker.split_script()`. Segments are kept for
    per-step inspection and human review."""

    topic_id: str
    segments: list[LessonNarrationSegment] = Field(default_factory=list)
    full_text_with_markers: str = ""
    diagrams_referenced: list[str] = Field(default_factory=list)


@dataclass
class LessonNarrationReport:
    """Operational telemetry. Counts useful for Phase H wiring + lint."""

    plans_seen: int = 0
    plans_rendered: int = 0
    steps_rendered: int = 0
    equations_rendered: int = 0
    unsupported_actions: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"LessonNarrator — {self.plans_rendered}/{self.plans_seen} plans, "
            f"{self.steps_rendered} steps, {self.equations_rendered} equations, "
            f"{self.unsupported_actions} unsupported actions, "
            f"{len(self.warnings)} warnings"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Synthesizer
# ─────────────────────────────────────────────────────────────────────────────


class LessonNarrator:
    """Deterministic renderer. `config` carries no Anthropic state because
    this class never talks to an LLM — accepted for symmetry with the other
    lecture_plan modules and to give Phase H a clean place to inject knobs
    (e.g., disable equation interleaving) later.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def render(
        self,
        *,
        topic_id: str,
        plan: LessonPlan,
        diagram_id_resolver: Callable[[str], str | None] | None = None,
        report: LessonNarrationReport | None = None,
    ) -> TopicNarration:
        """Render one LessonPlan → TopicNarration. Pure function.

        `diagram_id_resolver` maps the plan's diagram_id (e.g. "train-frame")
        to the runtime UID (e.g. "diagram:topic-1:train_frame") emitted by
        `LessonDiagramGenerator`. If absent, the plan's id is used verbatim
        (test-friendly default; Phase H injects the real resolver).
        """
        local_report = report or LessonNarrationReport()
        local_report.plans_seen += 1

        # Index equations by their declared insertion point so a single walk
        # over choreography can fire each one in the right slot.
        equations_after: dict[int, list[EquationIntroduction]] = {}
        for eq in plan.equations:
            equations_after.setdefault(eq.introduces_after_step_index, []).append(eq)

        seen_diagrams: set[str] = set()
        diagrams_in_order: list[str] = []
        segments: list[LessonNarrationSegment] = []
        equation_counter = 0

        for step_index, step in enumerate(plan.choreography):
            step_diagram_id = _resolve_step_diagram_id(step, plan.diagrams)

            # SHOW_DIAGRAM bookkeeping — fires the first time each diagram
            # is referenced. Resolver is applied to the diagram_id BEFORE
            # we record it in `seen_diagrams` so the same logical diagram
            # isn't shown twice via two different aliases.
            show_diagram_marker = ""
            if step_diagram_id is not None:
                resolved_show = (
                    diagram_id_resolver(step_diagram_id)
                    if diagram_id_resolver is not None
                    else step_diagram_id
                )
                resolved_show = resolved_show or step_diagram_id
                if resolved_show not in seen_diagrams:
                    seen_diagrams.add(resolved_show)
                    diagrams_in_order.append(resolved_show)
                    show_diagram_marker = f"<<SHOW_DIAGRAM:{resolved_show}>>"

            before_markers, after_markers = _emit_action_markers(
                step, step_index, local_report
            )

            # Order within the step: clear/unfocus first, then show_diagram
            # (if first reference), then focus/clear, then narration, then
            # trace/point (after-style markers), then question-pause.
            parts: list[str] = []
            if before_markers:
                parts.extend(before_markers)
            if show_diagram_marker:
                parts.append(show_diagram_marker)
            parts.append(step.narration.strip())
            if after_markers:
                parts.extend(after_markers)
            if step.is_question:
                parts.append("<<PAUSE:short>>")

            text_with_markers = " ".join(p for p in parts if p)
            words = len(step.narration.split())
            duration = float(words) / _TARGET_WPS if words else 0.0

            segments.append(
                LessonNarrationSegment(
                    step_index=step_index,
                    raw_narration=step.narration,
                    text_with_markers=text_with_markers,
                    target_duration_seconds=duration,
                    is_question=step.is_question,
                    is_payoff=step.is_payoff,
                    presses_crucial_fact=step.presses_crucial_fact,
                )
            )
            local_report.steps_rendered += 1

            # Equation introductions tied to this step index.
            for eq in equations_after.get(step_index, []):
                equation_counter += 1
                eq_segment = _render_equation_segment(eq, step_index, equation_counter)
                segments.append(eq_segment)
                local_report.equations_rendered += 1

        full = " ".join(
            seg.text_with_markers for seg in segments if seg.text_with_markers
        )
        local_report.plans_rendered += 1

        return TopicNarration(
            topic_id=topic_id,
            segments=segments,
            full_text_with_markers=full,
            diagrams_referenced=diagrams_in_order,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers (kept at module scope so tests can hit them directly).
# ─────────────────────────────────────────────────────────────────────────────


def _emit_action_markers(
    step: ChoreographyStep,
    step_index: int,
    report: LessonNarrationReport,
) -> tuple[list[str], list[str]]:
    """Return (before_narration, after_narration) marker lists for a step.

    Position rationale (see plan):
      - CLEAR / UNFOCUS / FOCUS happen BEFORE the spoken sentence so the
        visual state is correct when the audio starts.
      - TRACE / POINT happen AFTER the spoken sentence so the visual
        animation lands as the sentence finishes (matches a teacher saying
        "watch this curve…" then drawing it).
    """
    before: list[str] = []
    after: list[str] = []

    for action in step.actions:
        if action == ChoreographyAction.clear:
            before.append("<<CLEAR_ANNOTATIONS>>")
        elif action == ChoreographyAction.unfocus:
            before.append("<<UNFOCUS>>")
        elif action == ChoreographyAction.focus:
            if step.target_element_id:
                before.append(f"<<FOCUS:{step.target_element_id}>>")
            else:
                report.warnings.append(
                    f"step {step_index}: focus action without target_element_id; skipped"
                )
                logger.warning(
                    "lesson_narrator.focus_without_target",
                    step_index=step_index,
                )
        elif action == ChoreographyAction.trace:
            if step.target_element_id:
                after.append(f"<<TRACE:{step.target_element_id}>>")
            else:
                report.warnings.append(
                    f"step {step_index}: trace action without target_element_id; skipped"
                )
                logger.warning(
                    "lesson_narrator.trace_without_target",
                    step_index=step_index,
                )
        elif action == ChoreographyAction.point_at:
            if step.target_element_id:
                after.append(f"<<POINT:{step.target_element_id}>>")
            else:
                report.warnings.append(
                    f"step {step_index}: point_at action without target_element_id; skipped"
                )
                logger.warning(
                    "lesson_narrator.point_at_without_target",
                    step_index=step_index,
                )
        elif action == ChoreographyAction.mark_point:
            report.unsupported_actions += 1
            report.warnings.append(
                f"step {step_index}: mark_point payload missing from ChoreographyStep "
                "(needs x/y); skipped — Phase A revision needed"
            )
            logger.warning(
                "lesson_narrator.mark_point_skipped",
                step_index=step_index,
                reason="payload not in ChoreographyStep model",
            )
        elif action == ChoreographyAction.write_margin:
            report.unsupported_actions += 1
            report.warnings.append(
                f"step {step_index}: write_margin payload missing from ChoreographyStep "
                "(needs text); skipped — Phase A revision needed"
            )
            logger.warning(
                "lesson_narrator.write_margin_skipped",
                step_index=step_index,
                reason="payload not in ChoreographyStep model",
            )

    return before, after


def _resolve_step_diagram_id(
    step: ChoreographyStep,
    plan_diagrams: list[DiagramRequirement],
) -> str | None:
    """Return the diagram_id this step references, falling back to a lookup
    by `target_element_id` if the step didn't declare it directly.

    Returns None if the step has no diagram association — fine for
    narration-only steps (no actions, no targets).
    """
    if step.target_diagram_id:
        return step.target_diagram_id
    if step.target_element_id:
        for diagram in plan_diagrams:
            for el in diagram.required_elements:
                if el.element_id == step.target_element_id:
                    return diagram.diagram_id
    return None


def _render_equation_segment(
    equation: EquationIntroduction,
    after_step_index: int,
    counter: int,
) -> LessonNarrationSegment:
    """Render one EquationIntroduction as an inline segment.

    The plain-language `explanation_in_words` is spoken first (no markers),
    then the WRITE_EQUATION marker fires. This enforces doc 19 §3: "equations
    arrive AFTER the picture explains them".
    """
    explanation = equation.explanation_in_words.strip()
    latex = equation.latex.strip()
    text = f"{explanation} <<WRITE_EQUATION:{latex}|id=eq-{counter}|boxed>>"
    words = len(explanation.split())
    duration = float(words) / _TARGET_WPS if words else 0.0
    # Equation segments use a synthetic step_index that follows their host
    # step. We don't have a real step in the choreography for them, so we
    # piggyback on after_step_index and rely on segment ordering.
    return LessonNarrationSegment(
        step_index=after_step_index,
        raw_narration=explanation,
        text_with_markers=text,
        target_duration_seconds=duration,
        is_question=False,
        is_payoff=False,
        presses_crucial_fact=False,
    )
