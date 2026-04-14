"""Tests for split-board panel routing.

Phase 2 of the split-board migration (`docs/design/10-split-board.md`). Every
visual instruction must carry a `panel` value stamped deterministically by the
backend based on instruction type. The LLM never sets panel.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import TypeAdapter

from feynman.agent.board import BoardManager
from feynman.agent.tools import (
    INSTRUCTION_TYPE_TO_PANEL,
    _publish_switch_board,
    _publish_visual,
    _stamp_panel,
    scroll_board,
)
from feynman.visuals.instructions import VisualInstruction
from feynman.visuals.schemas import (
    AnnotateInstruction,
    AnnotationAction,
    BoardIntent,
    ClearInstruction,
    DataPoint,
    DataSeries,
    DiagramNode,
    DrawDesignDiagramInstruction,
    DrawDiagramInstruction,
    DrawSceneInstruction,
    EquationStep,
    GraphType,
    HighlightInstruction,
    HighlightStyle,
    HighlightWalkInstruction,
    HighlightWalkStep,
    NewPageInstruction,
    Panel,
    SceneTemplateId,
    SceneTemplateRef,
    ScrollViewInstruction,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    SlidePendingInstruction,
    StepEquationInstruction,
    StrikethroughInstruction,
    SwitchBoardInstruction,
    WriteAnswerInstruction,
    WriteEquationInstruction,
    WriteSectionInstruction,
    WriteStepInstruction,
    WriteTextInstruction,
    _BaseInstruction,
)

# ── Mapping coverage ──────────────────────────────────────────


def _all_instruction_type_literals() -> list[str]:
    """Extract every concrete instruction type's `type` literal from the union."""
    # VisualInstruction = Annotated[Union[...], Discriminator]; unwrap to members.
    adapter = TypeAdapter(VisualInstruction)
    schema = adapter.json_schema()
    # The union's one_of items each reference a concrete instruction schema.
    members = []
    for item in schema.get("oneOf", []):
        ref = item.get("$ref", "")
        name = ref.rsplit("/", 1)[-1]
        if name:
            members.append(name)
    # Extract the `type` literal from each member via its schema.
    defs = schema.get("$defs", {})
    type_literals = []
    for name in members:
        props = defs.get(name, {}).get("properties", {})
        type_prop = props.get("type", {})
        lit = type_prop.get("const")
        if lit:
            type_literals.append(lit)
    return type_literals


def test_mapping_covers_every_instruction_type() -> None:
    """Every registered VisualInstruction variant has a panel mapping.

    Fails loudly if a new instruction type is added to the union without being
    registered in INSTRUCTION_TYPE_TO_PANEL.
    """
    type_literals = _all_instruction_type_literals()
    assert len(type_literals) == 21, (
        f"expected 21 instruction types, discovered {len(type_literals)}: {type_literals}"
    )
    missing = [t for t in type_literals if t not in INSTRUCTION_TYPE_TO_PANEL]
    assert not missing, f"missing from INSTRUCTION_TYPE_TO_PANEL: {missing}"


# ── _stamp_panel correctness ──────────────────────────────────


def _minimal(instruction_type: str) -> _BaseInstruction:
    """Build a minimally-valid instance of each instruction type.

    Uses per-type branching so one invalid constructor doesn't cascade
    into the other parametrized cases.
    """
    if instruction_type == "clear":
        return ClearInstruction()
    if instruction_type == "show_text":
        return ShowTextInstruction(text="hi")
    if instruction_type == "show_equation":
        return ShowEquationInstruction(latex="F=ma")
    if instruction_type == "step_equation":
        return StepEquationInstruction(steps=[EquationStep(latex="F=ma")])
    if instruction_type == "draw_diagram":
        return DrawDiagramInstruction(
            description="",
            nodes=[DiagramNode(id="n1", label="A")],
        )
    if instruction_type == "show_graph":
        return ShowGraphInstruction(
            graph_type=GraphType.LINE,
            series=[DataSeries(label="s", points=[DataPoint(x=0, y=0)])],
        )
    if instruction_type == "draw_design_diagram":
        return DrawDesignDiagramInstruction(
            spec={"title": "t", "elements": []},
        )
    if instruction_type == "draw_scene":
        return DrawSceneInstruction(
            template=SceneTemplateRef(template_id=SceneTemplateId.FREE_BODY),
        )
    if instruction_type == "highlight":
        return HighlightInstruction(target_id="x", style=HighlightStyle.GLOW)
    if instruction_type == "highlight_walk":
        return HighlightWalkInstruction(
            target_id="dg-1",
            steps=[HighlightWalkStep(sub_element_id="x", trigger_words=["hello"])],
        )
    if instruction_type == "annotate":
        return AnnotateInstruction(
            target_id="x",
            action=AnnotationAction.CIRCLE,
        )
    if instruction_type == "switch_board":
        return SwitchBoardInstruction(
            board_id="b",
            label="L",
            intent=BoardIntent.NEW,
        )
    if instruction_type == "scroll_view":
        return ScrollViewInstruction(target_x=0, target_y=0)
    if instruction_type == "slide_pending":
        return SlidePendingInstruction(title="Newton's 2nd Law")
    if instruction_type == "write_equation":
        return WriteEquationInstruction(latex="F = m a")
    if instruction_type == "write_step":
        return WriteStepInstruction(text="Solve for a")
    if instruction_type == "write_text":
        return WriteTextInstruction(text="Remember")
    if instruction_type == "write_section":
        return WriteSectionInstruction(title="Newton's 2nd Law")
    if instruction_type == "write_answer":
        return WriteAnswerInstruction(latex="a = 5")
    if instruction_type == "strikethrough":
        return StrikethroughInstruction(target_id="eq-3")
    if instruction_type == "new_page":
        return NewPageInstruction()
    raise ValueError(f"unknown instruction_type: {instruction_type}")


@pytest.mark.parametrize(
    "instruction_type,expected_panel",
    [
        ("show_text", Panel.NOTEBOOK),
        ("show_equation", Panel.NOTEBOOK),
        ("step_equation", Panel.NOTEBOOK),
        ("show_graph", Panel.NOTEBOOK),
        ("write_equation", Panel.NOTEBOOK),
        ("write_step", Panel.NOTEBOOK),
        ("write_text", Panel.NOTEBOOK),
        ("write_section", Panel.NOTEBOOK),
        ("write_answer", Panel.NOTEBOOK),
        ("strikethrough", Panel.NOTEBOOK),
        ("new_page", Panel.NOTEBOOK),
        ("draw_diagram", Panel.SLIDE),
        ("draw_design_diagram", Panel.SLIDE),
        ("draw_scene", Panel.SLIDE),
        ("slide_pending", Panel.SLIDE),
        ("highlight", Panel.REFERENCE),
        ("highlight_walk", Panel.REFERENCE),
        ("annotate", Panel.REFERENCE),
        ("clear", Panel.REFERENCE),
        ("switch_board", Panel.REFERENCE),
        ("scroll_view", Panel.REFERENCE),
    ],
)
def test_stamp_panel_sets_correct_value(instruction_type: str, expected_panel: Panel) -> None:
    instr = _minimal(instruction_type)
    assert instr.panel is None
    _stamp_panel(instr)
    assert instr.panel is expected_panel


def test_stamp_panel_missing_type_raises() -> None:
    """An unknown type literal is a KeyError, not a silent default."""
    instr = ShowTextInstruction(text="hi")
    # Simulate an unknown discriminator by mutating the frozen literal via
    # object.__setattr__ (Pydantic v2 allows this on instances).
    object.__setattr__(instr, "type", "nonexistent_type")
    with pytest.raises(KeyError):
        _stamp_panel(instr)


# ── Integration: _publish_visual ─────────────────────────────


def _make_mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()
    userdata = MagicMock()
    userdata.board_manager = BoardManager()
    userdata.current_concept = None
    userdata.lesson_plan = None
    userdata.current_concept_index = 0
    ctx.userdata = userdata
    return ctx


@pytest.mark.asyncio
async def test_publish_visual_stamps_panel() -> None:
    ctx = _make_mock_ctx()
    instr = ShowEquationInstruction(latex="F = ma")
    assert instr.panel is None
    await _publish_visual(ctx, instr)
    assert instr.panel is Panel.NOTEBOOK

    # And the published JSON must carry the panel field.
    call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
    published = json.loads(call_args[0][0])
    assert published["panel"] == "notebook"


@pytest.mark.asyncio
async def test_publish_visual_stamps_slide_for_diagram() -> None:
    ctx = _make_mock_ctx()
    instr = DrawDesignDiagramInstruction(
        spec={"title": "t", "elements": []},
    )
    await _publish_visual(ctx, instr)
    call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
    published = json.loads(call_args[0][0])
    assert published["panel"] == "slide"


@pytest.mark.asyncio
async def test_publish_switch_board_stamps_reference() -> None:
    ctx = _make_mock_ctx()
    await _publish_switch_board(ctx, "b1", "Label", BoardIntent.NEW)
    call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
    published = json.loads(call_args[0][0])
    assert published["type"] == "switch_board"
    assert published["panel"] == "reference"


@pytest.mark.asyncio
async def test_scroll_board_stamps_reference() -> None:
    """scroll_board bypasses _publish_visual; verify panel is still stamped."""
    ctx = _make_mock_ctx()
    # scroll_board calls _update_agent_prompt → ctx.session.current_agent.update_instructions
    ctx.session.current_agent.update_instructions = AsyncMock()
    # Seed a current concept on teaching context so prompt build works; None is fine.
    result = await scroll_board(ctx, direction="right")
    assert "Unknown direction" not in str(result)
    call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
    published = json.loads(call_args[0][0])
    assert published["type"] == "scroll_view"
    assert published["panel"] == "reference"


# ── JSON roundtrip ────────────────────────────────────────────


def test_json_roundtrip_preserves_panel() -> None:
    instr = ShowEquationInstruction(latex="E=mc^2")
    _stamp_panel(instr)
    assert instr.panel is Panel.NOTEBOOK
    raw = instr.model_dump_json(exclude_none=True)
    restored = TypeAdapter(VisualInstruction).validate_json(raw)
    assert restored.panel is Panel.NOTEBOOK
    assert restored.type == "show_equation"
