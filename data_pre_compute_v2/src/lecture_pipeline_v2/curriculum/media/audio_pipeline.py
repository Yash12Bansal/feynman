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
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ...config import ArtifactsConfig, TTSConfig
from ...tts.base import TTSProvider
from ...tts.chunker import DiagramFragment, PauseFragment, TextFragment, split_script
from ..lecture_script.script_writer import ChapterScript
from ..models import (
    AudioEvent,
    Chapter,
    Manifest,
    PauseEvent,
    ShowDiagramEvent,
    Topic,
    TopicStartEvent,
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
        *,
        concurrency: int = 4,
    ):
        self.tts = tts
        self.tts_config = tts_config
        self.artifacts = artifacts
        self.concurrency = concurrency

    async def build_for_book(
        self,
        chapters: list[Chapter],
        topics: list[Topic],
        chapter_scripts: dict[str, ChapterScript],
    ) -> AudioPipelineReport:
        report = AudioPipelineReport()
        start = time.monotonic()

        topic_by_id = {t.topic_id: t for t in topics}
        chapter_by_id = {c.chapter_id: c for c in chapters}

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [
            self._build_for_chapter(
                chapter_by_id[chapter_id], topic_by_id, script, semaphore, report,
            )
            for chapter_id, script in chapter_scripts.items()
            if chapter_id in chapter_by_id
        ]
        await asyncio.gather(*tasks)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    async def _build_for_chapter(
        self,
        chapter: Chapter,
        topic_by_id: dict[str, Topic],
        script: ChapterScript,
        semaphore: asyncio.Semaphore,
        report: AudioPipelineReport,
    ) -> None:
        async with semaphore:
            try:
                await self._do_build_for_chapter(chapter, topic_by_id, script, report)
                report.chapters_processed += 1
            except Exception as e:
                logger.exception("Audio build failed for chapter %s", chapter.chapter_id)
                report.failures.append(f"{chapter.chapter_id}: {e}")

    async def _do_build_for_chapter(
        self,
        chapter: Chapter,
        topic_by_id: dict[str, Topic],
        script: ChapterScript,
        report: AudioPipelineReport,
    ) -> None:
        chapter_dir = self._chapter_audio_dir(chapter.chapter_id)
        chapter_dir.mkdir(parents=True, exist_ok=True)

        chapter_events: list = []

        for seg in script.segments:
            tid = seg["topic_id"]
            topic = topic_by_id.get(tid)
            if topic is None:
                continue

            standalone_fragments = split_script(seg["narration_standalone"])
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

            chapter_fragments = split_script(seg["narration_chapter"])
            seg_events = await self._render_fragments(
                fragments=chapter_fragments,
                chapter_dir=chapter_dir,
                topic_id=tid,
                role="chapter",
                report=report,
            )
            chapter_events.append(TopicStartEvent(topic_id=tid))
            chapter_events.extend(seg_events)

        if chapter_events:
            chapter.chapter_manifest = Manifest(events=chapter_events)
            report.chapters_with_chapter_audio += 1

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
                file_name = (
                    f"{topic_id.replace(':', '_')}_{role}_{text_index:03d}."
                    f"{self.tts_config.output_format}"
                )
                file_path = chapter_dir / file_name
                if file_path.exists():
                    report.audio_files_skipped_existing += 1
                    duration_ms = self._probe_duration_ms(file_path)
                else:
                    result = await asyncio.to_thread(self.tts.synthesize, frag.text, file_path)
                    duration_ms = result.duration_ms
                    report.audio_files_written += 1
                events.append(AudioEvent(
                    url=self._artifact_url(file_path),
                    duration_ms=duration_ms,
                ))
                text_index += 1
            elif isinstance(frag, DiagramFragment):
                events.append(ShowDiagramEvent(diagram_id=frag.diagram_id))
            elif isinstance(frag, PauseFragment):
                ms = (
                    self.tts_config.pause_short_ms if frag.duration == "short"
                    else self.tts_config.pause_long_ms
                )
                events.append(PauseEvent(duration_ms=ms))
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
                logger.warning("Could not probe duration for %s — defaulting to 0", path)
                return 0
