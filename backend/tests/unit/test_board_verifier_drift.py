# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Phase 5a-3 — periodic drift verification + drift-flavoured feedback.

# Mirrors the 5a-2 verifier tests in shape:

# * :func:`_parse_drift_response` — JSON parsing for the drift prompt
# * :class:`DriftCheckResult` / :class:`PerceptionFeedback` (drift variant)
# * :class:`PerceptionFeedback.as_chat_note` — drift branch routing
# * ``BoardVerifier.request_drift_check`` end-to-end with mocked screenshot +
#   mocked Anthropic client
# * :func:`_format_element_summary` formatting
# * feedback enqueue behaviour keyed on ``is_consistent``
# * regression: annotation + diagram chat-note formats stay byte-identical
# """

# from __future__ import annotations

# from types import SimpleNamespace
# from typing import Any
# from unittest.mock import AsyncMock, patch

# import pytest

# from feynman.agent.board_verifier import (
#     BoardVerifier,
#     DriftCheckResult,
#     PerceptionFeedback,
#     _format_element_summary,
#     _parse_drift_response,
# )
# from feynman.agent.session_audit import SessionAudit

# # ── _parse_drift_response ────────────────────────────────


# def test_parse_valid_consistent_drift_json() -> None:
#     text = (
#         '{"is_consistent": true, "drift_kind": null, '
#         '"affected_element_id": null, "issue": "", "suggested_action": ""}'
#     )
#     result = _parse_drift_response(
#         text,
#         concept_index=2,
#         concept_title="Trigonometry",
#         state_hash="abc123",
#     )
#     assert result.is_consistent is True
#     assert result.drift_kind is None
#     assert result.affected_element_id is None
#     assert result.issue == ""
#     assert result.suggested_action == ""
#     assert result.concept_index == 2
#     assert result.concept_title == "Trigonometry"
#     assert result.state_hash == "abc123"


# def test_parse_concept_fit_drift_fully_populated() -> None:
#     text = (
#         '{"is_consistent": false, "drift_kind": "concept_fit", '
#         '"affected_element_id": "design-1", '
#         '"issue": "stale ladder diagram from previous concept", '
#         '"suggested_action": "Erase or repurpose design-1"}'
#     )
#     result = _parse_drift_response(
#         text,
#         concept_index=3,
#         concept_title="Right-triangle ratios",
#         state_hash="hash",
#     )
#     assert result.is_consistent is False
#     assert result.drift_kind == "concept_fit"
#     assert result.affected_element_id == "design-1"
#     assert "stale ladder" in result.issue
#     assert "Erase or repurpose" in result.suggested_action


# def test_parse_markdown_fenced_drift_response_strips_fences() -> None:
#     text = (
#         '```json\n{"is_consistent": false, "drift_kind": "cumulative_integrity", '
#         '"affected_element_id": "design-2", "issue": "ramp edited away", '
#         '"suggested_action": "modify_design_diagram(...)"}\n```'
#     )
#     result = _parse_drift_response(
#         text,
#         concept_index=0,
#         concept_title="x",
#         state_hash="h",
#     )
#     assert result.is_consistent is False
#     assert result.drift_kind == "cumulative_integrity"
#     assert result.affected_element_id == "design-2"


# def test_parse_malformed_drift_json_falls_back_to_consistent() -> None:
#     """Conservative fallback prevents false-positive drift recoveries."""
#     result = _parse_drift_response(
#         "totally invalid",
#         concept_index=0,
#         concept_title="x",
#         state_hash="h",
#     )
#     assert result.is_consistent is True
#     assert result.drift_kind is None
#     assert result.affected_element_id is None


# def test_parse_unknown_drift_kind_falls_back_to_consistent() -> None:
#     """Unknown drift_kind values flip the result to consistent — never act on garbage."""
#     text = (
#         '{"is_consistent": false, "drift_kind": "garbage_kind", '
#         '"affected_element_id": "design-1", "issue": "x", "suggested_action": "y"}'
#     )
#     result = _parse_drift_response(
#         text,
#         concept_index=0,
#         concept_title="x",
#         state_hash="h",
#     )
#     assert result.is_consistent is True
#     assert result.drift_kind is None


# def test_parse_missing_affected_element_id_yields_none() -> None:
#     text = (
#         '{"is_consistent": false, "drift_kind": "concept_fit", '
#         '"affected_element_id": null, "issue": "boardwide drift", '
#         '"suggested_action": "clean up"}'
#     )
#     result = _parse_drift_response(
#         text,
#         concept_index=0,
#         concept_title="x",
#         state_hash="h",
#     )
#     assert result.affected_element_id is None
#     assert result.is_consistent is False


# def test_parse_inconsistent_without_issue_or_action_collapses_to_consistent() -> None:
#     """Haiku said drift exists but gave no actionable content — treat as consistent."""
#     text = (
#         '{"is_consistent": false, "drift_kind": "concept_fit", '
#         '"affected_element_id": null, "issue": "", "suggested_action": ""}'
#     )
#     result = _parse_drift_response(
#         text,
#         concept_index=0,
#         concept_title="x",
#         state_hash="h",
#     )
#     assert result.is_consistent is True
#     assert result.drift_kind is None


# def test_parse_empty_suggested_action_preserved_when_issue_present() -> None:
#     """Inconsistent + issue but empty action is still actionable (issue carries info)."""
#     text = (
#         '{"is_consistent": false, "drift_kind": "concept_fit", '
#         '"affected_element_id": "design-1", "issue": "stale diagram", '
#         '"suggested_action": ""}'
#     )
#     result = _parse_drift_response(
#         text,
#         concept_index=0,
#         concept_title="x",
#         state_hash="h",
#     )
#     assert result.is_consistent is False
#     assert result.suggested_action == ""


# # ── PerceptionFeedback drift chat note ───────────────────


# def test_perception_feedback_drift_as_chat_note() -> None:
#     fb = PerceptionFeedback(
#         tool_name="periodic_drift_check",
#         original_claim="Right-triangle trigonometry",
#         score=0,
#         issue="stale ladder diagram on screen",
#         drift_kind="concept_fit",
#         suggested_action="Erase or repurpose design-1",
#         target_diagram_id="design-1",
#     )
#     note = fb.as_chat_note()
#     assert note.startswith("[PERCEPTION_FEEDBACK] Drift detected during concept")
#     assert "Right-triangle trigonometry" in note
#     assert "Kind: concept_fit" in note
#     assert "Erase or repurpose design-1" in note
#     # Drift note must NOT use the diagram or annotation formats.
#     assert "modify_design_diagram(target_id=" not in note
#     assert "Re-point now:" not in note


# def test_perception_feedback_annotation_format_regression() -> None:
#     """5a-3 must not break the 5a-1 annotation chat-note format."""
#     fb = PerceptionFeedback(
#         tool_name="highlight_pulse",
#         original_claim="hypotenuse",
#         score=2,
#         issue="landed on right-angle marker",
#         suggested_target="side_AB",
#         suggested_tag_syntax='<highlight target="side_AB"/>',
#     )
#     note = fb.as_chat_note()
#     assert note.startswith("[PERCEPTION_FEEDBACK]")
#     assert "Drift detected" not in note
#     assert '<highlight target="side_AB"/>' in note


# def test_perception_feedback_diagram_format_regression() -> None:
#     """5a-3 must not break the 5a-2 diagram chat-note format."""
#     fb = PerceptionFeedback(
#         tool_name="modify_design_diagram",
#         original_claim="add a friction force",
#         score=2,
#         issue="friction landed on the wrong side",
#         suggested_modification="Add friction at the bottom",
#         target_diagram_id="design-1",
#     )
#     note = fb.as_chat_note()
#     assert note.startswith("[PERCEPTION_FEEDBACK]")
#     assert "Drift detected" not in note
#     assert 'modify_design_diagram(target_id="design-1"' in note


# # ── _format_element_summary ──────────────────────────────


# def test_format_element_summary_empty_returns_placeholder() -> None:
#     assert _format_element_summary([]) == "(no diagrams)"


# def test_format_element_summary_uses_modify_count_phrasing() -> None:
#     rows = [
#         ("design-1", "free body diagram of a block on a ramp", 0),
#         ("design-2", "ladder against wall", 1),
#         ("design-3", "right triangle", 3),
#     ]
#     out = _format_element_summary(rows)
#     assert "design-1 (original):" in out
#     assert "design-2 (modified 1x):" in out
#     assert "design-3 (modified 3x):" in out


# def test_format_element_summary_truncates_long_claims() -> None:
#     long_claim = "x" * 400
#     rows = [("design-1", long_claim, 0)]
#     out = _format_element_summary(rows)
#     # The 250-char truncate cap from _truncate_claim should kick in.
#     assert "…" in out
#     # Make sure the un-truncated 400-char version isn't present.
#     assert "x" * 400 not in out


# # ── request_drift_check end-to-end ───────────────────────


# def _fake_anthropic_response(text: str) -> SimpleNamespace:
#     return SimpleNamespace(content=[SimpleNamespace(text=text)])


# def _build_verifier() -> BoardVerifier:
#     publish = AsyncMock()
#     return BoardVerifier(publish_fn=publish, audit=SessionAudit())


# @pytest.mark.asyncio
# async def test_empty_element_summary_and_description_returns_none_no_haiku() -> None:
#     """Nothing to verify against — skip the call entirely."""
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_client_create = AsyncMock()
#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch(
#             "anthropic.AsyncAnthropic",
#             return_value=SimpleNamespace(messages=SimpleNamespace(create=fake_client_create)),
#         ),
#     ):
#         result = await verifier.request_drift_check(
#             concept_index=0,
#             concept_title="x",
#             concept_description="",
#             total_concepts=1,
#             element_summary=[],
#             state_hash="h",
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is None
#     assert captured == []
#     # Haiku must not be called when there's nothing to check.
#     fake_client_create.assert_not_called()


# @pytest.mark.asyncio
# async def test_concept_fit_drift_invokes_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[tuple[PerceptionFeedback, DriftCheckResult]] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"is_consistent": false, "drift_kind": "concept_fit", '
#         '"affected_element_id": "design-1", '
#         '"issue": "stale ladder on screen", '
#         '"suggested_action": "Erase or repurpose design-1"}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_drift_check(
#             concept_index=2,
#             concept_title="Right-triangle trigonometry",
#             concept_description="Use sin/cos/tan to relate sides.",
#             total_concepts=5,
#             element_summary=[("design-1", "ladder against wall", 0)],
#             state_hash="h-abc",
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is not None
#     assert result.is_consistent is False
#     assert result.drift_kind == "concept_fit"
#     assert len(captured) == 1
#     fb, _ = captured[0]
#     assert fb.tool_name == "periodic_drift_check"
#     assert fb.drift_kind == "concept_fit"
#     assert fb.target_diagram_id == "design-1"


# @pytest.mark.asyncio
# async def test_cumulative_integrity_drift_invokes_callback_with_element() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"is_consistent": false, "drift_kind": "cumulative_integrity", '
#         '"affected_element_id": "design-2", '
#         '"issue": "ramp edited away from a free body diagram", '
#         '"suggested_action": '
#         '"modify_design_diagram(target_id=\\"design-2\\", modification=\\"Restore ramp\\")"}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_drift_check(
#             concept_index=1,
#             concept_title="Free body diagrams",
#             concept_description="Draw forces on objects.",
#             total_concepts=4,
#             element_summary=[("design-2", "free body diagram of a block on a 30 degree ramp", 3)],
#             state_hash="h-cum",
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is not None
#     assert result.drift_kind == "cumulative_integrity"
#     assert result.affected_element_id == "design-2"
#     assert len(captured) == 1
#     fb, _ = captured[0]
#     assert fb.target_diagram_id == "design-2"
#     assert fb.drift_kind == "cumulative_integrity"


# @pytest.mark.asyncio
# async def test_consistent_result_does_not_invoke_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"is_consistent": true, "drift_kind": null, '
#         '"affected_element_id": null, "issue": "", "suggested_action": ""}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_drift_check(
#             concept_index=0,
#             concept_title="x",
#             concept_description="y",
#             total_concepts=1,
#             element_summary=[("design-1", "claim", 0)],
#             state_hash="h",
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is not None
#     assert result.is_consistent is True
#     assert captured == []


# @pytest.mark.asyncio
# async def test_screenshot_timeout_returns_none_no_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     with patch.object(verifier, "_request_screenshot", AsyncMock(return_value=None)):
#         result = await verifier.request_drift_check(
#             concept_index=0,
#             concept_title="x",
#             concept_description="y",
#             total_concepts=1,
#             element_summary=[("design-1", "claim", 0)],
#             state_hash="h",
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is None
#     assert captured == []


# @pytest.mark.asyncio
# async def test_vision_exception_swallowed_returns_none() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("boom")))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_drift_check(
#             concept_index=0,
#             concept_title="x",
#             concept_description="y",
#             total_concepts=1,
#             element_summary=[("design-1", "claim", 0)],
#             state_hash="h",
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is None
#     assert captured == []
