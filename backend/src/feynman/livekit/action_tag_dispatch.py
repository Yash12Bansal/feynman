# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Dispatch parsed action tags as visual instructions (Phase 4).

# The ``tts_node`` tap in :mod:`feynman.livekit.worker` feeds each
# parsed :class:`ActionTag` to :func:`dispatch_action_tag`, which:

# 1. Resolves the target string against the active diagram dictionary
#    (or, when no role matches, passes a soft-miss ``AnnotationTarget``
#    to the frontend's live-DOM resolver).
# 2. Builds the right Phase 2 annotation instruction
#    (``HighlightPulseInstruction`` / ``DrawCalloutInstruction`` /
#    ``BracketInstruction`` / ``PinLabelInstruction``).
# 3. Publishes it via the same ``_publish_visual`` path the tool-call
#    annotations use.

# Every emitted instruction uses
# ``sync_mode=SyncMode.AFTER_NEXT_SENTENCE`` so it rides Phase 2's
# frontend-side deferred queue and fires at the next sentence boundary.

# Fail-silent at every layer: a malformed tag, missing required attr,
# or downstream publish error logs and returns without raising — a
# broken tag must never crash the TTS stream.
# """

# from __future__ import annotations

# from typing import TYPE_CHECKING, Any

# import structlog

# from feynman.agent.action_tag_parser import ActionTag
# from feynman.agent.tools import (
#     _build_annotation_target,
#     _publish_visual,
#     _schedule_annotation_verification,
# )
# from feynman.visuals.schemas import (
#     BracketInstruction,
#     DrawCalloutInstruction,
#     HighlightPulseInstruction,
#     PinLabelInstruction,
#     SyncMode,
# )

# if TYPE_CHECKING:
#     from livekit.agents import AgentSession

#     from feynman.visuals.schemas import _BaseInstruction

# logger = structlog.get_logger()


# # Duration mapping: `<highlight>` lingers as a sustained glow while the
# # teacher explains; `<pulse>` is a quick attention grab.
# _HIGHLIGHT_DURATION_MS = 1500
# _PULSE_DURATION_MS = 800

# _VALID_CALLOUT_DIRECTIONS = {
#     "up",
#     "down",
#     "up-left",
#     "up-right",
#     "down-left",
#     "down-right",
# }
# _VALID_PIN_POSITIONS = {"above", "below", "left", "right"}
# _VALID_BRACKET_SIDES = {"above", "below", "left", "right"}

# # Phase 5a-1: route inline-tag verbs onto the same verification path as the
# # matching tool. `<highlight>` and `<pulse>` both render as
# # HighlightPulseInstruction, so they share the canonical tool name.
# _VERB_TO_TOOL_NAME = {
#     "highlight": "highlight_pulse",
#     "pulse": "highlight_pulse",
#     "callout": "draw_callout",
#     "bracket": "bracket",
#     "pin": "pin_label_near",
# }
# _VERB_TO_CLAIM_ATTR = {
#     "highlight": "target",
#     "pulse": "target",
#     "callout": "from",
#     "bracket": "between",
#     "pin": "near",
# }


# class _ActionTagContext:
#     """Minimal ``RunContext``-shaped adapter for :func:`_publish_visual`.

#     Tool handlers receive a real ``RunContext`` from livekit-agents; action
#     tags are dispatched from the ``tts_node`` tap where we have an
#     ``AgentSession`` but no per-call ``RunContext``. ``_publish_visual``
#     only reads ``ctx.userdata`` and ``ctx.session.room_io.room`` for the
#     AFTER_NEXT_SENTENCE path, so this adapter exposes exactly those.
#     """

#     def __init__(self, session: AgentSession) -> None:
#         self.session = session
#         self.userdata = session.userdata

#     async def wait_for_playout(self) -> None:
#         # Only invoked for sync_mode=ON_PLAYOUT, which action tags never use.
#         # Defined for shape conformance.
#         return


# async def dispatch_action_tag(session: AgentSession, tag: ActionTag) -> None:
#     """Build + publish the visual instruction for ``tag``. Fail-silent."""
#     try:
#         ctx = _ActionTagContext(session)
#         instruction = _build_instruction(ctx, tag)
#         if instruction is None:
#             return
#         await _publish_visual(ctx, instruction, wait_for_speech=False)
#         _schedule_verification_from_tag(ctx, tag, instruction)
#     except Exception:
#         logger.warning(
#             "action_tag.dispatch_failed",
#             verb=tag.verb,
#             attrs=tag.attrs,
#             exc_info=True,
#         )


# def _schedule_verification_from_tag(
#     ctx: _ActionTagContext,
#     tag: ActionTag,
#     instruction: _BaseInstruction,
# ) -> None:
#     """Bridge action-tag emission onto the Phase 5a-1 verification path."""
#     tool_name = _VERB_TO_TOOL_NAME.get(tag.verb)
#     if tool_name is None:
#         return
#     attrs = {k.lower(): v for k, v in tag.attrs.items()}
#     claim_attr = _VERB_TO_CLAIM_ATTR.get(tag.verb, "target")
#     claim = (attrs.get(claim_attr) or "").strip()
#     if not claim:
#         return
#     target_id = _instruction_target_id(instruction)
#     if not target_id:
#         return
#     spoken_context = (attrs.get("text") or attrs.get("label") or "").strip()
#     _schedule_annotation_verification(
#         ctx,  # type: ignore[arg-type]
#         tool_name=tool_name,
#         original_claim=claim,
#         target_id=target_id,
#         spoken_context=spoken_context,
#     )


# def _instruction_target_id(instruction: _BaseInstruction) -> str:
#     """Pull the resolved target id off whichever annotation instruction."""
#     if isinstance(instruction, BracketInstruction):
#         return f"{instruction.element_a_id},{instruction.element_b_id}"
#     target_id = getattr(instruction, "target_element_id", None)
#     return target_id or ""


# def _build_instruction(ctx: _ActionTagContext, tag: ActionTag) -> _BaseInstruction | None:
#     """Route by verb to the matching instruction builder.

#     Returns ``None`` when required attributes are missing or invalid; in
#     that case the call site silently skips (already logged).
#     """
#     # Lowercase attribute names for tolerant lookup. The parser preserves
#     # case as written; dispatcher is the canonicalization point.
#     attrs = {k.lower(): v for k, v in tag.attrs.items()}
#     builder = _VERB_DISPATCH.get(tag.verb)
#     if builder is None:
#         # Shouldn't reach here — the parser allowlist already filters. Defensive.
#         logger.warning("action_tag.no_builder", verb=tag.verb)
#         return None
#     return builder(ctx, attrs)


# def _build_highlight(
#     ctx: _ActionTagContext, attrs: dict[str, str]
# ) -> HighlightPulseInstruction | None:
#     target = attrs.get("target", "").strip()
#     if not target:
#         logger.warning("action_tag.missing_attr", verb="highlight", needs="target")
#         return None
#     target_id, target_obj, _ = _build_annotation_target(ctx, target)  # type: ignore[arg-type]
#     return HighlightPulseInstruction(
#         target_element_id=target_id,
#         target=target_obj,
#         duration_ms=_HIGHLIGHT_DURATION_MS,
#         sync_mode=SyncMode.AFTER_NEXT_SENTENCE,
#     )


# def _build_pulse(ctx: _ActionTagContext, attrs: dict[str, str]) -> HighlightPulseInstruction | None:
#     target = attrs.get("target", "").strip()
#     if not target:
#         logger.warning("action_tag.missing_attr", verb="pulse", needs="target")
#         return None
#     target_id, target_obj, _ = _build_annotation_target(ctx, target)  # type: ignore[arg-type]
#     return HighlightPulseInstruction(
#         target_element_id=target_id,
#         target=target_obj,
#         duration_ms=_PULSE_DURATION_MS,
#         sync_mode=SyncMode.AFTER_NEXT_SENTENCE,
#     )


# def _build_callout(ctx: _ActionTagContext, attrs: dict[str, str]) -> DrawCalloutInstruction | None:
#     from_target = attrs.get("from", "").strip()
#     text = attrs.get("text", "").strip()
#     if not from_target:
#         logger.warning("action_tag.missing_attr", verb="callout", needs="from")
#         return None
#     if not text:
#         logger.warning("action_tag.missing_attr", verb="callout", needs="text")
#         return None
#     target_id, target_obj, _ = _build_annotation_target(ctx, from_target)  # type: ignore[arg-type]
#     direction_raw = attrs.get("direction", "up-right")
#     direction: Any = direction_raw if direction_raw in _VALID_CALLOUT_DIRECTIONS else "up-right"
#     return DrawCalloutInstruction(
#         target_element_id=target_id,
#         target=target_obj,
#         text=text,
#         direction=direction,
#         sync_mode=SyncMode.AFTER_NEXT_SENTENCE,
#     )


# def _build_bracket(ctx: _ActionTagContext, attrs: dict[str, str]) -> BracketInstruction | None:
#     between = attrs.get("between", "")
#     label = attrs.get("label", "").strip()
#     parts = [p.strip() for p in between.split(",") if p.strip()]
#     if len(parts) < 2:
#         logger.warning(
#             "action_tag.missing_attr",
#             verb="bracket",
#             needs="between with 2+ comma-separated targets",
#         )
#         return None
#     if not label:
#         logger.warning("action_tag.missing_attr", verb="bracket", needs="label")
#         return None
#     a_id, target_a, _ = _build_annotation_target(ctx, parts[0])  # type: ignore[arg-type]
#     b_id, target_b, _ = _build_annotation_target(ctx, parts[1])  # type: ignore[arg-type]
#     side_raw = attrs.get("side", "above")
#     side: Any = side_raw if side_raw in _VALID_BRACKET_SIDES else "above"
#     return BracketInstruction(
#         element_a_id=a_id,
#         element_b_id=b_id,
#         target_a=target_a,
#         target_b=target_b,
#         label=label,
#         side=side,
#         sync_mode=SyncMode.AFTER_NEXT_SENTENCE,
#     )


# def _build_pin(ctx: _ActionTagContext, attrs: dict[str, str]) -> PinLabelInstruction | None:
#     near = attrs.get("near", "").strip()
#     label = attrs.get("label", "").strip()
#     if not near:
#         logger.warning("action_tag.missing_attr", verb="pin", needs="near")
#         return None
#     if not label:
#         logger.warning("action_tag.missing_attr", verb="pin", needs="label")
#         return None
#     target_id, target_obj, _ = _build_annotation_target(ctx, near)  # type: ignore[arg-type]
#     position_raw = attrs.get("position", "above")
#     position: Any = position_raw if position_raw in _VALID_PIN_POSITIONS else "above"
#     return PinLabelInstruction(
#         target_element_id=target_id,
#         target=target_obj,
#         text=label,
#         position=position,
#         sync_mode=SyncMode.AFTER_NEXT_SENTENCE,
#     )


# _VERB_DISPATCH = {
#     "highlight": _build_highlight,
#     "pulse": _build_pulse,
#     "callout": _build_callout,
#     "bracket": _build_bracket,
#     "pin": _build_pin,
# }
