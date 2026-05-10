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
    userdata.current_diagram_dictionary = {
        "side_AB": {"role": "hypotenuse", "semantic": "the ladder, 10 m"},
        "side_BC": {"role": "opposite", "semantic": "the wall"},
        "side_AC": {"role": "adjacent", "semantic": "the ground"},
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
async def test_pin_label_near_falls_back_to_raw_id_when_no_match() -> None:
    ctx = _make_mock_ctx()
    await pin_label_near(ctx, element_or_role="vertex_A", text="60°")
    payload = _published_payload(ctx)
    # vertex_A isn't in the ladder dict above → frontend gets the raw input.
    assert payload["target_element_id"] == "vertex_A"


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
