"""Marker-based script splitting.

Input: narration text with inline markers
  <<SHOW_DIAGRAM:diagram_id>>
  <<PAUSE:short>>
  <<PAUSE:long>>

Output: ordered list of fragments. Each fragment is either:
  - ("text", "fragment text", None)            → goes to TTS
  - ("show_diagram", "diagram_id", None)       → emits ShowDiagramEvent
  - ("pause", "short" or "long", None)         → emits PauseEvent

The pipeline iterates these fragments, runs TTS on text ones, and builds
the manifest event sequence in order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


_MARKER_RE = re.compile(r"<<(SHOW_DIAGRAM|PAUSE):([^>]+)>>", re.IGNORECASE)


@dataclass
class TextFragment:
    kind: Literal["text"]
    text: str


@dataclass
class DiagramFragment:
    kind: Literal["show_diagram"]
    diagram_id: str


@dataclass
class PauseFragment:
    kind: Literal["pause"]
    duration: Literal["short", "long"]


ScriptFragment = TextFragment | DiagramFragment | PauseFragment


def split_script(text: str) -> list[ScriptFragment]:
    """Split a narration string into ordered fragments at every marker."""
    if not text:
        return []

    fragments: list[ScriptFragment] = []
    pos = 0
    for match in _MARKER_RE.finditer(text):
        preceding = text[pos:match.start()].strip()
        if preceding:
            fragments.append(TextFragment(kind="text", text=preceding))

        marker_kind = match.group(1).upper()
        marker_value = match.group(2).strip()
        if marker_kind == "SHOW_DIAGRAM":
            fragments.append(DiagramFragment(kind="show_diagram", diagram_id=marker_value))
        elif marker_kind == "PAUSE":
            duration = "short" if marker_value.lower().startswith("s") else "long"
            fragments.append(PauseFragment(kind="pause", duration=duration))

        pos = match.end()

    tail = text[pos:].strip()
    if tail:
        fragments.append(TextFragment(kind="text", text=tail))

    return fragments
