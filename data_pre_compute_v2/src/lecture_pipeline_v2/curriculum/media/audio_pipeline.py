"""Audio pipeline — turn chapter scripts into per-topic + per-chapter manifests.

For each chapter script (one per chapter):
  1. For each topic segment, run TTS on the standalone narration:
       - Split by markers → for each text fragment call TTS → write audio file
       - Diagram markers → emit ShowDiagramEvent
       - Pause markers → emit PauseEvent
     → assemble Topic.standalone_manifest
  2. For the chapter narration:
       - For each topic segment, do the same split-and-TTS on narration_chapter
       - Prepend TopicStartEvent before each segment's events
     → assemble Chapter.chapter_manifest

Audio files live in artifacts_base/audio/<chapter_id>/<topic_id>_<role>_<index>.<ext>.
The manifest stores file:// URLs (or whatever artifact url_prefix is set to).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ...config import ArtifactsConfig, LayoutConfig, TTSConfig
from ...tts.base import TTSProvider
from ...tts.chunker import (
    AnimateParamFragment,
    AnswerFragment,
    BracketFragment,
    CalloutFragment,
    ClearAnnotationsFragment,
    DiagramFragment,
    EquationFragment,
    FocusFragment,
    HighlightFragment,
    KeyPointFragment,
    MarkPointFragment,
    NewPageFragment,
    PageBreakFragment,
    PauseFragment,
    PinFragment,
    PointAtFragment,
    PulseFragment,
    REVEAL_ALL_STEP,
    RevealStepFragment,
    SectionFragment,
    SetParamFragment,
    StepFragment,
    StrikeFragment,
    TextEntryFragment,
    TextFragment,
    TraceFragment,
    UnfocusFragment,
    WriteMarginFragment,
    split_script,
)
from ..ingestion.visual_term_index import build_concept_visual_index
from ..lecture_script.models import ChapterScript
from ..manifest_composer import ManifestComposer, MeasurementService
from ..models import (
    AnimateParameterEvent,
    AudioEvent,
    BracketEvent,
    CalloutEvent,
    Chapter,
    ClearAnnotationsEvent,
    Diagram,
    FocusEvent,
    HighlightEvent,
    Manifest,
    MarkPointEvent,
    NewPageEvent,
    PageBreakEvent,
    PauseEvent,
    PinEvent,
    PointAtEvent,
    PulseEvent,
    RevealStepEvent,
    SetParameterEvent,
    ShowDiagramEvent,
    StrikethroughEvent,
    Topic,
    TopicStartEvent,
    TraceEvent,
    UnfocusEvent,
    WriteAnswerEvent,
    WriteEquationEvent,
    WriteKeyPointEvent,
    WriteMarginEvent,
    WriteSectionEvent,
    WriteStepEvent,
    WriteTextEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class AudioPipelineReport:
    chapters_processed: int = 0
    topics_with_standalone_audio: int = 0
    chapters_with_chapter_audio: int = 0
    audio_files_written: int = 0
    audio_files_skipped_existing: int = 0
    elapsed_seconds: float = 0.0
    failures: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Audio pipeline — {self.chapters_with_chapter_audio} chapter manifests, "
            f"{self.topics_with_standalone_audio} topic standalones, "
            f"{self.audio_files_written} files written "
            f"({self.audio_files_skipped_existing} reused), "
            f"{len(self.failures)} failures, "
            f"{self.elapsed_seconds:.1f}s"
        )


class AudioPipeline:
    """Orchestrates TTS calls and manifest assembly."""

    def __init__(
        self,
        tts: TTSProvider,
        tts_config: TTSConfig,
        artifacts: ArtifactsConfig,
        layout: LayoutConfig | None = None,
        *,
        concurrency: int = 4,
    ):
        self.tts = tts
        self.tts_config = tts_config
        self.artifacts = artifacts
        self.layout = layout
        self.concurrency = concurrency

    async def build_for_book(
        self,
        chapters: list[Chapter],
        topics: list[Topic],
        chapter_scripts: dict[str, ChapterScript],
        diagrams: list[Diagram] | None = None,
    ) -> AudioPipelineReport:
        report = AudioPipelineReport()
        start = time.monotonic()

        topic_by_id = {t.topic_id: t for t in topics}
        chapter_by_id = {c.chapter_id: c for c in chapters}
        # Phase 2: composer needs each diagram's render_data["dictionary"]
        # to validate roles + read element bounds. Empty map is allowed —
        # composer drops all annotations gracefully.
        diagrams_by_id = {d.diagram_id: d for d in (diagrams or [])}

        # Phase 3: one MeasurementService singleton for the whole book run.
        # Constructed lazily inside `try/finally` so its lifecycle is bracketed.
        measurement: MeasurementService | None = None
        if self.layout is not None:
            cache_dir = Path(self.layout.measurement.cache_dir)
            try:
                measurement = MeasurementService(self.layout, cache_dir)
                await measurement.start()
            except Exception as e:
                logger.warning(
                    "MeasurementService unavailable; falling back to layout-disabled "
                    "composer for this run: %s",
                    e,
                )
                measurement = None

        try:
            semaphore = asyncio.Semaphore(self.concurrency)
            tasks = [
                self._build_for_chapter(
                    chapter_by_id[chapter_id],
                    topic_by_id,
                    script,
                    diagrams_by_id,
                    measurement,
                    semaphore,
                    report,
                )
                for chapter_id, script in chapter_scripts.items()
                if chapter_id in chapter_by_id
            ]
            await asyncio.gather(*tasks)
        finally:
            if measurement is not None:
                try:
                    await measurement.stop()
                except Exception as e:
                    logger.warning("MeasurementService.stop failed: %s", e)
                logger.info("MeasurementService report: %s", measurement.report)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    async def _build_for_chapter(
        self,
        chapter: Chapter,
        topic_by_id: dict[str, Topic],
        script: ChapterScript,
        diagrams_by_id: dict[str, Diagram],
        measurement: MeasurementService | None,
        semaphore: asyncio.Semaphore,
        report: AudioPipelineReport,
    ) -> None:
        async with semaphore:
            try:
                await self._do_build_for_chapter(
                    chapter,
                    topic_by_id,
                    script,
                    diagrams_by_id,
                    measurement,
                    report,
                )
                report.chapters_processed += 1
            except Exception as e:
                logger.exception(
                    "Audio build failed for chapter %s", chapter.chapter_id
                )
                report.failures.append(f"{chapter.chapter_id}: {e}")

    async def _do_build_for_chapter(
        self,
        chapter: Chapter,
        topic_by_id: dict[str, Topic],
        script: ChapterScript,
        diagrams_by_id: dict[str, Diagram],
        measurement: MeasurementService | None,
        report: AudioPipelineReport,
    ) -> None:
        chapter_dir = self._chapter_audio_dir(chapter.chapter_id)
        chapter_dir.mkdir(parents=True, exist_ok=True)

        # Phase 2+3: one composer per chapter holds per-diagram annotation
        # state AND per-chapter page state (resets between chapters).
        # Standalone narrations skip the composer per design doc Q8 —
        # Phase 4 drops standalone entirely.
        composer = ManifestComposer(
            diagrams_by_id=diagrams_by_id,
            layout_config=self.layout,
            measurement=measurement,
            topic_id=chapter.chapter_id,
        )
        chapter_events: list = []

        for seg in script.segments:
            tid = seg["topic_id"]
            topic = topic_by_id.get(tid)
            if topic is None:
                continue

            standalone_text = seg["narration_standalone"]
            topic.standalone_narration_text = standalone_text  # persist raw script
            standalone_fragments = split_script(standalone_text)
            standalone_events = await self._render_fragments(
                fragments=standalone_fragments,
                chapter_dir=chapter_dir,
                topic_id=tid,
                role="standalone",
                report=report,
            )
            topic.standalone_manifest = Manifest(events=standalone_events)
            if standalone_events:
                report.topics_with_standalone_audio += 1

            chapter_text = seg["narration_chapter"]
            chapter_fragments = split_script(chapter_text)
            # Phase 2+3: apply annotation + layout policies before rendering.
            # Composer state persists ACROSS topics within a chapter so:
            #   - cooldown / rolling-window timers stay continuous (Phase 2)
            #   - page state spans topic boundaries (Phase 3 Q19)
            chapter_fragments = await composer.compose(chapter_fragments)
            seg_events = await self._render_fragments(
                fragments=chapter_fragments,
                chapter_dir=chapter_dir,
                topic_id=tid,
                role="chapter",
                report=report,
            )
            chapter_events.append(TopicStartEvent(topic_id=tid))
            chapter_events.extend(seg_events)
            # Tag the topic boundary in the chapter narration for recovery.
            chapter.narration_text += f"\n\n<<TOPIC_START:{tid}>>\n{chapter_text}"

        # Phase 3: close the final page summary at chapter end.
        composer.flush()

        # Workstream B: if the chapter ends on a build_up diagram, flush it to
        # fully-revealed so the lecture never ends on a half-built figure
        # (mirrors the swap-time reveal-all the walker injects mid-stream).
        open_build_up = composer.open_build_up_diagram_id
        if open_build_up and chapter_events:
            chapter_events.append(
                RevealStepEvent(diagram_id=open_build_up, step=REVEAL_ALL_STEP)
            )

        if chapter_events:
            chapter.chapter_manifest = Manifest(events=chapter_events)
            report.chapters_with_chapter_audio += 1
        # Phase 3: persist per-page diagnostic summaries onto the Chapter.
        chapter.pages = list(composer.last_report.pages)
        # feat/unify_boardstate: authoritative board snapshots (1:1 with pages).
        chapter.board_snapshots = list(composer.last_report.board_snapshots)
        # Idea 2: Concept-to-Visual Index. Built from this chapter's diagrams
        # (filtered by topic-id intersection — a diagram belongs to the
        # chapter iff it links to at least one of its topics). Rebuilt every
        # regen-audio so it stays aligned with the diagrams as they evolve.
        chapter_topic_ids = set(chapter.topic_ids)
        chapter_diagrams = [
            d
            for d in diagrams_by_id.values()
            if chapter_topic_ids.intersection(d.linked_topic_ids)
        ]
        chapter.concept_visual_index = build_concept_visual_index(chapter_diagrams)

        # Phase 2+3 telemetry — one composer summary line per chapter.
        logger.info(
            "ManifestComposer (chapter %s): %s",
            chapter.chapter_id,
            composer.last_report.summary(),
        )

    async def _render_fragments(
        self,
        fragments: list,
        chapter_dir: Path,
        topic_id: str,
        role: str,
        report: AudioPipelineReport,
    ) -> list:
        events = []
        text_index = 0
        for frag in fragments:
            if isinstance(frag, TextFragment):
                file_name = _audio_file_name(
                    topic_id=topic_id,
                    role=role,
                    text_index=text_index,
                    text=frag.text,
                    ext=self.tts_config.output_format,
                )
                file_path = chapter_dir / file_name
                if file_path.exists():
                    report.audio_files_skipped_existing += 1
                    duration_ms = self._probe_duration_ms(file_path)
                else:
                    result = await asyncio.to_thread(
                        self.tts.synthesize, frag.text, file_path
                    )
                    duration_ms = result.duration_ms
                    report.audio_files_written += 1
                events.append(
                    AudioEvent(
                        url=self._artifact_url(file_path),
                        duration_ms=duration_ms,
                    )
                )
                text_index += 1
            elif isinstance(frag, DiagramFragment):
                events.append(
                    ShowDiagramEvent(
                        diagram_id=frag.diagram_id,
                        placement=frag.placement,
                        slide_element_bounds=frag.slide_element_bounds,
                        presentation_mode=frag.presentation_mode,
                    )
                )
            elif isinstance(frag, PauseFragment):
                ms = (
                    self.tts_config.pause_short_ms
                    if frag.duration == "short"
                    else self.tts_config.pause_long_ms
                )
                events.append(PauseEvent(duration_ms=ms))
            elif isinstance(frag, SectionFragment):
                events.append(
                    WriteSectionEvent(
                        id=frag.id,
                        title=frag.title,
                        placement=frag.placement,
                    )
                )
            elif isinstance(frag, EquationFragment):
                events.append(
                    WriteEquationEvent(
                        id=frag.id,
                        latex=frag.latex,
                        align_group=frag.align_group,
                        boxed=frag.boxed,
                        placement=frag.placement,
                    )
                )
            elif isinstance(frag, StepFragment):
                events.append(
                    WriteStepEvent(
                        id=frag.id,
                        text=frag.text,
                        indent=frag.indent,
                        placement=frag.placement,
                    )
                )
            elif isinstance(frag, KeyPointFragment):
                events.append(
                    WriteKeyPointEvent(
                        id=frag.id,
                        text=frag.text,
                        placement=frag.placement,
                    )
                )
            elif isinstance(frag, TextEntryFragment):
                events.append(
                    WriteTextEvent(
                        id=frag.id,
                        text=frag.text,
                        placement=frag.placement,
                    )
                )
            elif isinstance(frag, AnswerFragment):
                events.append(
                    WriteAnswerEvent(
                        id=frag.id,
                        text=frag.text,
                        placement=frag.placement,
                    )
                )
            elif isinstance(frag, StrikeFragment):
                events.append(StrikethroughEvent(target_id=frag.target_id))
            elif isinstance(frag, NewPageFragment):
                events.append(
                    NewPageEvent(carry_forward_ids=list(frag.carry_forward_ids))
                )
            elif isinstance(frag, PageBreakFragment):
                # Phase 3: deterministic page break from LayoutPlanner.
                events.append(
                    PageBreakEvent(
                        new_page_index=frag.new_page_index,
                        slide_action=frag.slide_action,
                        next_diagram_id=frag.next_diagram_id,
                        notebook_carry_forward_ids=list(
                            frag.notebook_carry_forward_ids
                        ),
                        reason=frag.reason,
                    )
                )
            # --- Attention-direction events (doc 18 spotlight) ------------
            elif isinstance(frag, FocusFragment):
                # Doc 19 §A-3: prefer target_element_id (stable id resolved
                # from role by the walker). target_role kept for human-
                # readability + back-compat. Co-highlight: target_element_ids
                # carries the full walker-resolved set (empty for single).
                events.append(
                    FocusEvent(
                        diagram_id=frag.diagram_id,
                        target_element_id=frag.element_id or None,
                        target_element_ids=list(frag.element_ids),
                        target_role=frag.role,
                        text=frag.text,
                    )
                )
            elif isinstance(frag, UnfocusFragment):
                events.append(UnfocusEvent(diagram_id=frag.diagram_id))
            # --- New live-annotation events (doc 19 §12) ------------------
            elif isinstance(frag, TraceFragment):
                events.append(
                    TraceEvent(
                        diagram_id=frag.diagram_id,
                        element_id=frag.element_id,
                        duration_ms=frag.duration_ms,
                    )
                )
            elif isinstance(frag, MarkPointFragment):
                events.append(
                    MarkPointEvent(
                        diagram_id=frag.diagram_id,
                        x=frag.x,
                        y=frag.y,
                        kind=frag.point_kind,
                        label=frag.label,
                    )
                )
            elif isinstance(frag, PointAtFragment):
                events.append(
                    PointAtEvent(
                        diagram_id=frag.diagram_id,
                        element_id=frag.element_id,
                        from_side=frag.from_side,
                    )
                )
            elif isinstance(frag, WriteMarginFragment):
                events.append(
                    WriteMarginEvent(
                        diagram_id=frag.diagram_id,
                        anchor_element_id=frag.anchor_element_id,
                        side=frag.side,
                        text=frag.text,
                    )
                )
            elif isinstance(frag, RevealStepFragment):
                events.append(
                    RevealStepEvent(diagram_id=frag.diagram_id, step=frag.step)
                )
            elif isinstance(frag, SetParamFragment):
                events.append(
                    SetParameterEvent(
                        diagram_id=frag.diagram_id,
                        name=frag.name,
                        value=frag.value,
                    )
                )
            elif isinstance(frag, AnimateParamFragment):
                events.append(
                    AnimateParameterEvent(
                        diagram_id=frag.diagram_id,
                        name=frag.name,
                        to=frag.to,
                        from_=frag.from_value,
                        duration_ms=frag.duration_ms,
                    )
                )
            # --- Legacy annotation events (defensive — walker drops) ------
            elif isinstance(frag, PinFragment):
                events.append(
                    PinEvent(
                        diagram_id=frag.diagram_id,
                        annotation_id=frag.id,
                        target_role=frag.role,
                        text=frag.text,
                        position=frag.position,
                    )
                )
            elif isinstance(frag, CalloutFragment):
                events.append(
                    CalloutEvent(
                        diagram_id=frag.diagram_id,
                        annotation_id=frag.id,
                        target_role=frag.role,
                        text=frag.text,
                        direction=frag.direction,
                    )
                )
            elif isinstance(frag, BracketFragment):
                events.append(
                    BracketEvent(
                        diagram_id=frag.diagram_id,
                        annotation_id=frag.id,
                        target_role_a=frag.role_a,
                        target_role_b=frag.role_b,
                        label=frag.label,
                        side=frag.side,
                    )
                )
            elif isinstance(frag, HighlightFragment):
                events.append(
                    HighlightEvent(
                        diagram_id=frag.diagram_id,
                        target_role=frag.role,
                        duration_ms=frag.duration_ms,
                        color_token=frag.color_token,
                    )
                )
            elif isinstance(frag, PulseFragment):
                events.append(
                    PulseEvent(
                        diagram_id=frag.diagram_id,
                        target_role=frag.role,
                        duration_ms=frag.duration_ms,
                        color_token=frag.color_token,
                    )
                )
            elif isinstance(frag, ClearAnnotationsFragment):
                events.append(ClearAnnotationsEvent(diagram_id=frag.diagram_id))
        return events

    def _chapter_audio_dir(self, chapter_id: str) -> Path:
        safe = chapter_id.replace(":", "_")
        return Path(self.artifacts.base_dir) / self.artifacts.audio_dir / safe

    def _artifact_url(self, path: Path) -> str:
        # Convert ./artifacts/audio/foo/bar.mp3 → {url_prefix}/audio/foo/bar.mp3
        base = Path(self.artifacts.base_dir).resolve()
        try:
            rel = path.resolve().relative_to(base)
        except ValueError:
            return f"file://{path.resolve()}"
        return f"{self.artifacts.url_prefix.rstrip('/')}/{rel.as_posix()}"

    @staticmethod
    def _probe_duration_ms(path: Path) -> int:
        """Best-effort duration probe for an existing audio file."""
        try:
            import soundfile as sf

            info = sf.info(str(path))
            return int(info.duration * 1000)
        except Exception:
            try:
                import wave

                with wave.open(str(path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    return int(frames / rate * 1000)
            except Exception:
                logger.warning(
                    "Could not probe duration for %s — defaulting to 0", path
                )
                return 0


# ─────────────────────────────────────────────────────────────────────────────
# Module-level cache-key helper (kept at module scope so tests can hit it).
# ─────────────────────────────────────────────────────────────────────────────


def _audio_file_name(
    *,
    topic_id: str,
    role: str,
    text_index: int,
    text: str,
    ext: str,
) -> str:
    """Build the per-fragment audio filename.

    Includes a 10-hex-char SHA-256 prefix of the TTS text so re-runs with
    different narration content (e.g., doc-19 prosody-applied vs legacy
    beat-narration) produce a different filename and trigger re-synthesis
    instead of silently reusing a stale MP3. Collision probability for
    ~1000 fragments at 40 bits is ~5e-10 — fine.

    The text-index stays in the name (after the role, before the hash) so a
    chapter's audio dir sorts naturally for human inspection.
    """
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    safe_topic = topic_id.replace(":", "_")
    return f"{safe_topic}_{role}_{text_index:03d}_{content_hash}.{ext}"
