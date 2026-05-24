"""Smoke tests for the kernel's public model surface."""

from __future__ import annotations

import pytest
from feynman_teaching_kernel import (
    ChecklistItem,
    ConceptTeachingPlan,
    TeachingBeat,
    VisualBeatAction,
)
from pydantic import ValidationError


def _arc_beats() -> list[TeachingBeat]:
    """The three mandatory opening beats."""
    return [
        TeachingBeat(beat_type="hook", speech_guidance="A surprising opening."),
        TeachingBeat(
            beat_type="big_picture", speech_guidance="Place it in the chapter."
        ),
        TeachingBeat(
            beat_type="first_principles", speech_guidance="Why it must be true."
        ),
    ]


def test_concept_teaching_plan_round_trips() -> None:
    plan = ConceptTeachingPlan(
        concept_title="Pythagoras",
        concept_index=0,
        opening_hook="A ladder against a wall...",
        core_analogy="A ramp climbing a curb",
        prerequisite_bridge="Right angles from last week.",
        beats=[
            *_arc_beats(),
            TeachingBeat(
                beat_type="explain",
                speech_guidance="State the formula a² + b² = c².",
                target_duration_seconds=20,
            ),
        ],
        board_pattern="single_focus",
        visual_narrative="One annotated triangle, slowly enriched.",
        transition_to_next="Next: how the formula falls out.",
    )
    raw = plan.model_dump_json()
    restored = ConceptTeachingPlan.model_validate_json(raw)
    assert restored.concept_title == "Pythagoras"
    assert [b.beat_type for b in restored.beats[:3]] == [
        "hook",
        "big_picture",
        "first_principles",
    ]
    assert restored.beats[3].beat_type == "explain"
    assert restored.resolution_checklist == []


def test_visual_beat_action_defaults_blank() -> None:
    v = VisualBeatAction(tool="write_section", description="header")
    assert v.zone == ""
    assert v.timing == "visual_first"
    assert v.builds_on == ""


def test_checklist_item_pending_default() -> None:
    item = ChecklistItem(description="show the formula written out")
    assert item.status == "pending"
    assert item.auto_satisfied_by == []
    assert item.keywords == []


def test_teaching_beat_visual_optional() -> None:
    beat = TeachingBeat(beat_type="explain", speech_guidance="say it")
    assert beat.visual is None
    assert beat.target_duration_seconds == 30
    assert beat.student_cue == ""


# ── Arc enforcement tests ──────────────────────────────────────


def _make_plan(
    *,
    concept_index: int,
    beats: list[TeachingBeat],
) -> ConceptTeachingPlan:
    return ConceptTeachingPlan(
        concept_title="t",
        concept_index=concept_index,
        opening_hook="o",
        core_analogy="a",
        prerequisite_bridge="p",
        beats=beats,
        board_pattern="concept_intro",
        visual_narrative="v",
    )


def test_arc_valid_plan_validates() -> None:
    plan = _make_plan(concept_index=0, beats=_arc_beats())
    assert plan.beats[0].beat_type == "hook"
    assert plan.beats[1].beat_type == "big_picture"
    assert plan.beats[2].beat_type == "first_principles"


def test_arc_missing_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _make_plan(
            concept_index=0,
            beats=[TeachingBeat(beat_type="explain", speech_guidance="x")],
        )
    assert "at least 3 beats" in str(exc_info.value)


def test_arc_wrong_order_raises() -> None:
    out_of_order = [
        TeachingBeat(beat_type="big_picture", speech_guidance="a"),
        TeachingBeat(beat_type="hook", speech_guidance="b"),
        TeachingBeat(beat_type="first_principles", speech_guidance="c"),
    ]
    with pytest.raises(ValidationError) as exc_info:
        _make_plan(concept_index=0, beats=out_of_order)
    assert "First three beats" in str(exc_info.value)


def test_arc_doubt_plan_exempt() -> None:
    """concept_index = -1 marks a doubt plan; the arc validator skips it."""
    doubt_plan = _make_plan(
        concept_index=-1,
        beats=[
            TeachingBeat(beat_type="explain", speech_guidance="address confusion"),
            TeachingBeat(beat_type="ask", speech_guidance="check understanding"),
            TeachingBeat(beat_type="transition", speech_guidance="back to lesson"),
        ],
    )
    assert doubt_plan.concept_index == -1
    assert doubt_plan.beats[0].beat_type == "explain"


# ── allowed_visual_tools kwarg injection ──────────────────────────────────


@pytest.mark.asyncio
async def test_plan_concept_injects_allowed_visual_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doc 18 §5.2 enforcement (kernel side): when allowed_visual_tools is
    passed, the constraint must be visible in the user message sent to
    Anthropic. When None (live default), no constraint is injected."""
    from feynman_teaching_kernel import plan_concept

    captured_messages: list[list[dict]] = []

    class FakeResponse:
        def __init__(self) -> None:
            self.content: list = []

    class FakeMessages:
        async def create(self, **kwargs):
            captured_messages.append(kwargs["messages"])
            return FakeResponse()

    class FakeAsyncAnthropic:
        def __init__(self, **_kwargs) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr(
        "feynman_teaching_kernel.planner.anthropic.AsyncAnthropic",
        FakeAsyncAnthropic,
    )

    # Minimal duck-typed curriculum + plan stubs.
    class _Concept:
        uid = "u1"
        topic_name = "T"
        concept_type = "topic"
        difficulty = "medium"
        summary = "s"
        source_text = "src"
        visual_hint = ""
        level = 0

    class _Curriculum:
        relationships: list = []
        concepts: list = []
        pre_generated_visuals: dict = {}

        def get_teaching_order(self):
            return [_Concept()]

        def get_prerequisites(self, _uid):
            return []

        def concept_by_uid(self, _uid):
            return None

    class _Plan:
        total_concepts = 1

    # Call 1: with allowed_visual_tools — constraint must appear.
    await plan_concept(
        0,
        _Curriculum(),
        _Plan(),
        allowed_visual_tools=["draw_design_diagram", "write_equation"],
        api_key="test",
    )
    msg1 = captured_messages[0][0]["content"]
    assert "CONSTRAINT" in msg1
    assert "draw_design_diagram" in msg1
    assert "write_equation" in msg1

    # Call 2: without allowed_visual_tools — no constraint section.
    await plan_concept(
        0,
        _Curriculum(),
        _Plan(),
        api_key="test",
    )
    msg2 = captured_messages[1][0]["content"]
    assert "CONSTRAINT" not in msg2
