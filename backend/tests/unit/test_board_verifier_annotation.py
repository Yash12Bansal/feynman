# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Phase 5a-1 — annotation-accuracy verification + feedback queue.

# These tests cover the new code paths added beside the existing layout
# verifier:

# * :func:`_parse_annotation_response` — JSON parsing for the annotation prompt
# * :class:`AnnotationVerificationResult` / :class:`PerceptionFeedback` shapes
# * ``BoardVerifier.request_annotation_verification`` end-to-end with mocked
#   screenshot + mocked Anthropic client
# * feedback enqueue behavior keyed on score and ``suggested_target``
# """

# from __future__ import annotations

# from types import SimpleNamespace
# from typing import Any
# from unittest.mock import AsyncMock, patch

# import pytest

# from feynman.agent.board_verifier import (
#     AnnotationVerificationResult,
#     BoardVerifier,
#     PerceptionFeedback,
#     _build_retry_tag_syntax,
#     _format_dictionary_lines,
#     _parse_annotation_response,
# )
# from feynman.agent.session_audit import SessionAudit

# # ── _parse_annotation_response ────────────────────────────


# def test_parse_valid_json() -> None:
#     text = (
#         '{"score": 1, "intent_match": false, '
#         '"issue": "highlight on right-angle marker, not hypotenuse", '
#         '"suggested_target": "side_AB"}'
#     )
#     result = _parse_annotation_response(
#         text,
#         tool_name="highlight_pulse",
#         original_claim="hypotenuse",
#         target_id="line-2",
#         concept_index=3,
#     )
#     assert result.score == 1
#     assert result.intent_match is False
#     assert "right-angle marker" in result.issue
#     assert result.suggested_target == "side_AB"
#     assert result.tool_name == "highlight_pulse"
#     assert result.original_claim == "hypotenuse"
#     assert result.original_target_id == "line-2"
#     assert result.concept_index == 3


# def test_parse_markdown_fenced_response_strips_fences() -> None:
#     text = (
#         '```json\n{"score": 2, "intent_match": false, '
#         '"issue": "wrong", "suggested_target": "x"}\n```'
#     )
#     result = _parse_annotation_response(
#         text,
#         tool_name="highlight_pulse",
#         original_claim="y",
#         target_id="line-1",
#         concept_index=0,
#     )
#     assert result.score == 2
#     assert result.suggested_target == "x"


# def test_parse_malformed_json_falls_back_to_score_3_intent_true() -> None:
#     """Conservative fallback prevents false-positive retries on parser errors."""
#     result = _parse_annotation_response(
#         "not json at all",
#         tool_name="highlight_pulse",
#         original_claim="x",
#         target_id="line-1",
#         concept_index=0,
#     )
#     assert result.score == 3
#     assert result.intent_match is True
#     assert result.suggested_target is None


# def test_parse_missing_intent_match_defaults_to_true() -> None:
#     result = _parse_annotation_response(
#         '{"score": 4, "issue": "fine", "suggested_target": null}',
#         tool_name="highlight_pulse",
#         original_claim="x",
#         target_id="line-1",
#         concept_index=0,
#     )
#     assert result.intent_match is True


# def test_parse_null_suggested_target_yields_none() -> None:
#     result = _parse_annotation_response(
#         '{"score": 5, "intent_match": true, "issue": "", "suggested_target": null}',
#         tool_name="highlight_pulse",
#         original_claim="x",
#         target_id="line-1",
#         concept_index=0,
#     )
#     assert result.suggested_target is None


# def test_parse_empty_string_suggested_target_yields_none() -> None:
#     result = _parse_annotation_response(
#         '{"score": 5, "intent_match": true, "issue": "", "suggested_target": ""}',
#         tool_name="highlight_pulse",
#         original_claim="x",
#         target_id="line-1",
#         concept_index=0,
#     )
#     assert result.suggested_target is None


# def test_parse_score_clamped_to_1_5() -> None:
#     high = _parse_annotation_response(
#         '{"score": 99, "intent_match": true, "issue": "", "suggested_target": null}',
#         tool_name="highlight_pulse",
#         original_claim="x",
#         target_id="line-1",
#         concept_index=0,
#     )
#     low = _parse_annotation_response(
#         '{"score": -3, "intent_match": false, "issue": "", "suggested_target": "y"}',
#         tool_name="highlight_pulse",
#         original_claim="x",
#         target_id="line-1",
#         concept_index=0,
#     )
#     assert high.score == 5
#     assert low.score == 1


# # ── PerceptionFeedback formatting ─────────────────────────


# def test_perception_feedback_as_chat_note_contains_signal() -> None:
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
#     assert "highlight_pulse" in note
#     assert "hypotenuse" in note
#     assert "2/5" in note
#     assert "side_AB" in note
#     assert '<highlight target="side_AB"/>' in note


# def test_build_retry_tag_syntax_per_tool() -> None:
#     assert _build_retry_tag_syntax("highlight_pulse", "x") == '<highlight target="x"/>'
#     assert _build_retry_tag_syntax("pin_label_near", "x") == '<pin near="x" label="..."/>'
#     assert _build_retry_tag_syntax("draw_callout", "x") == '<callout from="x" text="..."/>'
#     assert _build_retry_tag_syntax("bracket", "x") == '<bracket between="x" label="..."/>'
#     # Unknown tool falls back to a generic highlight template.
#     assert _build_retry_tag_syntax("unknown", "x") == '<highlight target="x"/>'
#     # No suggested target produces a hint without a tag.
#     assert "use the right element" in _build_retry_tag_syntax("highlight_pulse", None)


# # ── _format_dictionary_lines ─────────────────────────────


# def test_format_dictionary_lines_with_obj_metas() -> None:
#     dictionary = {
#         "line-1": SimpleNamespace(role="hypotenuse", semantic="long slanted side"),
#         "line-2": SimpleNamespace(role="adjacent", semantic="bottom"),
#     }
#     out = _format_dictionary_lines(dictionary)
#     assert "hypotenuse" in out
#     assert "adjacent" in out
#     assert "line-1" in out
#     assert "line-2" in out


# def test_format_dictionary_lines_with_dict_metas() -> None:
#     dictionary = {
#         "line-1": {"role": "hypotenuse", "semantic": "long side"},
#     }
#     out = _format_dictionary_lines(dictionary)
#     assert "hypotenuse" in out


# def test_format_dictionary_lines_empty() -> None:
#     assert _format_dictionary_lines({}) == "(no roles)"


# # ── request_annotation_verification end-to-end ────────────


# def _fake_anthropic_response(text: str) -> SimpleNamespace:
#     return SimpleNamespace(content=[SimpleNamespace(text=text)])


# def _build_verifier() -> BoardVerifier:
#     publish = AsyncMock()
#     return BoardVerifier(publish_fn=publish, audit=SessionAudit())


# @pytest.mark.asyncio
# async def test_low_score_with_suggestion_invokes_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[tuple[PerceptionFeedback, AnnotationVerificationResult]] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"score": 1, "intent_match": false, '
#         '"issue": "wrong element", "suggested_target": "side_AB"}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_annotation_verification(
#             tool_name="highlight_pulse",
#             original_claim="hypotenuse",
#             target_id="line-2",
#             spoken_context="the long side",
#             dictionary={"line-1": {"role": "hypotenuse"}},
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is not None
#     assert result.score == 1
#     assert len(captured) == 1
#     fb, res = captured[0]
#     assert fb.suggested_target == "side_AB"
#     assert fb.tool_name == "highlight_pulse"
#     assert fb.suggested_tag_syntax == '<highlight target="side_AB"/>'
#     assert res.intent_match is False


# @pytest.mark.asyncio
# async def test_high_score_does_not_invoke_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"score": 5, "intent_match": true, "issue": "", "suggested_target": null}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         result = await verifier.request_annotation_verification(
#             tool_name="highlight_pulse",
#             original_claim="hypotenuse",
#             target_id="line-1",
#             spoken_context="",
#             dictionary={"line-1": {"role": "hypotenuse"}},
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is not None
#     assert result.score == 5
#     assert captured == []


# @pytest.mark.asyncio
# async def test_low_score_without_suggestion_does_not_invoke_callback() -> None:
#     """score<=2 but no suggested_target — we have nothing to retry with."""
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     fake_haiku = _fake_anthropic_response(
#         '{"score": 2, "intent_match": false, "issue": "ambiguous", "suggested_target": null}'
#     )
#     fake_client = SimpleNamespace(
#         messages=SimpleNamespace(create=AsyncMock(return_value=fake_haiku))
#     )

#     with (
#         patch.object(verifier, "_request_screenshot", AsyncMock(return_value="b64")),
#         patch("anthropic.AsyncAnthropic", return_value=fake_client),
#     ):
#         await verifier.request_annotation_verification(
#             tool_name="highlight_pulse",
#             original_claim="x",
#             target_id="line-1",
#             spoken_context="",
#             dictionary={},
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert captured == []


# @pytest.mark.asyncio
# async def test_screenshot_timeout_returns_none_no_callback() -> None:
#     verifier = _build_verifier()
#     captured: list[Any] = []

#     with patch.object(verifier, "_request_screenshot", AsyncMock(return_value=None)):
#         result = await verifier.request_annotation_verification(
#             tool_name="highlight_pulse",
#             original_claim="x",
#             target_id="line-1",
#             spoken_context="",
#             dictionary={},
#             concept_index=0,
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
#         result = await verifier.request_annotation_verification(
#             tool_name="highlight_pulse",
#             original_claim="x",
#             target_id="line-1",
#             spoken_context="",
#             dictionary={},
#             concept_index=0,
#             on_feedback=lambda fb, r: captured.append((fb, r)),
#         )
#     assert result is None
#     assert captured == []
