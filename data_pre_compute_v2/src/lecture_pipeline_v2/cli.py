"""CLI for the v2 curriculum pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .config import PipelineConfig

app = typer.Typer(
    name="lecture-pipeline-v2",
    help="Curriculum precompute pipeline v2 — Topic/Diagram/Question graph with pre-rendered TTS.",
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


@app.command("ingest-book")
def ingest_book(
    pdf_path: str = typer.Argument(..., help="Path to PDF textbook"),
    subject: str = typer.Option(..., "--subject", "-s", help="Academic subject (e.g. 'physics')"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    chapters: Optional[str] = typer.Option(None, "--chapters", help="Comma-separated chapter numbers (1-based)"),
    chapter_name: Optional[str] = typer.Option(None, "--chapter", help="Chapter name substring (case-insensitive)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Directory for extraction JSON"),
    force: bool = typer.Option(False, "--force", help="Ignore idempotency snapshot — recompute everything"),
    skip_neo4j: bool = typer.Option(False, "--skip-neo4j"),
    skip_embeddings: bool = typer.Option(False, "--skip-embeddings"),
    skip_tts: bool = typer.Option(False, "--skip-tts"),
    skip_visuals: bool = typer.Option(False, "--skip-visuals"),
    skip_questions: bool = typer.Option(False, "--skip-questions"),
    skip_prereqs: bool = typer.Option(False, "--skip-prereqs"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Ingest a PDF textbook into the v2 curriculum graph.

    Without --force, the pipeline reads the current Neo4j state once and
    skips work for content that already exists (Topics, Diagrams, Questions,
    audio manifests, embeddings).
    """
    _setup_logging(verbose)

    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        raise typer.Exit(1)

    cfg = _load_config(config)
    chapter_filter = None
    if chapters:
        try:
            chapter_filter = [int(c.strip()) for c in chapters.split(",")]
        except ValueError:
            console.print("[red]Chapters must be comma-separated integers.[/red]")
            raise typer.Exit(1)

    console.print("\n[bold]Curriculum Pipeline v2[/bold]")
    console.print(f"  PDF: {pdf_path}")
    console.print(f"  Subject: {subject}")
    console.print(f"  LLM: {cfg.llm.provider} ({cfg.llm.model})")
    console.print(f"  TTS: {cfg.tts.provider} ({cfg.tts.voice})")
    if chapter_filter:
        console.print(f"  Chapters (by index): {chapter_filter}")
    if chapter_name:
        console.print(f"  Chapter (by name): {chapter_name}")
    if force:
        console.print("  [yellow]--force: idempotency disabled[/yellow]")
    console.print()

    from .pipeline import CurriculumPipelineV2

    pipeline = CurriculumPipelineV2(cfg)

    def on_stage(stage: str, detail: str) -> None:
        console.print(f"  [dim][{stage}] {detail}[/dim]")

    report = asyncio.run(
        pipeline.run(
            pdf_path, subject,
            chapters=chapter_filter,
            chapter_name=chapter_name,
            force=force,
            skip_neo4j=skip_neo4j,
            skip_embeddings=skip_embeddings,
            skip_tts=skip_tts,
            skip_visuals=skip_visuals,
            skip_questions=skip_questions,
            skip_prereqs=skip_prereqs,
            on_stage=on_stage,
        )
    )

    console.print(f"\n[bold green]Done![/bold green]\n")
    console.print(report.summary())
    for w in report.warnings:
        console.print(f"  [yellow]warning:[/yellow] {w}")

    if output and report.extraction:
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "extraction.json"
        report.extraction.save(path)
        console.print(f"\n  Extraction saved: {path}")


@app.command("list-chapters")
def list_chapters(
    pdf_path: str = typer.Argument(..., help="Path to PDF textbook"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
) -> None:
    """List detected chapters in a PDF (TOC or heuristic fallback)."""
    _setup_logging()

    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        raise typer.Exit(1)

    cfg = _load_config(config)

    from .pdf.parser import PDFParser
    from .pdf.toc import TOCExtractor

    pdf_content = PDFParser(cfg.pdf).parse(pdf_path)
    detected = TOCExtractor().extract_chapters(pdf_content)

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


@app.command()
def stats(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Show v2 curriculum graph statistics from Neo4j."""
    _setup_logging(verbose)
    cfg = _load_config(config)

    async def _run_stats() -> None:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password),
        )
        try:
            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt "
                    "ORDER BY cnt DESC"
                )
                node_rows = [(r["label"], r["cnt"]) async for r in result]

            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS cnt "
                    "ORDER BY cnt DESC"
                )
                rel_rows = [(r["type"], r["cnt"]) async for r in result]

            async with driver.session(database=cfg.neo4j.database) as session:
                result = await session.run(
                    "MATCH (n:Topic) RETURN "
                    "count(n) AS total, "
                    "sum(CASE WHEN n.needs_review = true THEN 1 ELSE 0 END) AS flagged"
                )
                topic_row = await result.single()
        finally:
            await driver.close()

        console.print("\n[bold]Curriculum Graph v2 Statistics[/bold]\n")

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

        if topic_row and topic_row["total"]:
            console.print(
                f"\n  Topics: {topic_row['total']} total, "
                f"{topic_row['flagged']} flagged for review"
            )

    asyncio.run(_run_stats())


@app.command()
def query(
    cypher: str = typer.Argument(..., help="Cypher query to execute"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    limit: int = typer.Option(25, "--limit", "-l"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run an ad-hoc Cypher query against the v2 graph."""
    _setup_logging(verbose)
    cfg = _load_config(config)

    async def _run_query() -> None:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password),
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


@app.command("init-schema")
def init_schema(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Initialize the v2 Neo4j schema (constraints, indexes, vector indexes)."""
    _setup_logging(verbose)
    cfg = _load_config(config)

    async def _run() -> None:
        from neo4j import AsyncGraphDatabase
        from .curriculum.schema import initialize_schema

        driver = AsyncGraphDatabase.driver(
            cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password),
        )
        try:
            result = await initialize_schema(
                driver, database=cfg.neo4j.database,
                embedding_dimensions=cfg.embedding.dimensions,
            )
        finally:
            await driver.close()

        console.print(f"\n[bold]Schema initialized:[/bold]")
        console.print(f"  Created: {result['success']}")
        console.print(f"  Skipped: {result['skipped']}")
        if result["enterprise_only"]:
            console.print(f"  Enterprise-only (skipped): {result['enterprise_only']}")
        if result["failed"]:
            console.print(f"  [red]Failed: {result['failed']}[/red]")

    asyncio.run(_run())


@app.command("load-extraction")
def load_extraction(
    extraction_path: str = typer.Argument(..., help="Path to extraction.json saved by --output"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Re-hydrate Neo4j from a previously-saved extraction JSON.

    Zero LLM calls, zero TTS. Runs Cypher MERGE for everything in the
    JSON (chapters, topics, diagrams, questions, manifests, embeddings)
    so a teammate can spin up the graph instantly from committed fixtures.
    """
    _setup_logging(verbose)

    if not Path(extraction_path).exists():
        console.print(f"[red]File not found: {extraction_path}[/red]")
        raise typer.Exit(1)

    cfg = _load_config(config)

    from .curriculum.ingestion.cypher_generator import CypherGenerator
    from .curriculum.ingestion.neo4j_writer import Neo4jWriter
    from .curriculum.models import CurriculumExtractionResult
    from .curriculum.schema import verify_ingestion

    extraction = CurriculumExtractionResult.load(extraction_path)
    counts = extraction.counts()

    console.print(f"\n[bold]Loading extraction from {extraction_path}[/bold]")
    console.print(
        f"  {counts['chapters']} chapters, {counts['topics']} topics, "
        f"{counts['diagrams']} diagrams, {counts['questions']} questions"
    )

    async def _run() -> None:
        cypher_gen = CypherGenerator()
        statements = cypher_gen.generate(extraction)
        console.print(f"  generated {len(statements)} Cypher statements")

        async with Neo4jWriter(cfg.neo4j) as writer:
            report = await writer.ingest(
                statements,
                embedding_dimensions=cfg.embedding.dimensions,
            )
            console.print(f"\n  {report.summary()}")

            expected_ids = (
                {c.chapter_id for c in extraction.chapters}
                | {t.topic_id for t in extraction.topics}
                | {d.diagram_id for d in extraction.diagrams}
                | {q.question_id for q in extraction.questions}
            )
            expected_rels = sum(
                1
                + (1 if t.next_topic_id else 0)
                + len(t.prereq_topic_ids)
                + len(t.has_diagram_ids)
                + len(t.has_question_ids)
                for t in extraction.topics
            )
            verification = await verify_ingestion(
                writer.driver,
                expected_node_ids=expected_ids,
                expected_rel_count=expected_rels,
                database=cfg.neo4j.database,
            )
            console.print(f"\n  {verification.summary()}")

        console.print("\n[bold green]Done.[/bold green]")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
