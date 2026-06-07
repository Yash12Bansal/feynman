"""STT capture for a single student doubt.

When the frontend signals `doubt_intent` over the LiveKit data channel, the
worker calls `capture_student_doubt(ctx)`. We subscribe to the student's
audio track, stream frames into Deepgram via LiveKit's STT plugin, and
**accumulate** the transcript until the student goes quiet for
`_SILENCE_TIMEOUT_S` seconds straight.

Why accumulate (not return the first final): a real doubt is often several
sentences with natural mid-thought pauses — "...so the force points up... [2s]
...but then why doesn't the block move?". Returning the first FINAL_TRANSCRIPT
(Deepgram fires it on the first short pause) chopped the doubt off at the first
breath. We instead treat a *continuous* `_SILENCE_TIMEOUT_S` gap with no STT
activity as "the student is done", which captures the whole doubt.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import structlog
from livekit import rtc
from livekit.agents import JobContext
from livekit.agents import stt as stt_module

from feynman.config import settings

logger = structlog.get_logger()


@dataclass
class CapturedDoubt:
    text: str
    duration_ms: int


# End-of-doubt detection: once the student has started speaking, finalise the
# capture after this many seconds of continuous silence (no interim or final
# STT events). The STT's own VAD already endpoints at ~350ms, so this is just a
# short "don't cut a mid-thought pause" buffer — kept small (config-backed) so
# Feynman starts replying fast rather than sitting through seconds of dead air.
_SILENCE_TIMEOUT_S = settings.doubt_silence_timeout_s
# Before the student says anything (they may pause to think after tapping Ask
# Feynman), wait this long for speech to begin. If nothing is heard, give up.
_PRE_SPEECH_TIMEOUT_S = 15.0
# Overall safety cap on a single capture so a runaway (mic noise keeps Deepgram
# streaming, student never stops) can't pin the worker forever. We return
# whatever was accumulated when this fires. Generous — longer than any
# realistic spoken doubt, even a rambling multi-sentence one.
_MAX_UTTERANCE_S = 90.0
# How long we'll wait for the student's audio track to become available after a
# doubt_intent signal. The mic is published when the user joined, so this
# usually resolves in <100ms.
_AUDIO_TRACK_WAIT_S = 5.0

# Event types that count as "the student is producing speech right now" and so
# reset the silence window. START_OF_SPEECH / interims fire while talking;
# finals fire on each endpoint (short pause). Any of them means "not silent".
_ACTIVITY_EVENT_TYPES = frozenset(
    {
        stt_module.SpeechEventType.START_OF_SPEECH,
        stt_module.SpeechEventType.INTERIM_TRANSCRIPT,
        stt_module.SpeechEventType.FINAL_TRANSCRIPT,
    }
)


async def accumulate_until_silence(
    stream: AsyncIterator[Any],
    *,
    on_speech_started: Callable[[], None] | None = None,
    silence_timeout_s: float = _SILENCE_TIMEOUT_S,
    pre_speech_timeout_s: float = _PRE_SPEECH_TIMEOUT_S,
) -> list[str]:
    """Pull STT events off `stream`, accumulating FINAL_TRANSCRIPT text until a
    continuous-silence gap ends the doubt.

    Pure of LiveKit wiring (takes any async iterator of objects with `.type`
    and, for finals, `.alternatives[0].text`) so it's unit-testable with a fake
    stream and a tiny `silence_timeout_s`. Returns the ordered transcript
    pieces; the caller joins them.

    Timing: before any speech, allow `pre_speech_timeout_s` for the student to
    start; once speech is detected, a `silence_timeout_s` gap with no activity
    finalises. `on_speech_started` fires once, on the first activity event.
    """
    pieces: list[str] = []
    speech_started = False
    while True:
        gap = silence_timeout_s if speech_started else pre_speech_timeout_s
        try:
            event = await asyncio.wait_for(anext(stream), timeout=gap)
        except TimeoutError:
            # Inner timeout only: either nothing was ever said (give up) or the
            # student has been silent for `silence_timeout_s` after speaking
            # (done). An OUTER cap cancellation arrives as CancelledError, not
            # TimeoutError, so it is NOT swallowed here.
            if speech_started:
                logger.info("doubt_capture.silence_finalized", silence_s=gap)
            else:
                logger.info("doubt_capture.no_speech", waited_s=gap)
            break
        except StopAsyncIteration:
            break

        if event.type in _ACTIVITY_EVENT_TYPES and not speech_started:
            speech_started = True
            if on_speech_started is not None:
                try:
                    on_speech_started()
                except Exception:
                    logger.warning("doubt_capture.on_speech_started_error", exc_info=True)

        if event.type == stt_module.SpeechEventType.FINAL_TRANSCRIPT:
            alternatives = getattr(event, "alternatives", None)
            if alternatives:
                candidate = alternatives[0].text.strip()
                if candidate:
                    pieces.append(candidate)
    return pieces


async def capture_student_doubt(
    ctx: JobContext,
    *,
    stt: stt_module.STT,
    on_speech_started: Callable[[], None] | None = None,
) -> CapturedDoubt | None:
    """Subscribe to the student's mic and capture one full doubt.

    Streams the mic into Deepgram and accumulates every FINAL_TRANSCRIPT until
    the student is silent for `_SILENCE_TIMEOUT_S` straight (end-of-doubt) or
    the overall `_MAX_UTTERANCE_S` cap is hit. `on_speech_started` fires once,
    when the first speech activity is detected, so the caller can tell the
    frontend "I'm listening" and keep a short listening-timeout from firing
    while the student is mid-doubt.

    Returns None if no audio track exists or nothing was transcribed.
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

    pieces: list[str] = []
    try:
        async with asyncio.timeout(_MAX_UTTERANCE_S):
            pieces = await accumulate_until_silence(
                stt_stream,
                on_speech_started=on_speech_started,
            )
    except TimeoutError:
        logger.warning("doubt_capture.max_utterance_cap", elapsed_s=_MAX_UTTERANCE_S)
    finally:
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
        with contextlib.suppress(Exception):
            await stt_stream.aclose()
        with contextlib.suppress(Exception):
            await audio_stream.aclose()

    final_text = " ".join(pieces).strip()
    if not final_text:
        return None

    elapsed_ms = int((asyncio.get_running_loop().time() - start) * 1000)
    logger.info(
        "doubt_capture.transcript_finalized",
        text=final_text,
        pieces=len(pieces),
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
