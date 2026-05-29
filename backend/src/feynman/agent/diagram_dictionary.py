# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Diagram dictionary resolver — role → element_id lookup for annotation tools.

# When the design_agent emits a ``DiagramSpec`` it now also emits a
# ``dictionary`` mapping each meaningful element id to a small ``ElementMeta``
# describing its functional role and bounds. The teaching agent then refers to
# elements by *role* (``"hypotenuse"``) instead of opaque IDs (``"side_AB"``).

# This module turns a role string into an exact element id, with a few small
# quality-of-life fallbacks (case-insensitive match, common typos, raw-id
# escape hatch).
# """

# from __future__ import annotations

# from typing import TYPE_CHECKING

# import structlog

# if TYPE_CHECKING:
#     from feynman.agent.teaching_context import TeachingContext

# logger = structlog.get_logger()

# # Common typos mapped to their canonical role. Kept tiny on purpose.
# _ROLE_NORMALIZATIONS: dict[str, str] = {
#     "hypoteneuse": "hypotenuse",
#     "hypotnuse": "hypotenuse",
#     "opp": "opposite",
#     "adj": "adjacent",
# }


# def _normalize(role_or_id: str) -> str:
#     s = role_or_id.strip().lower()
#     return _ROLE_NORMALIZATIONS.get(s, s)


# class DictionaryResolver:
#     """Resolves ``element_or_role`` → ``element_id`` against the active dictionary."""

#     def __init__(self, tc: TeachingContext) -> None:
#         self._tc = tc

#     @property
#     def dictionary(self) -> dict[str, object]:
#         """Active diagram's dictionary, or empty dict if no diagram is on the slide."""
#         return getattr(self._tc, "current_diagram_dictionary", None) or {}

#     def resolve(self, element_or_role: str) -> str | None:
#         """Return the resolved element_id, or None on no match.

#         Lookup order:
#           1. Exact id match against the active dictionary.
#           2. Case-insensitive role match (with common-typo normalization).
#              If multiple elements share the role, the first id wins.
#           3. No match → return ``None``. Callers (the annotation tools)
#              must check and surface a clear error to the LLM rather than
#              publishing an instruction with a bogus target id that the
#              frontend will silently drop.

#         Returns None when the input is empty, when no diagram is on the
#         slide (empty dictionary), or when neither an exact id nor a role
#         matches.
#         """
#         if not element_or_role:
#             return None

#         directory = self.dictionary
#         if not directory:
#             return None

#         # 1. Exact id match.
#         if element_or_role in directory:
#             return element_or_role

#         # 2. Role match (case-insensitive, normalized).
#         target = _normalize(element_or_role)
#         matches: list[str] = []
#         for element_id, meta in directory.items():
#             role = getattr(meta, "role", None)
#             if role is None and isinstance(meta, dict):
#                 role = meta.get("role")
#             if role and _normalize(role) == target:
#                 matches.append(element_id)

#         if matches:
#             if len(matches) > 1:
#                 logger.warning(
#                     "diagram_dictionary.multi_match",
#                     role=element_or_role,
#                     candidates=matches,
#                     chosen=matches[0],
#                 )
#             return matches[0]

#         # 3. No match — fail loud. Caller is responsible for telling the LLM.
#         logger.warning(
#             "diagram_dictionary.no_match",
#             element_or_role=element_or_role,
#             dictionary_keys=list(directory.keys()),
#         )
#         return None
