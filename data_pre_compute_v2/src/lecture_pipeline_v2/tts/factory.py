"""TTS provider factory."""

from __future__ import annotations

from ..config import TTSConfig
from .base import TTSProvider


def create_tts_provider(config: TTSConfig) -> TTSProvider:
    if config.provider == "kokoro":
        from .kokoro_provider import KokoroTTSProvider
        return KokoroTTSProvider(config)
    raise ValueError(f"Unknown TTS provider: {config.provider!r}")
