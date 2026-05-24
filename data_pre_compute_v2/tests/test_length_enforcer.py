"""LengthEnforcer (Phase 4d) — deterministic chapter-length trim tests."""

from __future__ import annotations

import pytest
from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat

from lecture_pipeline_v2.config import LengthEnforcerConfig
from lecture_pipeline_v2.curriculum.beat_narration.models import BeatNarration
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.length_enforcer import (
    STRUCTURAL,
    LengthEnforcer,
)
from lecture_pipeline_v2.curriculum.models import Chapter, Topic


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bn(
    *,
    topic_id: str,
    beat_index: int,
    beat_type: str,
    text: str = "x",
    estimated: float = 10.0,
    target: int = 10,
) -> BeatNarration:
    return BeatNarration(
        beat_id=f"{topic_id}_b{beat_index}",
        topic_id=topic_id,
        beat_index=beat_index,
        beat_type=beat_type,
        text=text,
        target_duration_seconds=target,
        estimated_duration_seconds=estimated,
    )


def _chapter(narrations: list[BeatNarration], *, budget_seconds: int = 120) -> Chapter:
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
        concept_sequence=["t1"],
        coverage_checklist=[],
        length_budget_seconds=budget_seconds,
        per_concept_budget_seconds={"t1": budget_seconds},
        closing_summary="",
    )
    ch.beat_narrations = narrations
    return ch


class _StubRewriter:
    """Minimal rewriter that shortens estimated_duration_seconds by 50%."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def rewrite(
        self,
        narration: BeatNarration,
        *,
        new_target_seconds: int,
        topic: Topic,
        plan: ConceptTeachingPlan,
        beat: TeachingBeat,
    ) -> BeatNarration:
        self.calls.append((narration.beat_id, new_target_seconds))
        return BeatNarration(
            beat_id=narration.beat_id,
            topic_id=narration.topic_id,
            beat_index=narration.beat_index,
            beat_type=narration.beat_type,
            text="(shortened)",
            target_duration_seconds=new_target_seconds,
            estimated_duration_seconds=narration.estimated_duration_seconds * 0.5,
        )


def _rewrite_context(plan: ConceptTeachingPlan, topic: Topic) -> dict:
    out = {}
    for i, b in enumerate(plan.beats):
        out[f"{topic.topic_id}_b{i}"] = (topic, plan, b)
    return out


def _topic() -> Topic:
    return Topic(
        topic_id="t1",
        chapter_id="ch1",
        section_number="1.1",
        within_chapter_order=1,
        topic_name="X",
        orig_book_content="",
        our_understanding="",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_within_budget_no_change() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, beat_type="hook", estimated=20),
        _bn(topic_id="t1", beat_index=1, beat_type="big_picture", estimated=30),
        _bn(topic_id="t1", beat_index=2, beat_type="first_principles", estimated=40),
    ]
    ch = _chapter(narrations, budget_seconds=120)
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())
    report = await enforcer.trim(chapter=ch)
    assert report.dropped_beats == []
    assert report.merged_pairs == []
    assert report.final_seconds == 90  # total
    assert len(ch.beat_narrations) == 3


@pytest.mark.asyncio
async def test_drops_summarize_first() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, beat_type="hook", estimated=30),
        _bn(topic_id="t1", beat_index=1, beat_type="big_picture", estimated=30),
        _bn(topic_id="t1", beat_index=2, beat_type="first_principles", estimated=40),
        _bn(topic_id="t1", beat_index=3, beat_type="summarize", estimated=60),
    ]
    ch = _chapter(narrations, budget_seconds=120)  # 160 > 132 (1.1*120)
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())
    report = await enforcer.trim(chapter=ch)
    assert "t1_b3" in report.dropped_beats
    assert all(n.beat_type != "summarize" for n in ch.beat_narrations)


@pytest.mark.asyncio
async def test_drops_secondary_example_keeps_first() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, beat_type="hook", estimated=30),
        _bn(topic_id="t1", beat_index=1, beat_type="big_picture", estimated=30),
        _bn(topic_id="t1", beat_index=2, beat_type="first_principles", estimated=40),
        _bn(topic_id="t1", beat_index=3, beat_type="example", estimated=40),
        _bn(topic_id="t1", beat_index=4, beat_type="example", estimated=40),
    ]
    ch = _chapter(narrations, budget_seconds=120)
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())
    report = await enforcer.trim(chapter=ch)
    examples = [n for n in ch.beat_narrations if n.beat_type == "example"]
    assert len(examples) == 1
    assert "t1_b4" in report.dropped_beats


@pytest.mark.asyncio
async def test_merges_adjacent_explain_within_topic() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, beat_type="hook", estimated=15),
        _bn(topic_id="t1", beat_index=1, beat_type="big_picture", estimated=25),
        _bn(topic_id="t1", beat_index=2, beat_type="first_principles", estimated=40),
        _bn(
            topic_id="t1", beat_index=3, beat_type="explain", text="alpha", estimated=40
        ),
        _bn(
            topic_id="t1", beat_index=4, beat_type="explain", text="beta", estimated=40
        ),
        _bn(
            topic_id="t1", beat_index=5, beat_type="derive", text="gamma", estimated=40
        ),
    ]
    ch = _chapter(narrations, budget_seconds=120)  # 200 > 132; trim
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())
    report = await enforcer.trim(chapter=ch)
    # explains+derives should have collapsed
    merged = [n for n in ch.beat_narrations if n.beat_type in {"explain", "derive"}]
    assert len(merged) == 1
    assert "alpha beta gamma" in merged[0].text
    assert len(report.merged_pairs) >= 1


@pytest.mark.asyncio
async def test_merges_dont_cross_topics() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, beat_type="hook", estimated=15),
        _bn(topic_id="t1", beat_index=1, beat_type="big_picture", estimated=25),
        _bn(topic_id="t1", beat_index=2, beat_type="first_principles", estimated=40),
        _bn(
            topic_id="t1", beat_index=3, beat_type="explain", text="alpha", estimated=40
        ),
        _bn(
            topic_id="t2", beat_index=0, beat_type="explain", text="beta", estimated=40
        ),
    ]
    ch = _chapter(narrations, budget_seconds=120)
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())
    await enforcer.trim(chapter=ch)
    # Both explains should still be present — different topics, no merge.
    explains = [n for n in ch.beat_narrations if n.beat_type == "explain"]
    assert len(explains) == 2


@pytest.mark.asyncio
async def test_pass3_rewrites_longest_non_structural() -> None:
    plan = ConceptTeachingPlan(
        concept_title="Pythagoras",
        concept_index=0,
        opening_hook="",
        core_analogy="",
        prerequisite_bridge="",
        beats=[
            TeachingBeat(
                beat_type="hook", speech_guidance="x", target_duration_seconds=15
            ),
            TeachingBeat(
                beat_type="big_picture", speech_guidance="x", target_duration_seconds=25
            ),
            TeachingBeat(
                beat_type="first_principles",
                speech_guidance="x",
                target_duration_seconds=40,
            ),
            TeachingBeat(
                beat_type="explain", speech_guidance="x", target_duration_seconds=80
            ),
        ],
        board_pattern="concept_intro",
        visual_narrative="x",
    )
    narrations = [
        _bn(topic_id="t1", beat_index=0, beat_type="hook", estimated=15, target=15),
        _bn(
            topic_id="t1",
            beat_index=1,
            beat_type="big_picture",
            estimated=25,
            target=25,
        ),
        _bn(
            topic_id="t1",
            beat_index=2,
            beat_type="first_principles",
            estimated=40,
            target=40,
        ),
        _bn(topic_id="t1", beat_index=3, beat_type="explain", estimated=120, target=80),
    ]
    ch = _chapter(narrations, budget_seconds=120)  # 200, hard ceiling 156
    rewriter = _StubRewriter()
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())

    report = await enforcer.trim(
        chapter=ch,
        rewriter=rewriter,
        rewrite_context=_rewrite_context(plan, _topic()),
    )
    assert rewriter.calls, "Expected the stub rewriter to be invoked"
    # The longest non-structural beat ('explain', b3) should be the target.
    assert rewriter.calls[0][0] == "t1_b3"
    assert "t1_b3" in report.rewritten


@pytest.mark.asyncio
async def test_structural_beats_never_dropped_or_rewritten() -> None:
    # Way over budget; structural beats dominate. Ensure none of them are
    # touched by drop/rewrite passes.
    plan = ConceptTeachingPlan(
        concept_title="X",
        concept_index=0,
        opening_hook="",
        core_analogy="",
        prerequisite_bridge="",
        beats=[
            TeachingBeat(
                beat_type="hook", speech_guidance="x", target_duration_seconds=80
            ),
            TeachingBeat(
                beat_type="big_picture", speech_guidance="x", target_duration_seconds=80
            ),
            TeachingBeat(
                beat_type="first_principles",
                speech_guidance="x",
                target_duration_seconds=80,
            ),
            TeachingBeat(
                beat_type="ask", speech_guidance="x", target_duration_seconds=80
            ),
            TeachingBeat(
                beat_type="misconception",
                speech_guidance="x",
                target_duration_seconds=80,
            ),
        ],
        board_pattern="concept_intro",
        visual_narrative="x",
    )
    narrations = [
        _bn(topic_id="t1", beat_index=i, beat_type=t, estimated=80, target=80)
        for i, t in enumerate(
            ["hook", "big_picture", "first_principles", "ask", "misconception"]
        )
    ]
    ch = _chapter(narrations, budget_seconds=60)  # 400 vs 60: way over
    rewriter = _StubRewriter()
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())

    report = await enforcer.trim(
        chapter=ch,
        rewriter=rewriter,
        rewrite_context=_rewrite_context(plan, _topic()),
    )
    # All structural beats survived.
    survivors = {n.beat_type for n in ch.beat_narrations}
    assert survivors == STRUCTURAL
    # And the rewriter was never called (no non-structural beat to shorten).
    assert rewriter.calls == []
    # Hard ceiling breached; flagged.
    assert report.needs_review is True


@pytest.mark.asyncio
async def test_hard_ceiling_flags_needs_review() -> None:
    narrations = [
        _bn(topic_id="t1", beat_index=0, beat_type="hook", estimated=200, target=15),
    ]
    ch = _chapter(narrations, budget_seconds=60)  # 200 > 60*1.3 = 78
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())
    report = await enforcer.trim(chapter=ch)
    assert report.needs_review is True


@pytest.mark.asyncio
async def test_empty_narrations_returns_empty_report() -> None:
    ch = _chapter([], budget_seconds=120)
    enforcer = LengthEnforcer(config=LengthEnforcerConfig())
    report = await enforcer.trim(chapter=ch)
    assert report.initial_seconds == 0
    assert report.final_seconds == 0
    assert report.dropped_beats == []
