"""Phase 5a-2 — layout-verification feedback routing.

The existing layout verifier (``request_verification``) was audit-only. 5a-2
extends it with an optional ``on_feedback`` callback that fires a
``modify_design_diagram``-flavoured ``PerceptionFeedback`` on severe scores
(``score <= 2``) backed by at least one actionable ``FixAction``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.board_verifier import (
    BoardVerifier,
    PerceptionFeedback,
    VerificationResult,
)
from feynman.agent.session_audit import SessionAudit


def _fake_anthropic_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _build_verifier() -> BoardVerifier:
    return BoardVerifier(publish_fn=AsyncMock(), audit=SessionAudit())


@pytest.mark.asyncio
async def test_layout_verification_audit_only_when_no_callback() -> None:
    """Default (5a-1 behavior) — no callback wired, no queue enqueue."""
    verifier = _build_verifier()

    fake_haiku = _fake_anthropic_response('{"score": 1, "issues": ["overlap on design-1"]}')
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
    )

    with (
        patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
        patch("anthropic.AsyncAnthropic", return_value=fake_client),
    ):
        result = await verifier.request_verification(
            element_id="design-1",
            concept_index=0,
            board_context="(empty)",
        )
    assert result is not None
    assert result.score == 1


@pytest.mark.asyncio
async def test_layout_severe_score_with_fixes_fires_callback() -> None:
    verifier = _build_verifier()
    captured: list[tuple[PerceptionFeedback, VerificationResult]] = []

    fake_haiku = _fake_anthropic_response(
        '{"score": 2, "issues": ["overlap between design-1 and eq-2"]}'
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
    )

    with (
        patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
        patch("anthropic.AsyncAnthropic", return_value=fake_client),
    ):
        await verifier.request_verification(
            element_id="design-1",
            concept_index=0,
            board_context="design-1 + eq-2",
            on_feedback=lambda fb, r: captured.append((fb, r)),
            original_claim="free body diagram",
        )

    assert len(captured) == 1
    fb, res = captured[0]
    assert fb.tool_name == "modify_design_diagram"
    assert fb.target_diagram_id == "design-1"
    assert fb.suggested_modification  # non-empty
    assert "layout: free body diagram" in fb.original_claim
    assert res.score == 2


@pytest.mark.asyncio
async def test_layout_score_three_does_not_fire_callback() -> None:
    """Score 3 = acceptable; only score <= 2 routes to the LLM queue."""
    verifier = _build_verifier()
    captured: list[Any] = []

    fake_haiku = _fake_anthropic_response(
        '{"score": 3, "issues": ["minor crowding near design-1"]}'
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
    )

    with (
        patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
        patch("anthropic.AsyncAnthropic", return_value=fake_client),
    ):
        await verifier.request_verification(
            element_id="design-1",
            concept_index=0,
            board_context="(...)",
            on_feedback=lambda fb, r: captured.append((fb, r)),
            original_claim="x",
        )

    assert captured == []


@pytest.mark.asyncio
async def test_layout_score_one_fires_callback() -> None:
    verifier = _build_verifier()
    captured: list[Any] = []

    fake_haiku = _fake_anthropic_response(
        '{"score": 1, "issues": ["unreadable label on design-2"]}'
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
    )

    with (
        patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
        patch("anthropic.AsyncAnthropic", return_value=fake_client),
    ):
        await verifier.request_verification(
            element_id="design-2",
            concept_index=0,
            board_context="(...)",
            on_feedback=lambda fb, r: captured.append((fb, r)),
            original_claim=None,  # exercise the default-claim path
        )

    assert len(captured) == 1
    fb, _r = captured[0]
    # When original_claim is None, the prefix falls back to "last diagram event".
    assert "layout: last diagram event" in fb.original_claim


@pytest.mark.asyncio
async def test_layout_severe_without_issues_no_callback() -> None:
    """score<=2 but the issues list is empty → no FixAction → no callback."""
    verifier = _build_verifier()
    captured: list[Any] = []

    # Edge case: malformed/empty issues — the suggest_fixes path returns [].
    fake_haiku = _fake_anthropic_response('{"score": 2, "issues": []}')
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
    )

    with (
        patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
        patch("anthropic.AsyncAnthropic", return_value=fake_client),
    ):
        await verifier.request_verification(
            element_id="design-1",
            concept_index=0,
            board_context="(...)",
            on_feedback=lambda fb, r: captured.append((fb, r)),
            original_claim="x",
        )

    assert captured == []


@pytest.mark.asyncio
async def test_layout_feedback_uses_first_fix_action_as_modification() -> None:
    """The PerceptionFeedback's suggested_modification comes from FixAction.detail."""
    verifier = _build_verifier()
    captured: list[tuple[PerceptionFeedback, VerificationResult]] = []

    fake_haiku = _fake_anthropic_response(
        '{"score": 1, "issues": '
        '["overlap between design-1 and design-2", "spacing on eq-3 is cramped"]}'
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
    )

    with (
        patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
        patch("anthropic.AsyncAnthropic", return_value=fake_client),
    ):
        await verifier.request_verification(
            element_id="design-1",
            concept_index=0,
            board_context="(...)",
            on_feedback=lambda fb, r: captured.append((fb, r)),
            original_claim="block on ramp",
        )

    assert len(captured) == 1
    fb, _r = captured[0]
    # FixAction.detail is the issue string verbatim; the first issue drives the
    # suggested modification.
    assert "overlap between design-1 and design-2" in fb.suggested_modification
