"""Request-shaping tests for the async provider surface.

We inject fake async clients (no network) and assert each provider builds the
correct wire format for tool-use and vision, and parses the response back into
the common contract. Also covers the base-class fallbacks (JSON-emulated
tool-use + vision-unsupported) used by text-only providers.
"""

from __future__ import annotations

import types

import pytest

from lecture_pipeline_v2.config import LLMConfig
from lecture_pipeline_v2.llm.anthropic_provider import AnthropicProvider
from lecture_pipeline_v2.llm.base import (
    LLMProvider,
    LLMResponse,
    ProviderCapabilityError,
)
from lecture_pipeline_v2.llm.openai_provider import OpenAIProvider


# ── Anthropic fakes ────────────────────────────────────────────────────────


class _ABlock:
    def __init__(self, type_: str, **kw) -> None:
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _AMsg:
    def __init__(self, content: list) -> None:
        self.content = content
        self.model = "claude-fake"
        self.usage = types.SimpleNamespace(input_tokens=3, output_tokens=7)


class _AMessages:
    def __init__(self, response: _AMsg) -> None:
        self.response = response
        self.kwargs: dict | None = None

    async def create(self, **kwargs) -> _AMsg:
        self.kwargs = kwargs
        return self.response


class _AClient:
    def __init__(self, response: _AMsg) -> None:
        self.messages = _AMessages(response)


def _anthropic(response: _AMsg) -> tuple[AnthropicProvider, _AClient]:
    prov = AnthropicProvider(
        LLMConfig(provider="anthropic", model="claude-x", api_key="k", max_tokens=999)
    )
    fake = _AClient(response)
    prov._aclient = fake  # type: ignore[assignment]
    return prov, fake


@pytest.mark.asyncio
async def test_anthropic_tool_use_shape_and_parse() -> None:
    prov, fake = _anthropic(_AMsg([_ABlock("tool_use", name="emit", input={"a": 1})]))
    out = await prov.agenerate_tool_use(
        "sys",
        "usr",
        tool_name="emit",
        tool_description="desc",
        input_schema={"type": "object"},
        max_tokens=50,
    )
    assert out == {"a": 1}
    kw = fake.messages.kwargs
    assert kw["tools"][0]["name"] == "emit"
    assert kw["tools"][0]["input_schema"] == {"type": "object"}
    assert kw["tool_choice"] == {"type": "tool", "name": "emit"}
    assert kw["max_tokens"] == 50  # per-call override beats config default


@pytest.mark.asyncio
async def test_anthropic_tool_use_returns_none_without_block() -> None:
    prov, _ = _anthropic(_AMsg([_ABlock("text", text="no tool here")]))
    out = await prov.agenerate_tool_use(
        "s", "u", tool_name="emit", tool_description="d", input_schema={}
    )
    assert out is None


@pytest.mark.asyncio
async def test_anthropic_vision_attaches_base64_image() -> None:
    prov, fake = _anthropic(_AMsg([_ABlock("text", text="looks good")]))
    resp = await prov.agenerate_vision("sys", "describe", b"PNGBYTES", max_tokens=64)
    assert resp.content == "looks good"
    content = fake.messages.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[1] == {"type": "text", "text": "describe"}


# ── OpenAI fakes ───────────────────────────────────────────────────────────


class _OFunc:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _OToolCall:
    def __init__(self, name: str, arguments: str) -> None:
        self.function = _OFunc(name, arguments)


class _OMessage:
    def __init__(self, content=None, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _OChoice:
    def __init__(self, message: _OMessage) -> None:
        self.message = message


class _OCompletion:
    def __init__(self, message: _OMessage) -> None:
        self.choices = [_OChoice(message)]
        self.model = "gpt-fake"
        self.usage = None


class _OCompletions:
    def __init__(self, response: _OCompletion) -> None:
        self.response = response
        self.kwargs: dict | None = None

    async def create(self, **kwargs) -> _OCompletion:
        self.kwargs = kwargs
        return self.response


class _OClient:
    def __init__(self, response: _OCompletion) -> None:
        self.chat = types.SimpleNamespace(completions=_OCompletions(response))


def _openai(response: _OCompletion) -> tuple[OpenAIProvider, _OClient]:
    prov = OpenAIProvider(
        LLMConfig(provider="openai", model="gpt-x", api_key="k", max_tokens=999)
    )
    fake = _OClient(response)
    prov._aclient = fake  # type: ignore[assignment]
    return prov, fake


@pytest.mark.asyncio
async def test_openai_tool_use_function_shape_and_parse() -> None:
    prov, fake = _openai(
        _OCompletion(_OMessage(tool_calls=[_OToolCall("emit", '{"a": 1}')]))
    )
    out = await prov.agenerate_tool_use(
        "sys",
        "usr",
        tool_name="emit",
        tool_description="desc",
        input_schema={"type": "object"},
    )
    assert out == {"a": 1}
    kw = fake.chat.completions.kwargs
    assert kw["tools"][0]["type"] == "function"
    assert kw["tools"][0]["function"]["name"] == "emit"
    assert kw["tools"][0]["function"]["parameters"] == {"type": "object"}
    assert kw["tool_choice"] == {"type": "function", "function": {"name": "emit"}}


@pytest.mark.asyncio
async def test_openai_tool_use_bad_json_returns_none() -> None:
    prov, _ = _openai(
        _OCompletion(_OMessage(tool_calls=[_OToolCall("emit", "not json")]))
    )
    out = await prov.agenerate_tool_use(
        "s", "u", tool_name="emit", tool_description="d", input_schema={}
    )
    assert out is None


@pytest.mark.asyncio
async def test_openai_vision_uses_image_url_data_uri() -> None:
    prov, fake = _openai(_OCompletion(_OMessage(content="great")))
    resp = await prov.agenerate_vision("sys", "describe", b"PNGBYTES")
    assert resp.content == "great"
    content = fake.chat.completions.kwargs["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


# ── base-class fallbacks (text-only providers, e.g. ollama judges) ─────────


class _SyncOnlyProvider(LLMProvider):
    """A provider that only implements the sync surface — exercises the base
    class's async fallbacks."""

    def __init__(self, json_payload: str) -> None:
        super().__init__(LLMConfig(provider="ollama", model="q"))
        self._json = json_payload

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return LLMResponse(content="plain text", model="q")

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return LLMResponse(content=self._json, model="q")


@pytest.mark.asyncio
async def test_base_tool_use_emulates_via_json_mode() -> None:
    prov = _SyncOnlyProvider('{"k": 5}')
    out = await prov.agenerate_tool_use(
        "sys",
        "usr",
        tool_name="t",
        tool_description="d",
        input_schema={"type": "object"},
    )
    assert out == {"k": 5}


@pytest.mark.asyncio
async def test_base_tool_use_returns_none_on_bad_json() -> None:
    prov = _SyncOnlyProvider("definitely not json")
    out = await prov.agenerate_tool_use(
        "s", "u", tool_name="t", tool_description="d", input_schema={}
    )
    assert out is None


@pytest.mark.asyncio
async def test_base_text_fallback_delegates_to_sync() -> None:
    prov = _SyncOnlyProvider("{}")
    resp = await prov.agenerate_text("s", "u")
    assert resp.content == "plain text"


@pytest.mark.asyncio
async def test_base_vision_raises_capability_error() -> None:
    prov = _SyncOnlyProvider("{}")
    with pytest.raises(ProviderCapabilityError):
        await prov.agenerate_vision("s", "u", b"PNG")
