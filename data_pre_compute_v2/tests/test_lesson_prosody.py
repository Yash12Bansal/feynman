"""LessonProsody tests — doc 19 Phase G.

Deterministic, no LLM mocking. Each test constructs a `TopicNarration`
with the segments it cares about and asserts the resulting marker
placement. We use the LessonNarrationSegment / TopicNarration Pydantic
models directly rather than going through LessonNarrator (no need to
exercise Phase E's logic here).
"""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (
    LessonNarrationSegment,
    TopicNarration,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_prosody import (
    LessonProsody,
    ProsodyConfig,
    _apply_to_segment,
    _strip_trailing_pause_marker,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _seg(
    *,
    step_index: int = 0,
    text: str = "Some narration.",
    is_question: bool = False,
    is_payoff: bool = False,
    presses_crucial_fact: bool = False,
) -> LessonNarrationSegment:
    return LessonNarrationSegment(
        step_index=step_index,
        raw_narration=text,
        text_with_markers=text,
        target_duration_seconds=1.0,
        is_question=is_question,
        is_payoff=is_payoff,
        presses_crucial_fact=presses_crucial_fact,
    )


def _narration(segments: list[LessonNarrationSegment]) -> TopicNarration:
    return TopicNarration(
        topic_id="topic-1",
        segments=segments,
        full_text_with_markers=" ".join(s.text_with_markers for s in segments),
        diagrams_referenced=["d1"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_apply_passthrough_when_disabled() -> None:
    """`enabled=False` → input returned unchanged."""
    narration = _narration(
        [
            _seg(text="A question step?", is_question=True),
            _seg(text="A payoff step.", is_payoff=True),
        ]
    )
    prosody = LessonProsody(ProsodyConfig(enabled=False))
    result = prosody.apply(narration)
    assert result.segments == narration.segments
    assert result.full_text_with_markers == narration.full_text_with_markers


def test_apply_adds_pause_long_after_question() -> None:
    """is_question=True → `<<PAUSE:long>>` appended."""
    narration = _narration([_seg(text="A question step?", is_question=True)])
    result = LessonProsody().apply(narration)
    new_text = result.segments[0].text_with_markers
    assert new_text.endswith("<<PAUSE:long>>")
    assert "A question step?" in new_text


def test_apply_strips_phase_e_pause_short_before_replacing() -> None:
    """Phase E's pre-pended `<<PAUSE:short>>` on question step is stripped
    and replaced by the prosody choice — no double pause."""
    narration = _narration(
        [
            _seg(
                text="A question step? <<PAUSE:short>>",
                is_question=True,
            )
        ]
    )
    result = LessonProsody().apply(narration)
    new_text = result.segments[0].text_with_markers
    # Only the long pause survives; the original short pause is gone.
    assert new_text.endswith("<<PAUSE:long>>")
    assert "<<PAUSE:short>>" not in new_text
    # Make sure we didn't accidentally double-emit pauses.
    assert new_text.count("<<PAUSE:") == 1


def test_apply_adds_pause_short_before_payoff() -> None:
    """is_payoff=True → `<<PAUSE:short>>` prepended."""
    narration = _narration([_seg(text="The clean payoff.", is_payoff=True)])
    result = LessonProsody().apply(narration)
    new_text = result.segments[0].text_with_markers
    assert new_text.startswith("<<PAUSE:short>>")
    assert "The clean payoff." in new_text


def test_apply_adds_pause_short_after_press() -> None:
    """presses_crucial_fact=True (no other flags) → `<<PAUSE:short>>` after."""
    narration = _narration([_seg(text="The crucial fact.", presses_crucial_fact=True)])
    result = LessonProsody().apply(narration)
    new_text = result.segments[0].text_with_markers
    assert new_text.endswith("<<PAUSE:short>>")
    assert "The crucial fact." in new_text


def test_apply_question_pause_wins_over_press_pause() -> None:
    """Step with BOTH is_question and presses_crucial_fact → single long
    pause from the question rule, no double."""
    narration = _narration(
        [
            _seg(
                text="A pressing question?",
                is_question=True,
                presses_crucial_fact=True,
            )
        ]
    )
    result = LessonProsody().apply(narration)
    new_text = result.segments[0].text_with_markers
    assert new_text.endswith("<<PAUSE:long>>")
    # Only one pause marker, period.
    assert new_text.count("<<PAUSE:") == 1


def test_apply_no_flags_unchanged() -> None:
    """All flags false → text_with_markers identical."""
    narration = _narration([_seg(text="Plain narration with no flags.")])
    result = LessonProsody().apply(narration)
    assert result.segments[0].text_with_markers == "Plain narration with no flags."


def test_apply_none_disables_payoff_prefix() -> None:
    """`payoff_pre_pause='none'` → no prefix on payoff segments."""
    narration = _narration([_seg(text="Payoff step.", is_payoff=True)])
    prosody = LessonProsody(ProsodyConfig(payoff_pre_pause="none"))
    result = prosody.apply(narration)
    new_text = result.segments[0].text_with_markers
    assert not new_text.startswith("<<PAUSE:")
    assert new_text == "Payoff step."


def test_apply_none_disables_press_suffix() -> None:
    """`press_post_pause='none'` → no suffix on press segments."""
    narration = _narration([_seg(text="Press step.", presses_crucial_fact=True)])
    prosody = LessonProsody(ProsodyConfig(press_post_pause="none"))
    result = prosody.apply(narration)
    new_text = result.segments[0].text_with_markers
    assert not new_text.endswith("<<PAUSE:")
    assert new_text == "Press step."


def test_apply_configurable_question_pause_short() -> None:
    """`question_pause='short'` → emitted as short, not long."""
    narration = _narration([_seg(text="A question?", is_question=True)])
    prosody = LessonProsody(ProsodyConfig(question_pause="short"))
    result = prosody.apply(narration)
    assert result.segments[0].text_with_markers.endswith("<<PAUSE:short>>")


def test_apply_rebuilds_full_text_from_new_segments() -> None:
    """`full_text_with_markers` equals join of new segment.text_with_markers."""
    narration = _narration(
        [
            _seg(step_index=0, text="A question?", is_question=True),
            _seg(step_index=1, text="A payoff.", is_payoff=True),
            _seg(
                step_index=2,
                text="Plain.",
            ),
        ]
    )
    result = LessonProsody().apply(narration)
    rebuilt = " ".join(s.text_with_markers for s in result.segments)
    assert rebuilt == result.full_text_with_markers
    # Sanity: the rebuilt text contains every step's words.
    for word in ("A question?", "A payoff.", "Plain."):
        assert word in result.full_text_with_markers


def test_apply_preserves_topic_id_and_diagrams_referenced() -> None:
    """Non-text fields are passed through unchanged."""
    narration = TopicNarration(
        topic_id="topic-42",
        segments=[_seg(text="A question?", is_question=True)],
        full_text_with_markers="A question?",
        diagrams_referenced=["d1", "d2", "d3"],
    )
    result = LessonProsody().apply(narration)
    assert result.topic_id == "topic-42"
    assert result.diagrams_referenced == ["d1", "d2", "d3"]
    # Segment count must be identical.
    assert len(result.segments) == len(narration.segments)


def test_apply_is_idempotent() -> None:
    """Calling apply twice produces the same result as calling it once
    (because the strip step removes whatever prosody we already added)."""
    narration = _narration(
        [
            _seg(text="A question?", is_question=True),
            _seg(text="A payoff.", is_payoff=True),
            _seg(text="A press.", presses_crucial_fact=True),
        ]
    )
    prosody = LessonProsody()
    once = prosody.apply(narration)
    twice = prosody.apply(once)
    assert once.full_text_with_markers == twice.full_text_with_markers


def test_strip_trailing_pause_marker_handles_both_durations() -> None:
    """`_strip_trailing_pause_marker` removes `<<PAUSE:short>>` and
    `<<PAUSE:long>>` and any surrounding whitespace."""
    assert _strip_trailing_pause_marker("Some text. <<PAUSE:short>>") == "Some text."
    assert _strip_trailing_pause_marker("Some text.<<PAUSE:long>>") == "Some text."
    assert (
        _strip_trailing_pause_marker("Some text.   <<PAUSE:short>>   ") == "Some text."
    )
    # No marker → unchanged.
    assert _strip_trailing_pause_marker("No marker here.") == "No marker here."
    # Marker in the middle is NOT stripped.
    assert (
        _strip_trailing_pause_marker("Before <<PAUSE:short>> after.")
        == "Before <<PAUSE:short>> after."
    )


def test_apply_to_segment_helper_direct() -> None:
    """Direct unit on the per-segment helper."""
    seg = _seg(text="Test.", is_payoff=True, presses_crucial_fact=True)
    config = ProsodyConfig()
    result = _apply_to_segment(seg, config)
    assert result.startswith("<<PAUSE:short>>")  # payoff prefix
    assert result.endswith("<<PAUSE:short>>")  # press suffix (no question)
    assert "Test." in result
