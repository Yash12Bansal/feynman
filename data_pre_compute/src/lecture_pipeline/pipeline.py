"""Curriculum graph pipeline orchestrator.

Wires together all extraction phases into one end-to-end pipeline:
PDF → skeleton → anchors → chapters → validate → gap-fill → merge → unify → ingest.

Usage (Python API):
    config = PipelineConfig.load("config.yaml")
    pipeline = CurriculumPipeline(config)
    report = await pipeline.run("textbook.pdf", subject="physics")

Usage (CLI):
    lecture-pipeline ingest-book textbook.pdf --subject physics
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .config import PipelineConfig
from .curriculum.anchors import DeterministicAnchorExtractor
from .curriculum.anchors.models import ExtractionAnchors
from .curriculum.chapter_extractor import ChapterExtractor
from .curriculum.ingestion import CypherGenerator, EmbeddingGenerator, Neo4jWriter
from .curriculum.merge import ExtractionMerger, MergeReport
from .curriculum.merge.text_chunker import TextChunk, chunk_text, needs_chunking
from .curriculum.models import BookSkeleton, CurriculumExtractionResult
from .curriculum.salience import SalienceService
from .curriculum.skeleton_extractor import SkeletonExtractor
from .curriculum.unification import BookUnifier, UnificationReport
from .curriculum.visuals import Neo4jVisualWriter, VisualGenerator, VisualGenerationReport
from .curriculum.visuals.neo4j_visual_writer import VisualWriteReport
from .curriculum.validation import (
    GapFiller,
    SemanticValidator,
    StructuralValidator,
    ValidationReport,
)
from .curriculum.validation.semantic import SemanticValidationReport
from .llm.factory import create_llm_provider
from .pdf.parser import PDFContent, PageContent, PDFParser
from .pdf.toc import Chapter, TOCExtractor

if TYPE_CHECKING:
    from .curriculum.ingestion.embedding_generator import EmbeddingReport
    from .curriculum.ingestion.neo4j_writer import IngestionReport
    from .curriculum.salience.salience_service import SalienceReport

logger = logging.getLogger(__name__)

StageCallback = Callable[[str, str], None]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ChapterPipelineResult:
    """Result of processing a single chapter through the pipeline."""

    chapter: Chapter
    chapter_index: int
    extraction: CurriculumExtractionResult | None = None
    anchors: ExtractionAnchors | None = None
    structural_report: ValidationReport | None = None
    semantic_report: SemanticValidationReport | None = None
    merge_report: MergeReport | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class PipelineReport:
    """Full pipeline result across all stages."""

    pdf_path: str = ""
    subject: str = ""
    total_chapters: int = 0
    chapters_succeeded: int = 0
    chapters_failed: int = 0
    chapter_results: list[ChapterPipelineResult] = field(default_factory=list)
    skeleton: BookSkeleton | None = None
    unified_extraction: CurriculumExtractionResult | None = None
    unification_report: UnificationReport | None = None
    ingestion_report: IngestionReport | None = None
    embedding_report: EmbeddingReport | None = None
    salience_report: SalienceReport | None = None
    visual_generation_report: VisualGenerationReport | None = None
    visual_write_report: VisualWriteReport | None = None
    total_elapsed_seconds: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Pipeline complete — {self.pdf_path}",
            f"  Subject: {self.subject}",
            f"  Chapters: {self.chapters_succeeded}/{self.total_chapters} succeeded"
            + (f" ({self.chapters_failed} failed)" if self.chapters_failed else ""),
        ]
        if self.unified_extraction:
            lines.append(
                f"  Unified graph: {len(self.unified_extraction.nodes)} nodes, "
                f"{len(self.unified_extraction.relationships)} relationships"
            )
        if self.unification_report:
            lines.append(f"  {self.unification_report.summary()}")
        if self.ingestion_report:
            lines.append(f"  {self.ingestion_report.summary()}")
        if self.embedding_report:
            lines.append(f"  {self.embedding_report.summary()}")
        if self.salience_report:
            lines.append(f"  {self.salience_report.summary()}")
        if self.visual_generation_report:
            lines.append(f"  {self.visual_generation_report.summary()}")
        if self.visual_write_report:
            lines.append(f"  {self.visual_write_report.summary()}")
        lines.append(f"  Total time: {self.total_elapsed_seconds:.1f}s")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class CurriculumPipeline:
    """End-to-end curriculum graph pipeline.

    Orchestrates: PDF parse → skeleton → per-chapter extraction → unification → Neo4j ingestion.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.llm = create_llm_provider(config.llm)
        self.pdf_parser = PDFParser(config.pdf)
        self.toc_extractor = TOCExtractor()
        self.skeleton_extractor = SkeletonExtractor(self.llm)
        self.anchor_extractor = DeterministicAnchorExtractor()
        self.chapter_extractor = ChapterExtractor(self.llm)
        self.structural_validator = StructuralValidator()
        self.gap_filler = GapFiller(self.llm, self.structural_validator)
        self.merger = ExtractionMerger(llm=self.llm)
        self.unifier = BookUnifier()
        self.cypher_generator = CypherGenerator()
        self.salience_service = SalienceService()

    async def run(
        self,
        pdf_path: str | Path,
        subject: str,
        *,
        chapters: list[int] | None = None,
        skip_neo4j: bool = False,
        skip_embeddings: bool = False,
        skip_salience: bool = False,
        skip_visuals: bool = False,
        on_stage: StageCallback | None = None,
    ) -> PipelineReport:
        """Run the full curriculum pipeline.

        Args:
            pdf_path: Path to the input PDF textbook.
            subject: Academic subject (e.g. "physics").
            chapters: Optional 1-based chapter indices to process. None = all.
            skip_neo4j: Skip Neo4j ingestion (extraction only).
            skip_embeddings: Skip embedding generation.
            skip_salience: Skip salience scoring.
            skip_visuals: Skip visual pre-generation.
            on_stage: Progress callback — called with (stage_name, detail_message).

        Returns:
            PipelineReport with all results and diagnostics.
        """
        start = time.monotonic()
        report = PipelineReport(pdf_path=str(pdf_path), subject=subject)
        notify = on_stage or (lambda _s, _d: None)

        # --- Stage 1: Parse PDF ---
        notify("parse", "Parsing PDF...")
        pdf_content, detected_chapters = self._parse_pdf(Path(pdf_path))
        logger.info(
            "Parsed %d pages, %d chapters detected",
            pdf_content.total_pages,
            len(detected_chapters),
        )

        # Filter chapters if specified
        if chapters:
            detected_chapters = [
                c for i, c in enumerate(detected_chapters, 1) if i in chapters
            ]

        report.total_chapters = len(detected_chapters)
        if not detected_chapters:
            logger.warning("No chapters to process.")
            report.total_elapsed_seconds = time.monotonic() - start
            return report

        # --- Stage 2: Book skeleton ---
        notify("skeleton", "Extracting book skeleton...")
        skeleton = self._extract_skeleton(pdf_content, detected_chapters, subject)
        report.skeleton = skeleton
        logger.info("Skeleton extracted: %s", skeleton.textbook_title)

        # --- Stage 3: Per-chapter extraction ---
        chapter_results: list[ChapterPipelineResult] = []
        for i, chapter in enumerate(detected_chapters, 1):
            notify(
                "chapter",
                f"Chapter {i}/{len(detected_chapters)}: {chapter.title}",
            )
            result = self._process_chapter(
                pdf_content, chapter, i, skeleton, subject
            )
            chapter_results.append(result)

        report.chapter_results = chapter_results
        report.chapters_succeeded = sum(
            1 for r in chapter_results if r.error is None
        )
        report.chapters_failed = sum(
            1 for r in chapter_results if r.error is not None
        )

        # Collect successful extractions for unification
        successful = [
            r for r in chapter_results
            if r.extraction is not None and r.error is None
        ]
        if not successful:
            logger.error("All chapters failed — nothing to unify.")
            report.total_elapsed_seconds = time.monotonic() - start
            return report

        # --- Stage 4: Unification ---
        notify("unify", f"Unifying {len(successful)} chapters...")
        extractions = [r.extraction for r in successful]
        unified, unification_report = self.unifier.unify(extractions, skeleton)
        report.unified_extraction = unified
        report.unification_report = unification_report
        logger.info(unification_report.summary())

        # --- Stage 5: Visual pre-generation ---
        visuals = []
        if not skip_visuals:
            hinted_count = sum(1 for n in unified.nodes if n.visual_hint)
            if hinted_count:
                notify("visuals", f"Generating visuals for {hinted_count} concepts...")
                visual_gen = VisualGenerator(self.llm, concurrency=10)
                visuals, visual_gen_report = await visual_gen.generate_visuals(unified)
                report.visual_generation_report = visual_gen_report
                logger.info(visual_gen_report.summary())
        else:
            logger.info("Skipping visual pre-generation (--skip-visuals).")

        # --- Stage 6: Neo4j ingestion ---
        if not skip_neo4j:
            ingestion_report, embedding_report, salience_report, visual_write_report = (
                await self._ingest_to_neo4j(
                    unified,
                    visuals=visuals,
                    skip_embeddings=skip_embeddings,
                    skip_salience=skip_salience,
                    on_stage=notify,
                )
            )
            report.ingestion_report = ingestion_report
            report.embedding_report = embedding_report
            report.salience_report = salience_report
            report.visual_write_report = visual_write_report
        else:
            logger.info("Skipping Neo4j ingestion (--skip-neo4j).")

        report.total_elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    # ------------------------------------------------------------------
    # Stage helpers
    # ------------------------------------------------------------------

    def _parse_pdf(self, pdf_path: Path) -> tuple[PDFContent, list[Chapter]]:
        """Parse PDF and extract chapters from TOC."""
        pdf_content = self.pdf_parser.parse(pdf_path)
        detected = self.toc_extractor.extract_chapters(pdf_content)

        if not detected:
            logger.warning("No chapters detected. Treating entire PDF as one chapter.")
            detected = [
                Chapter(
                    title=pdf_content.metadata.get("title", "Full Document"),
                    level=1,
                    start_page=1,
                    end_page=pdf_content.total_pages,
                )
            ]

        return pdf_content, detected

    def _extract_skeleton(
        self,
        pdf_content: PDFContent,
        chapters: list[Chapter],
        subject: str,
    ) -> BookSkeleton:
        """Extract the book skeleton (fatal on failure)."""
        return self.skeleton_extractor.extract(
            pdf_content, chapters, subject_hint=subject
        )

    def _process_chapter(
        self,
        pdf_content: PDFContent,
        chapter: Chapter,
        chapter_index: int,
        skeleton: BookSkeleton,
        subject: str,
    ) -> ChapterPipelineResult:
        """Process a single chapter: extract → validate → gap-fill → semantic check.

        Never raises — returns ChapterPipelineResult with error set on failure.
        """
        start = time.monotonic()
        result = ChapterPipelineResult(chapter=chapter, chapter_index=chapter_index)

        try:
            chapter_text = pdf_content.get_text_for_range(
                chapter.start_page, chapter.end_page
            )

            # Anchors
            anchors = self.anchor_extractor.extract_for_chapter(pdf_content, chapter)
            result.anchors = anchors

            # Extraction (with optional chunking)
            if needs_chunking(chapter_text):
                extraction, merge_report = self._extract_with_chunking(
                    pdf_content, chapter, chapter_index, skeleton, anchors, subject
                )
                result.merge_report = merge_report
            else:
                extraction = self.chapter_extractor.extract_chapter(
                    pdf_content, chapter, chapter_index, skeleton, anchors, subject
                )

            # Structural validation + gap filling
            extraction, structural_report = self.gap_filler.fill_gaps(
                extraction, anchors, chapter_text
            )
            result.structural_report = structural_report
            result.extraction = extraction

            # Semantic validation
            semantic_validator = SemanticValidator(self.llm)
            semantic_report = semantic_validator.validate(extraction, chapter_text)
            result.semantic_report = semantic_report

            logger.info(
                "Chapter %d '%s' done: %d nodes, %d rels | %s | %s",
                chapter_index,
                chapter.title,
                len(extraction.nodes),
                len(extraction.relationships),
                structural_report.summary() if structural_report else "no validation",
                semantic_report.summary(),
            )

        except Exception:
            logger.exception(
                "Chapter %d '%s' failed", chapter_index, chapter.title
            )
            result.error = f"Chapter {chapter_index} failed"

        result.elapsed_seconds = time.monotonic() - start
        return result

    def _extract_with_chunking(
        self,
        pdf_content: PDFContent,
        chapter: Chapter,
        chapter_index: int,
        skeleton: BookSkeleton,
        anchors: ExtractionAnchors,
        subject: str,
    ) -> tuple[CurriculumExtractionResult, MergeReport]:
        """Handle chapters that exceed the chunking threshold."""
        chapter_text = pdf_content.get_text_for_range(
            chapter.start_page, chapter.end_page
        )
        chunks = chunk_text(chapter_text)
        logger.info(
            "Chapter %d '%s' split into %d chunks (%d chars)",
            chapter_index,
            chapter.title,
            len(chunks),
            len(chapter_text),
        )

        chunk_results: list[CurriculumExtractionResult] = []
        for chunk in chunks:
            chunk_pdf, chunk_chapter = self._make_chunk_pdf_content(chunk, chapter)
            result = self.chapter_extractor.extract_chapter(
                chunk_pdf, chunk_chapter, chapter_index, skeleton, anchors, subject
            )
            chunk_results.append(result)

        merged, merge_report = self.merger.merge_chunks(chunk_results)
        logger.info(
            "Merged %d chunks: %d→%d nodes",
            len(chunks),
            merge_report.total_input_nodes,
            merge_report.total_output_nodes,
        )
        return merged, merge_report

    @staticmethod
    def _make_chunk_pdf_content(
        chunk: TextChunk, chapter: Chapter
    ) -> tuple[PDFContent, Chapter]:
        """Wrap a text chunk into PDFContent/Chapter for the extractor."""
        page = PageContent(page_number=chapter.start_page, text=chunk.text)
        pdf = PDFContent(
            pages=[page], toc_raw=[], total_pages=1, metadata={}
        )
        fake_chapter = Chapter(
            title=chapter.title,
            level=chapter.level,
            start_page=chapter.start_page,
            end_page=chapter.start_page,
        )
        return pdf, fake_chapter

    async def _ingest_to_neo4j(
        self,
        unified: CurriculumExtractionResult,
        *,
        visuals: list | None = None,
        skip_embeddings: bool = False,
        skip_salience: bool = False,
        on_stage: StageCallback | None = None,
    ) -> tuple[IngestionReport, EmbeddingReport | None, SalienceReport | None, VisualWriteReport | None]:
        """Ingest unified extraction into Neo4j: cypher → visuals → embeddings → salience."""
        notify = on_stage or (lambda _s, _d: None)
        embedding_report = None
        salience_report = None
        visual_write_report = None

        async with Neo4jWriter(self.config.neo4j) as writer:
            # Generate and execute Cypher
            notify("ingest", "Generating Cypher and ingesting to Neo4j...")
            statements = self.cypher_generator.generate(unified)
            ingestion_report = await writer.ingest(statements)
            logger.info(ingestion_report.summary())

            # Visuals
            if visuals:
                notify("visuals_store", f"Storing {len(visuals)} visuals in Neo4j...")
                try:
                    visual_writer = Neo4jVisualWriter()
                    visual_write_report = await visual_writer.write_visuals(
                        writer.driver,
                        visuals,
                        generation_model=self.config.llm.model,
                        database=self.config.neo4j.database,
                    )
                    logger.info(visual_write_report.summary())
                except Exception:
                    logger.exception("Visual write failed (non-fatal).")

            # Embeddings
            if not skip_embeddings:
                notify("embed", "Generating embeddings...")
                try:
                    embedding_gen = EmbeddingGenerator(
                        model=self.config.neo4j.embedding_model,
                        dimensions=self.config.neo4j.embedding_dimensions,
                        batch_size=self.config.neo4j.embedding_batch_size,
                    )
                    embedding_report = await embedding_gen.generate_and_store(
                        writer.driver, unified, database=self.config.neo4j.database
                    )
                    logger.info(embedding_report.summary())
                except Exception:
                    logger.exception("Embedding generation failed (non-fatal).")

            # Salience
            if not skip_salience:
                notify("salience", "Scoring salience...")
                try:
                    salience_report = await self.salience_service.score_and_write(
                        writer.driver,
                        unified,
                        self.config.salience,
                        database=self.config.neo4j.database,
                    )
                    logger.info(salience_report.summary())
                except Exception:
                    logger.exception("Salience scoring failed (non-fatal).")

        return ingestion_report, embedding_report, salience_report, visual_write_report
