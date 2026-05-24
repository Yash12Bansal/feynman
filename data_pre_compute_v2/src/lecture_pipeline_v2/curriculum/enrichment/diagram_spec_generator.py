"""Phase 4c — per-beat DiagramSpec generation.

Consumes the per-concept TeachingBeats produced by Phase 7b's ConceptPlanner.
For each beat whose ``visual.tool`` is in
``{"draw_design_diagram", "modify_design_diagram"}``, generates a DiagramSpec
JSON via the same prompt the Phase 1 DiagramGenerator uses (verbatim-copied
from ``design_agent/backend/prompts.py:SYSTEM_PROMPT``). The output is a
``Diagram`` object with ``linked_beat_id`` populated so Phase 4d's
``ScriptAssembler`` can look it up.

Phase 4c v1 supports ``mode="direct"`` only. ``mode="auto"`` is an alias for
``"direct"`` (no heuristic yet); ``mode="python"`` raises
``NotImplementedError`` (the ``canvas_dsl`` sandbox lives in
``backend/src/feynman/agent/design_bridge.py`` — porting it into v2 or a
shared kernel is a future sub-phase).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time

from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat

from ...llm.base import LLMProvider
from ..id_generator import generate_diagram_uid
from ..models import Diagram, DiagramRenderer, Topic
from .diagrams import DIAGRAM_SYSTEM_PROMPT, build_design_diagram_user_prompt

logger = logging.getLogger(__name__)


DESIGN_DIAGRAM_TOOLS = frozenset({"draw_design_diagram", "modify_design_diagram"})

# Doc 18 §4.3 — concept-style beats reveal incrementally as the teacher talks
# (matches a teacher building the diagram). Mechanic beats and per-topic
# diagrams use overview (everything visible, spotlight one at a time).
_BUILD_UP_BEAT_TYPES: frozenset[str] = frozenset(
    {
        "hook",
        "big_picture",
        "first_principles",
        "visual_build",
        "misconception",
    }
)


def _presentation_mode_for_beat(beat_type: str) -> str:
    return "build_up" if beat_type in _BUILD_UP_BEAT_TYPES else "overview"


@dataclasses.dataclass
class DiagramSpecGenerationReport:
    beats_seen: int = 0
    beats_design_diagram: int = 0
    diagrams_generated: int = 0
    failures: list[str] = dataclasses.field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"DiagramSpecGenerator — {self.diagrams_generated} diagrams from "
            f"{self.beats_design_diagram} design-diagram beats "
            f"(out of {self.beats_seen} total), "
            f"{len(self.failures)} failures, {self.elapsed_seconds:.1f}s"
        )


class DiagramSpecGenerator:
    """Async per-beat DiagramSpec generator.

    Phase 4c constraint: mode in {"direct", "auto"} only. "python" raises.
    """

    def __init__(
        self,
        llm: LLMProvider,
        *,
        concurrency: int = 5,
        mode: str = "direct",
    ) -> None:
        if mode == "python":
            raise NotImplementedError(
                "DiagramSpecGenerator mode='python' is not implemented in Phase 4c. "
                "The canvas_dsl sandbox lives in "
                "backend/src/feynman/agent/design_bridge.py; porting it into v2 "
                "is a future sub-phase. Use mode='direct'."
            )
        if mode not in {"direct", "auto"}:
            raise ValueError(
                f"Unknown DiagramSpecGenerator mode: {mode!r} "
                "(expected 'direct', 'auto', or 'python')."
            )
        self.llm = llm
        self.concurrency = concurrency
        # "auto" aliases to "direct" in Phase 4c (no heuristic yet).
        self.mode = "direct"

    async def generate_for_chapter(
        self,
        topics_by_id: dict[str, Topic],
        concept_plans: list[ConceptTeachingPlan],
        topic_id_by_plan_index: dict[int, str],
        existing_diagram_ids: set[str] | None = None,
    ) -> tuple[list[Diagram], DiagramSpecGenerationReport]:
        """Generate one Diagram per design-diagram beat across all concept_plans.

        ``topic_id_by_plan_index`` maps the position of each ConceptTeachingPlan
        in ``concept_plans`` to its source topic_id (the kernel's
        ConceptTeachingPlan doesn't carry topic_id directly).
        """
        existing = set(existing_diagram_ids or ())
        report = DiagramSpecGenerationReport()
        start = time.monotonic()

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks: list[asyncio.Task[Diagram | None]] = []

        for plan_index, plan in enumerate(concept_plans):
            topic_id = topic_id_by_plan_index.get(plan_index)
            if not topic_id:
                logger.warning(
                    "diagram_spec_generator.no_topic_for_plan",
                    extra={
                        "plan_index": plan_index,
                        "concept_title": plan.concept_title,
                    },
                )
                continue
            topic = topics_by_id.get(topic_id)
            if topic is None:
                logger.warning(
                    "diagram_spec_generator.unknown_topic",
                    extra={"topic_id": topic_id},
                )
                continue
            for beat_index, beat in enumerate(plan.beats):
                report.beats_seen += 1
                if beat.visual is None:
                    continue
                if beat.visual.tool not in DESIGN_DIAGRAM_TOOLS:
                    continue
                report.beats_design_diagram += 1
                tasks.append(
                    asyncio.create_task(
                        self._generate_one(
                            topic,
                            plan,
                            beat,
                            beat_index,
                            existing,
                            semaphore,
                            report,
                        ),
                    ),
                )

        results: list[Diagram | None] = await asyncio.gather(*tasks) if tasks else []
        diagrams: list[Diagram] = [d for d in results if d is not None]
        report.diagrams_generated = len(diagrams)
        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return diagrams, report

    async def _generate_one(
        self,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
        beat_index: int,
        existing: set[str],
        semaphore: asyncio.Semaphore,
        report: DiagramSpecGenerationReport,
    ) -> Diagram | None:
        async with semaphore:
            try:
                diagram = await self._generate_for_beat_impl(
                    topic,
                    plan,
                    beat,
                    beat_index,
                    hint="",
                )
                if diagram is None:
                    return None
                if diagram.diagram_id in existing:
                    return None
                existing.add(diagram.diagram_id)
                return diagram
            except Exception as e:  # noqa: BLE001 — any LLM/parse error is recoverable
                logger.warning(
                    "DiagramSpecGenerator failed for %s beat %d: %s",
                    topic.topic_id,
                    beat_index,
                    e,
                )
                report.failures.append(f"{topic.topic_id}_b{beat_index}: {e}")
                return None

    async def regenerate_for_beat(
        self,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
        beat_index: int,
        *,
        hint: str,
    ) -> Diagram | None:
        """Re-generate one beat's diagram with a QA-corrective hint.

        Called from the DiagramQA retry loop. Not semaphore-bounded — caller
        controls concurrency at the QA level. Raises propagate to the caller
        so the QA loop can flag needs_review.
        """
        return await self._generate_for_beat_impl(
            topic,
            plan,
            beat,
            beat_index,
            hint=hint,
        )

    async def _generate_for_beat_impl(
        self,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
        beat_index: int,
        *,
        hint: str,
    ) -> Diagram | None:
        if beat.visual is None or beat.visual.tool not in DESIGN_DIAGRAM_TOOLS:
            return None
        brief = self._build_brief(beat, beat_index)
        context = self._build_context(topic, plan, beat_index)
        user_prompt = build_design_diagram_user_prompt(
            brief, context=context, hint=hint
        )
        response = await asyncio.to_thread(
            self.llm.generate_json,
            DIAGRAM_SYSTEM_PROMPT,
            user_prompt,
        )
        spec = self._parse_response(response.content)
        if not isinstance(spec, dict) or not spec.get("elements"):
            logger.warning(
                "diagram_spec_generator.missing_elements",
                extra={"topic_id": topic.topic_id, "beat_index": beat_index},
            )
            return None
        name = (
            spec.get("title")
            or beat.visual.description[:60].strip()
            or topic.topic_name
        ).strip()
        description = beat.visual.description.strip() or name
        suffix = f"beat{beat_index}_{name}"
        if hint:
            suffix += "_retry"
        diagram_id = generate_diagram_uid(topic.topic_id, suffix)
        return Diagram(
            diagram_id=diagram_id,
            renderer=DiagramRenderer.SVG,
            render_data=spec,
            description=description,
            linked_topic_ids=[topic.topic_id],
            linked_beat_id=f"{topic.topic_id}_b{beat_index}",
            presentation_mode=_presentation_mode_for_beat(beat.beat_type),  # type: ignore[arg-type]
        )

    @staticmethod
    def _build_brief(beat: TeachingBeat, beat_index: int) -> str:
        v = beat.visual
        assert v is not None  # gated by caller
        zone_hint = f" (board zone: {v.zone})" if v.zone else ""
        builds_on = f"\nBuilds on prior visual: {v.builds_on}" if v.builds_on else ""
        return f"Beat {beat_index} ({beat.beat_type}){zone_hint}: {v.description}{builds_on}"

    @staticmethod
    def _build_context(
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat_index: int,
    ) -> str:
        prior_visuals: list[str] = []
        for i, b in enumerate(plan.beats[:beat_index]):
            if b.visual is not None and b.visual.tool in DESIGN_DIAGRAM_TOOLS:
                prior_visuals.append(
                    f"- beat {i} ({b.beat_type}): {b.visual.description[:140]}"
                )
        prior_section = ""
        if prior_visuals:
            prior_section = "\n## Prior design diagrams in this concept:\n" + "\n".join(
                prior_visuals
            )
        speech = (
            plan.beats[beat_index].speech_guidance
            if beat_index < len(plan.beats)
            else ""
        )
        return (
            f"Parent topic: {topic.topic_name}\n"
            f"Topic understanding: {topic.our_understanding[:300]}...\n"
            f"Speech for this beat: {speech[:300]}"
            f"{prior_section}"
        )

    @staticmethod
    def _parse_response(raw: str) -> dict:
        stripped = raw.strip()
        if stripped.startswith("```"):
            first_nl = stripped.index("\n") if "\n" in stripped else 3
            stripped = stripped[first_nl + 1 :]
            if stripped.endswith("```"):
                stripped = stripped[:-3].strip()
        return json.loads(stripped)
