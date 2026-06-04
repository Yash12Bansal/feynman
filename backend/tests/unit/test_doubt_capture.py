"""Tests for doubt_capture's silence-accumulation core.

`accumulate_until_silence` pulls STT events off any async iterator and
accumulates FINAL_TRANSCRIPT text until a continuous gap with no activity ends
the doubt. We feed fake streams with a tiny silence timeout so the (real: 5s)
end-of-doubt behaviour is exercised in milliseconds, with no LiveKit/mic.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from livekit.agents import stt as stt_module

from feynman.agent.doubt_resolution.doubt_capture import accumulate_until_silence

_T = stt_module.SpeechEventType


class _Alt:
    def __init__(self, text: str) -> None:
        self.text = text


class _Event:
    def __init__(self, type_: Any, text: str | None = None) -> None:
        self.type = type_
        self.alternatives = [_Alt(text)] if text is not None else []


async def _stream(steps: list[tuple[float, _Event]]) -> AsyncIterator[_Event]:
    """Yield each event after `gap` seconds, then hang — modelling ongoing
    silence so the consumer's next wait times out (end-of-doubt)."""
    for gap, ev in steps:
        await asyncio.sleep(gap)
        yield ev
    await asyncio.Event().wait()  # never resolves → next anext() times out


@pytest.mark.asyncio
async def test_accumulates_sentences_across_a_short_pause() -> None:
    """A mid-thought pause shorter than the silence window must NOT cut off the
    doubt; both sentences are captured."""
    started: list[bool] = []
    pieces = await accumulate_until_silence(
        _stream(
            [
                (0.0, _Event(_T.START_OF_SPEECH)),
                (0.02, _Event(_T.INTERIM_TRANSCRIPT, "the force")),
                (0.02, _Event(_T.FINAL_TRANSCRIPT, "The force points up.")),
                (0.1, _Event(_T.INTERIM_TRANSCRIPT, "but why")),  # short pause < window
                (0.02, _Event(_T.FINAL_TRANSCRIPT, "But why doesn't it move?")),
            ]
        ),
        on_speech_started=lambda: started.append(True),
        silence_timeout_s=0.3,
        pre_speech_timeout_s=1.0,
    )
    assert pieces == ["The force points up.", "But why doesn't it move?"]
    assert started == [True]  # fired exactly once, on first activity


@pytest.mark.asyncio
async def test_returns_empty_and_no_callback_when_no_speech() -> None:
    started: list[bool] = []
    pieces = await accumulate_until_silence(
        _stream([]),  # immediate hang, never speaks
        on_speech_started=lambda: started.append(True),
        silence_timeout_s=1.0,
        pre_speech_timeout_s=0.1,
    )
    assert pieces == []
    assert started == []


@pytest.mark.asyncio
async def test_single_final_then_silence() -> None:
    pieces = await accumulate_until_silence(
        _stream([(0.0, _Event(_T.FINAL_TRANSCRIPT, "What is a semiconductor?"))]),
        silence_timeout_s=0.3,
        pre_speech_timeout_s=1.0,
    )
    assert pieces == ["What is a semiconductor?"]


@pytest.mark.asyncio
async def test_ignores_blank_final_transcripts() -> None:
    pieces = await accumulate_until_silence(
        _stream(
            [
                (0.0, _Event(_T.FINAL_TRANSCRIPT, "   ")),  # whitespace only
                (0.02, _Event(_T.FINAL_TRANSCRIPT, "Real question.")),
            ]
        ),
        silence_timeout_s=0.3,
        pre_speech_timeout_s=1.0,
    )
    assert pieces == ["Real question."]
