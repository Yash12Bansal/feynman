"""Tests for the Phase 5 DoubtDelivery worker module.

TTS + RTC primitives are mocked. We verify the wire protocol: each beat
publishes a `doubt_beat_start` event in order, the visual grace pause
happens between visual + voice, and `speak()` synthesises + pumps frames.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feynman.agent.doubt_resolution import (
    ChapterContext,
    FocusAction,
    PointAtAction,
    ResolutionBeat,
    ResolutionPlan,
)
from feynman.livekit.doubt_delivery import DoubtDelivery


def _make_tts(sample_rate: int = 24000, chunks: list[Any] | None = None) -> MagicMock:
    """A TTS stand-in. `synthesize(text)` returns an async iterable of chunks."""
    tts = MagicMock()
    tts.sample_rate = sample_rate
    tts.num_channels = 1

    class _Stream:
        def __init__(self, items: list[Any]) -> None:
            self._items = list(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)

    tts.synthesize = MagicMock(
        side_effect=lambda text: _Stream(chunks or [SimpleNamespace(frame="frame-1")])
    )
    return tts


@pytest.fixture
def mocked_room() -> MagicMock:
    room = MagicMock()
    room.local_participant = MagicMock()
    publication = SimpleNamespace(sid="track-sid")
    room.local_participant.publish_track = AsyncMock(return_value=publication)
    room.local_participant.unpublish_track = AsyncMock()
    return room


def _patch_rtc_primitives():
    """Patch AudioSource + LocalAudioTrack so we don't touch real LiveKit."""
    audio_source = MagicMock()
    audio_source.capture_frame = AsyncMock()
    audio_source.aclose = AsyncMock()
    track = MagicMock()
    return audio_source, track


# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_publishes_track_with_tts_sample_rate(mocked_room):
    tts = _make_tts(sample_rate=48000)
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()

    with (
        patch(
            "feynman.livekit.doubt_delivery.rtc.AudioSource",
            return_value=audio_source,
        ) as audio_source_ctor,
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
    ):
        await delivery.start(mocked_room)

    audio_source_ctor.assert_called_once_with(sample_rate=48000, num_channels=1)
    mocked_room.local_participant.publish_track.assert_awaited_once_with(track)
    assert delivery.is_started


@pytest.mark.asyncio
async def test_speak_synthesizes_and_pushes_frames(mocked_room):
    chunks = [
        SimpleNamespace(frame="frame-1"),
        SimpleNamespace(frame="frame-2"),
        SimpleNamespace(frame="frame-3"),
    ]
    tts = _make_tts(chunks=chunks)
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()

    with (
        patch("feynman.livekit.doubt_delivery.rtc.AudioSource", return_value=audio_source),
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
    ):
        await delivery.start(mocked_room)
        await delivery.speak("hello world")

    tts.synthesize.assert_called_once_with("hello world")
    assert audio_source.capture_frame.await_count == 3
    audio_source.capture_frame.assert_any_await("frame-1")


@pytest.mark.asyncio
async def test_speak_skips_when_not_started():
    """No-op when the source isn't published yet — defensive."""
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    await delivery.speak("anything")
    tts.synthesize.assert_not_called()


@pytest.mark.asyncio
async def test_speak_skips_empty_text(mocked_room):
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()
    with (
        patch("feynman.livekit.doubt_delivery.rtc.AudioSource", return_value=audio_source),
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
    ):
        await delivery.start(mocked_room)
        await delivery.speak("   ")
    tts.synthesize.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_resolution_publishes_beat_start_per_beat(mocked_room):
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()

    plan = ResolutionPlan(
        beats=[
            ResolutionBeat(
                narration_text="First beat — here's the idea.",
                visual_intent_description="trains and platforms",
                annotation_actions=[FocusAction(target_role="trajectory", text="watch this")],
                target_diagram_id="d_train",
            ),
            ResolutionBeat(
                narration_text="Second beat — therefore the result.",
                visual_intent_description="trajectories diverge",
                annotation_actions=[PointAtAction(element_id="ball", from_side="left")],
                target_diagram_id=None,
            ),
        ]
    )
    chapter = ChapterContext(chapter_id="c1", title="t", topics={}, diagrams={})

    published: list[dict[str, Any]] = []

    async def _publish(payload: dict[str, Any]) -> None:
        published.append(payload)

    with (
        patch("feynman.livekit.doubt_delivery.rtc.AudioSource", return_value=audio_source),
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
        # Speed the visual-grace pauses to zero so the test runs fast.
        patch("feynman.livekit.doubt_delivery.asyncio.sleep", new=AsyncMock()),
    ):
        await delivery.start(mocked_room)
        await delivery.deliver_resolution(plan=plan, chapter_context=chapter, publish_data=_publish)

    assert len(published) == 2
    assert published[0]["type"] == "doubt_beat_start"
    assert published[0]["beat_index"] == 0
    assert published[0]["target_diagram_id"] == "d_train"
    assert published[0]["annotation_actions"][0]["action"] == "focus"
    assert published[0]["annotation_actions"][0]["target_role"] == "trajectory"

    assert published[1]["beat_index"] == 1
    assert published[1]["target_diagram_id"] is None
    assert published[1]["annotation_actions"][0]["action"] == "point_at"

    # Each beat narration triggers a synthesize() call.
    assert tts.synthesize.call_count == 2


@pytest.mark.asyncio
async def test_stop_unpublishes_and_closes(mocked_room):
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()

    with (
        patch("feynman.livekit.doubt_delivery.rtc.AudioSource", return_value=audio_source),
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
    ):
        await delivery.start(mocked_room)
        await delivery.stop(mocked_room)

    mocked_room.local_participant.unpublish_track.assert_awaited_once_with("track-sid")
    audio_source.aclose.assert_awaited_once()
    assert not delivery.is_started
