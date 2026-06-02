"""Config-level tests for the single LLM switch + per-role overrides + factory."""

from __future__ import annotations

import pytest

from lecture_pipeline_v2.config import (
    LLMConfig,
    PipelineConfig,
    api_key_for_provider,
)
from lecture_pipeline_v2.llm.anthropic_provider import AnthropicProvider
from lecture_pipeline_v2.llm.factory import create_llm_provider
from lecture_pipeline_v2.llm.gemini_provider import GeminiProvider
from lecture_pipeline_v2.llm.ollama_provider import OllamaProvider
from lecture_pipeline_v2.llm.openai_provider import OpenAIProvider


# ── api_key_for_provider ──────────────────────────────────────────────────


def test_api_key_for_provider_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert api_key_for_provider("anthropic") == "a"
    assert api_key_for_provider("openai") == "o"
    assert api_key_for_provider("gemini") == "g"
    assert api_key_for_provider("ollama") is None
    assert api_key_for_provider("unknown") is None


def test_gemini_falls_back_to_google_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "from-google")
    assert api_key_for_provider("gemini") == "from-google"


# ── LLMConfig.for_override ────────────────────────────────────────────────


def test_for_override_noop_returns_self() -> None:
    base = LLMConfig(provider="anthropic", model="claude-x", api_key="k")
    assert base.for_override(None, None) is base
    # Same provider + same model is also a no-op.
    assert base.for_override("anthropic", "claude-x") is base


def test_for_override_model_only_keeps_key_and_provider() -> None:
    base = LLMConfig(provider="anthropic", model="claude-x", api_key="k")
    out = base.for_override(None, "claude-y")
    assert out is not base
    assert out.provider == "anthropic"
    assert out.model == "claude-y"
    assert out.api_key == "k"  # same provider → key preserved


def test_for_override_provider_switch_reresolves_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gkey")
    base = LLMConfig(provider="anthropic", model="claude-x", api_key="akey")
    out = base.for_override("gemini", "gemini-3")
    assert out.provider == "gemini"
    assert out.model == "gemini-3"
    assert out.api_key == "gkey"  # re-resolved for the new provider


# ── factory ───────────────────────────────────────────────────────────────


def test_factory_builds_each_provider() -> None:
    def prov(p: str, m: str):
        return create_llm_provider(LLMConfig(provider=p, model=m, api_key="k"))

    assert isinstance(prov("anthropic", "claude-x"), AnthropicProvider)
    assert isinstance(prov("openai", "gpt-x"), OpenAIProvider)
    assert isinstance(prov("ollama", "qwen"), OllamaProvider)
    # Gemini lazy-imports the SDK only on first use, so construction is safe
    # even when google-genai is not installed.
    assert isinstance(prov("gemini", "gemini-x"), GeminiProvider)


def test_factory_rejects_unknown_provider() -> None:
    cfg = LLMConfig.model_construct(provider="mystery", model="m", api_key="k")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm_provider(cfg)


# ── PipelineConfig.load fills the right key ───────────────────────────────


def test_load_fills_gemini_key_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g-secret")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("llm:\n  provider: gemini\n  model: gemini-2.5-pro\n")
    cfg = PipelineConfig.load(cfg_file)
    assert cfg.llm.provider == "gemini"
    assert cfg.llm.api_key == "g-secret"
