"""Tests for Phase 8 — Board Visual Verification Loop."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.board_verifier import (
    BoardVerifier,
    FixAction,
    VerificationResult,
    _parse_vision_response,
    suggest_fixes,
)
from feynman.agent.session_audit import SessionAudit

# ── Dataclass tests ────────────────────────────────────────


class TestVerificationResult:
    def test_fields_accessible(self):
        result = VerificationResult(
            score=4, issues=["minor overlap"], element_id="design-1", concept_index=2,
        )
        assert result.score == 4
        assert result.issues == ["minor overlap"]
        assert result.element_id == "design-1"
        assert result.concept_index == 2

    def test_frozen(self):
        result = VerificationResult(score=5, issues=[], element_id="eq-1", concept_index=0)
        with pytest.raises(AttributeError):
            result.score = 3  # type: ignore[misc]


class TestFixAction:
    def test_fields_accessible(self):
        fix = FixAction(
            element_id="eq-2",
            action="move",
            detail="move eq-2 right by 50px",
        )
        assert fix.element_id == "eq-2"
        assert fix.action == "move"
        assert fix.detail == "move eq-2 right by 50px"


# ── Vision response parsing ────────────────────────────────


class TestParseVisionResponse:
    def test_valid_json(self):
        text = '{"score": 4, "issues": ["minor spacing issue"]}'
        result = _parse_vision_response(text, "design-1", 2)
        assert result.score == 4
        assert result.issues == ["minor spacing issue"]
        assert result.element_id == "design-1"
        assert result.concept_index == 2

    def test_perfect_score(self):
        text = '{"score": 5, "issues": []}'
        result = _parse_vision_response(text, "eq-1", 0)
        assert result.score == 5
        assert result.issues == []

    def test_score_clamped_high(self):
        text = '{"score": 10, "issues": []}'
        result = _parse_vision_response(text, "design-1", 1)
        assert result.score == 5

    def test_score_clamped_low(self):
        text = '{"score": -1, "issues": []}'
        result = _parse_vision_response(text, "design-1", 1)
        assert result.score == 1

    def test_malformed_json_fallback(self):
        text = "This is not JSON at all"
        result = _parse_vision_response(text, "design-1", 1)
        assert result.score == 3
        assert len(result.issues) == 1
        assert "parse" in result.issues[0].lower()

    def test_json_with_markdown_fences(self):
        text = '```json\n{"score": 4, "issues": ["overlap"]}\n```'
        result = _parse_vision_response(text, "design-1", 0)
        assert result.score == 4
        assert result.issues == ["overlap"]

    def test_issues_not_list_converted(self):
        text = '{"score": 3, "issues": "single issue string"}'
        result = _parse_vision_response(text, "eq-1", 0)
        assert result.score == 3
        assert result.issues == ["single issue string"]


# ── Fix suggestions ────────────────────────────────────────


class TestSuggestFixes:
    def test_overlap_issue(self):
        result = VerificationResult(
            score=2,
            issues=["eq-2 overlaps with design-1 border"],
            element_id="design-1",
            concept_index=1,
        )
        fixes = suggest_fixes(result)
        assert len(fixes) == 1
        assert fixes[0].action == "remove_overlap"
        assert fixes[0].element_id == "eq-2"

    def test_spacing_issue(self):
        result = VerificationResult(
            score=3,
            issues=["Elements are too close together in the top-left"],
            element_id="text-1",
            concept_index=0,
        )
        fixes = suggest_fixes(result)
        assert len(fixes) == 1
        assert fixes[0].action == "move"

    def test_cutoff_issue(self):
        result = VerificationResult(
            score=2,
            issues=["design-3 is cut off at the right edge"],
            element_id="design-3",
            concept_index=2,
        )
        fixes = suggest_fixes(result)
        assert len(fixes) == 1
        assert fixes[0].action == "resize"
        assert fixes[0].element_id == "design-3"

    def test_no_issues_no_fixes(self):
        result = VerificationResult(score=5, issues=[], element_id="eq-1", concept_index=0)
        fixes = suggest_fixes(result)
        assert fixes == []

    def test_multiple_issues(self):
        result = VerificationResult(
            score=1,
            issues=[
                "text-1 overlaps with design-1",
                "eq-2 is too small to read",
                "elements cramped in top-left",
            ],
            element_id="design-1",
            concept_index=1,
        )
        fixes = suggest_fixes(result)
        assert len(fixes) == 3
        assert fixes[0].action == "remove_overlap"
        assert fixes[1].action == "resize"
        assert fixes[2].action == "move"

    def test_generic_issue_defaults_to_move(self):
        result = VerificationResult(
            score=3,
            issues=["something looks off with the layout"],
            element_id="design-1",
            concept_index=0,
        )
        fixes = suggest_fixes(result)
        assert len(fixes) == 1
        assert fixes[0].action == "move"
        assert fixes[0].element_id == "design-1"


# ── BoardVerifier async tests ─────────────────────────────


class TestBoardVerifier:
    @pytest.fixture()
    def audit(self):
        return SessionAudit()

    @pytest.fixture()
    def publish_fn(self):
        return AsyncMock()

    @pytest.fixture()
    def verifier(self, publish_fn, audit):
        return BoardVerifier(publish_fn=publish_fn, audit=audit)

    def test_resolve_capture_completes_future(self, verifier):
        """resolve_capture should set the result on a pending future."""
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        verifier._pending["req-123"] = future
        verifier.resolve_capture("req-123", "base64data")
        assert future.result() == "base64data"
        loop.close()

    def test_resolve_capture_ignores_unknown_request(self, verifier):
        """resolve_capture with unknown request_id is a no-op."""
        verifier.resolve_capture("nonexistent", "data")
        assert len(verifier._pending) == 0

    @pytest.mark.asyncio()
    async def test_screenshot_timeout_logs_audit(self, verifier, publish_fn, audit):
        """When frontend doesn't respond, logs timeout to audit."""
        # Don't resolve the future — let it timeout.
        # Patch _request_screenshot to return None (simulating timeout).
        with patch.object(verifier, "_request_screenshot", new_callable=AsyncMock, return_value=None):
            result = await verifier.request_verification(
                element_id="design-1",
                concept_index=0,
                board_context="Board: 50% free.",
            )
        assert result is None
        events = audit._events
        assert any(e.event == "screenshot_timeout" for e in events)

    @pytest.mark.asyncio()
    async def test_request_verification_calls_vision(self, verifier, publish_fn, audit):
        """Full flow: screenshot → vision model → result."""
        fake_screenshot = "iVBORw0KGgo="  # Tiny fake base64.
        vision_result = VerificationResult(
            score=4, issues=["minor spacing"], element_id="design-1", concept_index=0,
        )

        with (
            patch.object(verifier, "_request_screenshot", new_callable=AsyncMock, return_value=fake_screenshot),
            patch.object(verifier, "_verify_with_vision", new_callable=AsyncMock, return_value=vision_result),
        ):
            result = await verifier.request_verification(
                element_id="design-1",
                concept_index=0,
                board_context="Board: 50% free.",
            )
        assert result is not None
        assert result.score == 4
        # Audit should have the result logged.
        events = audit._events
        assert any(e.event == "result" for e in events)

    @pytest.mark.asyncio()
    async def test_low_score_generates_fix_suggestions(self, verifier, publish_fn, audit):
        """Score <= 3 triggers fix suggestions logged to audit."""
        vision_result = VerificationResult(
            score=2,
            issues=["eq-1 overlaps with design-1"],
            element_id="design-1",
            concept_index=0,
        )

        with (
            patch.object(verifier, "_request_screenshot", new_callable=AsyncMock, return_value="fakedata"),
            patch.object(verifier, "_verify_with_vision", new_callable=AsyncMock, return_value=vision_result),
        ):
            await verifier.request_verification(
                element_id="design-1",
                concept_index=0,
                board_context="Board: 30% free.",
            )
        events = audit._events
        assert any(e.event == "fix_suggested" for e in events)

    @pytest.mark.asyncio()
    async def test_high_score_no_fix_suggestions(self, verifier, publish_fn, audit):
        """Score > 3 does not trigger fix suggestions."""
        vision_result = VerificationResult(
            score=5, issues=[], element_id="design-1", concept_index=0,
        )

        with (
            patch.object(verifier, "_request_screenshot", new_callable=AsyncMock, return_value="fakedata"),
            patch.object(verifier, "_verify_with_vision", new_callable=AsyncMock, return_value=vision_result),
        ):
            await verifier.request_verification(
                element_id="design-1",
                concept_index=0,
                board_context="Board: 70% free.",
            )
        events = audit._events
        assert not any(e.event == "fix_suggested" for e in events)

    @pytest.mark.asyncio()
    async def test_exception_caught_and_logged(self, verifier, publish_fn, audit):
        """Errors in verification don't propagate — logged to audit."""
        with patch.object(
            verifier, "_request_screenshot", new_callable=AsyncMock,
            side_effect=RuntimeError("network failure"),
        ):
            result = await verifier.request_verification(
                element_id="design-1",
                concept_index=0,
                board_context="Board: 50% free.",
            )
        assert result is None
        events = audit._events
        assert any(e.event == "error" for e in events)

    @pytest.mark.asyncio()
    async def test_request_screenshot_sends_capture_message(self, verifier, publish_fn):
        """_request_screenshot publishes a capture_board message."""
        # We'll let it timeout, but check that publish was called.
        with patch.object(verifier, "_request_screenshot", wraps=verifier._request_screenshot):
            # Manually trigger — will timeout since no frontend.
            result = await verifier._request_screenshot()
        assert result is None
        # Publish should have been called with the capture request.
        publish_fn.assert_called_once()
        call_args = publish_fn.call_args[0]
        payload = json.loads(call_args[0])
        assert payload["type"] == "capture_board"
        assert "request_id" in payload
        assert payload["max_width"] == 512
        assert payload["max_height"] == 288
