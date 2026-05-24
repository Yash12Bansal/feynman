"""DiagramQA (Phase 4c) — vision-loop scoring + graceful failure tests."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from lecture_pipeline_v2.curriculum.enrichment.diagram_qa import DiagramQA, QAResult
from lecture_pipeline_v2.curriculum.models import Diagram, DiagramRenderer


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[_FakeTextBlock]


class _FakeMessages:
    """Mimics anthropic.AsyncAnthropic.messages.create."""

    def __init__(self, response: _FakeMessage | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def create(self, **kwargs: object) -> _FakeMessage:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


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


def _install_fake_client(
    qa: DiagramQA, response: _FakeMessage | Exception
) -> _FakeMessages:
    fake = _FakeMessages(response)
    qa.client.messages = fake  # type: ignore[assignment]
    return fake


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
    qa = DiagramQA(api_key="test", min_score=3)
    # Force PNG generation to succeed regardless of cairosvg availability.
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"\x89PNG\r\n\x1a\nfake")
    _install_fake_client(
        qa,
        _FakeMessage(
            content=[
                _FakeTextBlock(
                    text=json.dumps(
                        {"score": 4, "passed": True, "issue": "", "suggestion": ""},
                    )
                ),
            ]
        ),
    )

    result = await qa.verify(_make_diagram(), "right triangle claim")
    assert result.passed is True
    assert result.score == 4


@pytest.mark.asyncio
async def test_low_score_returns_suggestion(monkeypatch: pytest.MonkeyPatch) -> None:
    qa = DiagramQA(api_key="test", min_score=3)
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"\x89PNGfake")
    _install_fake_client(
        qa,
        _FakeMessage(
            content=[
                _FakeTextBlock(
                    text=json.dumps(
                        {
                            "score": 2,
                            "passed": False,
                            "issue": "angle is wrong",
                            "suggestion": "rotate the angle marker 90 degrees",
                        }
                    )
                ),
            ]
        ),
    )

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
    qa = DiagramQA(api_key="test")

    def boom(_d: Diagram) -> bytes:
        raise RuntimeError("svg rendering exploded")

    monkeypatch.setattr(qa, "_render_to_png", boom)
    # No need to install fake client — vision call should never happen.

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "render failed" in result.issue
    assert "svg rendering exploded" in result.issue


@pytest.mark.asyncio
async def test_cairosvg_missing_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    qa = DiagramQA(api_key="test")
    monkeypatch.setattr(qa, "_render_to_png", lambda d: None)

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "cairosvg" in result.issue


@pytest.mark.asyncio
async def test_vision_call_failure_returns_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qa = DiagramQA(api_key="test")
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")
    _install_fake_client(qa, RuntimeError("anthropic 503"))

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "vision call failed" in result.issue
    assert "anthropic 503" in result.issue


@pytest.mark.asyncio
async def test_parse_failure_returns_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    qa = DiagramQA(api_key="test")
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")
    _install_fake_client(
        qa,
        _FakeMessage(
            content=[
                _FakeTextBlock(text="not json at all { broken"),
            ]
        ),
    )

    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "parse failed" in result.issue


@pytest.mark.asyncio
async def test_response_with_markdown_fence_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qa = DiagramQA(api_key="test", min_score=3)
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")
    fenced = (
        "```json\n"
        + json.dumps({"score": 5, "passed": True, "issue": "", "suggestion": ""})
        + "\n```"
    )
    _install_fake_client(qa, _FakeMessage(content=[_FakeTextBlock(text=fenced)]))
    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert result.score == 5


@pytest.mark.asyncio
async def test_no_text_block_in_response(monkeypatch: pytest.MonkeyPatch) -> None:
    qa = DiagramQA(api_key="test")
    monkeypatch.setattr(qa, "_render_to_png", lambda d: b"PNG")
    _install_fake_client(qa, _FakeMessage(content=[]))
    result = await qa.verify(_make_diagram(), "claim")
    assert result.passed is True
    assert "no text in response" in result.issue
