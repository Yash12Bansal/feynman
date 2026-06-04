"""Tests for the real-time doubt diagram generator.

The Anthropic call is mocked (injected client); we verify prompt loading,
JSON extraction/validation, and graceful degradation.
"""

from __future__ import annotations

import json

import pytest

from feynman.agent.doubt_resolution import diagram_generator as dg


class _Block:
    def __init__(self, text: str) -> None:
        self.text = text


class _Response:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text

    async def create(self, **_kwargs):  # noqa: ANN003
        return _Response(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.messages = _FakeMessages(text)


_VALID_SPEC = {
    "title": "Relative velocity",
    "width": 800,
    "height": 600,
    "elements": [{"id": "arrow-a", "type": "svg_path", "d": "M0 0 L10 10"}],
    "dictionary": {"arrow-a": {"role": "velocity", "semantic": "the ball's velocity"}},
}


def test_canonical_design_prompt_loads_from_disk():
    # The generator must find the design-agent SYSTEM_PROMPT and it must mandate
    # a dictionary — that's what makes generated doubt diagrams annotatable.
    assert dg._SYSTEM_PROMPT is not None
    assert "dictionary" in dg._SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_generates_spec_from_plain_json():
    client = _FakeClient(json.dumps(_VALID_SPEC))
    spec = await dg.generate_doubt_diagram(brief="a velocity arrow", client=client)
    assert spec is not None
    assert spec["dictionary"]["arrow-a"]["role"] == "velocity"
    assert spec["width"] == 800


@pytest.mark.asyncio
async def test_parses_fenced_json():
    client = _FakeClient("```json\n" + json.dumps(_VALID_SPEC) + "\n```")
    spec = await dg.generate_doubt_diagram(brief="x", client=client)
    assert spec is not None and isinstance(spec["elements"], list)


@pytest.mark.asyncio
async def test_defaults_width_height_when_missing():
    minimal = {"elements": [{"id": "e1"}], "dictionary": {"e1": {"role": "r"}}}
    client = _FakeClient(json.dumps(minimal))
    spec = await dg.generate_doubt_diagram(brief="x", title="My Title", client=client)
    assert spec is not None
    assert spec["width"] == dg._DEFAULT_WIDTH
    assert spec["height"] == dg._DEFAULT_HEIGHT
    assert spec["title"] == "My Title"


@pytest.mark.asyncio
async def test_garbage_response_returns_none():
    client = _FakeClient("I cannot draw that, sorry.")
    spec = await dg.generate_doubt_diagram(brief="x", client=client)
    assert spec is None


@pytest.mark.asyncio
async def test_missing_elements_returns_none():
    client = _FakeClient(json.dumps({"dictionary": {}}))
    spec = await dg.generate_doubt_diagram(brief="x", client=client)
    assert spec is None


@pytest.mark.asyncio
async def test_empty_brief_returns_none():
    client = _FakeClient(json.dumps(_VALID_SPEC))
    assert await dg.generate_doubt_diagram(brief="   ", client=client) is None
