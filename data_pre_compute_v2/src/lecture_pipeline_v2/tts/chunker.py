"""Marker-based script splitting (Path C).

Walks a narration string left-to-right and emits ordered fragments at every
inline marker the script writer is allowed to use. Text fragments go to TTS;
the rest become zero-duration manifest events (notebook entries, diagram
cues, pauses).

Marker grammar:

    <<SHOW_DIAGRAM:diagram_id>>
    <<PAUSE:short>>  or  <<PAUSE:long>>
    <<SECTION:title|id=section-1>>
    <<WRITE_EQUATION:LaTeX>>
    <<WRITE_EQUATION:LaTeX|group=g1|id=eq-1|boxed>>
    <<WRITE_STEP:text|indent=1|id=step-1>>
    <<WRITE_KEY:text|id=key-1>>
    <<WRITE_TEXT:text|id=text-1>>
    <<WRITE_ANSWER:text|id=ans-1>>
    <<STRIKE:eq-3>>
    <<NEW_PAGE>>
    <<NEW_PAGE|carry=eq-1,key-2>>

The body of each marker is split on `|` to extract optional named attributes.
Missing ids are auto-generated as `{kind}-{counter}`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


_MARKER_RE = re.compile(
    r"<<(SHOW_DIAGRAM|PAUSE|SECTION|WRITE_EQUATION|WRITE_STEP|WRITE_KEY|"
    r"WRITE_TEXT|WRITE_ANSWER|STRIKE|NEW_PAGE):?([^>]*)>>",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Fragment types (consumed by audio_pipeline.py)
# ---------------------------------------------------------------------------


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


@dataclass
class SectionFragment:
    kind: Literal["section"]
    id: str
    title: str


@dataclass
class EquationFragment:
    kind: Literal["equation"]
    id: str
    latex: str
    align_group: str | None = None
    boxed: bool = False


@dataclass
class StepFragment:
    kind: Literal["step"]
    id: str
    text: str
    indent: int = 0


@dataclass
class KeyPointFragment:
    kind: Literal["key_point"]
    id: str
    text: str


@dataclass
class TextEntryFragment:
    kind: Literal["text_entry"]
    id: str
    text: str


@dataclass
class AnswerFragment:
    kind: Literal["answer"]
    id: str
    text: str


@dataclass
class StrikeFragment:
    kind: Literal["strike"]
    target_id: str


@dataclass
class NewPageFragment:
    kind: Literal["new_page"]
    carry_forward_ids: list[str] = field(default_factory=list)


ScriptFragment = (
    TextFragment
    | DiagramFragment
    | PauseFragment
    | SectionFragment
    | EquationFragment
    | StepFragment
    | KeyPointFragment
    | TextEntryFragment
    | AnswerFragment
    | StrikeFragment
    | NewPageFragment
)


# ---------------------------------------------------------------------------
# Attribute parsing
# ---------------------------------------------------------------------------


def _parse_body(body: str) -> tuple[str, dict[str, str]]:
    """Split 'content|key=val|flag' into (content, {key: val, flag: ''})."""
    parts = body.split("|")
    content = parts[0].strip()
    attrs: dict[str, str] = {}
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            attrs[k.strip().lower()] = v.strip()
        else:
            attrs[part.lower()] = ""
    return content, attrs


class _IdAllocator:
    """Auto-IDs for markers that don't specify one. {kind}-{n} per script."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, kind: str) -> str:
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return f"{kind}-{self._counters[kind]}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def split_script(text: str) -> list[ScriptFragment]:
    """Walk the script and emit fragments in order."""
    if not text:
        return []

    fragments: list[ScriptFragment] = []
    allocator = _IdAllocator()
    pos = 0

    for match in _MARKER_RE.finditer(text):
        preceding = text[pos:match.start()].strip()
        if preceding:
            fragments.append(TextFragment(kind="text", text=preceding))

        kind_raw = match.group(1).upper()
        body = match.group(2) or ""
        content, attrs = _parse_body(body)

        fragments.append(_build_fragment(kind_raw, content, attrs, allocator))
        pos = match.end()

    tail = text[pos:].strip()
    if tail:
        fragments.append(TextFragment(kind="text", text=tail))

    return fragments


def _build_fragment(
    kind: str,
    content: str,
    attrs: dict[str, str],
    allocator: _IdAllocator,
) -> ScriptFragment:
    if kind == "SHOW_DIAGRAM":
        return DiagramFragment(kind="show_diagram", diagram_id=content)

    if kind == "PAUSE":
        duration: Literal["short", "long"] = (
            "short" if content.lower().startswith("s") else "long"
        )
        return PauseFragment(kind="pause", duration=duration)

    if kind == "SECTION":
        return SectionFragment(
            kind="section",
            id=attrs.get("id") or allocator.next("section"),
            title=content,
        )

    if kind == "WRITE_EQUATION":
        return EquationFragment(
            kind="equation",
            id=attrs.get("id") or allocator.next("eq"),
            latex=content,
            align_group=attrs.get("group"),
            boxed="boxed" in attrs,
        )

    if kind == "WRITE_STEP":
        indent_raw = attrs.get("indent", "0")
        try:
            indent = max(0, min(3, int(indent_raw)))
        except ValueError:
            indent = 0
        return StepFragment(
            kind="step",
            id=attrs.get("id") or allocator.next("step"),
            text=content,
            indent=indent,
        )

    if kind == "WRITE_KEY":
        return KeyPointFragment(
            kind="key_point",
            id=attrs.get("id") or allocator.next("key"),
            text=content,
        )

    if kind == "WRITE_TEXT":
        return TextEntryFragment(
            kind="text_entry",
            id=attrs.get("id") or allocator.next("text"),
            text=content,
        )

    if kind == "WRITE_ANSWER":
        return AnswerFragment(
            kind="answer",
            id=attrs.get("id") or allocator.next("ans"),
            text=content,
        )

    if kind == "STRIKE":
        return StrikeFragment(kind="strike", target_id=content)

    if kind == "NEW_PAGE":
        carry_raw = attrs.get("carry", "")
        carry = [x.strip() for x in carry_raw.split(",") if x.strip()]
        return NewPageFragment(kind="new_page", carry_forward_ids=carry)

    # Should not be reachable — regex only matches the known set.
    return TextFragment(kind="text", text="")
