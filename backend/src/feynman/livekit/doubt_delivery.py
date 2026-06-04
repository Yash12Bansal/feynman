"""Phase 5 — live voice + visual delivery of a doubt resolution.

Owns a single outbound `LocalAudioTrack` for the lecture session. Each
beat in a `ResolutionPlan` is:
  1. Announced to the frontend via a `doubt_beat_start` data-channel
     message (so it can swap diagrams + apply annotations).
  2. Spoken aloud via Cartesia TTS, frame-by-frame into the published
     audio source.

We don't use `AgentSession.say()` because that requires constructing a
full STT/LLM/TTS pipeline; here we only need the TTS leg. Raw LiveKit
primitives keep the code surface small and untangled from the Phase 3
manual STT capture path.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from livekit import rtc
from livekit.agents import tts as tts_module

from feynman.agent.doubt_resolution.board_events import compile_plan
from feynman.agent.doubt_resolution.diagram_generator import generate_doubt_diagram
from feynman.agent.doubt_resolution.diagram_templates import is_known
from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    GenerateDiagram,
    ResolutionPlan,
    ReuseDiagram,
    TemplateDiagram,
)

logger = logging.getLogger(__name__)


_BEAT_VISUAL_GRACE_MS = 150
"""Tiny pause between publishing a beat's visual and starting TTS so the
frontend has time to swap the diagram before the narration begins."""


class _PublishDataFn(Protocol):
    def __call__(self, payload: dict[str, Any]) -> Awaitable[None]: ...


class DoubtDelivery:
    """Owns the outbound audio track and pumps TTS frames through it."""

    def __init__(self, *, tts: tts_module.TTS) -> None:
        self._tts = tts
        self._audio_source: rtc.AudioSource | None = None
        self._track: rtc.LocalAudioTrack | None = None
        self._track_sid: str | None = None
        self._lock = asyncio.Lock()

    @property
    def is_started(self) -> bool:
        return self._audio_source is not None

    async def start(self, room: rtc.Room) -> None:
        """Create + publish the outbound voice track."""
        if self.is_started:
            return
        self._audio_source = rtc.AudioSource(
            sample_rate=self._tts.sample_rate,
            num_channels=self._tts.num_channels,
        )
        self._track = rtc.LocalAudioTrack.create_audio_track("feynman-voice", self._audio_source)
        publication = await room.local_participant.publish_track(self._track)
        self._track_sid = publication.sid
        logger.info(
            "doubt_delivery.started",
            extra={
                "sample_rate": self._tts.sample_rate,
                "num_channels": self._tts.num_channels,
                "track_sid": self._track_sid,
            },
        )

    async def stop(self, room: rtc.Room) -> None:
        """Unpublish + close. Safe to call multiple times."""
        if self._track_sid is not None:
            try:
                await room.local_participant.unpublish_track(self._track_sid)
            except Exception:
                logger.warning("doubt_delivery.unpublish_failed", exc_info=True)
            self._track_sid = None
        if self._audio_source is not None:
            try:
                await self._audio_source.aclose()
            except Exception:
                logger.warning("doubt_delivery.audio_source_close_failed", exc_info=True)
            self._audio_source = None
        self._track = None

    async def speak(
        self,
        text: str,
        *,
        on_first_frame: Callable[[], None] | None = None,
    ) -> None:
        """Synthesize + push frames into the published source.

        Serialised under `_lock` so two concurrent doubts can't interleave
        TTS chunks on the same track.

        `on_first_frame` fires once, synchronously, when the first audio
        frame is about to be captured. Phase 6 uses this for latency
        telemetry — measuring time-to-first-voice from the worker's
        doubt-intent timestamp.
        """
        clean = (text or "").strip()
        if not clean or self._audio_source is None:
            return

        async with self._lock:
            stream = self._tts.synthesize(clean)
            first_frame_emitted = False
            try:
                async for chunk in stream:
                    frame = getattr(chunk, "frame", None)
                    if frame is None:
                        continue
                    if not first_frame_emitted and on_first_frame is not None:
                        try:
                            on_first_frame()
                        except Exception:
                            logger.warning(
                                "doubt_delivery.first_frame_callback_error",
                                exc_info=True,
                            )
                        first_frame_emitted = True
                    await self._audio_source.capture_frame(frame)
            except Exception:
                logger.exception("doubt_delivery.tts_error")
            finally:
                # ChunkedStream may or may not have an explicit aclose hook
                # depending on the provider; close defensively.
                aclose = getattr(stream, "aclose", None)
                if callable(aclose):
                    try:
                        await aclose()
                    except Exception:
                        logger.warning("doubt_delivery.stream_close_failed", exc_info=True)

    async def deliver_resolution(
        self,
        *,
        plan: ResolutionPlan,
        chapter_context: ChapterContext,
        publish_data: _PublishDataFn,
        on_first_frame: Callable[[], None] | None = None,
        spec_cache: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Deliver a doubt as a mini-lecture: per beat, push the board events
        (diagram + notebook + annotations) then speak the narration.

        A beat that GENERATES a new diagram has its generation kicked off up
        front (a background task) and awaited only when delivery reaches that
        beat — so generation overlaps the narration of earlier beats and never
        blocks time-to-first-voice (the planner guarantees beat 0 never
        generates). `on_first_frame` fires once, on the first audio frame of
        the first beat.
        """
        beats = plan.beats
        valid_diagram_ids = set(chapter_context.diagrams.keys())

        # 1. Resolve the diagram id each beat SHOWS: a validated reuse id, a
        #    deterministic id for a to-be-generated diagram, or None. Start the
        #    generations now so they run while earlier beats narrate.
        resolved_ids: list[str | None] = []
        presentation_modes: list[str | None] = []
        gen_tasks: dict[int, asyncio.Task[dict[str, Any] | None]] = {}
        template_refs: dict[int, tuple[str, dict[str, float]]] = {}
        for i, beat in enumerate(beats):
            directive = beat.diagram
            if isinstance(directive, ReuseDiagram) and directive.diagram_id in valid_diagram_ids:
                resolved_ids.append(directive.diagram_id)
                reused = chapter_context.diagrams.get(directive.diagram_id)
                # Recap of an already-taught figure → show it complete.
                presentation_modes.append(reused.presentation_mode if reused else "overview")
            elif isinstance(directive, GenerateDiagram):
                resolved_ids.append(f"doubt-gen-{i}")
                # Fresh explanatory diagram → build it up as the doubt narrates.
                presentation_modes.append("build_up")
                gen_tasks[i] = asyncio.create_task(
                    self._resolve_generated_spec(directive, spec_cache)
                )
            elif isinstance(directive, TemplateDiagram) and is_known(directive.concept_id):
                # Canonical figure → instant, no generation. The frontend builds
                # it from the registry; show the complete figure (overview).
                resolved_ids.append(f"doubt-tpl-{i}")
                presentation_modes.append("overview")
                template_refs[i] = (directive.concept_id, dict(directive.params))
            else:  # KeepDiagram / NoDiagram / invalid reuse or template
                resolved_ids.append(None)
                presentation_modes.append(None)

        # 2. Compile to board events up front. Ids are deterministic, so a
        #    not-yet-ready generated spec doesn't block compilation.
        events_per_beat = compile_plan(beats, resolved_ids, presentation_modes=presentation_modes)

        # 3. Deliver beat by beat.
        first_voice_callback = on_first_frame
        for i, beat in enumerate(beats):
            events = events_per_beat[i]
            if i in gen_tasks:
                gen_id = f"doubt-gen-{i}"
                spec: dict[str, Any] | None = None
                try:
                    spec = await gen_tasks[i]
                except Exception:
                    logger.warning(
                        "doubt_delivery.generation_error",
                        extra={"beat": i},
                        exc_info=True,
                    )
                if spec is not None:
                    # Ship the generated spec before the beat that shows it.
                    await publish_data(
                        {
                            "type": "doubt_diagram_ready",
                            "diagram_id": gen_id,
                            "spec": spec,
                        }
                    )
                else:
                    # Generation failed — drop the events that referenced the
                    # missing diagram (show_diagram + its annotations) so the
                    # beat degrades to narration + notebook, not a stuck slide.
                    events = [e for e in events if getattr(e, "diagram_id", None) != gen_id]
            elif i in template_refs:
                concept_id, params = template_refs[i]
                await publish_data(
                    {
                        "type": "doubt_diagram_ready",
                        "diagram_id": f"doubt-tpl-{i}",
                        "spec": None,
                        "template_concept_id": concept_id,
                        "template_params": params or None,
                    }
                )
            await publish_data(
                {
                    "type": "doubt_beat_start",
                    "beat_index": i,
                    "board_events": [e.model_dump(by_alias=True) for e in events],
                }
            )
            await asyncio.sleep(_BEAT_VISUAL_GRACE_MS / 1000)
            await self.speak(beat.narration_text, on_first_frame=first_voice_callback)
            first_voice_callback = None  # consumed after the first beat fires it

    async def _resolve_generated_spec(
        self,
        directive: GenerateDiagram,
        spec_cache: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        """Generate (or reuse a cached) DesignDiagramSpec for a generate-beat."""
        key = (directive.brief or "").strip()
        if spec_cache is not None and key and key in spec_cache:
            return spec_cache[key]
        spec = await generate_doubt_diagram(brief=directive.brief, title=directive.title)
        if spec is not None and spec_cache is not None and key:
            spec_cache[key] = spec
        return spec
