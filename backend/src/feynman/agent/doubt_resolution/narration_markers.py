"""Inline highlight markers in doubt narration → ordered delivery fragments.

The planner embeds `<<FOCUS:part>>` / `<<TRACE:part>>` / `<<UNFOCUS>>` markers in
`narration_text`, right before the phrase that names a diagram part. This module
splits a beat's narration into an ordered list of fragments — text to *speak*
and highlights to *fire* — so delivery can interleave them: fire the highlight,
then speak the words that name it, so the spotlight lands exactly as the voice
does. That phrase-level sync is what makes voice + diagram feel like ONE thing.

The marker vocabulary is the same as the offline lecture pipeline
(`data_pre_compute_v2/.../tts/chunker.py`) so both paths speak one language. The
splitter is ported here (a small regex) rather than cross-imported, since
`data_pre_compute_v2` is not a backend dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `<<FOCUS:a+b>>` / `<<TRACE:id>>` / `<<UNFOCUS>>` — matches the precompute syntax
# (`<<KIND:body>>`, body may carry `|text=...` attrs we ignore here).
_MARKER_RE = re.compile(r"<<(FOCUS|TRACE|UNFOCUS):?([^>]*)>>")


@dataclass(frozen=True)
class TextFragment:
    """A run of narration to speak aloud (markers stripped)."""

    text: str


@dataclass(frozen=True)
class FocusFragment:
    """Spotlight one or more parts (raw targets — element_id or role)."""

    targets: tuple[str, ...]


@dataclass(frozen=True)
class TraceFragment:
    """Animate a stroke along a part (raw target — element_id or role)."""

    target: str


@dataclass(frozen=True)
class UnfocusFragment:
    """Drop the current spotlight."""


Fragment = TextFragment | FocusFragment | TraceFragment | UnfocusFragment


def split_narration(text: str) -> list[Fragment]:
    """Split marker-laden narration into ordered fragments.

    A FOCUS/TRACE/UNFOCUS marker becomes its own fragment placed BEFORE the text
    that follows it (so the highlight fires, then the naming words are spoken).
    The spoken `TextFragment`s never contain markers. Targets are kept verbatim;
    the caller validates them against the active diagram.
    """
    if not text:
        return []
    frags: list[Fragment] = []
    pos = 0
    for m in _MARKER_RE.finditer(text):
        preceding = text[pos : m.start()].strip()
        if preceding:
            frags.append(TextFragment(preceding))
        kind = m.group(1).upper()
        # body may carry `|text=...` attrs (precompute); we only need the target.
        body = (m.group(2) or "").split("|", 1)[0].strip()
        if kind == "FOCUS":
            ids = tuple(t.strip() for t in body.split("+") if t.strip())
            if ids:
                frags.append(FocusFragment(ids))
        elif kind == "TRACE":
            if body:
                frags.append(TraceFragment(body))
        else:  # UNFOCUS
            frags.append(UnfocusFragment())
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        frags.append(TextFragment(tail))
    return frags


def strip_markers(text: str) -> str:
    """The plain spoken text with all markers removed (for TTS of a whole beat /
    for logging). Collapses the whitespace the stripped markers leave behind."""
    return " ".join(_MARKER_RE.sub(" ", text or "").split())


def resolve_target(target: str, dictionary: dict | None) -> str | None:
    """Resolve a marker target to a real element_id in the active diagram's
    dictionary (`element_id -> {role, semantic, ...}`), or None if it matches
    nothing. Accepts a direct element_id or a role name (case-insensitive) — so
    reused diagrams (planner knows ids) and generated/template diagrams (planner
    knows only roles) both resolve to a concrete element_id the frontend can
    spotlight."""
    if not dictionary or not target:
        return None
    if target in dictionary:  # direct element_id hit
        return target
    want = target.strip().lower()
    for element_id, meta in dictionary.items():
        if isinstance(meta, dict) and str(meta.get("role", "")).strip().lower() == want:
            return element_id
    return None
