"""CLI for the v2 curriculum pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

# Load `.env` from the project root (or wherever the nearest .env is found)
# so `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / etc are available to the
# Anthropic + Kokoro + Neo4j clients without manually sourcing in every shell.
load_dotenv(find_dotenv(usecwd=True))

from .config import PipelineConfig  # noqa: E402 — must come after load_dotenv()

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
    subject: str = typer.Option(
        ..., "--subject", "-s", help="Academic subject (e.g. 'physics')"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to config.yaml"
    ),
    chapters: Optional[str] = typer.Option(
        None, "--chapters", help="Comma-separated chapter numbers (1-based)"
    ),
    chapter_name: Optional[str] = typer.Option(
        None, "--chapter", help="Chapter name substring (case-insensitive)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Directory for extraction JSON"
    ),
    force: bool = typer.Option(
        False, "--force", help="Ignore idempotency snapshot — recompute everything"
    ),
    skip_neo4j: bool = typer.Option(False, "--skip-neo4j"),
    skip_embeddings: bool = typer.Option(False, "--skip-embeddings"),
    skip_tts: bool = typer.Option(False, "--skip-tts"),
    skip_visuals: bool = typer.Option(False, "--skip-visuals"),
    skip_questions: bool = typer.Option(False, "--skip-questions"),
    skip_prereqs: bool = typer.Option(False, "--skip-prereqs"),
    skip_beat_narration: bool = typer.Option(False, "--skip-beat-narration"),
    skip_diagram_qa: bool = typer.Option(False, "--skip-diagram-qa"),
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
            pdf_path,
            subject,
            chapters=chapter_filter,
            chapter_name=chapter_name,
            force=force,
            skip_neo4j=skip_neo4j,
            skip_embeddings=skip_embeddings,
            skip_tts=skip_tts,
            skip_visuals=skip_visuals,
            skip_questions=skip_questions,
            skip_prereqs=skip_prereqs,
            skip_beat_narration=skip_beat_narration,
            skip_diagram_qa=skip_diagram_qa,
            on_stage=on_stage,
        )
    )

    console.print("\n[bold green]Done![/bold green]\n")
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
            cfg.neo4j.uri,
            auth=(cfg.neo4j.username, cfg.neo4j.password),
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
            cfg.neo4j.uri,
            auth=(cfg.neo4j.username, cfg.neo4j.password),
        )
        try:
            result = await initialize_schema(
                driver,
                database=cfg.neo4j.database,
                embedding_dimensions=cfg.embedding.dimensions,
            )
        finally:
            await driver.close()

        console.print("\n[bold]Schema initialized:[/bold]")
        console.print(f"  Created: {result['success']}")
        console.print(f"  Skipped: {result['skipped']}")
        if result["enterprise_only"]:
            console.print(f"  Enterprise-only (skipped): {result['enterprise_only']}")
        if result["failed"]:
            console.print(f"  [red]Failed: {result['failed']}[/red]")

    asyncio.run(_run())


@app.command("load-extraction")
def load_extraction(
    extraction_path: str = typer.Argument(
        ..., help="Path to extraction.json saved by --output"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to config.yaml"
    ),
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


@app.command("regen-audio")
def regen_audio(
    extraction_path: str = typer.Argument(..., help="Path to extraction.json"),
    chapter: Optional[str] = typer.Option(
        None,
        "--chapter",
        help="Chapter title substring (case-insensitive); regen all chapters if omitted.",
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Delete the chapter audio directory before regen (forces full re-synthesis).",
    ),
    skip_neo4j: bool = typer.Option(
        False, "--skip-neo4j", help="Skip writing the updated manifest to Neo4j."
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Regenerate TTS audio for one or all chapters in an extraction.json.

    Zero LLM calls. Loads the extraction, runs AudioPipeline only,
    updates each targeted chapter's `chapter_manifest` with the new audio
    URLs + durations, saves the extraction back to disk, and (unless
    --skip-neo4j) re-hydrates Neo4j so the preview server picks up the
    new manifest immediately.

    Use --clean when you've changed narration content and the audio cache
    needs to be wiped (the cache key DOES include a content hash, so this
    is only strictly needed if you want zero trace of prior MP3s).
    """
    _setup_logging(verbose)

    if not Path(extraction_path).exists():
        console.print(f"[red]File not found: {extraction_path}[/red]")
        raise typer.Exit(1)

    import shutil

    from .curriculum.ingestion.cypher_generator import CypherGenerator
    from .curriculum.ingestion.neo4j_writer import Neo4jWriter
    from .curriculum.lecture_script.models import ChapterScript
    from .curriculum.media.audio_pipeline import AudioPipeline
    from .curriculum.models import CurriculumExtractionResult
    from .tts.factory import create_tts_provider

    cfg = _load_config(config)
    extraction = CurriculumExtractionResult.load(extraction_path)

    # Filter to targeted chapters.
    if chapter:
        needle = chapter.lower()
        targets = [ch for ch in extraction.chapters if needle in ch.title.lower()]
        if not targets:
            console.print(
                f"[red]No chapter matches substring {chapter!r}.[/red] "
                "Available titles: "
                + ", ".join(f"'{c.title}'" for c in extraction.chapters)
            )
            raise typer.Exit(1)
    else:
        targets = list(extraction.chapters)

    console.print(
        f"\n[bold]regen-audio[/bold] — {len(targets)} chapter(s) targeted "
        f"from {extraction_path}"
    )
    for ch in targets:
        console.print(f"  • {ch.title}  ({ch.chapter_id})")

    # Optionally wipe stale audio dirs.
    audio_root = Path(cfg.artifacts.base_dir) / "audio"
    if clean:
        for ch in targets:
            chapter_dir = audio_root / ch.chapter_id.replace(":", "_")
            if chapter_dir.exists():
                console.print(f"  [yellow]nuking {chapter_dir}[/yellow]")
                shutil.rmtree(chapter_dir)

    # Reconstruct ChapterScripts from the per-chapter assembled_chapter_script dict.
    chapter_scripts: dict[str, ChapterScript] = {}
    for ch in targets:
        if ch.assembled_chapter_script is None:
            console.print(
                f"  [yellow]skip {ch.chapter_id}: no assembled_chapter_script[/yellow]"
            )
            continue
        chapter_scripts[ch.chapter_id] = ChapterScript(**ch.assembled_chapter_script)

    if not chapter_scripts:
        console.print(
            "[red]Nothing to render — no assembled scripts in extraction.[/red]"
        )
        raise typer.Exit(1)

    async def _run() -> None:
        tts = create_tts_provider(cfg.tts)
        audio_pipeline = AudioPipeline(
            tts,
            cfg.tts,
            cfg.artifacts,
            layout=cfg.layout,
        )
        report = await audio_pipeline.build_for_book(
            targets,
            extraction.topics,
            chapter_scripts,
            diagrams=extraction.diagrams,
        )
        console.print(f"\n  {report.summary()}")

        # Save the extraction with the updated chapter_manifests.
        extraction.save(extraction_path)
        console.print(f"  extraction saved → {extraction_path}")

        if skip_neo4j:
            console.print("  [yellow]skipping Neo4j write (--skip-neo4j)[/yellow]")
            return

        cypher_gen = CypherGenerator()
        statements = cypher_gen.generate(extraction)
        console.print(f"  generated {len(statements)} Cypher statements")
        async with Neo4jWriter(cfg.neo4j) as writer:
            ingest_report = await writer.ingest(
                statements,
                embedding_dimensions=cfg.embedding.dimensions,
            )
            console.print(f"  {ingest_report.summary()}")

    asyncio.run(_run())
    console.print("\n[bold green]Done.[/bold green]")


if __name__ == "__main__":
    app()
