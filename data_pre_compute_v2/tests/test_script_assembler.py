"""ScriptAssembler (Phase 4d) — pure-sync stitch tests."""

from __future__ import annotations

from lecture_pipeline_v2.config import ScriptAssemblerConfig
from lecture_pipeline_v2.curriculum.beat_narration.models import BeatNarration
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Chapter, Topic
from lecture_pipeline_v2.curriculum.script_assembler import ScriptAssembler


def _bn(
    *,
    topic_id: str,
    beat_index: int,
    text: str,
    beat_type: str = "explain",
) -> BeatNarration:
    return BeatNarration(
        beat_id=f"{topic_id}_b{beat_index}",
        topic_id=topic_id,
        beat_index=beat_index,
        beat_type=beat_type,
        text=text,
        target_duration_seconds=10,
        estimated_duration_seconds=10,
    )


def _topic(topic_id: str = "t1") -> Topic:
    return Topic(
        topic_id=topic_id,
        chapter_id="ch1",
        section_number="1.1",
        within_chapter_order=1,
        topic_name=topic_id,
        orig_book_content="",
        our_understanding="",
    )


def _chapter(
    narrations: list[BeatNarration], *, concept_sequence: list[str]
) -> Chapter:
    ch = Chapter(
        chapter_id="ch1",
        chapter_index=1,
        title="",
        summary="",
        page_start=1,
        page_end=10,
    )
    ch.lecture_plan = ChapterLecturePlan(
        chapter_id="ch1",
        chapter_title="",
        chapter_arc="",
        opening_hook="",
        concept_sequence=concept_sequence,
        coverage_checklist=[],
        length_budget_seconds=240,
        per_concept_budget_seconds={tid: 60 for tid in concept_sequence},
        closing_summary="",
    )
    ch.beat_narrations = narrations
    return ch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_assemble_one_topic_one_beat() -> None:
    ch = _chapter(
        [_bn(topic_id="t1", beat_index=0, text="hello")],
        concept_sequence=["t1"],
    )
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    out = a.assemble_chapter(chapter=ch, topics_by_id={"t1": _topic("t1")})
    assert out is not None
    assert out["chapter_id"] == "ch1"
    assert len(out["segments"]) == 1
    seg = out["segments"][0]
    assert seg["topic_id"] == "t1"
    assert seg["narration_standalone"] == "hello"


def test_assemble_groups_by_topic_id() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, text="a"),
        _bn(topic_id="t2", beat_index=0, text="b"),
    ]
    ch = _chapter(narrations, concept_sequence=["t1", "t2"])
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    out = a.assemble_chapter(
        chapter=ch,
        topics_by_id={"t1": _topic("t1"), "t2": _topic("t2")},
    )
    assert out is not None
    assert [s["topic_id"] for s in out["segments"]] == ["t1", "t2"]


def test_respects_concept_sequence_order() -> None:
    # Beats stored in t1-first order, but concept_sequence says t2 first.
    narrations = [
        _bn(topic_id="t1", beat_index=0, text="alpha"),
        _bn(topic_id="t2", beat_index=0, text="beta"),
    ]
    ch = _chapter(narrations, concept_sequence=["t2", "t1"])
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    out = a.assemble_chapter(
        chapter=ch,
        topics_by_id={"t1": _topic("t1"), "t2": _topic("t2")},
    )
    assert out is not None
    assert [s["topic_id"] for s in out["segments"]] == ["t2", "t1"]


def test_pause_between_beats() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, text="alpha"),
        _bn(topic_id="t1", beat_index=1, text="beta"),
    ]
    ch = _chapter(narrations, concept_sequence=["t1"])
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    out = a.assemble_chapter(chapter=ch, topics_by_id={"t1": _topic("t1")})
    assert out is not None
    seg = out["segments"][0]
    assert "<<PAUSE:short>>" in seg["narration_standalone"]
    # In default config, beats are pause_between_beats=short.
    assert seg["narration_standalone"] == "alpha<<PAUSE:short>>beta"


def test_sorts_beats_by_beat_index() -> None:
    # Beats stored out-of-order; assembler sorts by beat_index.
    narrations = [
        _bn(topic_id="t1", beat_index=2, text="two"),
        _bn(topic_id="t1", beat_index=0, text="zero"),
        _bn(topic_id="t1", beat_index=1, text="one"),
    ]
    ch = _chapter(narrations, concept_sequence=["t1"])
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    out = a.assemble_chapter(chapter=ch, topics_by_id={"t1": _topic("t1")})
    assert out is not None
    seg = out["segments"][0]
    assert seg["narration_standalone"] == "zero<<PAUSE:short>>one<<PAUSE:short>>two"


def test_skips_empty_text_narrations() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, text=""),  # empty → skipped
        _bn(topic_id="t1", beat_index=1, text="alpha"),
        _bn(topic_id="t1", beat_index=2, text="   "),  # whitespace → skipped
        _bn(topic_id="t1", beat_index=3, text="beta"),
    ]
    ch = _chapter(narrations, concept_sequence=["t1"])
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    out = a.assemble_chapter(chapter=ch, topics_by_id={"t1": _topic("t1")})
    assert out is not None
    seg = out["segments"][0]
    assert seg["narration_standalone"] == "alpha<<PAUSE:short>>beta"


def test_returns_none_when_no_lecture_plan() -> None:
    ch = Chapter(
        chapter_id="ch1",
        chapter_index=1,
        title="",
        summary="",
        page_start=1,
        page_end=10,
    )
    ch.beat_narrations = [_bn(topic_id="t1", beat_index=0, text="x")]
    # lecture_plan is None (the default)
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    assert a.assemble_chapter(chapter=ch, topics_by_id={"t1": _topic("t1")}) is None


def test_returns_none_when_no_beat_narrations() -> None:
    ch = _chapter([], concept_sequence=["t1"])
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    assert a.assemble_chapter(chapter=ch, topics_by_id={"t1": _topic("t1")}) is None


def test_returns_none_when_all_narrations_empty() -> None:
    ch = _chapter(
        [_bn(topic_id="t1", beat_index=0, text="")],
        concept_sequence=["t1"],
    )
    a = ScriptAssembler(config=ScriptAssemblerConfig())
    assert a.assemble_chapter(chapter=ch, topics_by_id={"t1": _topic("t1")}) is None
