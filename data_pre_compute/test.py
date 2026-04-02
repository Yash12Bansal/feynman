"""Test script for the lecture pipeline.

Usage:
    python test.py <pdf_path> <chapter_name> <mode> [options]

Examples:
    # Graph mode
    python test.py ./book.pdf "Chemical Reactions" graph --start-page 2 --end-page 16

    # Direct lecture mode
    python test.py ./book.pdf "Simple Harmonic Motion" direct_lecture --start-page 239 --end-page 253

    # Deep-dive on a specific topic within a chapter
    python test.py ./book.pdf "Simple Harmonic Motion" direct_lecture --start-page 239 --end-page 253 --topic "Energy Conservation in SHM"

    # Beginner quality
    python test.py ./book.pdf "SHM" direct_lecture --start-page 239 --end-page 253 --quality beginner

    # Graph + lecture from graph
    python test.py ./book.pdf "SHM" graph --start-page 239 --end-page 253 --generate-lec-from-graph
"""

import argparse
import logging
import sys
from pathlib import Path

from lecture_pipeline.config import PipelineConfig
from lecture_pipeline.graph.serializer import GraphSerializer
from lecture_pipeline.pdf import PDFParser, TOCExtractor
from lecture_pipeline.pdf.toc import Chapter
from lecture_pipeline.pipeline import Pipeline


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def find_chapter(chapters, chapter_name: str):
    """Find a chapter by name (case-insensitive substring match)."""
    query = chapter_name.strip().lower()
    for ch in chapters:
        if query in ch.title.strip().lower():
            return ch
        for child in ch.children:
            if query in child.title.strip().lower():
                return child
    return None


def flatten_chapters(chapters):
    """Flatten nested chapters into a single list."""
    flat = []
    for ch in chapters:
        flat.append(ch)
        flat.extend(flatten_chapters(ch.children))
    return flat


def main():
    parser = argparse.ArgumentParser(description="Test the lecture pipeline")
    parser.add_argument("pdf_path", help="Path to the PDF book")
    parser.add_argument("chapter_name", help="Name of the chapter to process (substring match)")
    parser.add_argument("mode", choices=["graph", "direct_lecture"], help="Output mode")
    parser.add_argument("--start-page", type=int, default=None,
                        help="Start page of the chapter (1-indexed)")
    parser.add_argument("--end-page", type=int, default=None,
                        help="End page of the chapter (1-indexed)")
    parser.add_argument("--topic", type=str, default=None,
                        help="Specific topic within the chapter for a deep-dive lecture")
    parser.add_argument("--quality", choices=["beginner", "advanced"], default="advanced",
                        help="Lecture quality/depth level (default: advanced)")
    parser.add_argument("--generate-lec-from-graph", action="store_true", default=False,
                        help="Also generate lecture from the concept graph (graph mode only)")
    parser.add_argument("--output-dir", default="./output", help="Output directory (default: ./output)")

    args = parser.parse_args()

    # Load config
    config = PipelineConfig.load()
    config.output.output_dir = args.output_dir
    config.lecture.audience_level = args.quality

    # Parse PDF
    logger.info(f"Parsing PDF: {args.pdf_path}")
    pdf_parser = PDFParser(config.pdf)
    page_range = None
    if args.start_page is not None and args.end_page is not None:
        page_range = (args.start_page, args.end_page)
    pdf_content = pdf_parser.parse(args.pdf_path, page_range=page_range)
    logger.info(f"Total pages: {pdf_content.total_pages}, TOC entries: {len(pdf_content.toc_raw)}")

    matched = None

    # If explicit page range is provided, use that directly
    if args.start_page is not None and args.end_page is not None:
        logger.info(f"Using explicit page range: {args.start_page}-{args.end_page}")
        matched = Chapter(
            title=args.chapter_name,
            level=1,
            start_page=args.start_page,
            end_page=args.end_page,
        )
    else:
        # Try TOC detection
        toc_extractor = TOCExtractor()
        chapters = toc_extractor.extract_chapters(pdf_content)

        if chapters:
            all_chapters = flatten_chapters(chapters)
            logger.info(f"Detected {len(all_chapters)} chapters/sections:")
            for i, ch in enumerate(all_chapters, 1):
                indent = "  " * (ch.level - 1)
                logger.info(f"  {indent}{i}. {ch.title} (pages {ch.start_page}-{ch.end_page})")

            matched = find_chapter(chapters, args.chapter_name)

            if not matched:
                logger.error(f"Chapter not found: '{args.chapter_name}'")
                logger.error("Available chapters:")
                for ch in all_chapters:
                    logger.error(f"  - {ch.title}")
                logger.error("\nTip: Use --start-page and --end-page to specify the page range manually.")
                sys.exit(1)
        else:
            logger.error("No chapters detected in this PDF and no page range provided.")
            logger.error("Use --start-page and --end-page to specify the chapter's page range.")
            sys.exit(1)

    logger.info(f"Processing: '{matched.title}' (pages {matched.start_page}-{matched.end_page})")
    logger.info(f"Quality: {args.quality}")
    if args.topic:
        logger.info(f"Topic deep-dive: '{args.topic}'")

    # Map mode
    pipeline_mode = "graph" if args.mode == "graph" else "lecture_script"

    # Run pipeline
    pipeline = Pipeline(config)

    logger.info(f"Running pipeline: mode={pipeline_mode}, generate_lec_from_graph={args.generate_lec_from_graph}")

    # Topic deep-dive mode
    if args.topic:
        from lecture_pipeline.lecture import ScriptGenerator
        gen = ScriptGenerator(pipeline.llm, config.lecture)
        lecture = gen.generate_topic(args.topic, matched, pdf_content)

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in args.topic)[:80]
        lecture_path = output_dir / f"{safe_topic}_deep_dive.md"
        lecture_path.write_text(lecture, encoding="utf-8")
        logger.info(f"Saved topic deep-dive: {lecture_path}")

        # Also extract images
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in matched.title)[:80]
        images_dir = output_dir / f"{safe_title}_images"
        image_files = pdf_content.extract_images_to_dir(images_dir, matched.start_page, matched.end_page)
        if image_files:
            logger.info(f"Saved {len(image_files)} images to {images_dir}")

        logger.info("Done!")
        return

    # Standard chapter processing
    if pipeline_mode == "graph":
        result_chapter = pipeline._process_graph_mode(matched, pdf_content, args.generate_lec_from_graph)
    else:
        result_chapter = pipeline._process_script_mode(matched, pdf_content)

    # Save outputs
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in matched.title)[:80]

    saved_files = []

    if result_chapter.concept_graph:
        graph_path = output_dir / f"{safe_title}_graph.json"
        GraphSerializer.to_json(result_chapter.concept_graph, graph_path)
        saved_files.append(graph_path)
        logger.info(f"Saved graph: {graph_path}")

        outline_path = output_dir / f"{safe_title}_graph_outline.md"
        outline = GraphSerializer.to_markdown_outline(result_chapter.concept_graph)
        outline_path.write_text(outline, encoding="utf-8")
        saved_files.append(outline_path)
        logger.info(f"Saved graph outline: {outline_path}")

    if result_chapter.lecture_script:
        lecture_path = output_dir / f"{safe_title}_lecture.md"
        lecture_path.write_text(result_chapter.lecture_script, encoding="utf-8")
        saved_files.append(lecture_path)
        logger.info(f"Saved lecture: {lecture_path}")

    # Extract and save images
    images_dir = output_dir / f"{safe_title}_images"
    logger.info(f"Extracting images from pages {matched.start_page}-{matched.end_page}...")
    image_files = pdf_content.extract_images_to_dir(images_dir, matched.start_page, matched.end_page)
    if image_files:
        logger.info(f"Saved {len(image_files)} images to {images_dir}")
        for f in image_files:
            saved_files.append(f)
    else:
        logger.info("No images found in chapter pages.")

    logger.info(f"Done! Generated {len(saved_files)} files in {output_dir}")
    for f in saved_files:
        logger.info(f"  -> {f}")


if __name__ == "__main__":
    main()
