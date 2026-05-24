"""Minimal artifact store — filesystem-backed.

Swap to S3/MinIO by changing url_prefix in config. The pipeline only
ever sees URLs, never raw paths in node properties.
"""

from __future__ import annotations

from pathlib import Path

from ...config import ArtifactsConfig


class ArtifactStore:
    def __init__(self, config: ArtifactsConfig):
        self.config = config
        self.base = Path(config.base_dir).resolve()
        self.audio_dir = self.base / config.audio_dir
        self.diagram_dir = self.base / config.diagram_dir
        self.animation_dir = self.base / config.animation_dir
        self.runs_dir = self.base / config.runs_dir
        for d in (self.audio_dir, self.diagram_dir, self.animation_dir, self.runs_dir):
            d.mkdir(parents=True, exist_ok=True)

    def url_for(self, path: Path) -> str:
        path = path.resolve()
        try:
            rel = path.relative_to(self.base)
        except ValueError:
            return f"file://{path}"
        return f"{self.config.url_prefix.rstrip('/')}/{rel.as_posix()}"

    def diagram_path(self, diagram_id: str, extension: str) -> Path:
        safe = diagram_id.replace(":", "_")
        return self.diagram_dir / f"{safe}.{extension}"
