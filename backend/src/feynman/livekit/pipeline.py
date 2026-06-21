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
from livekit.plugins import anthropic, cartesia, deepgram, elevenlabs, openai, silero

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
    provider = settings.tts_provider.lower()

    if provider == "cartesia" and settings.cartesia_api_key:
        model = settings.tts_model
        if model == "" or not model:
            model = "sonic-3"
        voice = settings.tts_voice or "91925fe5-42ee-4ebe-96c1-c84b12a85a32"
        logger.info("pipeline.tts", provider="cartesia", model=model, voice=voice)
        return cartesia.TTS(
            model=model,
            voice=voice,
            language="en",
            api_key=settings.cartesia_api_key,
        )

    elif provider == "elevenlabs" and settings.elevenlabs_api_key:
        model = settings.tts_model
        if model == "" or not model:
            model = "eleven_flash_v2_5"
        kwargs: dict = {
            "model": model,
            "api_key": settings.elevenlabs_api_key,
        }
        if settings.tts_voice:
            kwargs["voice"] = settings.tts_voice
        logger.info("pipeline.tts", provider="elevenlabs", model=model, voice=settings.tts_voice or "default")
        return elevenlabs.TTS(**kwargs)

    # Fallback to OpenAI
    model = settings.tts_model
    if model in ("sonic-3.5", "eleven_flash_v2_5") or not model:
        model = "gpt-4o-mini-tts"
    voice = settings.tts_voice or "ash"
    logger.info("pipeline.tts", provider="openai", model=model, voice=voice)
    kwargs: dict = {"model": model, "voice": voice}
    if api_key := _key_or_none(settings.openai_api_key):
        kwargs["api_key"] = api_key
    return openai.TTS(**kwargs)


def create_vad() -> vad.VAD:
    logger.info("pipeline.vad", provider="silero")
    return silero.VAD.load()
