"""Variant fork must not parse PDF."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.ingestion.spine_checkpoint import SpineCheckpoint
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    CurriculumExtractionResult,
    ExtractionSource,
)
from lecture_pipeline_v2.pipeline import CurriculumPipelineV2


def _checkpoint() -> SpineCheckpoint:
    ch = Chapter(
        chapter_id="chapter:physics:test",
        chapter_index=1,
        title="Test",
        summary="s",
        page_start=1,
        page_end=5,
        topic_ids=[],
    )
    ext = CurriculumExtractionResult(
        subject="physics",
        textbook_title="T",
        source=ExtractionSource(textbook_title="T", extractor_model="m"),
        chapters=[ch],
    )
    return SpineCheckpoint(spine_version="abc", subject="physics", extraction=ext)


@pytest.mark.asyncio
async def test_run_variant_never_parses_pdf() -> None:
    cfg = PipelineConfig(llm=LLMConfig(api_key="k", model="m"))
    pipeline = CurriculumPipelineV2(cfg)

    with patch.object(pipeline.pdf_parser, "parse", MagicMock()) as mock_parse:
        with patch.object(
            pipeline,
            "_run_variant_phases",
            return_value=None,
        ):
            report = await pipeline.run_variant(
                _checkpoint(),
                skip_tts=True,
                skip_neo4j=True,
                skip_embeddings=True,
                skip_visuals=True,
            )
    mock_parse.assert_not_called()
    assert report.subject == "physics"
