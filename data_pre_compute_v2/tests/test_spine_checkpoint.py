"""Spine checkpoint round-trip and version stability."""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.ingestion.spine_checkpoint import (
    SpineCheckpoint,
    compute_spine_version,
    load_checkpoint,
    strip_variant_fields,
    write_checkpoint,
)
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    CurriculumExtractionResult,
    ExtractionSource,
)


def _minimal_extraction() -> CurriculumExtractionResult:
    ch = Chapter(
        chapter_id="chapter:physics:test",
        chapter_index=1,
        title="Test",
        summary="s",
        page_start=1,
        page_end=5,
        topic_ids=[],
        narration_text="should be stripped",
    )
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="Test Book",
        source=ExtractionSource(textbook_title="Test Book", extractor_model="test"),
        chapters=[ch],
    )


def test_strip_variant_fields_clears_chapter_artifacts(tmp_path) -> None:
    ext = _minimal_extraction()
    stripped = strip_variant_fields(ext)
    assert stripped.chapters[0].narration_text == ""
    assert stripped.chapters[0].lesson_plans == []


def test_checkpoint_round_trip(tmp_path) -> None:
    ext = strip_variant_fields(_minimal_extraction())
    ckpt = SpineCheckpoint(
        spine_version=compute_spine_version(ext),
        subject="physics",
        extraction=ext,
    )
    path = tmp_path / "spine.json"
    write_checkpoint(ckpt, path)
    loaded = load_checkpoint(path)
    assert loaded.spine_version == ckpt.spine_version
    assert loaded.extraction.subject == "physics"


def test_spine_version_stable() -> None:
    ext = strip_variant_fields(_minimal_extraction())
    assert compute_spine_version(ext) == compute_spine_version(ext)
