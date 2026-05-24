"""LessonNarrator tests — doc 19 Phase E.

Deterministic synthesizer; no LLM mocking needed. Each test constructs a
valid LessonPlan via the `_make_plan` helper, calls `render`, and asserts
specific marker placements in `full_text_with_markers` or per-segment
fields.

The helper appends 2 filler steps (Q + P, both pressing the crucial_fact)
to user-provided steps so all LessonPlan validators pass.
"""

from __future__ import annotations

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (
    LessonNarrationReport,
    LessonNarrator,
    _emit_action_markers,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    ChoreographyAction,
    ChoreographyStep,
    DiagramRequirement,
    ElementRequirement,
    EquationIntroduction,
    Hook,
    HookType,
    LessonPlan,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures + helpers
# ─────────────────────────────────────────────────────────────────────────────


def _config() -> PipelineConfig:
    return PipelineConfig(llm=LLMConfig(api_key="test", model="claude-sonnet-4-test"))


def _make_plan(
    *,
    user_steps: list[ChoreographyStep],
    user_diagrams: list[DiagramRequirement] | None = None,
    equations: list[EquationIntroduction] | None = None,
) -> LessonPlan:
    """Wrap user steps in a valid LessonPlan envelope.

    Appends 2 filler steps (Q + P, both pressing the crucial fact) AFTER the
    user steps so:
      - has_question_payoff_pair passes
      - crucial_facts_pressed_twice passes (1 crucial_fact * 2 = 2 presses)
    All user-supplied element_ids are declared in a synthetic diagram.
    """
    user_element_ids = sorted(
        {s.target_element_id for s in user_steps if s.target_element_id}
    )
    if user_diagrams is None:
        ids_for_diagram = user_element_ids or ["filler-el"]
        user_diagrams = [
            DiagramRequirement(
                diagram_id="d1",
                purpose="Test diagram with the user-referenced elements.",
                required_elements=[
                    ElementRequirement(element_id=eid, role="role", description="desc")
                    for eid in ids_for_diagram
                ],
            )
        ]

    filler = [
        ChoreographyStep(
            narration="A filler question step.",
            actions=[],
            is_question=True,
            presses_crucial_fact=True,
        ),
        ChoreographyStep(
            narration="A filler payoff step.",
            actions=[],
            is_payoff=True,
            presses_crucial_fact=True,
        ),
    ]

    return LessonPlan(
        topic_id="topic-1",
        title="Test lesson",
        hook=Hook(type=HookType.fact, text="A real-feeling hook line."),
        crucial_facts=["the test crucial fact"],
        diagrams=user_diagrams,
        choreography=user_steps + filler,
        equations=equations or [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_render_emits_show_diagram_only_on_first_reference() -> None:
    """Two steps referencing the same diagram → SHOW_DIAGRAM fires once."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="First reference.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
            ),
            ChoreographyStep(
                narration="Second reference.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
            ),
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    # First user segment must contain SHOW_DIAGRAM:d1.
    assert "<<SHOW_DIAGRAM:d1>>" in nar.segments[0].text_with_markers
    # Second user segment must NOT.
    assert "<<SHOW_DIAGRAM:d1>>" not in nar.segments[1].text_with_markers
    # Diagrams referenced list has it exactly once.
    assert nar.diagrams_referenced == ["d1"]


def test_render_emits_focus_before_narration() -> None:
    """A step with `focus` action prepends FOCUS:element_id."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Look at this thing.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
            )
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    text = nar.segments[0].text_with_markers
    # FOCUS must come before the narration body. SHOW_DIAGRAM appears between
    # them because it's the first diagram reference.
    assert text.index("<<FOCUS:elem-1>>") < text.index("Look at this thing.")


def test_render_emits_trace_after_narration() -> None:
    """A step with `trace` action appends TRACE:element_id."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Watch this curve form.",
                actions=[ChoreographyAction.trace],
                target_element_id="elem-1",
                target_diagram_id="d1",
            )
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    text = nar.segments[0].text_with_markers
    assert text.index("Watch this curve form.") < text.index("<<TRACE:elem-1>>")


def test_render_emits_clear_before_narration() -> None:
    """A step with `clear` action prepends CLEAR_ANNOTATIONS."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Reset and let's begin.",
                actions=[ChoreographyAction.clear],
            )
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    text = nar.segments[0].text_with_markers
    assert text.startswith("<<CLEAR_ANNOTATIONS>>")
    assert "Reset and let's begin." in text


def test_render_skips_unsupported_actions() -> None:
    """mark_point and write_margin actions are skipped with a warning."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Mark something here.",
                actions=[ChoreographyAction.mark_point],
                target_element_id="elem-1",
                target_diagram_id="d1",
            ),
            ChoreographyStep(
                narration="Write something next to that.",
                actions=[ChoreographyAction.write_margin],
                target_element_id="elem-1",
                target_diagram_id="d1",
            ),
        ]
    )
    report = LessonNarrationReport()
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan, report=report)
    # No MARK or WRITE_MARGIN tokens emitted.
    assert "<<MARK" not in nar.full_text_with_markers
    assert "<<WRITE_MARGIN" not in nar.full_text_with_markers
    # Both got counted as unsupported.
    assert report.unsupported_actions == 2
    assert any("mark_point" in w for w in report.warnings)
    assert any("write_margin" in w for w in report.warnings)


def test_render_inserts_pause_after_question_step() -> None:
    """`is_question=True` appends <<PAUSE:short>>."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="What happens next?",
                actions=[],
                is_question=True,
            )
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    assert nar.segments[0].text_with_markers.rstrip().endswith("<<PAUSE:short>>")
    # Filler question step also gets a pause.
    filler_q = next(
        seg for seg in nar.segments if seg.raw_narration == "A filler question step."
    )
    assert "<<PAUSE:short>>" in filler_q.text_with_markers


def test_render_inserts_equations_at_declared_indices() -> None:
    """An EquationIntroduction is rendered immediately after its host step."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Velocity stays with the ball.",
                actions=[],
            )
        ],
        equations=[
            EquationIntroduction(
                latex="v_x = v_{x,0}",
                introduces_after_step_index=0,
                explanation_in_words="Horizontal velocity is conserved.",
            )
        ],
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    # Find the equation segment.
    eq_segs = [s for s in nar.segments if "<<WRITE_EQUATION:" in s.text_with_markers]
    assert len(eq_segs) == 1
    eq_seg = eq_segs[0]
    assert "v_x = v_{x,0}" in eq_seg.text_with_markers
    assert "Horizontal velocity is conserved." in eq_seg.text_with_markers
    # It must be positioned after the host step, before the filler steps.
    eq_index = nar.segments.index(eq_seg)
    assert eq_index == 1  # right after segments[0] (the user step)


def test_render_resolves_diagram_id_via_resolver() -> None:
    """A resolver maps the plan's diagram_id to a runtime UID."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Show me the diagram.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
            )
        ]
    )

    def resolver(diagram_id: str) -> str | None:
        return f"diagram:topic-1:{diagram_id}_resolved"

    nar = LessonNarrator(_config()).render(
        topic_id="topic-1", plan=plan, diagram_id_resolver=resolver
    )
    assert "<<SHOW_DIAGRAM:diagram:topic-1:d1_resolved>>" in nar.full_text_with_markers
    assert "<<SHOW_DIAGRAM:d1>>" not in nar.full_text_with_markers
    assert nar.diagrams_referenced == ["diagram:topic-1:d1_resolved"]


def test_render_falls_back_to_diagram_id_verbatim_without_resolver() -> None:
    """Without a resolver, the plan's diagram_id is emitted as-is."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Show me the diagram.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
            )
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    assert "<<SHOW_DIAGRAM:d1>>" in nar.full_text_with_markers


def test_render_handles_step_with_no_actions() -> None:
    """A narration-only step gets no markers around it."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="Just a plain sentence.",
                actions=[],
            )
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    seg = nar.segments[0]
    # No SHOW_DIAGRAM (no target), no FOCUS, no PAUSE.
    assert "<<SHOW_DIAGRAM:" not in seg.text_with_markers
    assert "<<FOCUS:" not in seg.text_with_markers
    assert seg.text_with_markers.strip() == "Just a plain sentence."


def test_render_produces_consistent_segments_and_full_text() -> None:
    """`full_text_with_markers` equals join of segment.text_with_markers."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="One.",
                actions=[ChoreographyAction.focus],
                target_element_id="elem-1",
                target_diagram_id="d1",
            ),
            ChoreographyStep(
                narration="Two.",
                actions=[ChoreographyAction.trace],
                target_element_id="elem-1",
                target_diagram_id="d1",
            ),
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    rebuilt = " ".join(s.text_with_markers for s in nar.segments if s.text_with_markers)
    assert rebuilt == nar.full_text_with_markers


def test_render_passes_through_press_twice_flag() -> None:
    """presses_crucial_fact propagates onto the segment."""
    plan = _make_plan(
        user_steps=[
            ChoreographyStep(
                narration="A crucial sentence.",
                actions=[],
                presses_crucial_fact=True,
            )
        ]
    )
    nar = LessonNarrator(_config()).render(topic_id="topic-1", plan=plan)
    assert nar.segments[0].presses_crucial_fact is True
    # Filler payoff also presses; spot-check it on the segment too.
    filler_p = next(
        seg for seg in nar.segments if seg.raw_narration == "A filler payoff step."
    )
    assert filler_p.is_payoff is True
    assert filler_p.presses_crucial_fact is True


def test_emit_action_markers_focus_without_target_warns() -> None:
    """Direct unit on the helper: focus with no target_element_id warns."""
    step = ChoreographyStep(
        narration="Bad focus step.",
        actions=[ChoreographyAction.focus],
        # No target_element_id — focus marker should NOT be emitted.
    )
    report = LessonNarrationReport()
    before, after = _emit_action_markers(step, 0, report)
    assert before == []
    assert after == []
    assert any("focus" in w for w in report.warnings)


@pytest.mark.parametrize(
    "action,expected_position,expected_marker_prefix",
    [
        (ChoreographyAction.focus, "before", "<<FOCUS:"),
        (ChoreographyAction.trace, "after", "<<TRACE:"),
        (ChoreographyAction.point_at, "after", "<<POINT:"),
        (ChoreographyAction.unfocus, "before", "<<UNFOCUS"),
    ],
)
def test_action_marker_positions_parametrized(
    action: ChoreographyAction, expected_position: str, expected_marker_prefix: str
) -> None:
    """Parametrized smoke covering focus/trace/point_at/unfocus."""
    step = ChoreographyStep(
        narration="Some narration.",
        actions=[action],
        target_element_id="elem-1" if action != ChoreographyAction.unfocus else None,
    )
    report = LessonNarrationReport()
    before, after = _emit_action_markers(step, 0, report)
    if expected_position == "before":
        assert any(m.startswith(expected_marker_prefix) for m in before)
        assert all(not m.startswith(expected_marker_prefix) for m in after)
    else:
        assert any(m.startswith(expected_marker_prefix) for m in after)
        assert all(not m.startswith(expected_marker_prefix) for m in before)
