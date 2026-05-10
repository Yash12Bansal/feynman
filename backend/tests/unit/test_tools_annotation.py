"""Tests for the four slide-annotation tools (diagram awareness)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from feynman.agent.board import BoardManager
from feynman.agent.tools import (
    bracket,
    draw_callout,
    highlight_pulse,
    pin_label_near,
)


def _make_mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()
    userdata = MagicMock()
    userdata.board_manager = BoardManager()
    userdata.current_concept = None
    userdata.lesson_plan = None
    userdata.current_concept_index = 0
    # Diagram dictionary for the ladder problem (role → element_id resolver).
    # `bounds` is required for frontend positioning; the annotation tools
    # reject entries without bounds so a bogus instruction never reaches the
    # silent-drop path in SlideAnnotationLayer.
    userdata.current_diagram_dictionary = {
        "side_AB": {
            "role": "hypotenuse",
            "semantic": "the ladder, 10 m",
            "bounds": [120, 100, 280, 360],
        },
        "side_BC": {
            "role": "opposite",
            "semantic": "the wall",
            "bounds": [380, 80, 4, 400],
        },
        "side_AC": {
            "role": "adjacent",
            "semantic": "the ground",
            "bounds": [120, 470, 280, 4],
        },
    }
    ctx.userdata = userdata
    return ctx


def _published_payload(ctx: MagicMock) -> dict:
    call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
    return json.loads(call_args[0][0])


@pytest.mark.asyncio
async def test_pin_label_near_resolves_role() -> None:
    ctx = _make_mock_ctx()
    result = await pin_label_near(
        ctx,
        element_or_role="hypotenuse",
        text="10 m",
        position="above",
    )
    assert "side_AB" in result
    payload = _published_payload(ctx)
    assert payload["type"] == "pin_label"
    assert payload["panel"] == "slide"
    assert payload["target_element_id"] == "side_AB"
    assert payload["text"] == "10 m"
    assert payload["position"] == "above"


@pytest.mark.asyncio
async def test_pin_label_near_errors_on_unknown_role() -> None:
    """Unknown role → tool returns an error message that lists available
    roles/ids; nothing is published to the frontend (no silent failure)."""
    ctx = _make_mock_ctx()
    result = await pin_label_near(ctx, element_or_role="the line in red", text="60°")
    assert "No element matched 'the line in red'" in result
    assert "hypotenuse" in result  # available role surfaced for LLM retry
    assert "side_AB" in result  # available element_id surfaced too
    # No instruction was published — the only call to publish_data was nothing.
    ctx.session.room_io.room.local_participant.publish_data.assert_not_called()


@pytest.mark.asyncio
async def test_highlight_pulse_errors_with_no_diagram() -> None:
    """Empty dictionary (no diagram drawn yet) → empty-state error string."""
    ctx = _make_mock_ctx()
    ctx.userdata.current_diagram_dictionary = {}
    result = await highlight_pulse(ctx, element_or_role="hypotenuse")
    assert "No diagram on the slide" in result
    assert "draw_design_diagram" in result
    ctx.session.room_io.room.local_participant.publish_data.assert_not_called()


@pytest.mark.asyncio
async def test_bracket_errors_when_either_element_unknown() -> None:
    """Bracket needs both ends — if either resolves to None, error + no publish."""
    ctx = _make_mock_ctx()
    result = await bracket(
        ctx,
        element_a="hypotenuse",  # valid
        element_b="floating_unicorn",  # invalid
        label="right triangle",
    )
    assert "No element matched 'floating_unicorn'" in result
    ctx.session.room_io.room.local_participant.publish_data.assert_not_called()


@pytest.mark.asyncio
async def test_annotation_tool_errors_when_bounds_missing() -> None:
    """Resolved id but its dictionary entry has no bounds → tool errors,
    nothing published. Catches the rare case where design_agent skips bounds
    for an irregular shape."""
    ctx = _make_mock_ctx()
    # Add an entry without bounds.
    ctx.userdata.current_diagram_dictionary["theta-marker"] = {
        "role": "right_angle_marker",
        "semantic": "the right angle marker",
        # no bounds key
    }
    result = await pin_label_near(
        ctx,
        element_or_role="right_angle_marker",
        text="90°",
    )
    assert "no bounds" in result.lower()
    ctx.session.room_io.room.local_participant.publish_data.assert_not_called()


@pytest.mark.asyncio
async def test_draw_callout_resolves_role() -> None:
    ctx = _make_mock_ctx()
    await draw_callout(
        ctx,
        from_element="hypotenuse",
        text="this is the ladder!",
        direction="up-right",
    )
    payload = _published_payload(ctx)
    assert payload["type"] == "draw_callout"
    assert payload["panel"] == "slide"
    assert payload["target_element_id"] == "side_AB"
    assert payload["direction"] == "up-right"


@pytest.mark.asyncio
async def test_bracket_resolves_both_roles() -> None:
    ctx = _make_mock_ctx()
    await bracket(
        ctx,
        element_a="hypotenuse",
        element_b="adjacent",
        label="right triangle",
        side="below",
    )
    payload = _published_payload(ctx)
    assert payload["type"] == "bracket"
    assert payload["panel"] == "slide"
    assert payload["element_a_id"] == "side_AB"
    assert payload["element_b_id"] == "side_AC"
    assert payload["label"] == "right triangle"
    assert payload["side"] == "below"


@pytest.mark.asyncio
async def test_highlight_pulse_resolves_role() -> None:
    ctx = _make_mock_ctx()
    await highlight_pulse(
        ctx,
        element_or_role="opposite",
        duration_ms=1500,
    )
    payload = _published_payload(ctx)
    assert payload["type"] == "highlight_pulse"
    assert payload["panel"] == "slide"
    assert payload["target_element_id"] == "side_BC"
    assert payload["duration_ms"] == 1500


@pytest.mark.asyncio
async def test_pin_label_near_normalizes_invalid_position() -> None:
    """Bad position string falls back to the default 'above'."""
    ctx = _make_mock_ctx()
    await pin_label_near(
        ctx,
        element_or_role="hypotenuse",
        text="hi",
        position="askew",  # not a valid Literal
    )
    payload = _published_payload(ctx)
    assert payload["position"] == "above"
