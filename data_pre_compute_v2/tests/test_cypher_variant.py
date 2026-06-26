"""CypherGenerator LectureVariant tests."""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.ingestion.cypher_generator import CypherGenerator
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    CurriculumExtractionResult,
    ExtractionSource,
    Manifest,
    TopicStartEvent,
)
from lecture_pipeline_v2.curriculum.variant_ids import variant_id


def _extraction_with_manifest() -> CurriculumExtractionResult:
    chapter = Chapter(
        chapter_id="chapter:finance:simple_interest",
        chapter_index=1,
        title="Simple Interest",
        summary="Intro",
        page_start=1,
        page_end=1,
        topic_ids=[],
        chapter_manifest=Manifest(
            events=[TopicStartEvent(topic_id="t1", topic_name="Intro")]
        ),
        narration_text="<<TOPIC_START:t1>>Hello.",
    )
    return CurriculumExtractionResult(
        subject="finance",
        textbook_title="Finance",
        source=ExtractionSource(textbook_title="Finance", extractor_model="test"),
        chapters=[chapter],
    )


def test_variant_ingest_emits_lecture_variant_node() -> None:
    extraction = _extraction_with_manifest()
    statements = CypherGenerator().generate(extraction, persona_id="finance_teacher")
    categories = {s.uid: s.query for s in statements}
    vid = variant_id("chapter:finance:simple_interest", "finance_teacher")
    assert vid in categories
    assert "LectureVariant" in categories[vid]
    assert "HAS_VARIANT" in " ".join(categories.values())


def test_legacy_ingest_writes_manifest_on_chapter() -> None:
    extraction = _extraction_with_manifest()
    chapter_stmt = CypherGenerator()._chapter_node(
        extraction.chapters[0], write_variant_on_chapter=True
    )
    assert "chapter_manifest" in chapter_stmt.query
    assert "chapter_manifest" in chapter_stmt.params


def test_persona_ingest_skips_manifest_on_chapter() -> None:
    extraction = _extraction_with_manifest()
    chapter_stmt = CypherGenerator()._chapter_node(
        extraction.chapters[0], write_variant_on_chapter=False
    )
    assert "chapter_manifest" not in chapter_stmt.query
