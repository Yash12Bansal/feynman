"""Phase 4d — BeatNarrationWriter.

One LLM call per `TeachingBeat`. Handles role-vocabulary resolution from the
active diagram (Phase 4c), prior-beat carry-forward for cohesion, and graceful
failure (empty text + `needs_review=True`, never re-raises). Emits
`BeatNarration` Pydantic objects ready for `LengthEnforcer` + `ScriptAssembler`.

Failure modes (never block the pipeline):
  * LLM exception → return `BeatNarration(text="", needs_review=True)`.
  * Empty / whitespace-only response → same.
  * Word count <50% or >200% of target → `needs_review=True` (keep text).
  * Markdown code fence in response → stripped on the way out.

`rewrite()` is the entry point `LengthEnforcer` Pass 3 calls when a beat needs
a shorter version. It rebuilds the same prompt with a tighter target.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from typing import TYPE_CHECKING

from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat

from ...config import BeatNarrationConfig
from ...llm.base import LLMProvider
from ..models import Chapter, Diagram, Topic
from .models import BeatNarration
from .prompts import BEAT_NARRATION_SYSTEM_PROMPT, build_beat_user_prompt

if TYPE_CHECKING:  # avoid runtime cycle with lecture_plan.models
    pass

logger = logging.getLogger(__name__)

# Strip the chunker's <<MARKER>> tokens before counting words.
MARKER_RE = re.compile(r"<<[^>]+>>")
# Pull marker IDs (e.g., `|id=eq-1>>`) into `audio_targets`.
ID_ATTR_RE = re.compile(r"\|id=([\w\-]+)")


def _estimate_seconds(text: str, wps: float) -> float:
    cleaned = MARKER_RE.sub("", text).strip()
    if not cleaned:
        return 0.0
    return len(cleaned.split()) / max(wps, 0.1)


def _extract_audio_targets(text: str) -> list[str]:
    return ID_ATTR_RE.findall(text)


def _strip_markdown_fence(text: str) -> str:
    """LLMs occasionally wrap output in ```...```. Strip if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    nl = stripped.find("\n")
    if nl == -1:
        # `\`\`\`json{...}\`\`\`` on one line — strip leading + trailing fences.
        body = stripped[3:]
        if body.endswith("```"):
            body = body[:-3]
        return body.strip()
    body = stripped[nl + 1 :]
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()


@dataclasses.dataclass
class BeatNarrationReport:
    chapters_processed: int = 0
    beats_seen: int = 0
    beats_written: int = 0
    beats_needing_review: int = 0
    failures: list[str] = dataclasses.field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"BeatNarrationWriter — {self.beats_written}/{self.beats_seen} beats "
            f"across {self.chapters_processed} chapters, "
            f"{self.beats_needing_review} need_review, "
            f"{len(self.failures)} failures, {self.elapsed_seconds:.1f}s"
        )


class BeatNarrationWriter:
    """Per-beat narration writer (async, semaphore-bounded)."""

    def __init__(self, llm: LLMProvider, *, config: BeatNarrationConfig) -> None:
        self.llm = llm
        self.config = config

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    async def write_for_chapter(
        self,
        *,
        chapter: Chapter,
        topics_by_id: dict[str, Topic],
        diagrams_by_beat_id: dict[str, Diagram],
        rewrite_context_out: dict[str, tuple[Topic, ConceptTeachingPlan, TeachingBeat]]
        | None = None,
    ) -> tuple[list[BeatNarration], BeatNarrationReport]:
        """Walk this chapter's concept_plans and write one BeatNarration per beat.

        Populates ``rewrite_context_out[beat_id] = (topic, plan, beat)`` if the
        caller passed a dict, so `LengthEnforcer.trim` can re-invoke
        `rewrite()` on the longest non-structural beat.
        """
        report = BeatNarrationReport()
        report.chapters_processed = 1
        start = time.monotonic()
        plans = chapter.concept_plans or []
        if not plans or chapter.lecture_plan is None:
            report.elapsed_seconds = time.monotonic() - start
            return [], report

        lp = chapter.lecture_plan
        sem = asyncio.Semaphore(max(1, self.config.concurrency))
        tasks: list[asyncio.Task[BeatNarration | None]] = []

        # Beats are written in the order they appear inside each concept_plan;
        # plans iterate in the order ConceptPlanner emitted them (matches
        # lecture_plan.concept_sequence for the present chapter).
        ordered_jobs: list[tuple[Topic, ConceptTeachingPlan, TeachingBeat, int]] = []
        for plan in plans:
            topic_id = self._resolve_topic_id(plan, lp.concept_sequence)
            topic = topics_by_id.get(topic_id or "")
            if topic is None:
                logger.info(
                    "beat_narration.skip_unknown_topic chapter=%s plan_concept=%s",
                    chapter.chapter_id,
                    plan.concept_title,
                )
                continue
            for beat_index, beat in enumerate(plan.beats):
                report.beats_seen += 1
                ordered_jobs.append((topic, plan, beat, beat_index))
                if rewrite_context_out is not None:
                    beat_id = f"{topic.topic_id}_b{beat_index}"
                    rewrite_context_out[beat_id] = (topic, plan, beat)

        # Build the per-concept "prior beats" sliding window upfront so async
        # tasks don't fight over it. We seed each beat's window with the
        # planner's `speech_guidance` for the prior 1-2 beats — generated text
        # isn't available yet (tasks run in parallel). Phase 4e can switch to
        # using actual generated text once we add a serial / staged pass.
        prior_texts_by_beat_id: dict[str, list[str]] = {}
        for topic, plan, beat, beat_index in ordered_jobs:
            beat_id = f"{topic.topic_id}_b{beat_index}"
            # Use prior beats' speech_guidance as a proxy for cohesion (we
            # don't have generated text yet — generation is parallel).
            prior_guidance: list[str] = []
            for prior_idx in range(max(0, beat_index - 2), beat_index):
                prior_beat = plan.beats[prior_idx]
                if prior_beat.speech_guidance:
                    prior_guidance.append(
                        f"[beat {prior_idx} {prior_beat.beat_type}] {prior_beat.speech_guidance}"
                    )
            prior_texts_by_beat_id[beat_id] = prior_guidance

        # Resolve active diagram per beat (Phase 4c carry-forward).
        active_diagram_by_beat_id: dict[str, Diagram | None] = {}
        for topic, plan, beat, beat_index in ordered_jobs:
            beat_id = f"{topic.topic_id}_b{beat_index}"
            active_diagram_by_beat_id[beat_id] = self._resolve_active_diagram(
                topic_id=topic.topic_id,
                plan_beats=plan.beats,
                beat_index=beat_index,
                diagrams_by_beat_id=diagrams_by_beat_id,
            )

        chapter_arc = lp.chapter_arc or ""

        for topic, plan, beat, beat_index in ordered_jobs:
            beat_id = f"{topic.topic_id}_b{beat_index}"
            tasks.append(
                asyncio.create_task(
                    self._write_one_bounded(
                        sem=sem,
                        topic=topic,
                        plan=plan,
                        beat=beat,
                        beat_index=beat_index,
                        chapter_arc=chapter_arc,
                        active_diagram=active_diagram_by_beat_id[beat_id],
                        prior_beat_texts=prior_texts_by_beat_id[beat_id],
                        report=report,
                    )
                )
            )

        results = await asyncio.gather(*tasks) if tasks else []
        narrations: list[BeatNarration] = [r for r in results if r is not None]
        report.beats_written = sum(1 for n in narrations if n.text)
        report.beats_needing_review = sum(1 for n in narrations if n.needs_review)
        report.elapsed_seconds = time.monotonic() - start
        return narrations, report

    async def write_one(
        self,
        *,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
        beat_index: int,
        chapter_arc: str,
        active_diagram: Diagram | None,
        prior_beat_texts: list[str],
    ) -> BeatNarration:
        """Public entry — single-beat write (no semaphore). Used by tests + rewrite."""
        return await self._write_one_impl(
            topic=topic,
            plan=plan,
            beat=beat,
            beat_index=beat_index,
            chapter_arc=chapter_arc,
            active_diagram=active_diagram,
            prior_beat_texts=prior_beat_texts,
            target_override=None,
        )

    async def rewrite(
        self,
        narration: BeatNarration,
        *,
        new_target_seconds: int,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
        chapter_arc: str = "",
        active_diagram: Diagram | None = None,
        prior_beat_texts: list[str] | None = None,
    ) -> BeatNarration:
        """LengthEnforcer Pass 3 — re-call the writer with a tighter target."""
        return await self._write_one_impl(
            topic=topic,
            plan=plan,
            beat=beat,
            beat_index=narration.beat_index,
            chapter_arc=chapter_arc,
            active_diagram=active_diagram,
            prior_beat_texts=prior_beat_texts or [],
            target_override=new_target_seconds,
        )

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    async def _write_one_bounded(
        self,
        *,
        sem: asyncio.Semaphore,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
        beat_index: int,
        chapter_arc: str,
        active_diagram: Diagram | None,
        prior_beat_texts: list[str],
        report: BeatNarrationReport,
    ) -> BeatNarration | None:
        async with sem:
            try:
                return await self._write_one_impl(
                    topic=topic,
                    plan=plan,
                    beat=beat,
                    beat_index=beat_index,
                    chapter_arc=chapter_arc,
                    active_diagram=active_diagram,
                    prior_beat_texts=prior_beat_texts,
                    target_override=None,
                )
            except Exception as e:  # noqa: BLE001 - write_one already catches; this is a belt-and-suspenders guard
                beat_id = f"{topic.topic_id}_b{beat_index}"
                report.failures.append(f"{beat_id}: {e}")
                logger.warning("BeatNarrationWriter.unhandled %s: %s", beat_id, e)
                return BeatNarration(
                    beat_id=beat_id,
                    topic_id=topic.topic_id,
                    beat_index=beat_index,
                    beat_type=beat.beat_type,
                    text="",
                    target_duration_seconds=beat.target_duration_seconds,
                    needs_review=True,
                    example_source=beat.example_source,
                    book_example_ref=beat.book_example_ref,
                )

    async def _write_one_impl(
        self,
        *,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
        beat_index: int,
        chapter_arc: str,
        active_diagram: Diagram | None,
        prior_beat_texts: list[str],
        target_override: int | None,
    ) -> BeatNarration:
        beat_id = f"{topic.topic_id}_b{beat_index}"
        raw_target = (
            target_override
            if target_override is not None
            else beat.target_duration_seconds
        )
        target_seconds = max(
            self.config.min_target_seconds,
            min(self.config.max_target_seconds, int(raw_target)),
        )
        target_words = max(8, int(target_seconds * self.config.target_wps))

        active_diagram_spec = active_diagram.render_data if active_diagram else None
        active_diagram_id = active_diagram.diagram_id if active_diagram else None

        # Resolve the BookExample if this beat carries a book-source reference.
        # Tolerate out-of-bounds (shouldn't happen — allocator owns the index —
        # but if topics change between plan + write we degrade to "no anchor").
        book_example_obj = None
        if (
            beat.example_source == "book"
            and beat.book_example_ref is not None
            and 0 <= beat.book_example_ref < len(topic.book_examples)
        ):
            book_example_obj = topic.book_examples[beat.book_example_ref]

        user_prompt = build_beat_user_prompt(
            beat=beat,
            beat_index=beat_index,
            beat_id=beat_id,
            topic=topic,
            concept_plan=plan,
            chapter_arc=chapter_arc,
            active_diagram=active_diagram_spec,
            active_diagram_id=active_diagram_id,
            target_seconds=target_seconds,
            target_words=target_words,
            prior_beat_texts=prior_beat_texts,
            book_example=book_example_obj,
        )

        try:
            response = await asyncio.to_thread(
                self.llm.generate, BEAT_NARRATION_SYSTEM_PROMPT, user_prompt
            )
            text = _strip_markdown_fence(response.content or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("BeatNarrationWriter.llm_failed %s: %s", beat_id, e)
            return BeatNarration(
                beat_id=beat_id,
                topic_id=topic.topic_id,
                beat_index=beat_index,
                beat_type=beat.beat_type,
                text="",
                target_duration_seconds=target_seconds,
                needs_review=True,
                example_source=beat.example_source,
                book_example_ref=beat.book_example_ref,
            )

        if not text:
            return BeatNarration(
                beat_id=beat_id,
                topic_id=topic.topic_id,
                beat_index=beat_index,
                beat_type=beat.beat_type,
                text="",
                target_duration_seconds=target_seconds,
                needs_review=True,
                example_source=beat.example_source,
                book_example_ref=beat.book_example_ref,
            )

        estimated = _estimate_seconds(text, self.config.target_wps)
        word_count = len(MARKER_RE.sub("", text).split())
        needs_review = (
            word_count < target_words * 0.5 or word_count > target_words * 2.0
        )

        return BeatNarration(
            beat_id=beat_id,
            topic_id=topic.topic_id,
            beat_index=beat_index,
            beat_type=beat.beat_type,
            text=text,
            target_duration_seconds=target_seconds,
            estimated_duration_seconds=estimated,
            audio_targets=_extract_audio_targets(text),
            needs_review=needs_review,
            example_source=beat.example_source,
            book_example_ref=beat.book_example_ref,
        )

    def _resolve_active_diagram(
        self,
        *,
        topic_id: str,
        plan_beats: list[TeachingBeat],
        beat_index: int,
        diagrams_by_beat_id: dict[str, Diagram],
    ) -> Diagram | None:
        """Return the diagram visible at this beat — own draw, or last prior draw."""
        own_id = f"{topic_id}_b{beat_index}"
        d = diagrams_by_beat_id.get(own_id)
        if d is not None:
            return d
        for i in range(beat_index - 1, -1, -1):
            prior_id = f"{topic_id}_b{i}"
            d = diagrams_by_beat_id.get(prior_id)
            if d is not None:
                return d
        return None

    def _resolve_topic_id(
        self,
        plan: ConceptTeachingPlan,
        concept_sequence: list[str],
    ) -> str | None:
        """ConceptPlanner stores `concept_index` matching the plan's position in
        the chapter's concept_sequence (ChapterLecturePlanner output). Out-of-
        range plans return None and are skipped.
        """
        idx = plan.concept_index
        if 0 <= idx < len(concept_sequence):
            return concept_sequence[idx]
        return None
