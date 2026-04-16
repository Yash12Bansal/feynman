"""Unit tests for the curriculum pipeline orchestrator."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lecture_pipeline.config import PipelineConfig
from lecture_pipeline.curriculum.anchors.models import ExtractionAnchors, SectionAnchor
from lecture_pipeline.curriculum.merge import MergeReport
from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    ChapterSummary,
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.validation.models import ValidationReport
from lecture_pipeline.curriculum.validation.semantic import SemanticValidationReport
from lecture_pipeline.pdf.parser import PageContent, PDFContent
from lecture_pipeline.pdf.toc import Chapter
from lecture_pipeline.pipeline import (
    ChapterPipelineResult,
    CurriculumPipeline,
    PipelineReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="Test Book",
        chapter_title="Ch1",
        page_range="1-10",
        extractor_model="mock",
    )


def _node(uid: str, topic: str = "Test Concept") -> ExtractionNode:
    return ExtractionNode(
        uid=uid,
        topic_name=topic,
        concept_type=ConceptType.DEFINITION,
        resolution_level=ResolutionLevel.CONCEPT,
        summary="A test concept.",
        page_start=1,
        page_end=5,
        chapter_order=1,
        within_chapter_order=1,
    )


def _extraction(
    nodes: list[ExtractionNode] | None = None,
    rels: list[ExtractionRelationship] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics",
        textbook_title="Test Book",
        scope="chapter",
        source=_source(),
        nodes=nodes or [_node("n1"), _node("n2", "Concept B")],
        relationships=rels or [],
    )


def _pdf_content(text: str = "This is chapter text about physics.") -> PDFContent:
    return PDFContent(
        pages=[PageContent(page_number=1, text=text)],
        toc_raw=[(1, "Chapter 1", 1)],
        total_pages=1,
        metadata={"title": "Test Book"},
    )


def _chapter() -> Chapter:
    return Chapter(title="Test Chapter", level=1, start_page=1, end_page=1)


def _skeleton() -> BookSkeleton:
    return BookSkeleton(
        textbook_title="Test Book",
        subject="physics",
        total_chapters=1,
        total_pages=10,
        subject_overview="A physics textbook.",
        chapters=[
            ChapterSummary(
                chapter_index=1,
                title="Test Chapter",
                page_start=1,
                page_end=10,
                summary="A test chapter.",
                key_concepts=["concept"],
            )
        ],
    )


def _anchors() -> ExtractionAnchors:
    return ExtractionAnchors(
        sections=[],
        figure_refs=[],
        equation_refs=[],
        example_refs=[],
        total_pages=10,
    )


def _validation_report() -> ValidationReport:
    report = ValidationReport()
    return report


# ---------------------------------------------------------------------------
# Tests — PipelineReport
# ---------------------------------------------------------------------------


class TestPipelineReport:
    def test_summary_basic(self):
        report = PipelineReport(
            pdf_path="test.pdf",
            subject="physics",
            total_chapters=3,
            chapters_succeeded=2,
            chapters_failed=1,
            total_elapsed_seconds=10.5,
        )
        s = report.summary()
        assert "test.pdf" in s
        assert "physics" in s
        assert "2/3 succeeded" in s
        assert "1 failed" in s
        assert "10.5s" in s

    def test_summary_no_failures(self):
        report = PipelineReport(
            pdf_path="test.pdf",
            subject="physics",
            total_chapters=2,
            chapters_succeeded=2,
            chapters_failed=0,
            total_elapsed_seconds=5.0,
        )
        s = report.summary()
        assert "2/2 succeeded" in s
        assert "failed" not in s

    def test_summary_with_unified(self):
        report = PipelineReport(
            pdf_path="test.pdf",
            subject="physics",
            total_chapters=1,
            chapters_succeeded=1,
            chapters_failed=0,
            unified_extraction=_extraction(),
            total_elapsed_seconds=1.0,
        )
        s = report.summary()
        assert "2 nodes" in s


# ---------------------------------------------------------------------------
# Tests — ChapterPipelineResult
# ---------------------------------------------------------------------------


class TestChapterPipelineResult:
    def test_success_result(self):
        result = ChapterPipelineResult(
            chapter=_chapter(),
            chapter_index=1,
            extraction=_extraction(),
            anchors=_anchors(),
            structural_report=_validation_report(),
            elapsed_seconds=2.0,
        )
        assert result.error is None
        assert result.extraction is not None
        assert len(result.extraction.nodes) == 2

    def test_error_result(self):
        result = ChapterPipelineResult(
            chapter=_chapter(),
            chapter_index=1,
            error="Something went wrong",
            elapsed_seconds=0.1,
        )
        assert result.error is not None
        assert result.extraction is None


# ---------------------------------------------------------------------------
# Tests — CurriculumPipeline
# ---------------------------------------------------------------------------


class TestProcessChapter:
    """Test _process_chapter with mocked components."""

    def _make_pipeline(self) -> CurriculumPipeline:
        """Create a pipeline with all components mocked."""
        config = PipelineConfig()
        with patch("lecture_pipeline.pipeline.create_llm_provider") as mock_factory:
            mock_factory.return_value = MagicMock()
            pipeline = CurriculumPipeline(config)

        # Mock individual components
        pipeline.anchor_extractor = MagicMock()
        pipeline.anchor_extractor.extract_for_chapter.return_value = _anchors()

        pipeline.chapter_extractor = MagicMock()
        pipeline.chapter_extractor.extract_chapter.return_value = _extraction()

        pipeline.gap_filler = MagicMock()
        pipeline.gap_filler.fill_gaps.return_value = (_extraction(), _validation_report())

        pipeline.merger = MagicMock()

        return pipeline

    @patch("lecture_pipeline.pipeline.SemanticValidator")
    def test_single_chapter_success(self, MockSV):
        mock_sv = MagicMock()
        mock_sv.validate.return_value = SemanticValidationReport()
        MockSV.return_value = mock_sv

        pipeline = self._make_pipeline()
        pdf = _pdf_content()

        result = pipeline._process_chapter(pdf, _chapter(), 1, _skeleton(), "physics")

        assert result.error is None
        assert result.extraction is not None
        assert result.anchors is not None
        assert result.structural_report is not None
        pipeline.chapter_extractor.extract_chapter.assert_called_once()
        pipeline.gap_filler.fill_gaps.assert_called_once()

    @patch("lecture_pipeline.pipeline.SemanticValidator")
    def test_chapter_failure_caught(self, MockSV):
        MockSV.return_value = MagicMock()
        pipeline = self._make_pipeline()
        pipeline.chapter_extractor.extract_chapter.side_effect = RuntimeError("LLM failed")

        pdf = _pdf_content()
        result = pipeline._process_chapter(pdf, _chapter(), 1, _skeleton(), "physics")

        assert result.error is not None
        assert result.extraction is None

    @patch("lecture_pipeline.pipeline.SemanticValidator")
    def test_chunking_triggered(self, MockSV):
        mock_sv = MagicMock()
        mock_sv.validate.return_value = SemanticValidationReport()
        MockSV.return_value = mock_sv

        pipeline = self._make_pipeline()

        # Create text > 50K chars
        big_text = "x" * 60_000
        pdf = _pdf_content(text=big_text)

        # Mock merger
        pipeline.merger.merge_chunks.return_value = (_extraction(), MergeReport())

        result = pipeline._process_chapter(pdf, _chapter(), 1, _skeleton(), "physics")

        assert result.error is None
        assert result.merge_report is not None
        pipeline.merger.merge_chunks.assert_called_once()

    @patch("lecture_pipeline.pipeline.SemanticValidator")
    def test_semantic_validation_runs(self, MockSV):
        mock_sv_instance = MagicMock()
        mock_sv_instance.validate.return_value = SemanticValidationReport()
        MockSV.return_value = mock_sv_instance

        pipeline = self._make_pipeline()
        pdf = _pdf_content()

        result = pipeline._process_chapter(pdf, _chapter(), 1, _skeleton(), "physics")

        assert result.semantic_report is not None
        mock_sv_instance.validate.assert_called_once()


@patch("lecture_pipeline.pipeline.SemanticValidator")
class TestPipelineRun:
    """Test the full async run() method."""

    def _make_pipeline(self) -> CurriculumPipeline:
        config = PipelineConfig()
        with patch("lecture_pipeline.pipeline.create_llm_provider") as mock_factory:
            mock_factory.return_value = MagicMock()
            pipeline = CurriculumPipeline(config)

        pipeline.pdf_parser = MagicMock()
        pipeline.pdf_parser.parse.return_value = _pdf_content()

        pipeline.toc_extractor = MagicMock()
        pipeline.toc_extractor.extract_chapters.return_value = [_chapter()]

        pipeline.skeleton_extractor = MagicMock()
        pipeline.skeleton_extractor.extract.return_value = _skeleton()

        pipeline.anchor_extractor = MagicMock()
        pipeline.anchor_extractor.extract_for_chapter.return_value = _anchors()

        pipeline.chapter_extractor = MagicMock()
        pipeline.chapter_extractor.extract_chapter.return_value = _extraction()

        pipeline.gap_filler = MagicMock()
        pipeline.gap_filler.fill_gaps.return_value = (_extraction(), _validation_report())

        pipeline.unifier = MagicMock()
        unified = _extraction()
        unified.scope = "book"
        pipeline.unifier.unify.return_value = (
            unified,
            MagicMock(summary=lambda: "Unified OK"),
        )

        return pipeline

    @pytest.mark.asyncio
    async def test_full_flow_skip_neo4j(self, MockSV):
        MockSV.return_value.validate.return_value = SemanticValidationReport()
        pipeline = self._make_pipeline()

        report = await pipeline.run(
            "test.pdf", "physics", skip_neo4j=True
        )

        assert report.chapters_succeeded == 1
        assert report.chapters_failed == 0
        assert report.unified_extraction is not None
        assert report.unification_report is not None
        assert report.ingestion_report is None  # skipped

    @pytest.mark.asyncio
    async def test_skips_failed_chapter(self, MockSV):
        MockSV.return_value.validate.return_value = SemanticValidationReport()
        pipeline = self._make_pipeline()

        # 3 chapters, middle one fails
        chapters = [
            Chapter(title=f"Ch{i}", level=1, start_page=i, end_page=i)
            for i in range(1, 4)
        ]
        pipeline.toc_extractor.extract_chapters.return_value = chapters

        call_count = 0

        def _failing_extract(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("LLM failed on chapter 2")
            return _extraction()

        pipeline.chapter_extractor.extract_chapter.side_effect = _failing_extract

        report = await pipeline.run(
            "test.pdf", "physics", skip_neo4j=True
        )

        assert report.total_chapters == 3
        assert report.chapters_succeeded == 2
        assert report.chapters_failed == 1
        assert report.chapter_results[1].error is not None

    @pytest.mark.asyncio
    async def test_no_chapters_detected(self, MockSV):
        MockSV.return_value.validate.return_value = SemanticValidationReport()
        pipeline = self._make_pipeline()
        pipeline.toc_extractor.extract_chapters.return_value = []

        report = await pipeline.run("test.pdf", "physics", skip_neo4j=True)
        # _parse_pdf creates a fallback "Full Document" chapter
        assert report.total_chapters == 1

    @pytest.mark.asyncio
    async def test_chapter_filter(self, MockSV):
        MockSV.return_value.validate.return_value = SemanticValidationReport()
        pipeline = self._make_pipeline()

        chapters = [
            Chapter(title=f"Ch{i}", level=1, start_page=i, end_page=i)
            for i in range(1, 6)
        ]
        pipeline.toc_extractor.extract_chapters.return_value = chapters

        report = await pipeline.run(
            "test.pdf", "physics", chapters=[2, 4], skip_neo4j=True
        )

        assert report.total_chapters == 2

    @pytest.mark.asyncio
    async def test_on_stage_callback(self, MockSV):
        MockSV.return_value.validate.return_value = SemanticValidationReport()
        pipeline = self._make_pipeline()

        stages: list[tuple[str, str]] = []

        def on_stage(stage: str, detail: str) -> None:
            stages.append((stage, detail))

        await pipeline.run(
            "test.pdf", "physics", skip_neo4j=True, on_stage=on_stage
        )

        stage_names = [s[0] for s in stages]
        assert "parse" in stage_names
        assert "skeleton" in stage_names
        assert "chapter" in stage_names
        assert "unify" in stage_names

    @pytest.mark.asyncio
    async def test_report_has_timing(self, MockSV):
        MockSV.return_value.validate.return_value = SemanticValidationReport()
        pipeline = self._make_pipeline()

        report = await pipeline.run("test.pdf", "physics", skip_neo4j=True)

        assert report.total_elapsed_seconds > 0


class TestMakeChunkPdfContent:
    def test_creates_valid_pdf_content(self):
        from lecture_pipeline.curriculum.merge.text_chunker import TextChunk

        chunk = TextChunk(
            text="Some chunk text",
            chunk_index=0,
            char_start=0,
            char_end=15,
            total_chunks=2,
        )
        chapter = Chapter(title="Ch1", level=1, start_page=5, end_page=10)

        pdf, fake_ch = CurriculumPipeline._make_chunk_pdf_content(chunk, chapter)

        assert len(pdf.pages) == 1
        assert pdf.pages[0].text == "Some chunk text"
        assert pdf.pages[0].page_number == 5
        assert fake_ch.title == "Ch1"
        assert fake_ch.start_page == 5
