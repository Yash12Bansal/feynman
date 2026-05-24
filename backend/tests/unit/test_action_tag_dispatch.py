"""Tests for the Phase 4 action-tag dispatcher.

These tests focus on the verb → instruction mapping. ``_build_annotation_target``
and ``_publish_visual`` are patched so we can inspect the constructed
``*Instruction`` objects directly without touching LiveKit or the
TeachingContext.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from feynman.agent.action_tag_parser import ActionTag
from feynman.livekit import action_tag_dispatch
from feynman.visuals.schemas import (
    AnnotationTarget,
    BracketInstruction,
    DrawCalloutInstruction,
    HighlightPulseInstruction,
    PinLabelInstruction,
    SyncMode,
)

# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def fake_session() -> SimpleNamespace:
    """An ``AgentSession``-shaped stub. ``userdata`` is unused because we
    patch out ``_build_annotation_target`` and ``_publish_visual`` — both
    of which are the only paths that read it. ``board_verifier=None`` lets
    the Phase 5a-1 scheduling helper short-circuit cleanly.
    """
    return SimpleNamespace(
        userdata=SimpleNamespace(
            board_verifier=None,
            current_diagram_dictionary={},
        ),
        room_io=None,
    )


@pytest.fixture
def patches(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the resolver and publish path. Capture every published
    instruction in ``state["published"]``.
    """
    state: dict[str, Any] = {"published": []}

    def fake_resolve(_ctx: Any, handle: str) -> tuple[str, AnnotationTarget, bool]:
        # Echo handle as id when caller passes "id:foo"; otherwise role.
        if handle.startswith("id:"):
            real = handle[3:]
            return real, AnnotationTarget(kind="id", value=real), True
        return handle, AnnotationTarget(kind="role", value=handle), False

    async def fake_publish(_ctx: Any, instruction: Any, *, wait_for_speech: bool) -> None:
        state["published"].append(instruction)
        state["last_wait"] = wait_for_speech

    monkeypatch.setattr(action_tag_dispatch, "_build_annotation_target", fake_resolve)
    monkeypatch.setattr(action_tag_dispatch, "_publish_visual", fake_publish)
    return state


# ── highlight ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_highlight_builds_highlight_pulse_with_long_duration(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(verb="highlight", attrs={"target": "hypotenuse"})
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert isinstance(inst, HighlightPulseInstruction)
    assert inst.target_element_id == "hypotenuse"
    assert inst.duration_ms == 1500
    assert inst.sync_mode == SyncMode.AFTER_NEXT_SENTENCE
    assert inst.target is not None
    assert inst.target.kind == "role"
    assert inst.target.value == "hypotenuse"


@pytest.mark.asyncio
async def test_pulse_builds_highlight_pulse_with_short_duration(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(verb="pulse", attrs={"target": "weight"})
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert isinstance(inst, HighlightPulseInstruction)
    assert inst.duration_ms == 800
    assert inst.target_element_id == "weight"
    assert inst.sync_mode == SyncMode.AFTER_NEXT_SENTENCE


@pytest.mark.asyncio
async def test_id_kind_propagates_when_resolver_matches(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    """When the dictionary resolves the handle, the target kind is ``id``."""
    tag = ActionTag(verb="highlight", attrs={"target": "id:line_3"})
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert inst.target is not None
    assert inst.target.kind == "id"
    assert inst.target.value == "line_3"


# ── callout ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callout_builds_draw_callout_with_text(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(
        verb="callout",
        attrs={"from": "weight", "text": "gravity pulls down", "direction": "down"},
    )
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert isinstance(inst, DrawCalloutInstruction)
    assert inst.text == "gravity pulls down"
    assert inst.direction == "down"
    assert inst.target_element_id == "weight"
    assert inst.sync_mode == SyncMode.AFTER_NEXT_SENTENCE


@pytest.mark.asyncio
async def test_callout_invalid_direction_falls_back_to_default(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(
        verb="callout",
        attrs={"from": "x", "text": "yo", "direction": "northeast"},
    )
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert inst.direction == "up-right"


# ── bracket ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bracket_splits_comma_separated_targets(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(
        verb="bracket",
        attrs={"between": "opposite, hypotenuse", "label": "sin θ"},
    )
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert isinstance(inst, BracketInstruction)
    assert inst.element_a_id == "opposite"
    assert inst.element_b_id == "hypotenuse"
    assert inst.label == "sin θ"
    assert inst.side == "above"
    assert inst.sync_mode == SyncMode.AFTER_NEXT_SENTENCE


@pytest.mark.asyncio
async def test_bracket_with_only_one_target_skips(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(
        verb="bracket",
        attrs={"between": "only_one", "label": "oops"},
    )
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    assert patches["published"] == []


# ── pin ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pin_builds_pin_label_with_label_text(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(
        verb="pin",
        attrs={"near": "f_right", "label": "F", "position": "right"},
    )
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert isinstance(inst, PinLabelInstruction)
    assert inst.text == "F"
    assert inst.position == "right"
    assert inst.target_element_id == "f_right"
    assert inst.sync_mode == SyncMode.AFTER_NEXT_SENTENCE


@pytest.mark.asyncio
async def test_pin_defaults_position_above_when_invalid(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(
        verb="pin",
        attrs={"near": "f_right", "label": "F", "position": "diagonally"},
    )
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert inst.position == "above"


# ── Missing required attrs ────────────────────────────────────


@pytest.mark.asyncio
async def test_highlight_with_no_target_is_skipped(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(verb="highlight", attrs={})
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    assert patches["published"] == []


@pytest.mark.asyncio
async def test_callout_with_no_text_is_skipped(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(verb="callout", attrs={"from": "x"})
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    assert patches["published"] == []


@pytest.mark.asyncio
async def test_pin_with_no_label_is_skipped(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    tag = ActionTag(verb="pin", attrs={"near": "x"})
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    assert patches["published"] == []


# ── Attribute case tolerance ──────────────────────────────────


@pytest.mark.asyncio
async def test_attribute_case_is_normalized(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    """Parser preserves case; dispatcher lowercases for lookup."""
    tag = ActionTag(verb="highlight", attrs={"TARGET": "x"})
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)
    [inst] = patches["published"]
    assert inst.target_element_id == "x"


# ── Fail-silent on publish error ──────────────────────────────


@pytest.mark.asyncio
async def test_publish_exception_is_swallowed(
    fake_session: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A downstream publish error must never crash the dispatcher."""

    def fake_resolve(_ctx: Any, handle: str) -> tuple[str, AnnotationTarget, bool]:
        return handle, AnnotationTarget(kind="role", value=handle), False

    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("downstream blew up")

    monkeypatch.setattr(action_tag_dispatch, "_build_annotation_target", fake_resolve)
    monkeypatch.setattr(action_tag_dispatch, "_publish_visual", boom)

    tag = ActionTag(verb="highlight", attrs={"target": "x"})
    # Must not raise.
    await action_tag_dispatch.dispatch_action_tag(fake_session, tag)


# ── Phase 5a-1: verification scheduling ────────────────────────


@pytest.mark.asyncio
async def test_dispatch_schedules_verification_for_highlight(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    """Successful dispatch of `<highlight target="..."/>` schedules a
    verification call with the right tool name, claim, and target id."""
    scheduled: list[dict[str, Any]] = []

    def fake_schedule(_ctx: Any, **kwargs: Any) -> None:
        scheduled.append(kwargs)

    with patch.object(action_tag_dispatch, "_schedule_annotation_verification", fake_schedule):
        tag = ActionTag(verb="highlight", attrs={"target": "hypotenuse"})
        await action_tag_dispatch.dispatch_action_tag(fake_session, tag)

    assert len(scheduled) == 1
    call = scheduled[0]
    assert call["tool_name"] == "highlight_pulse"
    assert call["original_claim"] == "hypotenuse"
    assert call["target_id"] == "hypotenuse"


@pytest.mark.asyncio
async def test_dispatch_schedules_verification_for_bracket_with_joined_id(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    """Bracket's target_id is the comma-joined pair so dedup keys are unique."""
    scheduled: list[dict[str, Any]] = []

    def fake_schedule(_ctx: Any, **kwargs: Any) -> None:
        scheduled.append(kwargs)

    with patch.object(action_tag_dispatch, "_schedule_annotation_verification", fake_schedule):
        tag = ActionTag(
            verb="bracket",
            attrs={"between": "opposite, hypotenuse", "label": "sin θ"},
        )
        await action_tag_dispatch.dispatch_action_tag(fake_session, tag)

    assert len(scheduled) == 1
    call = scheduled[0]
    assert call["tool_name"] == "bracket"
    assert call["original_claim"] == "opposite, hypotenuse"
    assert call["target_id"] == "opposite,hypotenuse"


@pytest.mark.asyncio
async def test_dispatch_missing_target_skips_verification(
    fake_session: SimpleNamespace, patches: dict[str, Any]
) -> None:
    """When the builder returns None (missing attr), no verification scheduled."""
    scheduled: list[dict[str, Any]] = []

    def fake_schedule(_ctx: Any, **kwargs: Any) -> None:
        scheduled.append(kwargs)

    with patch.object(action_tag_dispatch, "_schedule_annotation_verification", fake_schedule):
        # No target attribute → _build_highlight returns None → dispatch
        # short-circuits before publish or schedule.
        tag = ActionTag(verb="highlight", attrs={})
        await action_tag_dispatch.dispatch_action_tag(fake_session, tag)

    assert scheduled == []
