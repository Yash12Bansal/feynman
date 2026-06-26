"""Spine checkpoint — phases 1–7 output for persona variant generation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from lecture_pipeline_v2.curriculum.models import CurriculumExtractionResult


class SpineCheckpoint(BaseModel):
    """Immutable spine artifact; variants fork from this."""

    spine_version: str
    subject: str
    extraction: CurriculumExtractionResult
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


def strip_variant_fields(extraction: CurriculumExtractionResult) -> CurriculumExtractionResult:
    """Return a copy with per-variant chapter/topic fields cleared."""
    data = extraction.model_dump()
    for ch in data.get("chapters", []):
        ch["chapter_manifest"] = {"events": []}
        ch["narration_text"] = ""
        ch["lesson_plans"] = []
        ch["lesson_narrations"] = []
        ch["assembled_chapter_script"] = None
        ch["board_snapshots"] = []
        ch["pages"] = []
    for topic in data.get("topics", []):
        topic["extended_examples"] = []
    qs = data.get("quality_snapshot")
    if qs:
        qs["chapters"] = []
        qs["narration_judgements"] = []
        qs["persona_id"] = None
    return CurriculumExtractionResult.model_validate(data)


def compute_spine_version(extraction: CurriculumExtractionResult) -> str:
    """Stable hash of spine content (variant fields stripped)."""
    spine = strip_variant_fields(extraction)
    payload = spine.model_dump_json()
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def write_checkpoint(checkpoint: SpineCheckpoint, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    return out


def load_checkpoint(path: str | Path) -> SpineCheckpoint:
    return SpineCheckpoint.model_validate_json(Path(path).read_text(encoding="utf-8"))
