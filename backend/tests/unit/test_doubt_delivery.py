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
    DiagramData,
    FocusAction,
    PointAtAction,
    ResolutionBeat,
    ResolutionPlan,
)
from feynman.agent.doubt_resolution.models import (
    GenerateDiagram,
    KeepDiagram,
    ReuseDiagram,
    WriteStepBlock,
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
async def test_deliver_resolution_publishes_board_events_per_beat(mocked_room):
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()

    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                # Inline <<FOCUS:trajectory>> marker — fires synced to the words,
                # as its own interleaved message (NOT bundled at beat start).
                narration_text="First beat. <<FOCUS:trajectory>>Watch this path.",
                diagram=ReuseDiagram(diagram_id="d_train"),
            ),
            ResolutionBeat(
                narration_text="Second beat — therefore the result.",
                diagram=KeepDiagram(),
                annotation_actions=[PointAtAction(element_id="ball", from_side="left")],
            ),
        ],
    )
    chapter = ChapterContext(
        chapter_id="c1",
        title="t",
        topics={},
        diagrams={
            "d_train": DiagramData(
                diagram_id="d_train",
                description="d",
                dictionary={"traj_el": {"role": "trajectory"}},
            )
        },
    )

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

    beat_starts = [p for p in published if p["type"] == "doubt_beat_start"]
    types_per_msg = [[e["type"] for e in p["board_events"]] for p in beat_starts]
    # beat0 structural (show_diagram only — focus is inline now), a SEPARATE
    # interleaved focus, then beat1's pointer.
    assert ["show_diagram"] in types_per_msg
    assert ["focus"] in types_per_msg
    assert ["point_at"] in types_per_msg

    show_msg = next(p for p in beat_starts if p["board_events"][0]["type"] == "show_diagram")
    focus_msg = next(p for p in beat_starts if p["board_events"][0]["type"] == "focus")
    # the inline marker resolved role "trajectory" → element id "traj_el"
    assert focus_msg["board_events"][0]["target_element_id"] == "traj_el"
    # the diagram is shown before its part is highlighted
    assert published.index(show_msg) < published.index(focus_msg)
    point_msg = next(p for p in beat_starts if p["board_events"][0]["type"] == "point_at")
    assert point_msg["board_events"][0]["diagram_id"] == "d_train"

    # narration split into 3 spoken runs: "First beat." / "Watch this path." /
    # "Second beat — therefore the result."
    assert tts.synthesize.call_count == 3


@pytest.mark.asyncio
async def test_deliver_resolution_generates_and_publishes_spec_before_beat(mocked_room):
    """A generate-beat overlaps generation, then publishes the spec via
    doubt_diagram_ready BEFORE that beat's board events show it."""
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()

    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                narration_text="Start with the diagram you already have.",
                diagram=ReuseDiagram(diagram_id="d1"),
            ),
            ResolutionBeat(
                narration_text="Now let me sketch the platform view.",
                diagram=GenerateDiagram(brief="a relative-velocity triangle", title="Triangle"),
            ),
        ],
    )
    chapter = ChapterContext(
        chapter_id="c1",
        title="t",
        topics={},
        diagrams={"d1": DiagramData(diagram_id="d1", description="d")},
    )
    fake_spec = {
        "elements": [{"id": "v"}],
        "dictionary": {"v": {"role": "velocity"}},
        "width": 800,
        "height": 600,
    }
    published: list[dict[str, Any]] = []

    async def _publish(payload: dict[str, Any]) -> None:
        published.append(payload)

    cache: dict[str, dict[str, Any]] = {}
    with (
        patch("feynman.livekit.doubt_delivery.rtc.AudioSource", return_value=audio_source),
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
        patch("feynman.livekit.doubt_delivery.asyncio.sleep", new=AsyncMock()),
        patch(
            "feynman.livekit.doubt_delivery.generate_doubt_diagram",
            new=AsyncMock(return_value=fake_spec),
        ),
    ):
        await delivery.start(mocked_room)
        await delivery.deliver_resolution(
            plan=plan, chapter_context=chapter, publish_data=_publish, spec_cache=cache
        )

    ready = [p for p in published if p["type"] == "doubt_diagram_ready"]
    assert len(ready) == 1
    assert ready[0]["diagram_id"] == "doubt-gen-1"
    assert ready[0]["spec"]["dictionary"]["v"]["role"] == "velocity"

    beat1 = next(
        p for p in published if p.get("type") == "doubt_beat_start" and p["beat_index"] == 1
    )
    # spec shipped before the beat that shows it
    assert published.index(ready[0]) < published.index(beat1)
    assert beat1["board_events"][0]["type"] == "show_diagram"
    assert beat1["board_events"][0]["diagram_id"] == "doubt-gen-1"
    # cached for re-resolution reuse
    assert cache["a relative-velocity triangle"] is fake_spec


@pytest.mark.asyncio
async def test_deliver_resolution_generation_failure_degrades(mocked_room):
    """When generation returns None, the show_diagram + its annotations are
    dropped (no stuck slide) but notebook writing survives."""
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()

    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                narration_text="A quick sketch would make this concrete.",
                diagram=GenerateDiagram(brief="x"),
                notebook_writes=[WriteStepBlock(text="key step")],
                annotation_actions=[FocusAction(target_role="r")],
            )
        ],
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
        patch("feynman.livekit.doubt_delivery.asyncio.sleep", new=AsyncMock()),
        patch(
            "feynman.livekit.doubt_delivery.generate_doubt_diagram",
            new=AsyncMock(return_value=None),
        ),
    ):
        await delivery.start(mocked_room)
        await delivery.deliver_resolution(plan=plan, chapter_context=chapter, publish_data=_publish)

    assert not any(p["type"] == "doubt_diagram_ready" for p in published)
    beat0 = next(p for p in published if p["type"] == "doubt_beat_start")
    types = [e["type"] for e in beat0["board_events"]]
    assert "show_diagram" not in types  # dropped — generation failed
    assert "focus" not in types  # annotation on the missing diagram dropped
    assert "write_step" in types  # notebook survives


@pytest.mark.asyncio
async def test_speak_on_first_frame_callback_fires_once(mocked_room):
    """Phase 6: latency telemetry hook fires exactly once on the first frame."""
    chunks = [
        SimpleNamespace(frame="frame-1"),
        SimpleNamespace(frame="frame-2"),
        SimpleNamespace(frame="frame-3"),
    ]
    tts = _make_tts(chunks=chunks)
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()
    callback = MagicMock()

    with (
        patch("feynman.livekit.doubt_delivery.rtc.AudioSource", return_value=audio_source),
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
    ):
        await delivery.start(mocked_room)
        await delivery.speak("hello", on_first_frame=callback)

    callback.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_resolution_on_first_frame_fires_once_across_beats(mocked_room):
    """Phase 6: the callback fires on the first frame of the first beat only."""
    tts = _make_tts()
    delivery = DoubtDelivery(tts=tts)
    audio_source, track = _patch_rtc_primitives()
    callback = MagicMock()

    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                narration_text="Here's the first idea.",
                visual_intent_description="a",
            ),
            ResolutionBeat(
                narration_text="Here's the second idea.",
                visual_intent_description="b",
            ),
        ],
    )
    chapter = ChapterContext(chapter_id="c1", title="t", topics={}, diagrams={})

    async def _publish(payload: dict) -> None:
        return None

    with (
        patch("feynman.livekit.doubt_delivery.rtc.AudioSource", return_value=audio_source),
        patch(
            "feynman.livekit.doubt_delivery.rtc.LocalAudioTrack.create_audio_track",
            return_value=track,
        ),
        patch("feynman.livekit.doubt_delivery.asyncio.sleep", new=AsyncMock()),
    ):
        await delivery.start(mocked_room)
        await delivery.deliver_resolution(
            plan=plan,
            chapter_context=chapter,
            publish_data=_publish,
            on_first_frame=callback,
        )

    # Two beats, two synthesize() calls, but only one on_first_frame call.
    assert tts.synthesize.call_count == 2
    callback.assert_called_once()


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
