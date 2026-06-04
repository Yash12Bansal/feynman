"""Semantic highlight aligner — post-hoc re-choreography of diagram highlights.

THE PROBLEM THIS FIXES
----------------------
The lesson planner authors `<<FOCUS:id>>` / `<<POINT:id>>` / `<<TRACE:id>>`
markers inside the narration *before the diagram is generated* — it guesses
which element to highlight for a picture it cannot see, with no semantic
matching. Result: highlights point at the wrong element most of the time and
are barely related to what's being said.

THE FIX (this module)
---------------------
A pass that runs AFTER narration + diagrams already exist (now folded into the
ingest pipeline, before TTS):

  1. Take a topic's narration block, strip the old annotation markers, keep the
     structural ones (SHOW_DIAGRAM / SECTION / WRITE_* / PAUSE / TOPIC_START).
  2. Split the spoken prose into sentences; track which diagram is on-screen for
     each sentence (from the SHOW_DIAGRAM markers).
  3. ONE LLM call per topic: per sentence, decide a CHOREOGRAPHY of highlight
     "ops" against the REAL on-screen diagram's element dictionary. Each op is
     an `anchor` (a few words copied verbatim from the sentence — where the
     highlight should land) + `element_ids` + a treatment. The intelligence:
       • MULTIPLE ids in one op  → co-highlight: light those parts TOGETHER
         (the sentence relates / compares / connects them).
       • SEVERAL ops in one sentence → sequential: attention moves across parts
         in turn ("from the emitter, through the base, to the collector").
       • one op, one id → a single spotlight; repeat the same set → sustained.
  4. Insert markers DETERMINISTICALLY right before each matched anchor. Because
     we only insert markers (never rewrite prose) and skip anchors we can't
     find verbatim, the spoken words are preserved exactly. Sub-sentence anchor
     positions give phrase-level timing (the chunker splits at every marker) —
     finer than per-sentence, without needing word-level TTS timestamps.

The output is a new narration string. Re-running TTS + the manifest composer
over it produces correctly-targeted, well-timed highlights — single, co, or
sequential. No planner / diagram-generation re-run.

The rule, in one line: *light the part(s) the current moment is explaining —
together when they're discussed together, in turn when attention moves — and
nothing when it isn't about a specific on-screen part.*
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
    # Filled by the aligner: the sentence with highlight markers inserted at
    # sub-sentence positions, or None if untouched (render falls back to `text`).
    annotated: str | None = None


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


def _find_anchor(sentence: str, anchor: str) -> int | None:
    """Index where a verbatim `anchor` substring starts in `sentence`
    (case-insensitive), or None if not found. Empty anchor → start (0)."""
    anchor = anchor.strip()
    if not anchor:
        return 0
    idx = sentence.lower().find(anchor.lower())
    return idx if idx >= 0 else None


def _render_block(tokens: list[Token]) -> str:
    """Rebuild the block: structural markers verbatim, sentences with their
    inserted highlight markers (or the raw text when untouched)."""
    parts: list[str] = []
    for t in tokens:
        if isinstance(t, _StructuralToken):
            parts.append(t.raw)
        else:
            parts.append(t.annotated if t.annotated is not None else t.text)
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
            f"{self.spans} highlight markers, {self.dropped_invalid_id} invalid-id dropped, "
            f"{self.llm_failures} llm failures"
        )


class SemanticHighlightAligner:
    """Re-decides diagram highlights against the real on-screen diagrams,
    supporting co-highlight (multiple ids at once) and sequential moves."""

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
        # UNFOCUS are ours; a stray planner POINT/MARK/etc. occasionally
        # survives an edge case — drop it so it can't render).
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
            return _render_block(tokens)  # nothing on screen to highlight

        decisions = await self._decide(sentences, diagrams_by_id, report)
        self._annotate(sentences, decisions, diagrams_by_id, report)
        return _render_block(tokens)

    def _annotate(
        self,
        sentences: list[_SentenceToken],
        decisions: dict[int, list[dict[str, Any]]],
        diagrams_by_id: dict[str, dict[str, Any]],
        report: AlignerReport,
    ) -> None:
        """Insert highlight markers into each sentence at its ops' anchors.

        `active` is the last-emitted focus set (for sustained-span collapse);
        it resets whenever the on-screen diagram changes (the frontend clears
        the spotlight on SHOW_DIAGRAM). When a previously-focused sentence is
        followed by one with no ops, we drop the spotlight with <<UNFOCUS>>.
        """
        active: tuple[str, ...] | None = None
        prev_diagram: str | None = None
        for i, s in enumerate(sentences):
            if s.diagram_id != prev_diagram:
                active = None  # new diagram (or none) clears the spotlight
            prev_diagram = s.diagram_id

            dic: dict[str, Any] = {}
            if s.diagram_id:
                dic = (diagrams_by_id.get(s.diagram_id, {}) or {}).get(
                    "dictionary"
                ) or {}

            placed: list[tuple[int, list[str], str]] = []
            for op in decisions.get(i, []):
                raw_ids = op.get("element_ids") or []
                ids: list[str] = []
                for e in raw_ids:
                    if e in dic and e not in ids:
                        ids.append(e)
                if not ids:
                    if raw_ids:
                        report.dropped_invalid_id += 1
                    continue
                pos = _find_anchor(s.text, str(op.get("anchor") or ""))
                if pos is None:
                    continue
                placed.append((pos, ids, str(op.get("treatment") or "focus")))

            placed.sort(key=lambda x: x[0])

            if not placed:
                if active is not None:
                    s.annotated = "<<UNFOCUS>> " + s.text
                    active = None
                continue

            markers: list[tuple[int, str]] = []
            for pos, ids, treatment in placed:
                key = tuple(ids)
                if key == active:
                    continue  # sustained — hold, don't re-emit a marker
                active = key
                if treatment == "trace" and len(ids) == 1:
                    markers.append((pos, f"<<TRACE:{ids[0]}>>"))
                else:
                    markers.append((pos, f"<<FOCUS:{'+'.join(ids)}>>"))
                report.spans += 1

            if not markers:
                continue
            report.sentences_highlighted += 1
            text = s.text
            for pos, marker in sorted(markers, key=lambda m: m[0], reverse=True):
                text = f"{text[:pos]}{marker} {text[pos:]}"
            s.annotated = " ".join(text.split())

    async def _decide(
        self,
        sentences: list[_SentenceToken],
        diagrams_by_id: dict[str, dict[str, Any]],
        report: AlignerReport,
    ) -> dict[int, list[dict[str, Any]]]:
        """One LLM call → ordered highlight ops per sentence index."""
        user_message = _build_user_message(sentences, diagrams_by_id)
        try:
            raw = await self._call_llm(user_message)
        except Exception as e:  # noqa: BLE001
            report.llm_failures += 1
            report.warnings.append(f"aligner LLM call failed: {e}")
            logger.warning("highlight_aligner.llm_failed", exc_info=True)
            return {}
        out: dict[int, list[dict[str, Any]]] = {}
        for item in raw.get("decisions", []):
            try:
                i = int(item["sentence_index"])
            except (KeyError, ValueError, TypeError):
                continue
            if not (0 <= i < len(sentences)):
                continue
            ids = item.get("element_ids")
            if isinstance(ids, str):
                ids = [ids]
            if not isinstance(ids, list):
                continue
            ids = [str(x) for x in ids if x]
            if not ids:
                continue
            out.setdefault(i, []).append(
                {
                    "anchor": item.get("anchor") or "",
                    "element_ids": ids,
                    "treatment": item.get("treatment") or "focus",
                }
            )
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

    lines.append("# Narration sentences (choreograph highlights across these)\n")
    for i, s in enumerate(sentences):
        tag = "" if s.diagram_id else "  (no diagram on screen — emit nothing)"
        lines.append(f"[{i}] {s.text}{tag}")
    lines.append(
        "\nReturn highlight ops via emit_highlights. For each moment the "
        "student's eye should land on a part, emit a row: the sentence_index, an "
        "`anchor` (a few words copied EXACTLY from that sentence — the highlight "
        "is placed right before it), and element_ids. Put MULTIPLE ids in one row "
        "to light parts TOGETHER when the sentence relates/compares/connects them; "
        "emit SEVERAL rows for one sentence when attention moves across parts in "
        "turn (each with its own anchor). Omit sentences that aren't about a "
        "specific on-screen part. Every id MUST belong to that sentence's "
        "on-screen diagram."
    )
    return "\n".join(lines)


_ALIGN_TOOL = {
    "name": "emit_highlights",
    "description": (
        "Emit ordered highlight ops. Multiple ids in one row = co-highlight "
        "(parts lit together for a relationship). Multiple rows for one "
        "sentence_index = attention moving across parts in sequence."
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
                        "anchor": {
                            "type": "string",
                            "description": (
                                "A SHORT substring copied EXACTLY (verbatim) from "
                                "the sentence, marking where attention should land. "
                                "The marker is inserted right before it."
                            ),
                        },
                        "element_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "description": (
                                "One id = single spotlight. Multiple ids = "
                                "co-highlight (light them together)."
                            ),
                        },
                        "treatment": {
                            "type": "string",
                            "enum": ["focus", "trace"],
                            "description": (
                                "focus = spotlight; trace = draw along a line/curve "
                                "being followed (single id only)."
                            ),
                        },
                    },
                    "required": ["sentence_index", "anchor", "element_ids"],
                },
            }
        },
        "required": ["decisions"],
    },
}
