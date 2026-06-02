"""Semantic highlight aligner — post-hoc re-choreography of diagram highlights.

THE PROBLEM THIS FIXES
----------------------
The lesson planner authors `<<FOCUS:id>>` / `<<POINT:id>>` / `<<TRACE:id>>`
markers inside the narration *before the diagram is generated* — it guesses
which element to highlight for a picture it cannot see, with no semantic
matching. Result: highlights point at the wrong element most of the time, fire
at coarse 14-50s chunk boundaries, and are barely related to what's being said.

THE FIX (this module)
---------------------
A post-hoc pass that runs AFTER narration + diagrams already exist:

  1. Take a topic's narration block, strip the old annotation markers, keep the
     structural ones (SHOW_DIAGRAM / SECTION / WRITE_* / PAUSE / TOPIC_START).
  2. Split the spoken prose into sentences; track which diagram is on-screen for
     each sentence (from the SHOW_DIAGRAM markers).
  3. ONE LLM call per topic: given each sentence + the REAL on-screen diagram's
     element dictionary (id -> role + plain-English semantic), decide which
     element that sentence is *explaining* — semantically, even if the element
     is never named — or NONE. The model only ever sees ids that are actually on
     screen, so it cannot point at something that isn't there.
  4. Collapse consecutive same-element sentences into a *sustained* highlight
     (hold while that part is explained), and re-insert FOCUS/TRACE markers at
     the sentence boundaries where attention should move.

The output is a new narration string. Re-running TTS + the manifest composer
over it (cheap, local Kokoro) produces correctly-targeted, well-timed,
sentence-bound highlights. No planner / diagram-generation re-run.

The rule, in one line: *highlight the element the current sentence is
explaining; if it's not about a specific on-screen part, highlight nothing.*
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from lecture_pipeline_v2.llm.base import LLMProvider
from lecture_pipeline_v2.llm.factory import create_llm_provider

from .highlight_aligner_prompt import HIGHLIGHT_ALIGNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_MAX_OUTPUT_TOKENS = 8192

# Markers we STRIP (we re-decide all attention direction from scratch).
_ANNOTATION_KINDS = {
    "FOCUS",
    "UNFOCUS",
    "RESET_FOCUS",
    "CLEAR_ANNOTATIONS",
    "POINT",
    "TRACE",
    "MARK",
    "WRITE_MARGIN",
    # legacy, already dropped downstream — strip so they don't survive a re-run
    "PIN",
    "CALLOUT",
    "BRACKET",
    "HIGHLIGHT",
    "PULSE",
}

# Any `<<KIND:body>>` or `<<KIND>>`.
_MARKER_RE = re.compile(r"<<([A-Z_]+)(?::([^>]*))?>>")

# Final-pass strip of stray planner annotation markers we did NOT author. We
# keep FOCUS / TRACE / UNFOCUS (ours) + all structural markers; anything else in
# the annotation family that slipped through is removed so it can't render.
_STRAY_ANNOTATION_RE = re.compile(
    r"<<(?:POINT|MARK|WRITE_MARGIN|PIN|CALLOUT|BRACKET|HIGHLIGHT|PULSE|"
    r"RESET_FOCUS|CLEAR_ANNOTATIONS)(?::[^>]*)?>>\s*"
)

# Sentence splitter: end punctuation followed by whitespace + a capital/quote.
# Good enough for narration prose (not math-dense), keeps decimals intact.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'“])")


# ---------------------------------------------------------------------------
# Tokenisation of a narration block
# ---------------------------------------------------------------------------


@dataclass
class _StructuralToken:
    """A marker we keep verbatim (SHOW_DIAGRAM, SECTION, WRITE_*, PAUSE, ...)."""

    raw: str
    kind: str
    body: str


@dataclass
class _SentenceToken:
    """One spoken sentence of prose."""

    text: str
    diagram_id: str | None = None  # on-screen diagram when this is spoken
    # Filled by the aligner:
    element_id: str | None = None
    treatment: str | None = None  # "focus" | "trace" | None
    # True when this sentence continues the SAME span as the previous one, so
    # it must NOT re-emit a marker (the span's marker is on its first sentence).
    suppress_marker: bool = False


Token = _StructuralToken | _SentenceToken


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _SENTENCE_END_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _tokenize(block: str) -> list[Token]:
    """Split a narration block into structural markers + prose sentences,
    dropping all existing annotation markers. Order is preserved."""
    tokens: list[Token] = []
    pos = 0
    for m in _MARKER_RE.finditer(block):
        pre = block[pos : m.start()]
        for sent in _split_sentences(pre):
            tokens.append(_SentenceToken(text=sent))
        kind = m.group(1).upper()
        body = (m.group(2) or "").strip()
        if kind not in _ANNOTATION_KINDS:
            tokens.append(_StructuralToken(raw=m.group(0), kind=kind, body=body))
        pos = m.end()
    for sent in _split_sentences(block[pos:]):
        tokens.append(_SentenceToken(text=sent))
    return tokens


def _stamp_active_diagram(tokens: list[Token]) -> None:
    """Walk tokens, tracking the on-screen diagram from SHOW_DIAGRAM markers,
    and stamp each sentence with the diagram active when it's spoken."""
    active: str | None = None
    for t in tokens:
        if isinstance(t, _StructuralToken) and t.kind == "SHOW_DIAGRAM":
            active = t.body
        elif isinstance(t, _SentenceToken):
            t.diagram_id = active


# ---------------------------------------------------------------------------
# Span collapsing — sustained highlights
# ---------------------------------------------------------------------------


def _collapse_into_spans(
    sentences: list[_SentenceToken], report: AlignerReport
) -> None:
    """Consecutive sentences pointing at the same element become ONE sustained
    span: only the FIRST sentence of the run carries a marker; the rest hold.
    A run of None keeps no marker. Short jabs (1-sentence run) and long holds
    (multi-sentence run) emerge automatically. `suppress_marker` is consumed by
    `_render_tokens`."""
    prev_eid: str | None = None
    for s in sentences:
        if s.element_id:
            report.sentences_highlighted += 1
            if s.element_id == prev_eid:
                s.suppress_marker = True  # span continues
            else:
                s.suppress_marker = False  # new span starts here
                report.spans += 1
        prev_eid = s.element_id


def _render_tokens(tokens: list[Token]) -> str:
    """Rebuild the narration block, inserting a single marker at the start of
    each highlight span, and an UNFOCUS when attention drops. Structural markers
    pass through verbatim; SHOW_DIAGRAM resets the active spotlight."""
    parts: list[str] = []
    active_eid: str | None = None
    for t in tokens:
        if isinstance(t, _StructuralToken):
            if t.kind == "SHOW_DIAGRAM":
                active_eid = None  # new diagram clears attention
            parts.append(t.raw)
            continue
        # sentence token
        if t.element_id and not t.suppress_marker:
            kind = "TRACE" if t.treatment == "trace" else "FOCUS"
            parts.append(f"<<{kind}:{t.element_id}>>")
            active_eid = t.element_id
        elif not t.element_id and active_eid is not None:
            parts.append("<<UNFOCUS>>")
            active_eid = None
        parts.append(t.text)
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Topic-block splitting (keep the <<TOPIC_START:...>> headers)
# ---------------------------------------------------------------------------

_TOPIC_SPLIT_RE = re.compile(r"(<<TOPIC_START:[^>]+>>)")


def _split_topic_blocks(narration_text: str) -> list[tuple[str, str]]:
    """Return [(header_marker_or_empty, body), ...] preserving order."""
    parts = _TOPIC_SPLIT_RE.split(narration_text)
    blocks: list[tuple[str, str]] = []
    if parts and parts[0].strip():
        blocks.append(("", parts[0]))
    for i in range(1, len(parts), 2):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        blocks.append((header, body))
    return blocks


# ---------------------------------------------------------------------------
# Aligner
# ---------------------------------------------------------------------------


@dataclass
class AlignerReport:
    topics_processed: int = 0
    sentences_total: int = 0
    sentences_highlighted: int = 0
    spans: int = 0
    dropped_invalid_id: int = 0
    llm_failures: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"aligner: {self.topics_processed} topics, "
            f"{self.sentences_highlighted}/{self.sentences_total} sentences highlighted, "
            f"{self.spans} spans, {self.dropped_invalid_id} invalid-id dropped, "
            f"{self.llm_failures} llm failures"
        )


class SemanticHighlightAligner:
    """Re-decides diagram highlights against the real on-screen diagrams."""

    def __init__(self, config, *, model: str | None = None, provider=None):
        """`config` is the pipeline LLMConfig (provider/model/api_key).

        Follows the main `llm` switch; pass `model` to pin a different model
        (api_key is re-resolved if that implies a different provider). The
        `provider` kwarg injects a pre-built provider (tests / shared client).
        """
        self._config = config
        self._provider: LLMProvider = provider or create_llm_provider(
            config.for_override(None, model)
        )

    async def realign_chapter_narration(
        self,
        narration_text: str,
        diagrams_by_id: dict[str, dict[str, Any]],
        report: AlignerReport | None = None,
    ) -> str:
        """Realign every topic block in a chapter narration string.

        `diagrams_by_id` maps diagram_id -> render_data dict (must contain a
        `dictionary` of element_id -> {role, semantic, ...}).
        Returns a new narration string with re-decided highlight markers.
        """
        report = report or AlignerReport()
        blocks = _split_topic_blocks(narration_text)
        out_blocks: list[str] = []
        for header, body in blocks:
            new_body = await self._realign_block(body, diagrams_by_id, report)
            out_blocks.append(f"{header}\n{new_body}" if header else new_body)
            report.topics_processed += 1
        result = "\n\n".join(b for b in out_blocks if b.strip())
        # Defensive: strip any annotation marker we didn't author (FOCUS/TRACE/
        # UNFOCUS are ours; a stray planner POINT/MARK/etc. pointing at a bogus
        # id occasionally survives an edge case — drop it so it can't render).
        result = _STRAY_ANNOTATION_RE.sub("", result)
        return result

    async def _realign_block(
        self,
        block: str,
        diagrams_by_id: dict[str, dict[str, Any]],
        report: AlignerReport,
    ) -> str:
        tokens = _tokenize(block)
        _stamp_active_diagram(tokens)
        sentences = [t for t in tokens if isinstance(t, _SentenceToken)]
        report.sentences_total += len(sentences)
        if not any(s.diagram_id for s in sentences):
            return _render_tokens(tokens)  # nothing on screen to highlight

        decisions = await self._decide(sentences, diagrams_by_id, report)
        for i, dec in decisions.items():
            s = sentences[i]
            eid = dec.get("element_id")
            if not eid or not s.diagram_id:
                continue
            dic = (diagrams_by_id.get(s.diagram_id, {}) or {}).get("dictionary") or {}
            if eid not in dic:
                report.dropped_invalid_id += 1
                continue
            s.element_id = eid
            s.treatment = dec.get("treatment") or "focus"

        _collapse_into_spans(sentences, report)
        return _render_tokens(tokens)

    async def _decide(
        self,
        sentences: list[_SentenceToken],
        diagrams_by_id: dict[str, dict[str, Any]],
        report: AlignerReport,
    ) -> dict[int, dict[str, Any]]:
        """One LLM call: per sentence, which on-screen element is it explaining?"""
        user_message = _build_user_message(sentences, diagrams_by_id)
        try:
            raw = await self._call_llm(user_message)
        except Exception as e:  # noqa: BLE001
            report.llm_failures += 1
            report.warnings.append(f"aligner LLM call failed: {e}")
            logger.warning("highlight_aligner.llm_failed", exc_info=True)
            return {}
        out: dict[int, dict[str, Any]] = {}
        for item in raw.get("decisions", []):
            try:
                i = int(item["sentence_index"])
            except (KeyError, ValueError, TypeError):
                continue
            if 0 <= i < len(sentences):
                out[i] = {
                    "element_id": (item.get("element_id") or None),
                    "treatment": (item.get("treatment") or None),
                }
        return out

    async def _call_llm(self, user_message: str) -> dict[str, Any]:
        payload = await self._provider.agenerate_tool_use(
            HIGHLIGHT_ALIGNER_SYSTEM_PROMPT,
            user_message,
            tool_name=_ALIGN_TOOL["name"],
            tool_description=_ALIGN_TOOL["description"],
            input_schema=_ALIGN_TOOL["input_schema"],
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
        return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# Prompt user-message + tool schema
# ---------------------------------------------------------------------------


def _build_user_message(
    sentences: list[_SentenceToken],
    diagrams_by_id: dict[str, dict[str, Any]],
) -> str:
    """One message: the sentence sequence + the element catalog of every diagram
    on-screen during this topic."""
    lines: list[str] = []
    lines.append("# On-screen diagram elements (the ONLY things you may highlight)\n")
    shown: set[str] = set()
    for s in sentences:
        did = s.diagram_id
        if not did or did in shown:
            continue
        shown.add(did)
        info = diagrams_by_id.get(did, {}) or {}
        dic = info.get("dictionary") or {}
        title = info.get("title") or did.split(":")[-1]
        lines.append(f"## Diagram `{did}` — {title}")
        if not dic:
            lines.append("  (no labelled elements)")
        for eid, meta in dic.items():
            meta = meta or {}
            role = meta.get("role", "")
            sem = meta.get("semantic", "")
            lines.append(f"  - `{eid}`  [{role}] — {sem}")
        lines.append("")

    lines.append("# Narration sentences (decide a highlight for each)\n")
    for i, s in enumerate(sentences):
        tag = "" if s.diagram_id else "  (no diagram on screen — must be null)"
        lines.append(f"[{i}] {s.text}{tag}")
    lines.append(
        "\nReturn one decision per sentence index you want to highlight "
        "(omit a sentence to highlight nothing). element_id MUST come from the "
        "on-screen diagram for that sentence."
    )
    return "\n".join(lines)


_ALIGN_TOOL = {
    "name": "emit_highlights",
    "description": (
        "Emit the per-sentence highlight decisions. Only include sentences that "
        "are genuinely explaining a specific on-screen element."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sentence_index": {"type": "integer"},
                        "element_id": {
                            "type": "string",
                            "description": "An element_id from the on-screen diagram, or omit to skip.",
                        },
                        "treatment": {
                            "type": "string",
                            "enum": ["focus", "trace"],
                            "description": "focus = spotlight; trace = draw along a line/curve being 'watched form'.",
                        },
                    },
                    "required": ["sentence_index", "element_id"],
                },
            }
        },
        "required": ["decisions"],
    },
}
