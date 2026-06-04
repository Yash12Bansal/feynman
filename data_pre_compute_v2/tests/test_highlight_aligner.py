"""Unit tests for the semantic highlight aligner.

Inject a fake LLM provider (canned `emit_highlights` payload) so we test the
deterministic marker-insertion logic: co-highlight (one marker, many ids),
sequential (several markers in one sentence), sustained-span collapse,
invalid-id drop, anchor-not-found skip, and prose preservation.
"""

from __future__ import annotations

import re

import pytest

from lecture_pipeline_v2.curriculum.lecture_plan.highlight_aligner import (
    AlignerReport,
    SemanticHighlightAligner,
)


class _FakeProvider:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls = 0

    async def agenerate_tool_use(self, system, user, **kwargs):  # noqa: ANN001
        self.calls += 1
        return self._payload


_DIAGRAMS = {
    "d1": {
        "title": "BJT",
        "dictionary": {
            "emitter": {"role": "emitter", "semantic": "the emitter region"},
            "base": {"role": "base", "semantic": "the base region"},
            "collector": {"role": "collector", "semantic": "the collector region"},
        },
    }
}


def _aligner(payload: dict) -> SemanticHighlightAligner:
    # config is unused when a provider is injected.
    return SemanticHighlightAligner(config=None, provider=_FakeProvider(payload))


def _strip_markers(s: str) -> str:
    return " ".join(re.sub(r"<<[^>]*>>", "", s).split())


@pytest.mark.asyncio
async def test_co_highlight_one_marker_multiple_ids() -> None:
    nar = (
        "<<TOPIC_START:t1>> <<SHOW_DIAGRAM:d1>> "
        "The current flows between the emitter and the collector."
    )
    payload = {
        "decisions": [
            {
                "sentence_index": 0,
                "anchor": "between the emitter",
                "element_ids": ["emitter", "collector"],
            }
        ]
    }
    out = await _aligner(payload).realign_chapter_narration(nar, _DIAGRAMS)
    assert "<<FOCUS:emitter+collector>>" in out
    assert "between the emitter and the collector" in _strip_markers(out)


@pytest.mark.asyncio
async def test_sequential_multiple_markers_in_one_sentence() -> None:
    nar = (
        "<<TOPIC_START:t1>> <<SHOW_DIAGRAM:d1>> "
        "The signal goes from the emitter through the base to the collector."
    )
    payload = {
        "decisions": [
            {"sentence_index": 0, "anchor": "emitter", "element_ids": ["emitter"]},
            {"sentence_index": 0, "anchor": "base", "element_ids": ["base"]},
            {"sentence_index": 0, "anchor": "collector", "element_ids": ["collector"]},
        ]
    }
    out = await _aligner(payload).realign_chapter_narration(nar, _DIAGRAMS)
    assert "<<FOCUS:emitter>>" in out
    assert "<<FOCUS:base>>" in out
    assert "<<FOCUS:collector>>" in out
    # Attention moves in spoken order.
    assert (
        out.index("<<FOCUS:emitter>>")
        < out.index("<<FOCUS:base>>")
        < out.index("<<FOCUS:collector>>")
    )


@pytest.mark.asyncio
async def test_sustained_span_not_repeated() -> None:
    nar = (
        "<<TOPIC_START:t1>> <<SHOW_DIAGRAM:d1>> "
        "The emitter injects carriers. The emitter is heavily doped."
    )
    payload = {
        "decisions": [
            {"sentence_index": 0, "anchor": "emitter", "element_ids": ["emitter"]},
            {"sentence_index": 1, "anchor": "emitter", "element_ids": ["emitter"]},
        ]
    }
    out = await _aligner(payload).realign_chapter_narration(nar, _DIAGRAMS)
    assert out.count("<<FOCUS:emitter>>") == 1


@pytest.mark.asyncio
async def test_invalid_id_dropped() -> None:
    nar = "<<TOPIC_START:t1>> <<SHOW_DIAGRAM:d1>> The mystery part does something."
    payload = {
        "decisions": [
            {
                "sentence_index": 0,
                "anchor": "mystery part",
                "element_ids": ["bogus_id"],
            }
        ]
    }
    report = AlignerReport()
    out = await _aligner(payload).realign_chapter_narration(nar, _DIAGRAMS, report)
    assert "<<FOCUS" not in out
    assert report.dropped_invalid_id == 1


@pytest.mark.asyncio
async def test_anchor_not_found_skipped() -> None:
    nar = "<<TOPIC_START:t1>> <<SHOW_DIAGRAM:d1>> The emitter injects carriers."
    payload = {
        "decisions": [
            {
                "sentence_index": 0,
                "anchor": "this phrase is absent",
                "element_ids": ["emitter"],
            }
        ]
    }
    out = await _aligner(payload).realign_chapter_narration(nar, _DIAGRAMS)
    assert "<<FOCUS" not in out


@pytest.mark.asyncio
async def test_prose_and_structural_markers_preserved() -> None:
    nar = (
        "<<TOPIC_START:t1>> <<SHOW_DIAGRAM:d1>> "
        "The emitter injects carriers into the base."
    )
    payload = {
        "decisions": [
            {"sentence_index": 0, "anchor": "emitter", "element_ids": ["emitter"]}
        ]
    }
    out = await _aligner(payload).realign_chapter_narration(nar, _DIAGRAMS)
    assert "<<SHOW_DIAGRAM:d1>>" in out
    assert "<<TOPIC_START:t1>>" in out
    assert "The emitter injects carriers into the base." in _strip_markers(out)


@pytest.mark.asyncio
async def test_no_diagram_emits_nothing() -> None:
    # No SHOW_DIAGRAM → nothing on screen → no highlights even if LLM returns some.
    nar = "<<TOPIC_START:t1>> The emitter injects carriers."
    payload = {
        "decisions": [
            {"sentence_index": 0, "anchor": "emitter", "element_ids": ["emitter"]}
        ]
    }
    out = await _aligner(payload).realign_chapter_narration(nar, _DIAGRAMS)
    assert "<<FOCUS" not in out
