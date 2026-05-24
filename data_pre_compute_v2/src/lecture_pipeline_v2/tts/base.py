"""Abstract TTS provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TTSResult:
    """Result of synthesising one text fragment."""

    audio_path: Path
    duration_ms: int
    sample_rate: int
    format: str


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """Synthesise text to an audio file at output_path. Returns metadata."""

    @abstractmethod
    def synthesize_silence(self, duration_ms: int, output_path: Path) -> TTSResult:
        """Write a silent audio file of the given duration."""
