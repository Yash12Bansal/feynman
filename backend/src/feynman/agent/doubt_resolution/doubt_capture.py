"""STT capture for a single student doubt.

When the frontend signals `doubt_intent` over the LiveKit data channel, the
worker calls `capture_student_doubt(ctx)`. We subscribe to the student's
audio track, stream frames into Deepgram via LiveKit's STT plugin, and
return the first FINAL_TRANSCRIPT we receive — Deepgram's endpointing fires
that event as soon as the student pauses, so the student doesn't need a
button press to "submit".

Phase 3 scope: capture one utterance and return its text. The actual
classification + planning + delivery is wired in Phases 4 and 5; here we
just hand back the transcript.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass

import structlog
from livekit import rtc
from livekit.agents import JobContext
from livekit.agents import stt as stt_module

logger = structlog.get_logger()


@dataclass
class CapturedDoubt:
    text: str
    duration_ms: int


# Safety net so a runaway capture (student never stops talking, mic muted but
# noise floor keeps Deepgram interim-streaming, etc.) doesn't pin the worker
# in listening mode indefinitely. Tuned generously — 60s is longer than any
# realistic doubt utterance.
_MAX_UTTERANCE_S = 60.0
# How long we'll wait for the student's audio track to become available
# after a doubt_intent signal. The mic is published when the user joined,
# so this usually resolves in <100ms.
_AUDIO_TRACK_WAIT_S = 5.0


async def capture_student_doubt(
    ctx: JobContext,
    *,
    stt: stt_module.STT,
) -> CapturedDoubt | None:
    """Subscribe to the student's mic and capture one utterance.

    Returns None if no remote participant / audio track exists, or if the
    capture times out without producing a final transcript.
    """
    track = await _wait_for_student_audio_track(ctx)
    if track is None:
        logger.warning("doubt_capture.no_audio_track")
        return None

    audio_stream = rtc.AudioStream.from_track(track=track)
    stt_stream = stt.stream()

    async def _pump_audio() -> None:
        try:
            async for event in audio_stream:
                stt_stream.push_frame(event.frame)
        except Exception:
            logger.exception("doubt_capture.audio_pump_error")
        finally:
            stt_stream.end_input()

    pump_task = asyncio.create_task(_pump_audio())
    start = asyncio.get_running_loop().time()

    final_text = ""
    try:
        async with asyncio.timeout(_MAX_UTTERANCE_S):
            async for event in stt_stream:
                if event.type == stt_module.SpeechEventType.FINAL_TRANSCRIPT:
                    alternatives = event.alternatives
                    if alternatives:
                        candidate = alternatives[0].text.strip()
                        if candidate:
                            final_text = candidate
                            break
    except TimeoutError:
        logger.warning("doubt_capture.timeout", elapsed_s=_MAX_UTTERANCE_S)
    finally:
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
        with contextlib.suppress(Exception):
            await stt_stream.aclose()
        with contextlib.suppress(Exception):
            await audio_stream.aclose()

    if not final_text:
        return None

    elapsed_ms = int((asyncio.get_running_loop().time() - start) * 1000)
    logger.info(
        "doubt_capture.transcript_finalized",
        text=final_text,
        duration_ms=elapsed_ms,
    )
    return CapturedDoubt(text=final_text, duration_ms=elapsed_ms)


async def _wait_for_student_audio_track(
    ctx: JobContext,
) -> rtc.Track | None:
    """Wait for any remote participant's audio track to be available."""
    deadline = asyncio.get_running_loop().time() + _AUDIO_TRACK_WAIT_S
    while asyncio.get_running_loop().time() < deadline:
        for participant in ctx.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.kind == rtc.TrackKind.KIND_AUDIO and publication.track:
                    return publication.track
        await asyncio.sleep(0.1)
    return None
