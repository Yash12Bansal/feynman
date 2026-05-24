"""STT/LLM/TTS/VAD provider configuration with fallbacks.

Fallback chain (uses first available key):
- STT: Deepgram → OpenAI
- LLM: Anthropic Claude (always)
- TTS: Cartesia → OpenAI
- VAD: Silero (local, no key needed)

When a key is empty, we omit the api_key kwarg so the plugin can fall back
to its own env-var lookup (e.g. OPENAI_API_KEY). Passing an empty string
triggers a ValueError inside the plugin.
"""

import structlog
from livekit.agents import stt, tts, vad
from livekit.plugins import anthropic, cartesia, deepgram, openai, silero

from feynman.config import settings

logger = structlog.get_logger()


def _key_or_none(key: str) -> str | None:
    """Return the key if non-empty, else None (omitted from plugin kwargs)."""
    return key or None


def create_stt() -> stt.STT:
    if settings.deepgram_api_key:
        logger.info("pipeline.stt", provider="deepgram", model="nova-3")
        return deepgram.STT(model="nova-3", language="en", api_key=settings.deepgram_api_key)

    logger.info("pipeline.stt", provider="openai", model="gpt-4o-mini-transcribe")
    kwargs: dict = {"model": "gpt-4o-mini-transcribe", "language": "en"}
    if api_key := _key_or_none(settings.openai_api_key):
        kwargs["api_key"] = api_key
    return openai.STT(**kwargs)


def create_llm() -> anthropic.LLM:
    logger.info("pipeline.llm", provider="anthropic", model="claude-sonnet-4-20250514")
    kwargs: dict = {"model": "claude-sonnet-4-20250514"}
    if api_key := _key_or_none(settings.anthropic_api_key):
        kwargs["api_key"] = api_key
    return anthropic.LLM(**kwargs)


def create_tts() -> tts.TTS:
    if settings.cartesia_api_key:
        logger.info("pipeline.tts", provider="cartesia", model="sonic-3", voice="amit")
        return cartesia.TTS(
            model="sonic-3",
            voice="91925fe5-42ee-4ebe-96c1-c84b12a85a32",
            language="en",
            api_key=settings.cartesia_api_key,
        )

    logger.info("pipeline.tts", provider="openai", model="gpt-4o-mini-tts")
    kwargs: dict = {"model": "gpt-4o-mini-tts", "voice": "ash"}
    if api_key := _key_or_none(settings.openai_api_key):
        kwargs["api_key"] = api_key
    return openai.TTS(**kwargs)


def create_vad() -> vad.VAD:
    logger.info("pipeline.vad", provider="silero")
    return silero.VAD.load()
