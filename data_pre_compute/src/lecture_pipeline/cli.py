"""CLI interface for the curriculum graph pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .config import PipelineConfig

app = typer.Typer(
    name="lecture-pipeline",
    help="Curriculum graph pipeline — build knowledge graphs from PDF textbooks.",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _load_config(config_path: str | None = None) -> PipelineConfig:
    return PipelineConfig.load(config_path)


def _parse_chapter_filter(chapters: str | None) -> list[int] | None:
    if not chapters:
        return None
    try:
        return [int(c.strip()) for c in chapters.split(",")]
    except ValueError:
        console.print("[red]Chapters must be comma-separated integers.[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# ingest-book — primary command
# ---------------------------------------------------------------------------


@app.command("ingest-book")
def ingest_book(
    pdf_path: str = typer.Argument(..., help="Path to PDF textbook"),
    subject: str = typer.Option(..., "--subject", "-s", help="Academic subject (e.g. 'physics')"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    chapters: Optional[str] = typer.Option(None, "--chapters", help="Comma-separated chapter numbers (1-based)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory for extraction JSON"),
    skip_neo4j: bool = typer.Option(False, "--skip-neo4j", help="Skip Neo4j ingestion (extraction only)"),
    skip_embeddings: bool = typer.Option(False, "--skip-embeddings", help="Skip embedding generation"),
    skip_salience: bool = typer.Option(False, "--skip-salience", help="Skip salience scoring"),
    skip_visuals: bool = typer.Option(False, "--skip-visuals", help="Skip visual pre-generation"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Ingest a PDF textbook into a Neo4j curriculum graph.

    Runs the full pipeline: PDF → skeleton → anchors → chapters →
    validate → gap-fill → merge → unify → visuals → ingest → embeddings → salience.
    """
    _setup_logging(verbose)

    # Validate PDF
    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        raise typer.Exit(1)

    cfg = _load_config(config)
    chapter_filter = _parse_chapter_filter(chapters)

    # Banner
    console.print(f"\n[bold]Curriculum Graph Pipeline[/bold]")
    console.print(f"  PDF: {pdf_path}")
    console.print(f"  Subject: {subject}")
    console.print(f"  Provider: {cfg.llm.provider} ({cfg.llm.model})")
    if skip_neo4j:
        console.print("  [yellow]Neo4j ingestion: SKIPPED[/yellow]")
    console.print()

    # Import here to avoid circular imports and heavy startup cost
    from .pipeline import CurriculumPipeline

    pipeline = CurriculumPipeline(cfg)

    # Progress callback
    def on_stage(stage: str, detail: str) -> None:
        console.print(f"  [dim]{detail}[/dim]")

    # Run
    report = asyncio.run(
        pipeline.run(
            pdf_path,
            subject,
            chapters=chapter_filter,
            skip_neo4j=skip_neo4j,
            skip_embeddings=skip_embeddings,
            skip_salience=skip_salience,
            skip_visuals=skip_visuals,
            on_stage=on_stage,
        )
    )

    # Summary
    console.print(f"\n[bold green]Done![/bold green]\n")
    console.print(report.summary())

    # Save extraction JSON if requested
    if output and report.unified_extraction:
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        extraction_path = out_dir / "unified_extraction.json"
        extraction_path.write_text(
            report.unified_extraction.model_dump_json(indent=2),
            encoding="utf-8",
        )
        console.print(f"\n  Extraction saved: {extraction_path}")


# ---------------------------------------------------------------------------
# list-chapters — kept from old CLI
# ---------------------------------------------------------------------------


@app.command("list-chapters")
def list_chapters(
    pdf_path: str = typer.Argument(..., help="Path to the input PDF file"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """List detected chapters in a PDF."""
    _setup_logging()

    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        raise typer.Exit(1)

    cfg = _load_config(config)

    from .pdf.parser import PDFParser
    from .pdf.toc import TOCExtractor

    pdf_parser = PDFParser(cfg.pdf)
    pdf_content = pdf_parser.parse(pdf_path)
    toc_extractor = TOCExtractor()
    detected = toc_extractor.extract_chapters(pdf_content)

    console.print(
        f"\n[bold]Chapters in {pdf_path}[/bold] ({pdf_content.total_pages} pages)\n"
    )

    if not detected:
        console.print("[yellow]No chapters detected.[/yellow]")
        return

    for i, ch in enumerate(detected, 1):
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


# ---------------------------------------------------------------------------
# stats — Neo4j graph statistics
# ---------------------------------------------------------------------------


@app.command()
def stats(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Show curriculum graph statistics from Neo4j."""
    _setup_logging(verbose)
    cfg = _load_config(config)

    async def _run_stats() -> None:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            cfg.neo4j.uri,
            auth=(cfg.neo4j.username, cfg.neo4j.password),
        )
        try:
            # Node counts
            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt "
                    "ORDER BY cnt DESC"
                )
                node_rows = [(r["label"], r["cnt"]) async for r in result]

            # Relationship counts
            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS cnt "
                    "ORDER BY cnt DESC"
                )
                rel_rows = [(r["type"], r["cnt"]) async for r in result]

            # Salience
            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(
                    "MATCH (n) WHERE n.salience_total IS NOT NULL "
                    "RETURN min(n.salience_total) AS mn, "
                    "max(n.salience_total) AS mx, "
                    "avg(n.salience_total) AS av, "
                    "count(n) AS cnt"
                )
                sal_row = await result.single()

            # Embedding coverage
            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(
                    "MATCH (n) "
                    "RETURN count(n) AS total, "
                    "sum(CASE WHEN n.embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded"
                )
                emb_row = await result.single()
        finally:
            await driver.close()

        # Display
        console.print("\n[bold]Curriculum Graph Statistics[/bold]\n")

        table = Table(title="Nodes")
        table.add_column("Label", style="cyan")
        table.add_column("Count", justify="right")
        for label, cnt in node_rows:
            table.add_row(label or "(unlabeled)", str(cnt))
        console.print(table)

        table = Table(title="Relationships")
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right")
        for rtype, cnt in rel_rows:
            table.add_row(rtype, str(cnt))
        console.print(table)

        if sal_row and sal_row["cnt"] > 0:
            console.print(
                f"\n  Salience: {sal_row['cnt']} nodes scored, "
                f"range [{sal_row['mn']:.1f}, {sal_row['mx']:.1f}], "
                f"avg {sal_row['av']:.1f}"
            )

        if emb_row:
            console.print(
                f"  Embeddings: {emb_row['embedded']}/{emb_row['total']} nodes"
            )

    asyncio.run(_run_stats())


# ---------------------------------------------------------------------------
# query — ad-hoc Cypher
# ---------------------------------------------------------------------------


@app.command()
def query(
    cypher: str = typer.Argument(..., help="Cypher query to execute"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    limit: int = typer.Option(25, "--limit", "-l", help="Max rows to display"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Run a Cypher query against the curriculum graph."""
    _setup_logging(verbose)
    cfg = _load_config(config)

    async def _run_query() -> None:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            cfg.neo4j.uri,
            auth=(cfg.neo4j.username, cfg.neo4j.password),
        )
        try:
            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(cypher)
                records = [dict(r) async for r in result]
                keys = list(result.keys()) if records else []
        finally:
            await driver.close()

        if not records:
            console.print("[yellow]No results.[/yellow]")
            return

        table = Table(title=f"Results ({min(len(records), limit)} of {len(records)})")
        for key in keys:
            table.add_column(key, style="cyan")

        for row in records[:limit]:
            table.add_row(*[str(row.get(k, "")) for k in keys])

        console.print(table)

    asyncio.run(_run_query())


# ---------------------------------------------------------------------------
# validate — run validators on saved extraction
# ---------------------------------------------------------------------------


@app.command()
def validate(
    extraction_path: str = typer.Argument(..., help="Path to extraction JSON file"),
    semantic: bool = typer.Option(False, "--semantic", help="Also run semantic validation (requires LLM)"),
    chapter_text_path: Optional[str] = typer.Option(None, "--chapter-text", help="Path to chapter text file (for semantic validation)"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Run validation on a saved extraction JSON."""
    _setup_logging(verbose)

    if not Path(extraction_path).exists():
        console.print(f"[red]File not found: {extraction_path}[/red]")
        raise typer.Exit(1)

    from .curriculum.models import CurriculumExtractionResult
    from .curriculum.validation import StructuralValidator

    raw = Path(extraction_path).read_text(encoding="utf-8")
    extraction = CurriculumExtractionResult.model_validate_json(raw)

    console.print(
        f"\n[bold]Validating[/bold]: {len(extraction.nodes)} nodes, "
        f"{len(extraction.relationships)} relationships\n"
    )

    # Structural validation (no anchors available for standalone validation)
    validator = StructuralValidator()
    report = validator.validate(extraction)
    console.print(f"  Structural: {report.summary()}")

    if report.issues:
        table = Table(title="Issues")
        table.add_column("Level", style="cyan")
        table.add_column("Code")
        table.add_column("Message")
        for issue in report.issues[:50]:
            table.add_row(issue.level, issue.code, issue.message)
        console.print(table)

    # Semantic validation
    if semantic:
        chapter_text = ""
        if chapter_text_path and Path(chapter_text_path).exists():
            chapter_text = Path(chapter_text_path).read_text(encoding="utf-8")

        cfg = _load_config(config)
        from .curriculum.validation import SemanticValidator
        from .llm.factory import create_llm_provider

        llm = create_llm_provider(cfg.llm)
        sem_validator = SemanticValidator(llm)
        sem_report = sem_validator.validate(extraction, chapter_text)
        console.print(f"\n  Semantic: {sem_report.summary()}")

        if sem_report.issues:
            table = Table(title="Semantic Issues")
            table.add_column("Type", style="cyan")
            table.add_column("Severity")
            table.add_column("Node")
            table.add_column("Description")
            for issue in sem_report.issues[:50]:
                table.add_row(
                    issue.issue_type, issue.severity, issue.node_uid, issue.description
                )
            console.print(table)


if __name__ == "__main__":
    app()
