"""DiagramFitMatcher — Phase 4 two-stage diagram retrieval.

For each beat with `target_diagram_id=None`, we (1) score every chapter
diagram lexically + structurally (no LLM, deterministic), then (2) ask
Claude Haiku to verify the top-K=3 candidates per beat. The first
candidate that the verifier accepts with confidence ≥ 0.7 wins. If none
pass, `target_diagram_id` stays None — Feynman narrates without showing
a new diagram. No forced reuse.
"""

from __future__ import annotations

import asyncio
import json
import math
import re

import anthropic
import structlog
from pydantic import ValidationError

from feynman.agent.doubt_resolution.doubt_classifier import DoubtClassification
from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    DiagramData,
    FitVerdict,
    ResolutionBeat,
    ResolutionPlan,
)
from feynman.agent.doubt_resolution.prompts import MATCHER_SYSTEM
from feynman.config import settings

logger = structlog.get_logger()

_MODEL = "claude-haiku-4-5-20251001"
_TOOL_NAME = "emit_fit_verdict"
_TOOL_DESCRIPTION = "Emit a strict FitVerdict for the (diagram, doubt) pair."
_MAX_TOKENS = 512
_FIT_CONFIDENCE_THRESHOLD = 0.7
_TOP_K = 3
_STAGE1_WEIGHTS = (0.55, 0.35, 0.10)  # text_sim, topic_overlap, recency_penalty

# Tiny stopword list — for the chapter-local corpora we work with (5-10
# diagrams), this is more than enough signal-cleanup.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "you",
        "your",
        "i",
        "we",
        "they",
        "them",
        "what",
        "when",
        "where",
        "which",
        "why",
        "how",
        "do",
        "does",
        "did",
        "so",
        "but",
        "if",
        "then",
        "there",
        "here",
    ]
)


# ── Stage 1: deterministic lexical/structural scoring ──────────────────────


def _tokenize(text: str) -> list[str]:
    """Lowercase + strip punctuation + drop stopwords."""
    if not text:
        return []
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]*", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _diagram_text_surface(diagram: DiagramData) -> str:
    """Concatenate every searchable string on a Diagram."""
    parts: list[str] = [diagram.description or ""]
    for entry in diagram.dictionary.values():
        if not isinstance(entry, dict):
            continue
        for key in ("role", "semantic"):
            v = entry.get(key)
            if isinstance(v, str) and v:
                parts.append(v)
    return " ".join(parts)


def _compute_idf(corpus_tokens: list[list[str]]) -> dict[str, float]:
    """IDF per token across the chapter's diagram corpus."""
    n_docs = max(1, len(corpus_tokens))
    df: dict[str, int] = {}
    for tokens in corpus_tokens:
        for tok in set(tokens):
            df[tok] = df.get(tok, 0) + 1
    return {tok: math.log((n_docs + 1) / (count + 1)) + 1 for tok, count in df.items()}


def _tfidf_vec(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}
    tf: dict[str, int] = {}
    for tok in tokens:
        tf[tok] = tf.get(tok, 0) + 1
    return {tok: count * idf.get(tok, 0.0) for tok, count in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0.0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _stage1_scores(
    *,
    doubt_text: str,
    beat: ResolutionBeat,
    chapter_context: ChapterContext,
    classification: DoubtClassification,
    current_topic_id: str | None,
    shown_diagram_ids: set[str],
) -> list[tuple[str, float]]:
    """Score every diagram for this beat. Returns sorted (diagram_id, score)."""
    diagrams = list(chapter_context.diagrams.values())
    if not diagrams:
        return []

    corpus_tokens = [_tokenize(_diagram_text_surface(d)) for d in diagrams]
    idf = _compute_idf(corpus_tokens)
    query_tokens = _tokenize(f"{doubt_text} {beat.visual_intent_description}")
    q_vec = _tfidf_vec(query_tokens, idf)

    topic_set = {tid for tid in [current_topic_id, *classification.related_concept_ids] if tid}

    w_text, w_topic, w_recency = _STAGE1_WEIGHTS
    scores: list[tuple[str, float]] = []
    for diagram, tokens in zip(diagrams, corpus_tokens, strict=False):
        d_vec = _tfidf_vec(tokens, idf)
        text_sim = _cosine(q_vec, d_vec)
        overlap = len(set(diagram.linked_topic_ids) & topic_set)
        # Normalise topic overlap to [0, 1] by capping at 3.
        topic_score = min(overlap, 3) / 3.0
        recency_penalty = 1.0 if diagram.diagram_id in shown_diagram_ids else 0.0
        score = w_text * text_sim + w_topic * topic_score - w_recency * recency_penalty
        scores.append((diagram.diagram_id, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


# ── Stage 2: Haiku verifier ────────────────────────────────────────────────


async def _verify_fit(
    *,
    doubt_text: str,
    beat: ResolutionBeat,
    diagram: DiagramData,
) -> FitVerdict | None:
    """One Haiku call. Returns None on a non-tool response or error."""
    diagram_payload = {
        "diagram_id": diagram.diagram_id,
        "description": diagram.description,
        "elements": [
            {
                "role": (e or {}).get("role"),
                "semantic": (e or {}).get("semantic"),
            }
            for e in diagram.dictionary.values()
            if isinstance(e, dict)
        ][:20],
    }
    user_message = (
        f"STUDENT DOUBT:\n{doubt_text}\n\n"
        f"BEAT VISUAL INTENT:\n{beat.visual_intent_description}\n\n"
        f"CANDIDATE DIAGRAM:\n{json.dumps(diagram_payload, indent=2)}\n\n"
        "Emit FitVerdict via `emit_fit_verdict`."
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "")
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=MATCHER_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": _TOOL_DESCRIPTION,
                    "input_schema": FitVerdict.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
    except Exception as exc:
        logger.warning(
            "diagram_fit_matcher.haiku_error",
            diagram_id=diagram.diagram_id,
            error=str(exc),
        )
        return None

    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == _TOOL_NAME
        ):
            payload = block.input
            if not isinstance(payload, dict):
                return None
            try:
                return FitVerdict.model_validate(payload)
            except ValidationError as exc:
                logger.warning(
                    "diagram_fit_matcher.invalid_verdict",
                    diagram_id=diagram.diagram_id,
                    error=str(exc),
                )
                return None
    return None


# ── Public entry point ─────────────────────────────────────────────────────


async def match_diagrams_for_plan(
    *,
    plan: ResolutionPlan,
    chapter_context: ChapterContext,
    doubt_text: str,
    classification: DoubtClassification,
    current_topic_id: str | None = None,
    shown_diagram_ids: set[str] | None = None,
    skip_stage2: bool = False,
) -> None:
    """For each beat with no diagram yet, pick the best fit (or leave None).

    Mutates `plan.beats[*].target_diagram_id` in place.

    `skip_stage2=True` is the latency-budget escape hatch (used in Phase 6
    when classification is `local_clarification` and we want to keep
    time-to-first-voice under the cap).
    """
    shown_ids = shown_diagram_ids or set()
    if not chapter_context.diagrams:
        return

    async def _match_one(beat: ResolutionBeat) -> None:
        if beat.target_diagram_id is not None:
            return
        ranked = _stage1_scores(
            doubt_text=doubt_text,
            beat=beat,
            chapter_context=chapter_context,
            classification=classification,
            current_topic_id=current_topic_id,
            shown_diagram_ids=shown_ids,
        )
        top = ranked[:_TOP_K]
        if not top:
            return

        if skip_stage2:
            # Stage-1-only: accept the top candidate if it cleared a
            # reasonable score floor.
            best_id, best_score = top[0]
            if best_score >= 0.15:
                beat.target_diagram_id = best_id
            return

        for diagram_id, _score in top:
            diagram = chapter_context.diagrams[diagram_id]
            verdict = await _verify_fit(
                doubt_text=doubt_text,
                beat=beat,
                diagram=diagram,
            )
            if (
                verdict is not None
                and verdict.fits
                and verdict.confidence >= _FIT_CONFIDENCE_THRESHOLD
            ):
                beat.target_diagram_id = diagram_id
                logger.info(
                    "diagram_fit_matcher.match",
                    diagram_id=diagram_id,
                    confidence=verdict.confidence,
                )
                return

        logger.info(
            "diagram_fit_matcher.no_match",
            candidates=[d for d, _ in top],
        )

    await asyncio.gather(*(_match_one(b) for b in plan.beats))
