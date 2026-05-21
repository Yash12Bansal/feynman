"""Kokoro TTS provider — local synthesis on Apple Silicon (MPS) via the kokoro pip package.

Kokoro is the lightweight (~82M param) high-quality classroom-voice model.
Install via the [tts] extra: `uv pip install -e ".[tts]"`.

Output format: written by soundfile as WAV at the model's native rate (24000 Hz),
then converted to MP3/OGG via FFmpeg if a different format is requested.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import wave
from pathlib import Path

from ..config import TTSConfig
from .base import TTSProvider, TTSResult

logger = logging.getLogger(__name__)


class KokoroTTSProvider(TTSProvider):
    def __init__(self, config: TTSConfig):
        self.config = config
        self._pipeline = None  # lazy-init

    def _ensure_pipeline(self):
        if self._pipeline is None:
            try:
                from kokoro import KPipeline
            except ImportError as e:
                raise RuntimeError(
                    "Kokoro is not installed. Install with: uv pip install -e \".[tts]\""
                ) from e
            lang_code = self.config.voice[:1].lower() if self.config.voice else "a"
            self._pipeline = KPipeline(lang_code=lang_code)
        return self._pipeline

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        import soundfile as sf

        pipeline = self._ensure_pipeline()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path = output_path.with_suffix(".wav")

        chunks: list = []
        for _gs, _ps, audio in pipeline(text, voice=self.config.voice):
            chunks.append(audio)

        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for text len={len(text)}")

        import numpy as np
        combined = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        sf.write(str(wav_path), combined, self.config.sample_rate)

        duration_ms = int(len(combined) / self.config.sample_rate * 1000)

        if self.config.output_format != "wav":
            self._convert_format(wav_path, output_path, self.config.output_format)
            wav_path.unlink()
        else:
            if wav_path != output_path:
                wav_path.rename(output_path)

        return TTSResult(
            audio_path=output_path,
            duration_ms=duration_ms,
            sample_rate=self.config.sample_rate,
            format=self.config.output_format,
        )

    def synthesize_silence(self, duration_ms: int, output_path: Path) -> TTSResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path = output_path.with_suffix(".wav")

        sr = self.config.sample_rate
        n_samples = int(sr * duration_ms / 1000)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(b"\x00\x00" * n_samples)

        if self.config.output_format != "wav":
            self._convert_format(wav_path, output_path, self.config.output_format)
            wav_path.unlink()
        else:
            if wav_path != output_path:
                wav_path.rename(output_path)

        return TTSResult(
            audio_path=output_path,
            duration_ms=duration_ms,
            sample_rate=sr,
            format=self.config.output_format,
        )

    @staticmethod
    def _convert_format(src: Path, dst: Path, fmt: str) -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "ffmpeg not found on PATH. Install ffmpeg or set tts.output_format='wav'."
            )
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), str(dst)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")
