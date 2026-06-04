"""Marker-based script splitting (Path C).

Walks a narration string left-to-right and emits ordered fragments at every
inline marker the script writer is allowed to use. Text fragments go to TTS;
the rest become zero-duration manifest events (notebook entries, diagram
cues, pauses, attention-direction).

Notebook + slide markers:

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

Attention-direction markers (doc 18 spotlight redesign):

    <<FOCUS:role>>                         — spotlight this role; dim the rest
    <<FOCUS:role|text=2-3 words>>          — focus + inline label
    <<UNFOCUS>>                            — clear current focus
    <<RESET_FOCUS>> (alias: CLEAR_ANNOTATIONS) — wipe spotlight state for the
                                              active diagram
    <<REVEAL_STEP:n>>                      — advance staged build_up reveal to
                                              group n (frontend clamps + fills)
    <<SET_PARAM:name|value=V>>             — set a parameter on the active diagram
    <<ANIMATE_PARAM:name|to=T|from=F|duration=D>> — tween a parameter (the sweep)

Focus targets a ROLE from the active diagram's `dictionary` (set by
`enrichment/diagrams.py`). The fragment's `diagram_id` field is filled by
the ManifestComposer walker once it knows which diagram is active.

Legacy annotation markers (PIN / CALLOUT / BRACKET / HIGHLIGHT / PULSE) are
still parsed for back-compat with stored extraction files, but the walker
drops them silently and emits nothing — the spotlight primitive replaces
them. The parse path is kept so old narration strings don't crash the
chunker mid-ingest; the deprecation will be removed after one re-ingest
cycle validates the spotlight redesign.

The body of each marker is split on `|` to extract optional named attributes.
Missing ids are auto-generated as `{kind}-{counter}`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from lecture_pipeline_v2.curriculum.models import Placement, Rect


_MARKER_RE = re.compile(
    r"<<(SHOW_DIAGRAM|PAUSE|SECTION|WRITE_EQUATION|WRITE_STEP|WRITE_KEY|"
    r"WRITE_TEXT|WRITE_ANSWER|STRIKE|NEW_PAGE|"
    r"FOCUS|UNFOCUS|RESET_FOCUS|REVEAL_STEP|SET_PARAM|ANIMATE_PARAM|"
    r"TRACE|MARK|POINT|WRITE_MARGIN|"
    r"PIN|CALLOUT|BRACKET|HIGHLIGHT|PULSE|CLEAR_ANNOTATIONS):?([^>]*)>>",
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
    # Phase 3: walker stamps these via LayoutPlanner.place_diagram.
    placement: "Placement | None" = None
    slide_element_bounds: "dict[str, Rect] | None" = None
    # Doc 18 §4.3: walker stamps this from the active Diagram so the
    # frontend can pick "build_up" or "overview" rendering. None for
    # back-compat with paths that don't have a Diagram lookup.
    presentation_mode: Literal["build_up", "overview"] | None = None


@dataclass
class PauseFragment:
    kind: Literal["pause"]
    duration: Literal["short", "long"]


@dataclass
class SectionFragment:
    kind: Literal["section"]
    id: str
    title: str
    placement: "Placement | None" = None


@dataclass
class EquationFragment:
    kind: Literal["equation"]
    id: str
    latex: str
    align_group: str | None = None
    boxed: bool = False
    placement: "Placement | None" = None


@dataclass
class StepFragment:
    kind: Literal["step"]
    id: str
    text: str
    indent: int = 0
    placement: "Placement | None" = None


@dataclass
class KeyPointFragment:
    kind: Literal["key_point"]
    id: str
    text: str
    placement: "Placement | None" = None


@dataclass
class TextEntryFragment:
    kind: Literal["text_entry"]
    id: str
    text: str
    placement: "Placement | None" = None


@dataclass
class AnswerFragment:
    kind: Literal["answer"]
    id: str
    text: str
    placement: "Placement | None" = None


@dataclass
class StrikeFragment:
    kind: Literal["strike"]
    target_id: str


@dataclass
class NewPageFragment:
    kind: Literal["new_page"]
    carry_forward_ids: list[str] = field(default_factory=list)


# Phase 3: synthetic fragment INJECTED by the walker (not parsed from text).
# Carries a deterministic page break with slide_action resolved via the
# LayoutPlanner's look-ahead.
@dataclass
class PageBreakFragment:
    kind: Literal["page_break"]
    new_page_index: int = 0
    slide_action: Literal["keep", "swap", "release"] = "keep"
    next_diagram_id: str | None = None
    notebook_carry_forward_ids: list[str] = field(default_factory=list)
    reason: Literal["text_overflow", "new_diagram", "writer_marker"] = "text_overflow"


# --- Attention-direction fragments (doc 18 spotlight redesign) ----------------
#
# FocusFragment: spotlight one role on the active diagram. Replaces any
#   previous focus. Optional inline label (`text`) appears near the focused
#   element.
# UnfocusFragment: clear current focus. Rarely needed in practice — the
#   next FOCUS or SHOW_DIAGRAM implicitly releases the previous one.
#
# `diagram_id` is filled by ManifestComposer once it knows the active
# diagram (from the preceding ShowDiagram). RESET_FOCUS produces a
# ClearAnnotationsFragment (see the legacy block below) for back-compat
# event-name continuity.


@dataclass
class FocusFragment:
    kind: Literal["focus"]
    role: str
    text: str = ""
    diagram_id: str = ""
    # Doc 19 §A-3: stable element_id resolved from `role` by the
    # ManifestComposer walker. Stays empty if the walker drops the fragment.
    element_id: str = ""
    # Co-highlight: when a FOCUS marker targets multiple elements at once
    # (`<<FOCUS:a+b>>`), this holds the parsed id/role list; the walker resolves
    # each to a real element_id. Single-target focus leaves it empty.
    element_ids: list[str] = field(default_factory=list)


@dataclass
class UnfocusFragment:
    kind: Literal["unfocus"]
    diagram_id: str = ""


# --- New live-annotation fragments (doc 19 §12) ------------------------------
#
# Four new primitives extending the focus surface. The walker validates that
# the active diagram is set + that element_id-based primitives reference a
# real element in the dictionary; mark_point only requires an active diagram
# (it carries raw coordinates). All four mirror the FocusFragment pattern:
# `diagram_id` is empty at parse time and stamped by the ManifestComposer.


@dataclass
class TraceFragment:
    kind: Literal["trace"]
    element_id: str
    duration_ms: int = 1500
    diagram_id: str = ""


@dataclass
class MarkPointFragment:
    kind: Literal["mark_point"]
    point_kind: Literal["dot", "cross", "star"] = "dot"
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    diagram_id: str = ""


@dataclass
class PointAtFragment:
    kind: Literal["point_at"]
    element_id: str = ""
    from_side: Literal["top", "bottom", "left", "right"] = "left"
    diagram_id: str = ""


@dataclass
class WriteMarginFragment:
    kind: Literal["write_margin"]
    anchor_element_id: str = ""
    side: Literal["top", "bottom", "left", "right"] = "right"
    text: str = ""
    diagram_id: str = ""


# --- Staged-reveal fragment (Workstream B) ------------------------------------
#
# Advances a build_up diagram's staged element reveal. Authored as
# `<<REVEAL_STEP:n>>` (reveal group n), OR injected by the walker with
# step=REVEAL_ALL_STEP — the reveal-all sentinel emitted when a build_up diagram
# leaves the screen (swap) or the chapter ends, so no element is left hidden.
# The frontend clamps step to the last group and fills every group idempotently,
# so the sentinel reveals everything; reveal_step is a no-op on non-staging
# diagrams. `diagram_id` is stamped by the walker (empty at parse time).
REVEAL_ALL_STEP = 10_000


@dataclass
class RevealStepFragment:
    kind: Literal["reveal_step"]
    step: int = 0
    diagram_id: str = ""


# --- Parameter-choreography fragments (Workstream A5) -------------------------
#
# set_parameter jumps a parameter to a value; animate_parameter tweens it (the
# sweep IS the explanation). `name` is a parameter of the active diagram (a
# template param, or a declared parameters[] entry on an LLM diagram). The
# walker validates the name against the active diagram + stamps `diagram_id`;
# an unknown name drops. `from_value` (animate) is optional — absent ⇒ tween
# from the live value.


@dataclass
class SetParamFragment:
    kind: Literal["set_parameter"]
    name: str
    value: float = 0.0
    diagram_id: str = ""


@dataclass
class AnimateParamFragment:
    kind: Literal["animate_parameter"]
    name: str
    to: float = 0.0
    from_value: float | None = None
    duration_ms: int | None = None
    diagram_id: str = ""


# --- Legacy annotation fragments (back-compat parse; walker drops) ------------
#
# These five fragments are produced by the chunker for old PIN/CALLOUT/
# BRACKET/HIGHLIGHT/PULSE markers in narration strings (e.g., from extraction
# files predating the spotlight redesign). The walker silently drops them
# with a one-shot deprecation log per chapter. Schedule for removal one
# re-ingest cycle after the spotlight redesign validates.


@dataclass
class PinFragment:
    kind: Literal["pin"]
    id: str
    role: str
    text: str
    position: Literal["above", "below", "left", "right"] = "above"
    diagram_id: str = ""


@dataclass
class CalloutFragment:
    kind: Literal["callout"]
    id: str
    role: str
    text: str
    direction: Literal[
        "up", "down", "up-right", "up-left", "down-right", "down-left"
    ] = "up-right"
    diagram_id: str = ""


@dataclass
class BracketFragment:
    kind: Literal["bracket"]
    id: str
    role_a: str
    role_b: str
    label: str
    side: Literal["above", "below", "left", "right"] = "above"
    diagram_id: str = ""


@dataclass
class HighlightFragment:
    kind: Literal["highlight"]
    role: str
    duration_ms: int = 1500
    color_token: str | None = None
    diagram_id: str = ""


@dataclass
class PulseFragment:
    kind: Literal["pulse"]
    role: str
    duration_ms: int = 800
    color_token: str | None = None
    diagram_id: str = ""


@dataclass
class ClearAnnotationsFragment:
    kind: Literal["clear_annotations"]
    diagram_id: str = ""


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
    | PageBreakFragment
    | FocusFragment
    | UnfocusFragment
    | ClearAnnotationsFragment
    | TraceFragment
    | MarkPointFragment
    | PointAtFragment
    | WriteMarginFragment
    | RevealStepFragment
    | SetParamFragment
    | AnimateParamFragment
    | PinFragment
    | CalloutFragment
    | BracketFragment
    | HighlightFragment
    | PulseFragment
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
        preceding = text[pos : match.start()].strip()
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

    # --- Attention-direction markers (spotlight redesign) -------------------

    if kind == "FOCUS":
        # Co-highlight: `<<FOCUS:a+b+c>>` spotlights several elements at once.
        # `+` is safe — element ids/roles never contain it.
        targets = [t.strip() for t in content.split("+") if t.strip()]
        return FocusFragment(
            kind="focus",
            role=targets[0] if targets else content.strip(),
            text=attrs.get("text", "").strip(),
            element_ids=targets if len(targets) > 1 else [],
        )

    if kind == "UNFOCUS":
        return UnfocusFragment(kind="unfocus")

    if kind == "RESET_FOCUS":
        return ClearAnnotationsFragment(kind="clear_annotations")

    if kind == "REVEAL_STEP":
        try:
            step = int(content)
        except (ValueError, TypeError):
            step = 0
        return RevealStepFragment(kind="reveal_step", step=max(0, step))

    if kind == "SET_PARAM":
        try:
            value = float(attrs.get("value", "0"))
        except (ValueError, TypeError):
            value = 0.0
        return SetParamFragment(kind="set_parameter", name=content, value=value)

    if kind == "ANIMATE_PARAM":
        try:
            to = float(attrs.get("to", "0"))
        except (ValueError, TypeError):
            to = 0.0
        from_value: float | None
        try:
            from_value = float(attrs["from"]) if "from" in attrs else None
        except (ValueError, TypeError):
            from_value = None
        duration_ms: int | None
        try:
            duration_ms = int(attrs["duration"]) if "duration" in attrs else None
        except (ValueError, TypeError):
            duration_ms = None
        return AnimateParamFragment(
            kind="animate_parameter",
            name=content,
            to=to,
            from_value=from_value,
            duration_ms=duration_ms,
        )

    # --- New live-annotation markers (doc 19 §12) ----------------------------

    if kind == "TRACE":
        try:
            duration_ms = int(attrs.get("duration_ms", "1500"))
        except ValueError:
            duration_ms = 1500
        return TraceFragment(
            kind="trace",
            element_id=content,
            duration_ms=max(0, duration_ms),
        )

    if kind == "MARK":
        point_kind_raw = (content or "dot").lower()
        point_kind: Literal["dot", "cross", "star"] = (
            point_kind_raw  # type: ignore[assignment]
            if point_kind_raw in ("dot", "cross", "star")
            else "dot"
        )
        try:
            x = float(attrs.get("x", "0"))
        except ValueError:
            x = 0.0
        try:
            y = float(attrs.get("y", "0"))
        except ValueError:
            y = 0.0
        return MarkPointFragment(
            kind="mark_point",
            point_kind=point_kind,
            x=x,
            y=y,
            label=attrs.get("label", "").strip(),
        )

    if kind == "POINT":
        from_side_raw = attrs.get("from_side", "left").lower()
        from_side: Literal["top", "bottom", "left", "right"] = (
            from_side_raw  # type: ignore[assignment]
            if from_side_raw in ("top", "bottom", "left", "right")
            else "left"
        )
        return PointAtFragment(
            kind="point_at",
            element_id=content,
            from_side=from_side,
        )

    if kind == "WRITE_MARGIN":
        side_raw_wm = attrs.get("side", "right").lower()
        side_wm: Literal["top", "bottom", "left", "right"] = (
            side_raw_wm  # type: ignore[assignment]
            if side_raw_wm in ("top", "bottom", "left", "right")
            else "right"
        )
        return WriteMarginFragment(
            kind="write_margin",
            anchor_element_id=content,
            side=side_wm,
            text=attrs.get("text", "").strip(),
        )

    # --- Legacy annotation markers (back-compat parse; walker drops) --------

    if kind == "PIN":
        position_raw = attrs.get("position", "above").lower()
        position: Literal["above", "below", "left", "right"] = (
            position_raw  # type: ignore[assignment]
            if position_raw in ("above", "below", "left", "right")
            else "above"
        )
        return PinFragment(
            kind="pin",
            id=attrs.get("id") or allocator.next("pin"),
            role=content,
            text=attrs.get("text", "").strip(),
            position=position,
        )

    if kind == "CALLOUT":
        direction_raw = attrs.get("direction", "up-right").lower()
        valid_dirs = ("up", "down", "up-right", "up-left", "down-right", "down-left")
        direction: Literal[
            "up", "down", "up-right", "up-left", "down-right", "down-left"
        ] = (
            direction_raw  # type: ignore[assignment]
            if direction_raw in valid_dirs
            else "up-right"
        )
        return CalloutFragment(
            kind="callout",
            id=attrs.get("id") or allocator.next("callout"),
            role=content,
            text=attrs.get("text", "").strip(),
            direction=direction,
        )

    if kind == "BRACKET":
        side_raw = attrs.get("side", "above").lower()
        side: Literal["above", "below", "left", "right"] = (
            side_raw  # type: ignore[assignment]
            if side_raw in ("above", "below", "left", "right")
            else "above"
        )
        roles = [r.strip() for r in content.split(",") if r.strip()]
        # Always emit a fragment — composer drops degenerate brackets with a
        # structured log entry. Empty / single-role parses come through with
        # empty role_b so the composer can report on them.
        role_a = roles[0] if roles else ""
        role_b = roles[1] if len(roles) > 1 else ""
        return BracketFragment(
            kind="bracket",
            id=attrs.get("id") or allocator.next("bracket"),
            role_a=role_a,
            role_b=role_b,
            label=attrs.get("label", "").strip(),
            side=side,
        )

    if kind == "HIGHLIGHT":
        try:
            duration_ms = int(attrs.get("duration", "1500"))
        except ValueError:
            duration_ms = 1500
        return HighlightFragment(
            kind="highlight",
            role=content,
            duration_ms=duration_ms,
            color_token=attrs.get("color") or None,
        )

    if kind == "PULSE":
        try:
            duration_ms = int(attrs.get("duration", "800"))
        except ValueError:
            duration_ms = 800
        return PulseFragment(
            kind="pulse",
            role=content,
            duration_ms=duration_ms,
            color_token=attrs.get("color") or None,
        )

    if kind == "CLEAR_ANNOTATIONS":
        return ClearAnnotationsFragment(kind="clear_annotations")

    # Should not be reachable — regex only matches the known set.
    return TextFragment(kind="text", text="")
