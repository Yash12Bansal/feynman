"""Main pipeline orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import PipelineConfig
from .graph.builder import GraphBuilder
from .graph.models import ConceptGraph
from .graph.serializer import GraphSerializer
from .lecture.graph_generator import GraphLectureGenerator
from .lecture.script_generator import ScriptGenerator
from .llm.factory import create_llm_provider
from .pdf.parser import PDFContent, PDFParser
from .pdf.toc import Chapter, TOCExtractor

logger = logging.getLogger(__name__)

OutputMode = Literal["graph", "lecture_script"]


@dataclass
class ChapterResult:
    """Result for a single chapter."""
    chapter: Chapter
    mode: OutputMode
    lecture_script: str | None = None
    concept_graph: ConceptGraph | None = None


@dataclass
class PipelineResult:
    """Full pipeline result across all chapters."""
    pdf_path: str
    mode: OutputMode
    chapters: list[ChapterResult]
    pdf_content: PDFContent

    def save(self, output_dir: str | Path) -> list[Path]:
        """Save all results to output directory. Returns list of saved files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []

        for i, result in enumerate(self.chapters):
            safe_title = _sanitize_filename(result.chapter.title)
            prefix = f"{i + 1:02d}_{safe_title}"

            if result.lecture_script:
                script_path = output_dir / f"{prefix}_lecture.md"
                script_path.write_text(result.lecture_script, encoding="utf-8")
                saved.append(script_path)
                logger.info(f"Saved lecture: {script_path}")

            if result.concept_graph:
                graph_path = output_dir / f"{prefix}_graph.json"
                GraphSerializer.to_json(result.concept_graph, graph_path)
                saved.append(graph_path)
                logger.info(f"Saved graph: {graph_path}")

        return saved


class Pipeline:
    """Main lecture pipeline — PDF to lecture scripts or concept graphs.

    Usage (Python API):
        config = PipelineConfig.load("config.yaml")
        pipeline = Pipeline(config)
        result = pipeline.run("textbook.pdf", mode="graph")
        result.save("./output")

    Usage (CLI):
        lecture-pipeline run textbook.pdf --mode graph --output ./output
    """

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig.load()
        self.pdf_parser = PDFParser(self.config.pdf)
        self.toc_extractor = TOCExtractor()
        self.llm = create_llm_provider(self.config.llm)

    def run(
        self,
        pdf_path: str | Path,
        mode: OutputMode = "graph",
        chapters: list[int] | None = None,
        generate_lec_from_graph: bool = False,
    ) -> PipelineResult:
        """Run the pipeline on a PDF.

        Args:
            pdf_path: Path to the input PDF.
            mode: "graph" for concept graph, "lecture_script" for naive script.
            chapters: Optional list of chapter indices (1-based) to process.
                      If None, processes all chapters.
            generate_lec_from_graph: If True and mode is "graph", also generates
                      a lecture script from the concept graph. Default False.

        Returns:
            PipelineResult with all chapter results.
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Parsing PDF: {pdf_path}")

        # Step 1: Parse PDF
        pdf_content = self.pdf_parser.parse(pdf_path)
        logger.info(
            f"Extracted {pdf_content.total_pages} pages, "
            f"TOC entries: {len(pdf_content.toc_raw)}"
        )

        # Step 2: Extract chapters
        detected_chapters = self.toc_extractor.extract_chapters(pdf_content)
        if not detected_chapters:
            logger.warning("No chapters detected. Treating entire PDF as one chapter.")
            detected_chapters = [
                Chapter(
                    title=pdf_content.metadata.get("title", "Full Document"),
                    level=1,
                    start_page=1,
                    end_page=pdf_content.total_pages,
                )
            ]

        logger.info(f"Detected {len(detected_chapters)} chapters")

        # Filter chapters if specified
        if chapters:
            detected_chapters = [
                c for i, c in enumerate(detected_chapters, 1) if i in chapters
            ]

        # Step 3: Process each chapter
        results = []
        for chapter in detected_chapters:
            logger.info(f"Processing chapter: {chapter.title} (pages {chapter.start_page}-{chapter.end_page})")

            if mode == "graph":
                result = self._process_graph_mode(chapter, pdf_content, generate_lec_from_graph)
            else:
                result = self._process_script_mode(chapter, pdf_content)

            results.append(result)

        return PipelineResult(
            pdf_path=str(pdf_path),
            mode=mode,
            chapters=results,
            pdf_content=pdf_content,
        )

    def _process_graph_mode(
        self, chapter: Chapter, pdf_content: PDFContent, generate_lec_from_graph: bool = False
    ) -> ChapterResult:
        """Mode: graph — build concept graph, optionally generate lecture from it."""
        # Build concept graph
        builder = GraphBuilder(self.llm, self.config.graph)
        graph = builder.build_chapter_graph(chapter, pdf_content)

        # Only generate lecture if explicitly requested
        lecture = None
        if generate_lec_from_graph:
            generator = GraphLectureGenerator(self.llm, self.config.lecture)
            lecture = generator.generate(graph)

        return ChapterResult(
            chapter=chapter,
            mode="graph",
            lecture_script=lecture,
            concept_graph=graph,
        )

    def _process_script_mode(self, chapter: Chapter, pdf_content: PDFContent) -> ChapterResult:
        """Mode: lecture_script — direct text to lecture."""
        generator = ScriptGenerator(self.llm, self.config.lecture)
        lecture = generator.generate(chapter, pdf_content)

        return ChapterResult(
            chapter=chapter,
            mode="lecture_script",
            lecture_script=lecture,
        )

    def generate_from_graph(self, graph: ConceptGraph) -> str:
        """Generate a lecture script from an existing concept graph.

        Useful when the user has a pre-built or edited graph.
        """
        generator = GraphLectureGenerator(self.llm, self.config.lecture)
        return generator.generate(graph)


def _sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip()[:80]
