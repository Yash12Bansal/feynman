"""CLI interface for the lecture pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import PipelineConfig
from .graph.serializer import GraphSerializer
from .pipeline import Pipeline, OutputMode

app = typer.Typer(
    name="lecture-pipeline",
    help="Generate lecture scripts and concept graphs from PDF textbooks.",
    add_completion=False,
)
console = Console()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@app.command()
def run(
    pdf_path: str = typer.Argument(..., help="Path to the input PDF file"),
    mode: str = typer.Option("graph", "--mode", "-m", help="Output mode: 'graph' or 'lecture_script'"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    chapters: Optional[str] = typer.Option(None, "--chapters", help="Comma-separated chapter numbers (e.g. '1,3,5')"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider: 'openai' or 'anthropic'"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model name"),
    generate_lec_from_graph: bool = typer.Option(False, "--generate-lec-from-graph", help="When mode is 'graph', also generate a lecture script from the concept graph"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
):
    """Process a PDF and generate lecture scripts or concept graphs."""
    setup_logging(verbose)

    if mode not in ("graph", "lecture_script"):
        console.print(f"[red]Invalid mode: {mode}. Use 'graph' or 'lecture_script'.[/red]")
        raise typer.Exit(1)

    # Load config
    cfg = PipelineConfig.load(config)

    # Override from CLI flags
    if provider:
        cfg.llm.provider = provider
    if model:
        cfg.llm.model = model
    cfg.output.output_dir = output

    # Parse chapter filter
    chapter_filter = None
    if chapters:
        try:
            chapter_filter = [int(c.strip()) for c in chapters.split(",")]
        except ValueError:
            console.print("[red]Chapters must be comma-separated integers.[/red]")
            raise typer.Exit(1)

    # Validate PDF exists
    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        raise typer.Exit(1)

    # Run pipeline
    pipeline = Pipeline(cfg)

    console.print(f"\n[bold]Lecture Pipeline[/bold]")
    console.print(f"  PDF: {pdf_path}")
    console.print(f"  Mode: {mode}")
    console.print(f"  Provider: {cfg.llm.provider} ({cfg.llm.model})")
    console.print(f"  Output: {output}\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing PDF...", total=None)
        result = pipeline.run(pdf_path, mode=mode, chapters=chapter_filter, generate_lec_from_graph=generate_lec_from_graph)

        progress.update(task, description="Saving results...")
        saved_files = result.save(output)

    console.print(f"\n[green]Done![/green] Generated {len(saved_files)} files:")
    for f in saved_files:
        console.print(f"  {f}")


@app.command()
def list_chapters(
    pdf_path: str = typer.Argument(..., help="Path to the input PDF file"),
):
    """List detected chapters in a PDF."""
    setup_logging()

    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        raise typer.Exit(1)

    cfg = PipelineConfig.load()
    parser = __import__("lecture_pipeline.pdf.parser", fromlist=["PDFParser"])
    toc_mod = __import__("lecture_pipeline.pdf.toc", fromlist=["TOCExtractor"])

    pdf_parser = parser.PDFParser(cfg.pdf)
    pdf_content = pdf_parser.parse(pdf_path)
    toc_extractor = toc_mod.TOCExtractor()
    chapters = toc_extractor.extract_chapters(pdf_content)

    console.print(f"\n[bold]Chapters in {pdf_path}[/bold] ({pdf_content.total_pages} pages)\n")

    if not chapters:
        console.print("[yellow]No chapters detected.[/yellow]")
        return

    for i, ch in enumerate(chapters, 1):
        indent = "  " * (ch.level - 1)
        console.print(
            f"  {indent}[cyan]{i}.[/cyan] {ch.title} "
            f"[dim](pages {ch.start_page}-{ch.end_page}, {ch.page_count} pages)[/dim]"
        )
        for child in ch.children:
            console.print(
                f"  {indent}    - {child.title} "
                f"[dim](pages {child.start_page}-{child.end_page})[/dim]"
            )


@app.command()
def from_graph(
    graph_path: str = typer.Argument(..., help="Path to concept graph JSON file"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model name"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a lecture script from an existing concept graph JSON."""
    setup_logging(verbose)

    cfg = PipelineConfig.load(config)
    if provider:
        cfg.llm.provider = provider
    if model:
        cfg.llm.model = model

    graph = GraphSerializer.from_json(path=graph_path)
    console.print(f"\n[bold]Generating lecture from graph:[/bold] {graph.chapter_title}")
    console.print(f"  Nodes: {len(graph.nodes)}, Edges: {len(graph.edges)}\n")

    pipeline = Pipeline(cfg)
    lecture = pipeline.generate_from_graph(graph)

    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in graph.chapter_title)[:80]
    out_path = out_dir / f"{safe_title}_lecture.md"
    out_path.write_text(lecture, encoding="utf-8")

    console.print(f"[green]Saved lecture:[/green] {out_path}")


if __name__ == "__main__":
    app()
