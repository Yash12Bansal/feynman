"""Tests for the doubt-resolution board-event compiler.

The compiler turns high-level `ResolutionBeat`s (the planner's output) into the
ManifestEvent-shaped board events the frontend plays on the doubt board.
"""

from __future__ import annotations

import pytest

from feynman.agent.doubt_resolution.board_events import (
    REVEAL_ALL_STEP,
    AnimateParameterBE,
    FocusBE,
    PointAtBE,
    RevealStepBE,
    ShowDiagramBE,
    TraceBE,
    WriteEquationBE,
    WriteKeyPointBE,
    compile_plan,
)
from feynman.agent.doubt_resolution.models import (
    AnimateParameterAction,
    FocusAction,
    GenerateDiagram,
    KeepDiagram,
    NoDiagram,
    PointAtAction,
    ResolutionBeat,
    ReuseDiagram,
    RevealStepAction,
    SetParameterAction,
    TraceAction,
    WriteEquationBlock,
    WriteKeyPointBlock,
    WriteStepBlock,
)


def _beat(**kw) -> ResolutionBeat:
    kw.setdefault("narration_text", "The ball lands back in your hand.")
    return ResolutionBeat(**kw)


def test_reuse_beat_emits_show_then_notebook_then_annotations():
    beat = _beat(
        diagram=ReuseDiagram(diagram_id="diagram:phys:two_frames"),
        notebook_writes=[
            WriteStepBlock(text="Velocity adds: v_ball + v_train"),
            WriteEquationBlock(latex="v = u + at", boxed=True),
        ],
        annotation_actions=[
            FocusAction(target_element_id="train-ball-arc", text="watch this"),
            TraceAction(element_id="platform-ball-arc", duration_ms=1200),
        ],
    )
    [events] = compile_plan([beat], ["diagram:phys:two_frames"])
    kinds = [e.type for e in events]
    # show_diagram first, then both notebook writes, then both annotations.
    assert kinds == [
        "show_diagram",
        "write_step",
        "write_equation",
        "focus",
        "trace",
    ]
    assert isinstance(events[0], ShowDiagramBE)
    assert events[0].diagram_id == "diagram:phys:two_frames"
    assert isinstance(events[2], WriteEquationBE) and events[2].boxed is True
    # annotations are stamped with the active diagram id.
    assert isinstance(events[3], FocusBE)
    assert events[3].diagram_id == "diagram:phys:two_frames"
    assert isinstance(events[4], TraceBE)
    assert events[4].diagram_id == "diagram:phys:two_frames"


def test_keep_beat_inherits_active_diagram_for_annotations():
    beats = [
        _beat(diagram=ReuseDiagram(diagram_id="d1")),
        _beat(
            diagram=KeepDiagram(),
            annotation_actions=[PointAtAction(element_id="arrow", from_side="right")],
        ),
    ]
    first, second = compile_plan(beats, ["d1", None])
    assert [e.type for e in first] == ["show_diagram"]
    # second beat shows no new diagram but its pointer still targets d1.
    assert [e.type for e in second] == ["point_at"]
    assert isinstance(second[0], PointAtBE)
    assert second[0].diagram_id == "d1"


def test_none_beat_without_active_diagram_drops_annotations():
    # An annotation with no diagram ever shown has nothing to anchor to — it
    # must be dropped, never crash delivery.
    beat = _beat(
        diagram=NoDiagram(),
        notebook_writes=[WriteKeyPointBlock(text="Motion is relative.")],
        annotation_actions=[FocusAction(target_role="ghost")],
    )
    [events] = compile_plan([beat], [None])
    assert [e.type for e in events] == ["write_key_point"]
    assert isinstance(events[0], WriteKeyPointBE)


def test_generate_beat_uses_resolved_id():
    beat = _beat(diagram=GenerateDiagram(brief="a relative-velocity vector triangle"))
    [events] = compile_plan([beat], ["doubt-gen-0"])
    assert isinstance(events[0], ShowDiagramBE)
    assert events[0].diagram_id == "doubt-gen-0"


def test_notebook_block_ids_are_unique_across_beats():
    beats = [
        _beat(notebook_writes=[WriteStepBlock(text="step a")]),
        _beat(notebook_writes=[WriteStepBlock(text="step b")]),
    ]
    first, second = compile_plan(beats, [None, None])
    id_a = first[0].id  # type: ignore[union-attr]
    id_b = second[0].id  # type: ignore[union-attr]
    assert id_a != id_b


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        compile_plan([_beat()], [])


def test_resolution_beat_defaults_to_no_diagram():
    beat = _beat()
    assert isinstance(beat.diagram, NoDiagram)
    assert beat.notebook_writes == []
    # back-compat fields still present with defaults.
    assert beat.target_diagram_id is None
    assert beat.visual_intent_description == ""


# ── Phase IV: presentation_mode + build_up reveal-all safety ─────────────────


def test_show_diagram_stamps_presentation_mode():
    [events] = compile_plan(
        [_beat(diagram=ReuseDiagram(diagram_id="d1"))],
        ["d1"],
        presentation_modes=["build_up"],
    )
    assert isinstance(events[0], ShowDiagramBE)
    assert events[0].presentation_mode == "build_up"


def test_presentation_mode_defaults_none_without_modes():
    # Backward compatible: omitting presentation_modes leaves mode None and
    # injects no reveal events.
    [events] = compile_plan([_beat(diagram=ReuseDiagram(diagram_id="d1"))], ["d1"])
    assert events[0].presentation_mode is None
    assert [e.type for e in events] == ["show_diagram"]


def test_build_up_swap_injects_reveal_all_for_outgoing():
    beats = [
        _beat(diagram=ReuseDiagram(diagram_id="A")),
        _beat(diagram=ReuseDiagram(diagram_id="B")),
    ]
    first, second = compile_plan(beats, ["A", "B"], presentation_modes=["build_up", "overview"])
    assert [e.type for e in first] == ["show_diagram"]
    # B's beat flushes the outgoing build_up A to fully-revealed BEFORE showing B.
    assert [e.type for e in second] == ["reveal_step", "show_diagram"]
    assert isinstance(second[0], RevealStepBE)
    assert second[0].diagram_id == "A" and second[0].step == REVEAL_ALL_STEP
    assert second[1].diagram_id == "B"


def test_build_up_last_diagram_gets_terminal_reveal_all():
    [events] = compile_plan(
        [_beat(diagram=ReuseDiagram(diagram_id="A"))],
        ["A"],
        presentation_modes=["build_up"],
    )
    assert [e.type for e in events] == ["show_diagram", "reveal_step"]
    assert isinstance(events[1], RevealStepBE)
    assert events[1].diagram_id == "A" and events[1].step == REVEAL_ALL_STEP


def test_overview_diagrams_never_inject_reveal_all():
    beats = [
        _beat(diagram=ReuseDiagram(diagram_id="A")),
        _beat(diagram=ReuseDiagram(diagram_id="B")),
    ]
    out = compile_plan(beats, ["A", "B"], presentation_modes=["overview", "overview"])
    assert [[e.type for e in b] for b in out] == [["show_diagram"], ["show_diagram"]]


def test_presentation_modes_length_mismatch_raises():
    with pytest.raises(ValueError):
        compile_plan([_beat(), _beat()], [None, None], presentation_modes=["build_up"])


def test_animate_parameter_be_from_alias_serialization():
    # D3: the by_alias dump (what doubt_delivery uses) emits the JSON key `from`
    # the frontend reads; the bare field name is `from_` (a Python keyword).
    ev = AnimateParameterBE(diagram_id="A", name="theta", to=55, from_=20, duration_ms=900)
    aliased = ev.model_dump(by_alias=True)
    assert aliased["from"] == 20 and "from_" not in aliased
    assert ev.model_dump()["from_"] == 20


def test_param_and_reveal_actions_compile_to_board_events():
    # Phase V-A: the doubt planner's new annotation actions compile to the
    # matching board events, stamped with the active diagram id.
    beat = _beat(
        diagram=ReuseDiagram(diagram_id="A"),
        annotation_actions=[
            RevealStepAction(step=2),
            SetParameterAction(name="theta", value=20),
            AnimateParameterAction(name="theta", to=55, from_=20, duration_ms=900),
        ],
    )
    [events] = compile_plan([beat], ["A"])  # overview → no terminal reveal-all
    assert [e.type for e in events] == [
        "show_diagram",
        "reveal_step",
        "set_parameter",
        "animate_parameter",
    ]
    assert events[1].step == 2  # the authored reveal_step
    assert isinstance(events[3], AnimateParameterBE)
    assert events[3].from_ == 20 and events[3].to == 55 and events[3].diagram_id == "A"
    assert events[3].model_dump(by_alias=True)["from"] == 20  # delivery dump
