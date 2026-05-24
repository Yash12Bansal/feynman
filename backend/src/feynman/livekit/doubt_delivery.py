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
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from livekit import rtc
from livekit.agents import tts as tts_module

from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    ResolutionBeat,
    ResolutionPlan,
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
    ) -> None:
        """Walk the plan's beats: visual signal → grace → narration.

        `on_first_frame` fires once on the first audio frame of the FIRST
        beat (i.e. the moment Feynman starts speaking). Subsequent beats
        do not refire it.
        """
        _ = chapter_context  # frontend looks up the diagram from its cached chapter
        first_voice_callback = on_first_frame
        for index, beat in enumerate(plan.beats):
            await publish_data(_beat_payload(index, beat))
            await asyncio.sleep(_BEAT_VISUAL_GRACE_MS / 1000)
            await self.speak(beat.narration_text, on_first_frame=first_voice_callback)
            first_voice_callback = None  # consumed after the first beat fires it


def _beat_payload(index: int, beat: ResolutionBeat) -> dict[str, Any]:
    """JSON-safe payload for a single beat-start event."""
    return {
        "type": "doubt_beat_start",
        "beat_index": index,
        "target_diagram_id": beat.target_diagram_id,
        # Each AnnotationAction has its discriminator + payload; dump as
        # plain dicts so the frontend can route by `action`.
        "annotation_actions": [
            json.loads(action.model_dump_json()) for action in beat.annotation_actions
        ],
    }
