"""DiagramQA (Phase 4c) — vision-loop scoring + graceful failure tests.

Exercises the provider-injection boundary: a fake vision provider supplies the
model's text response (or raises), so these tests are provider-agnostic (the
same behaviour holds whether the real provider is claude / gpt-4o / gemini).
"""

from __future__ import annotations

import json

import pytest

from lecture_pipeline_v2.curriculum.enrichment.diagram_qa import DiagramQA, QAResult
from lecture_pipeline_v2.curriculum.models import Diagram, DiagramRenderer
from lecture_pipeline_v2.llm.base import LLMResponse, ProviderCapabilityError


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeVisionProvider:
    """Provider double — `agenerate_vision` returns canned text or raises."""

    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def agenerate_vision(
        self,
        system_prompt: str,
        user_text: str,
        image_png: bytes,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "user_text": user_text,
                "n_bytes": len(image_png),
                "max_tokens": max_tokens,
            }
        )
        if isinstance(self.result, Exception):
            raise self.result
        return LLMResponse(content=self.result, model="fake", usage=None)


def _make_diagram(diagram_id: str = "d1", desc: str = "right triangle") -> Diagram:
    return Diagram(
        diagram_id=diagram_id,
        renderer=DiagramRenderer.SVG,
        render_data={
            "width": 200,
            "height": 200,
            "elements": [
                {"type": "svg_line", "id": "l", "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            ],
        },
        description=desc,
        linked_topic_ids=["t1"],
        linked_beat_id="t1_b3",
    )


def _qa(
    result: str | Exception, *, min_score: int = 3
) -> tuple[DiagramQA, _FakeVisionProvider]:
    provider = _FakeVisionProvider(result)
    return DiagramQA(provider=provider, min_score=min_score), provider


# ---------------------------------------------------------------------------
# Result-shape tests
# ---------------------------------------------------------------------------


def test_qaresult_from_dict() -> None:
    r = QAResult.from_dict({"score": 4, "passed": True, "issue": "", "suggestion": ""})
    assert r.score == 4
    assert r.passed is True


def test_qaresult_skipped_passes_through() -> None:
    r = QAResult.skipped("cairosvg missing")
    assert r.passed is True  # skip is permissive
    assert r.score == 3
    assert r.issue == "cairosvg missing"


# ---------------------------------------------------------------------------
# verify() — green path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_score_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    qa, _ = _qa(
        json.dumps({"score": 4, "passed": True, "issue": "", "suggestion": ""}),
        min_score=3,
    )
    # Force PNG generation to succeed regardless of cairosvg availability.
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"\x89PNG\r\n\x1a\nfake")

    result = await qa.verify(_make_diagram(), "right triangle claim")
    assert result.passed is True
    assert result.score == 4


@pytest.mark.asyncio
async def test_low_score_returns_suggestion(monkeypatch: pytest.MonkeyPatch) -> None:
    qa, _ = _qa(
        json.dumps(
            {
                "score": 2,
                "passed": False,
                "issue": "angle is wrong",
                "suggestion": "rotate the angle marker 90 degrees",
            }
        ),
        min_score=3,
    )
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"\x89PNGfake")

    result = await qa.verify(_make_diagram(), "right triangle claim")
    assert result.passed is False
    assert result.score == 2
    assert "angle" in result.issue
    assert "rotate" in result.suggestion


# ---------------------------------------------------------------------------
# verify() — graceful skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_failure_returns_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    qa, provider = _qa(json.dumps({"score": 5, "passed": True}))

    def boom(_d: Diagram) -> bytes:
        raise RuntimeError("svg rendering exploded")

    monkeypatch.setattr(qa, "_render_to_png", boom)

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "render failed" in result.issue
    assert "svg rendering exploded" in result.issue
    # The vision provider should never have been called.
    assert provider.calls == []


@pytest.mark.asyncio
async def test_cairosvg_missing_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    qa, provider = _qa(json.dumps({"score": 5, "passed": True}))
    monkeypatch.setattr(qa, "_render_to_png", lambda d: None)

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "cairosvg" in result.issue
    assert provider.calls == []


@pytest.mark.asyncio
async def test_vision_call_failure_returns_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qa, _ = _qa(RuntimeError("provider 503"))
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "vision call failed" in result.issue
    assert "provider 503" in result.issue


@pytest.mark.asyncio
async def test_vision_unsupported_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """A text-only provider raises ProviderCapabilityError → graceful skip."""
    qa, _ = _qa(ProviderCapabilityError("no image input"))
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "vision unsupported" in result.issue


@pytest.mark.asyncio
async def test_parse_failure_returns_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    qa, _ = _qa("not json at all { broken")
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "parse failed" in result.issue


@pytest.mark.asyncio
async def test_response_with_markdown_fence_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fenced = (
        "```json\n"
        + json.dumps({"score": 5, "passed": True, "issue": "", "suggestion": ""})
        + "\n```"
    )
    qa, _ = _qa(fenced, min_score=3)
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert result.score == 5


@pytest.mark.asyncio
async def test_empty_response_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    qa, _ = _qa("")
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "no text in response" in result.issue
