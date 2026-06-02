"""LessonDiagramGenerator — per-DiagramRequirement DiagramSpec generation
(doc 19 Phase D).

Sits ALONGSIDE the existing `DiagramSpecGenerator` (per-beat, free-text brief).
Phase H will be the cutover where the pipeline calls this instead. Until then
the legacy path is untouched.

The coupling contract is enforced by `_validate_required_elements`: every
`element_id` declared in the `DiagramRequirement.required_elements` MUST exist
in BOTH `spec["elements"][i].id` AND `spec["dictionary"][element_id]`. On
failure the generator retries once with a feedback message naming the missing
ids; on second failure it returns None and downstream tolerates the gap.

Text-JSON parsing (not tool-use) mirrors the legacy generator — DiagramSpec
has no Pydantic model and the element-types are polymorphic. The validation
we care about is content (id presence), not shape (schema), so JSON-as-text
is fine.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.id_generator import generate_diagram_uid
from lecture_pipeline_v2.llm.base import LLMProvider
from lecture_pipeline_v2.llm.factory import create_llm_provider
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_prompts import (
    LESSON_DIAGRAM_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    DiagramRequirement,
)
from lecture_pipeline_v2.curriculum.models import Diagram, DiagramRenderer

logger = structlog.get_logger()


_MAX_TOKENS = 8192
_MAX_ATTEMPTS = 2
_DEFAULT_CONCURRENCY = 5


@dataclass
class LessonDiagramGenerationReport:
    requirements_seen: int = 0
    diagrams_generated: int = 0
    failures: list[str] = field(default_factory=list)
    retries_used: int = 0
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"LessonDiagramGenerator — {self.diagrams_generated} diagrams "
            f"from {self.requirements_seen} requirements, "
            f"{len(self.failures)} failures, {self.retries_used} retries, "
            f"{self.elapsed_seconds:.1f}s"
        )


class LessonDiagramGenerator:
    """Generates a `Diagram` per `DiagramRequirement`, enforcing the
    element_id coupling contract.

    Pinning behavior: `diagram_id` on the resulting `Diagram` is ALWAYS
    `requirement.diagram_id` (the spec's `title`/`id` is ignored for ID
    purposes). This mirrors LessonPlanner's topic_id pin — the curriculum
    owns identity, not the LLM.
    """

    def __init__(
        self,
        config: PipelineConfig,
        *,
        concurrency: int = _DEFAULT_CONCURRENCY,
        provider: LLMProvider | None = None,
    ) -> None:
        self.config = config
        self.concurrency = max(1, concurrency)
        self._provider = provider or create_llm_provider(config.llm)

    async def generate_for_requirements(
        self,
        requirements: list[tuple[str, str, DiagramRequirement]],
    ) -> tuple[list[Diagram], LessonDiagramGenerationReport]:
        """Generate one Diagram per (chapter_id, topic_id, requirement) tuple.

        Failed requirements are DROPPED from the result list (not returned as
        None entries). Callers can `len(result) < len(requirements)` to detect
        partial failures, and `report.failures` lists the offenders.
        """
        report = LessonDiagramGenerationReport(requirements_seen=len(requirements))
        start = time.monotonic()

        if not requirements:
            report.elapsed_seconds = time.monotonic() - start
            return [], report

        semaphore = asyncio.Semaphore(self.concurrency)

        async def _run_one(
            chapter_id: str, topic_id: str, requirement: DiagramRequirement
        ) -> Diagram | None:
            async with semaphore:
                return await self._generate_one_with_retry(
                    chapter_id=chapter_id,
                    topic_id=topic_id,
                    requirement=requirement,
                    report=report,
                )

        results = await asyncio.gather(
            *[_run_one(c, t, r) for (c, t, r) in requirements]
        )
        diagrams = [d for d in results if d is not None]
        report.diagrams_generated = len(diagrams)
        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return diagrams, report

    async def generate_one_requirement(
        self,
        *,
        chapter_id: str,
        topic_id: str,
        requirement: DiagramRequirement,
        prior_quality_feedback: str | None = None,
        report: LessonDiagramGenerationReport | None = None,
    ) -> Diagram | None:
        """Public single-requirement entrypoint. Phase F quality gate calls
        this to re-generate one diagram with judge feedback in the user
        message. The internal 2-attempt validator retry budget still applies.
        """
        local_report = report or LessonDiagramGenerationReport(requirements_seen=1)
        return await self._generate_one_with_retry(
            chapter_id=chapter_id,
            topic_id=topic_id,
            requirement=requirement,
            report=local_report,
            prior_quality_feedback=prior_quality_feedback,
        )

    async def _generate_one_with_retry(
        self,
        *,
        chapter_id: str,
        topic_id: str,
        requirement: DiagramRequirement,
        report: LessonDiagramGenerationReport,
        prior_quality_feedback: str | None = None,
    ) -> Diagram | None:
        """Two attempts. First clean; second with prior-error feedback. Returns
        the constructed Diagram (with pinned diagram_id) or None on
        unrecoverable failure.

        `prior_quality_feedback` (Phase F) is the judge's note from a prior
        attempt at an EARLIER diagram that was element-id-complete but
        visually below the bar. It sits in EVERY attempt's user message.
        """
        prior_error: str | None = None

        for attempt in range(_MAX_ATTEMPTS):
            try:
                spec = await self._call_llm(
                    requirement=requirement,
                    prior_validation_error=prior_error,
                    prior_quality_feedback=prior_quality_feedback,
                )
            except Exception as exc:  # noqa: BLE001 — defensive boundary
                logger.warning(
                    "lesson_diagram_generator.unexpected_exception",
                    chapter_id=chapter_id,
                    topic_id=topic_id,
                    diagram_id=requirement.diagram_id,
                    attempt=attempt,
                    error=str(exc),
                )
                spec = None

            if spec is None:
                # No parse / no response — retry budget allows one more try,
                # but without specific feedback (we don't know what went
                # wrong on the wire).
                prior_error = (
                    "Your previous attempt produced no usable JSON. Re-emit "
                    "a complete, well-formed DiagramSpec following the system "
                    "instructions exactly."
                )
                if attempt + 1 < _MAX_ATTEMPTS:
                    report.retries_used += 1
                continue

            validation_error = _validate_required_elements(spec, requirement)
            if validation_error is None:
                if attempt > 0:
                    logger.info(
                        "lesson_diagram_generator.recovered_on_retry",
                        chapter_id=chapter_id,
                        topic_id=topic_id,
                        diagram_id=requirement.diagram_id,
                    )
                return _build_diagram(spec, requirement, topic_id)

            logger.warning(
                "lesson_diagram_generator.validation_failed",
                chapter_id=chapter_id,
                topic_id=topic_id,
                diagram_id=requirement.diagram_id,
                attempt=attempt,
                error=validation_error,
            )
            prior_error = validation_error
            if attempt + 1 < _MAX_ATTEMPTS:
                report.retries_used += 1

        # All attempts exhausted.
        report.failures.append(
            f"{topic_id}::{requirement.diagram_id}: {prior_error or 'unknown failure'}"
        )
        logger.error(
            "lesson_diagram_generator.final_failure",
            chapter_id=chapter_id,
            topic_id=topic_id,
            diagram_id=requirement.diagram_id,
        )
        return None

    async def _call_llm(
        self,
        *,
        requirement: DiagramRequirement,
        prior_validation_error: str | None,
        prior_quality_feedback: str | None = None,
    ) -> dict[str, Any] | None:
        """One LLM round-trip via the configured provider. Returns the parsed
        spec dict, or None if the response had no usable text content. JSON
        parse errors bubble as exceptions (caller catches at the boundary).
        """
        user_message = _build_user_message(
            requirement, prior_validation_error, prior_quality_feedback
        )

        response = await self._provider.agenerate_text(
            LESSON_DIAGRAM_SYSTEM_PROMPT,
            user_message,
            max_tokens=_MAX_TOKENS,
        )

        text = (response.content or "").strip()
        if not text:
            logger.warning(
                "lesson_diagram_generator.no_text_in_response",
                diagram_id=requirement.diagram_id,
            )
            return None

        try:
            return _parse_json(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "lesson_diagram_generator.json_parse_failed",
                diagram_id=requirement.diagram_id,
                error=str(exc),
            )
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Validators + builders (module-level so tests can hit them directly).
# ─────────────────────────────────────────────────────────────────────────────


def _validate_required_elements(
    spec: dict[str, Any],
    requirement: DiagramRequirement,
) -> str | None:
    """Return None if the spec satisfies the requirement, else a feedback string.

    Checks the two-axis contract: every required `element_id` must appear in
    BOTH `spec["dictionary"]` (as a key) AND `spec["elements"]` (as the `id`
    of some entry).
    """
    if not isinstance(spec, dict):
        return "Spec is not a JSON object. Emit a single top-level JSON object."

    dictionary = spec.get("dictionary")
    if not isinstance(dictionary, dict):
        return (
            "Missing or non-object `dictionary` field. Every required "
            "element MUST have a `dictionary` entry."
        )

    elements = spec.get("elements")
    if not isinstance(elements, list):
        return (
            "Missing or non-list `elements` field. Every required element "
            "MUST appear in `elements[]` with a matching `id`."
        )

    element_ids_in_elements: set[str] = set()
    for el in elements:
        if isinstance(el, dict):
            eid = el.get("id")
            if isinstance(eid, str) and eid:
                element_ids_in_elements.add(eid)

    missing_from_dict: list[str] = []
    missing_from_elements: list[str] = []
    for req in requirement.required_elements:
        if req.element_id not in dictionary:
            missing_from_dict.append(req.element_id)
        if req.element_id not in element_ids_in_elements:
            missing_from_elements.append(req.element_id)

    if not missing_from_dict and not missing_from_elements:
        return None

    parts: list[str] = []
    if missing_from_elements:
        parts.append(
            f"elements[] missing entries with id: {sorted(missing_from_elements)!r}"
        )
    if missing_from_dict:
        parts.append(f"dictionary{{}} missing keys: {sorted(missing_from_dict)!r}")
    return "; ".join(parts)


def _build_diagram(
    spec: dict[str, Any],
    requirement: DiagramRequirement,
    topic_id: str,
) -> Diagram:
    """Construct the Diagram object. `diagram_id` is pinned to
    `requirement.diagram_id` (LLM cannot rename); `linked_topic_ids` carries
    the caller's topic_id so the manifest can resolve back.
    """
    name_for_uid = requirement.diagram_id
    diagram_id = generate_diagram_uid(topic_id, name_for_uid)
    description = requirement.purpose.strip() or requirement.diagram_id
    return Diagram(
        diagram_id=diagram_id,
        renderer=DiagramRenderer.SVG,
        render_data=spec,
        description=description,
        linked_topic_ids=[topic_id],
        linked_beat_id="",  # Phase D doesn't use the per-beat linkage.
        presentation_mode=requirement.presentation_mode,
    )


def _build_user_message(
    requirement: DiagramRequirement,
    prior_validation_error: str | None,
    prior_quality_feedback: str | None = None,
) -> str:
    """Compose the per-requirement user message.

    Lists `(element_id, role, description)` triples as the structural contract
    the spec must satisfy. On retry, appends the prior failure message so the
    LLM can self-correct. Phase F also threads `prior_quality_feedback` from
    the DiagramQA judge when the gate requests a regen.
    """
    parts: list[str] = []
    parts.append(f"## Diagram requirement: {requirement.diagram_id}")
    parts.append(f"Purpose: {requirement.purpose.strip()}")
    parts.append(f"Presentation mode: {requirement.presentation_mode}")
    parts.append("")
    parts.append("## REQUIRED elements (these element_ids MUST exist)")
    for el in requirement.required_elements:
        parts.append(
            f"- `{el.element_id}` (role: {el.role}) — {el.description.strip()}"
        )
    parts.append("")
    parts.append(
        "Generate the DiagramSpec JSON. Every required `element_id` above "
        "must appear in BOTH `elements[]` (as `id`) AND `dictionary{}` (as "
        "a key with `bounds` populated). You may add additional elements as "
        "context. Return ONE JSON object — no markdown fences, no commentary."
    )

    if prior_validation_error:
        parts.append("")
        parts.append("## RETRY — your previous DiagramSpec failed validation")
        parts.append(
            "Fix EXACTLY what is described below. Do not change the rest of "
            "the spec — keep the elements and dictionary entries that were "
            "already correct."
        )
        parts.append("")
        parts.append("```")
        parts.append(_clip(prior_validation_error, 2000))
        parts.append("```")

    # Phase F — quality-gate retry feedback from the DiagramQA judge.
    if prior_quality_feedback:
        parts.append("")
        parts.append(
            "## QUALITY RETRY — judge said the previous diagram was below the bar"
        )
        parts.append(
            "A prior version of this DiagramSpec was element-id-complete but "
            "scored below the visual-quality threshold. The judge's specific "
            "suggestion is below. Address it directly; keep what was working."
        )
        parts.append("")
        parts.append("```")
        parts.append(_clip(prior_quality_feedback, 2000))
        parts.append("```")

    return "\n".join(parts)


def _parse_json(raw: str) -> dict[str, Any]:
    """Strip optional markdown fences and parse as JSON.

    Mirrors `DiagramSpecGenerator._parse_response` so existing test fixtures
    that emit fenced JSON keep working through Phase H.
    """
    stripped = raw.strip()
    if stripped.startswith("```"):
        first_nl = stripped.index("\n") if "\n" in stripped else 3
        stripped = stripped[first_nl + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    return json.loads(stripped)


def _clip(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "…"
    return text
