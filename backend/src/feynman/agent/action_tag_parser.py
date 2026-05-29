# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Inline action-tag stream parser (Phase 4 of diagram-awareness re-architecture).

# The teaching LLM emits self-closing pointing tags inside its narration:

#     "Here you can see <highlight target=\"weight\"/> the weight pulling down."

# This parser is fed text chunks as they stream from the LLM toward TTS. It
# extracts complete tags, strips them from the text destined for TTS, and
# returns the parsed tags so the worker can dispatch them as visual
# instructions on the ``visuals`` channel.

# Design constraints:
# - Chunks split tags at arbitrary points. Cross-chunk buffering is the rule.
# - Bad input must never crash the parser — fail-silent with structured logs.
# - A pathological "<" with no closing "/>" must not blow up memory; the
#   in-flight carry is capped at ``_MAX_BUFFER`` chars and overflows flush
#   as text.
# """

# from __future__ import annotations

# import re
# from dataclasses import dataclass, field

# import structlog

# logger = structlog.get_logger()


# # Verbs the parser will actually dispatch. Anything that looks like a tag but
# # uses a different verb is stripped + logged so it can't reach TTS as broken
# # speech. Keep in sync with ``action_tag_dispatch.VERB_DISPATCH``.
# ALLOWED_VERBS: frozenset[str] = frozenset({"highlight", "pulse", "callout", "bracket", "pin"})

# # A single self-closing tag. Tolerant on whitespace and quote style:
# #   <verb attr="val" attr='val' />
# # Verb is case-insensitive; attribute values are quoted (single or double).
# _TAG_RE = re.compile(
#     r"""<
#         (?P<verb>[A-Za-z][A-Za-z0-9_-]*)
#         (?P<attrs>(?:\s+[A-Za-z_][A-Za-z0-9_-]*\s*=\s*(?:"[^"]*"|'[^']*'))*)
#         \s*/>
#     """,
#     re.VERBOSE,
# )

# # Attribute pulled out of the captured attribute group.
# _ATTR_RE = re.compile(
#     r"""(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?:"(?P<v1>[^"]*)"|'(?P<v2>[^']*)')"""
# )

# # Hard cap on the carry-over buffer. If the LLM streams >256 chars after an
# # unmatched "<" without ever closing it, flush as plain text and log. 256 is
# # generous — a real tag is rarely >100 chars.
# _MAX_BUFFER = 256


# @dataclass(frozen=True)
# class ActionTag:
#     """A parsed inline action tag.

#     ``verb`` is always lower-cased and guaranteed to be in ``ALLOWED_VERBS``.
#     ``attrs`` preserves attribute-name casing as written by the LLM; values
#     are the raw quoted strings (quotes stripped).
#     """

#     verb: str
#     attrs: dict[str, str] = field(default_factory=dict)


# class ActionTagParser:
#     """Streaming parser. One instance per TTS turn; not thread-safe.

#     Usage::

#         parser = ActionTagParser()
#         for chunk in stream:
#             clean, tags = parser.feed(chunk)
#             # ... yield clean, dispatch tags
#         tail = parser.finalize()
#         # ... yield tail
#     """

#     def __init__(self) -> None:
#         self._buffer: str = ""

#     def feed(self, chunk: str) -> tuple[str, list[ActionTag]]:
#         """Process ``chunk``. Returns ``(clean_text, parsed_tags)``.

#         ``clean_text`` is safe to forward to TTS immediately. An unmatched
#         partial tag is carried forward to the next ``feed`` call.
#         """
#         if not chunk:
#             return "", []

#         self._buffer += chunk

#         out_parts: list[str] = []
#         tags: list[ActionTag] = []
#         pos = 0

#         while pos < len(self._buffer):
#             lt = self._buffer.find("<", pos)
#             if lt < 0:
#                 out_parts.append(self._buffer[pos:])
#                 pos = len(self._buffer)
#                 break

#             if lt > pos:
#                 out_parts.append(self._buffer[pos:lt])

#             m = _TAG_RE.match(self._buffer, lt)
#             if m:
#                 tag = _build_tag(m.group("verb"), m.group("attrs"))
#                 if tag is not None:
#                     tags.append(tag)
#                 pos = m.end()
#                 continue

#             if _looks_like_partial_tag(self._buffer[lt:]):
#                 carry = self._buffer[lt:]
#                 if len(carry) > _MAX_BUFFER:
#                     logger.warning(
#                         "action_tag.buffer_overflow",
#                         buffer_len=len(carry),
#                         head=carry[:80],
#                     )
#                     out_parts.append(carry)
#                     self._buffer = ""
#                     return "".join(out_parts), tags
#                 self._buffer = carry
#                 return "".join(out_parts), tags

#             # Stray "<" — pass through as text.
#             out_parts.append("<")
#             pos = lt + 1

#         self._buffer = ""
#         return "".join(out_parts), tags

#     def finalize(self) -> str:
#         """Flush any remaining buffered text.

#         If the buffer ends with an open tag fragment (a "<" with no "/>"),
#         log it as an orphan and drop. The voice flow is intentionally
#         lossy here rather than speaking a half-tag aloud.
#         """
#         if not self._buffer:
#             return ""

#         if _looks_like_partial_tag(self._buffer):
#             logger.warning(
#                 "action_tag.orphan",
#                 fragment=self._buffer[:80],
#             )
#             self._buffer = ""
#             return ""

#         flushed = self._buffer
#         self._buffer = ""
#         return flushed


# def _build_tag(verb: str, attrs_str: str) -> ActionTag | None:
#     """Validate verb against allowlist; parse attributes. Return None when
#     the verb is not in the allowlist (so the tag is stripped without
#     dispatch).
#     """
#     v = verb.lower()
#     if v not in ALLOWED_VERBS:
#         logger.info("action_tag.unknown_verb", verb=verb)
#         return None

#     attrs: dict[str, str] = {}
#     for m in _ATTR_RE.finditer(attrs_str):
#         value = m.group("v1") if m.group("v1") is not None else m.group("v2")
#         attrs[m.group("name")] = value
#     return ActionTag(verb=v, attrs=attrs)


# def _looks_like_partial_tag(fragment: str) -> bool:
#     """Heuristic: given the buffer starting at "<", does it look like an
#     incomplete tag (i.e., the next chunks might close it)?

#     A fragment is "partial" when it starts with "<" followed by a letter
#     (i.e., looks like a tag start) and does not contain "/>" anywhere. A
#     bare "<" with a non-letter next (e.g., "< 5") is NOT a partial tag —
#     flush it as text.
#     """
#     if not fragment.startswith("<"):
#         return False
#     if "/>" in fragment:
#         return False
#     if len(fragment) == 1:
#         return True
#     return fragment[1].isalpha() or fragment[1] == "_"
