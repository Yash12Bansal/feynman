# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Phase 5a-2 — diagram-intent verification + diagram-flavored feedback.

# These tests cover the new code paths added beside the 5a-1 annotation
# verifier and the original layout verifier:

# * :func:`_parse_diagram_intent_response` — JSON parsing for the diagram-intent prompt
# * :class:`DiagramIntentVerificationResult` / :class:`PerceptionFeedback` (diagram variant)
# * :class:`PerceptionFeedback.as_chat_note` — branching between annotation and diagram formats
# * ``BoardVerifier.request_diagram_intent_verification`` end-to-end with mocked
#   screenshot + mocked Anthropic client
# * feedback enqueue behavior keyed on score and ``suggested_modification``
# """

# from __future__ import annotations

# from types import SimpleNamespace
# from typing import Any
# from unittest.mock import AsyncMock, patch

# import pytest

# from feynman.agent.board_verifier import (
#     BoardVerifier,
#     DiagramIntentVerificationResult,
#     PerceptionFeedback,
#     _format_role_list,
#     _parse_diagram_intent_response,
#     _truncate_claim,
# )
# from feynman.agent.session_audit import SessionAudit

# # ── _parse_diagram_intent_response ────────────────────────


# def test_parse_valid_diagram_intent_json() -> None:
#     text = (
#         '{"score": 1, "intent_match": false, '
#         '"issue": "missing ramp under the block", '
#         '"suggested_modification": "Add an inclined ramp at 30°"}'
#     )
#     result = _parse_diagram_intent_response(
#         text,
#         tool_name="draw_design_diagram",
#         original_claim="free body diagram of a block on a ramp",
#         target_diagram_id="design-1",
#         diagram_version=0,
#         concept_index=2,
#     )
#     assert result.score == 1
#     assert result.intent_match is False
#     assert "ramp" in result.issue
#     assert result.suggested_modification == "Add an inclined ramp at 30°"
#     assert result.tool_name == "draw_design_diagram"
#     assert result.target_diagram_id == "design-1"
#     assert result.diagram_version == 0
#     assert result.concept_index == 2


# def test_parse_markdown_fenced_diagram_response_strips_fences() -> None:
#     text = (
#         '```json\n{"score": 2, "intent_match": false, '
#         '"issue": "wrong", "suggested_modification": "Add x"}\n```'
#     )
#     result = _parse_diagram_intent_response(
#         text,
#         tool_name="modify_design_diagram",
#         original_claim="add a friction vector",
#         target_diagram_id="design-2",
#         diagram_version=1,
#         concept_index=0,
#     )
#     assert result.score == 2
#     assert result.suggested_modification == "Add x"


# def test_parse_malformed_diagram_json_falls_back_to_score_3_intent_true() -> None:
#     """Conservative fallback prevents false-positive modify retries on parser errors."""
#     result = _parse_diagram_intent_response(
#         "not json at all",
#         tool_name="draw_design_diagram",
#         original_claim="anything",
#         target_diagram_id="design-1",
#         diagram_version=0,
#         concept_index=0,
#     )
#     assert result.score == 3
#     assert result.intent_match is True
#     assert result.suggested_modification is None


# def test_parse_missing_intent_match_defaults_to_true_for_diagrams() -> None:
#     result = _parse_diagram_intent_response(
#         '{"score": 4, "issue": "fine", "suggested_modification": null}',
#         tool_name="draw_design_diagram",
#         original_claim="anything",
#         target_diagram_id="design-1",
#         diagram_version=0,
#         concept_index=0,
#     )
#     assert result.intent_match is True


# def test_parse_null_suggested_modification_yields_none() -> None:
#     result = _parse_diagram_intent_response(
#         '{"score": 5, "intent_match": true, "issue": "", "suggested_modification": null}',
#         tool_name="draw_design_diagram",
#         original_claim="x",
#         target_diagram_id="design-1",
#         diagram_version=0,
#         concept_index=0,
#     )
#     assert result.suggested_modification is None


# def test_parse_empty_string_suggested_modification_yields_none() -> None:
#     result = _parse_diagram_intent_response(
#         '{"score": 5, "intent_match": true, "issue": "", "suggested_modification": ""}',
#         tool_name="draw_design_diagram",
#         original_claim="x",
#         target_diagram_id="design-1",
#         diagram_version=0,
#         concept_index=0,
#     )
#     assert result.suggested_modification is None


# def test_parse_diagram_score_clamped_to_1_5() -> None:
#     high = _parse_diagram_intent_response(
#         '{"score": 99, "intent_match": true, "issue": "", "suggested_modification": null}',
#         tool_name="draw_design_diagram",
#         original_claim="x",
#         target_diagram_id="design-1",
#         diagram_version=0,
#         concept_index=0,
#     )
#     low = _parse_diagram_intent_response(
#         '{"score": -3, "intent_match": false, "issue": "", "suggested_modification": "y"}',
#         tool_name="draw_design_diagram",
#         original_claim="x",
#         target_diagram_id="design-1",
#         diagram_version=0,
#         concept_index=0,
#     )
#     assert high.score == 5
#     assert low.score == 1


# # ── PerceptionFeedback diagram chat note ─────────────────


# def test_perception_feedback_diagram_as_chat_note_contains_modify_call() -> None:
#     fb = PerceptionFeedback(
#         tool_name="draw_design_diagram",
#         original_claim="free body diagram of a block on a ramp",
#         score=1,
#         issue="ramp is missing",
#         suggested_modification="Add an inclined ramp at 30°",
#         target_diagram_id="design-1",
#     )
#     note = fb.as_chat_note()
#     assert note.startswith("[PERCEPTION_FEEDBACK]")
#     assert "draw_design_diagram" in note
#     assert "1/5" in note
#     # The pre-baked modify call is the recovery hint the LLM should fire.
#     assert 'modify_design_diagram(target_id="design-1"' in note
#     assert "Add an inclined ramp at 30°" in note


# def test_perception_feedback_modify_variant_uses_diagram_format() -> None:
#     fb = PerceptionFeedback(
#         tool_name="modify_design_diagram",
#         original_claim="add a friction force",
#         score=2,
#         issue="friction landed on the wrong side",
#         suggested_modification="Add the friction force on the bottom of the block",
#         target_diagram_id="design-1",
#     )
#     note = fb.as_chat_note()
#     assert note.startswith("[PERCEPTION_FEEDBACK]")
#     assert "modify_design_diagram" in note
#     assert "Add the friction force on the bottom of the block" in note


# def test_perception_feedback_annotation_format_regression() -> None:
#     """5a-2 must not break the 5a-1 annotation chat-note format."""
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
#     # Annotation-flavoured note does NOT contain the modify call format.
#     assert "modify_design_diagram(" not in note
#     assert "highlight_pulse" in note
#     assert "side_AB" in note
#     assert '<highlight target="side_AB"/>' in note


# def test_perception_feedback_diagram_missing_target_uses_placeholder() -> None:
#     fb = PerceptionFeedback(
#         tool_name="draw_design_diagram",
#         original_claim="x",
#         score=1,
#         issue="y",
#         suggested_modification="z",
#     )
#     note = fb.as_chat_note()
#     # Defensive: the diagram note should still render even if target_id is missing.
#     assert "<unknown>" in note


# # ── _format_role_list + _truncate_claim ───────────────────


# def test_format_role_list_empty() -> None:
#     assert _format_role_list([]) == "(no roles)"


# def test_format_role_list_filters_blanks_and_caps_at_20() -> None:
#     roles = ["hypotenuse", "", "opposite", ""] + [f"r{i}" for i in range(25)]
#     out = _format_role_list(roles)
#     lines = out.split("\n")
#     assert len(lines) == 20  # capped
#     assert all(line.startswith("- ") for line in lines)
#     assert "- hypotenuse" in lines


# def test_truncate_claim_short_passthrough() -> None:
#     assert _truncate_claim("a short claim") == "a short claim"


# def test_truncate_claim_long_gets_ellipsis() -> None:
#     long = "x" * 400
#     out = _truncate_claim(long)
#     assert len(out) <= 260  # 250 + ellipsis tolerance
#     assert out.endswith("…")


# # ── request_diagram_intent_verification end-to-end ────────


# def _fake_anthropic_response(text: str) -> SimpleNamespace:
#     return SimpleNamespace(content=[SimpleNamespace(text=text)])


# def _build_verifier() -> BoardVerifier:
#     publish = AsyncMock()
#     return BoardVerifier(publish_fn=publish, audit=SessionAudit())


# @pytest.mark.asyncio
# async def test_low_diagram_score_with_modification_invokes_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[tuple[PerceptionFeedback, DiagramIntentVerificationResult]] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"score": 1, "intent_match": false, '
#         '"issue": "missing ramp", '
#         '"suggested_modification": "Add an inclined ramp at 30°"}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_diagram_intent_verification(
#             tool_name="draw_design_diagram",
#             original_claim="free body diagram of a block on a ramp",
#             target_diagram_id="design-1",
#             diagram_version=0,
#             role_list=["block", "ground"],
#             concept_index=2,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is not None
#     assert result.score == 1
#     assert len(captured) == 1
#     fb, res = captured[0]
#     assert fb.tool_name == "draw_design_diagram"
#     assert fb.target_diagram_id == "design-1"
#     assert fb.suggested_modification == "Add an inclined ramp at 30°"
#     assert res.intent_match is False


# @pytest.mark.asyncio
# async def test_high_diagram_score_does_not_invoke_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"score": 5, "intent_match": true, "issue": "", "suggested_modification": null}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_diagram_intent_verification(
#             tool_name="draw_design_diagram",
#             original_claim="anything",
#             target_diagram_id="design-1",
#             diagram_version=0,
#             role_list=[],
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is not None
#     assert result.score == 5
#     assert captured == []


# @pytest.mark.asyncio
# async def test_low_diagram_score_without_modification_does_not_invoke_callback() -> None:
#     """score<=2 but no suggested_modification — we have nothing to retry with."""
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"score": 2, "intent_match": false, "issue": "ambiguous", "suggested_modification": null}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         await verifier.request_diagram_intent_verification(
#             tool_name="draw_design_diagram",
#             original_claim="x",
#             target_diagram_id="design-1",
#             diagram_version=0,
#             role_list=[],
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert captured == []


# @pytest.mark.asyncio
# async def test_diagram_screenshot_timeout_returns_none_no_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     with patch.object(verifier, "_request_screenshot", AsyncMock(return_value=None)):
#         result = await verifier.request_diagram_intent_verification(
#             tool_name="draw_design_diagram",
#             original_claim="x",
#             target_diagram_id="design-1",
#             diagram_version=0,
#             role_list=[],
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is None
#     assert captured == []


# @pytest.mark.asyncio
# async def test_diagram_vision_exception_swallowed_returns_none() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("boom")))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_diagram_intent_verification(
#             tool_name="draw_design_diagram",
#             original_claim="x",
#             target_diagram_id="design-1",
#             diagram_version=0,
#             role_list=[],
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is None
#     assert captured == []
