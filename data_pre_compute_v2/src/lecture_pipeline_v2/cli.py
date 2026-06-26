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

import yaml
from feynman_teaching_kernel.persona import TeacherPersona, merge_domain_overlay
from feynman_teaching_kernel.persona_registry import PersonaNotFoundError, load_persona

from .config import PipelineConfig  # noqa: E402 — must come after load_dotenv()
from .persona_paths import default_personas_dir

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


def _resolve_style_context(style_source: str | None) -> str | None:
    if not style_source:
        return None
    sp = Path(style_source)
    return sp.read_text(encoding="utf-8") if sp.exists() else style_source


def _load_domain_overlay(subject: str, personas_dir: Path) -> TeacherPersona | None:
    path = personas_dir / "domains" / f"{subject}.yaml"
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return TeacherPersona.model_validate(raw)


def _resolve_persona(
    persona_id: str | None,
    style_source: str | None,
    *,
    subject: str | None = None,
    personas_dir: Path | None = None,
) -> tuple[TeacherPersona | None, str | None]:
    """Return (persona, legacy_style_context). --persona wins over --style-source."""
    pdir = personas_dir or default_personas_dir()
    resolved: TeacherPersona | None = None

    if persona_id:
        try:
            resolved = load_persona(persona_id, pdir)
        except PersonaNotFoundError:
            console.print(f"[red]Persona not found: {persona_id} (looked in {pdir})[/red]")
            raise typer.Exit(1)
    elif style_source:
        return None, _resolve_style_context(style_source)

    if subject:
        domain = _load_domain_overlay(subject, pdir)
        if domain is not None:
            if resolved is None:
                resolved = load_persona("default", pdir)
            resolved = merge_domain_overlay(resolved, domain)

    return resolved, None


def _save_quality_report(
    extraction_path: Path,
    *,
    persona_id: str | None = None,
    label: str | None = None,
    elapsed_seconds: float | None = None,
) -> tuple[Path, float | None]:
    """Write quality_report.json next to extraction.json."""
    from .curriculum.models import CurriculumExtractionResult
    from .quality import RunMetadata, evaluate_extraction

    extraction = CurriculumExtractionResult.load(extraction_path)
    report = evaluate_extraction(
        extraction,
        run=RunMetadata(
            label=label or extraction_path.parent.name,
            persona_id=persona_id,
            source_path=str(extraction_path),
            total_elapsed_seconds=elapsed_seconds,
        ),
    )
    out = extraction_path.parent / "quality_report.json"
    report.save(str(out))
    return out, report.indices.lecture_excellence_score


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
    single_chapter: Optional[str] = typer.Option(
        None,
        "--single-chapter",
        help="Treat the whole PDF as one chapter with this title (bypass TOC detection)",
    ),
    style_source: Optional[str] = typer.Option(
        None,
        "--style-source",
        help=(
            "Deprecated: use --persona. Path to a file (or inline text) with a "
            "master-teacher style guide woven into lesson plans."
        ),
    ),
    persona: Optional[str] = typer.Option(
        None,
        "--persona",
        help="Teacher persona id (loads data_pre_compute_v2/personas/{id}.yaml).",
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

    resolved_persona, style_context = _resolve_persona(
        persona, style_source, subject=subject
    )

    console.print("\n[bold]Curriculum Pipeline v2[/bold]")
    console.print(f"  PDF: {pdf_path}")
    console.print(f"  Subject: {subject}")
    console.print(f"  LLM: {cfg.llm.provider} ({cfg.llm.model})")
    console.print(f"  TTS: {cfg.tts.provider} ({cfg.tts.voice})")
    if chapter_filter:
        console.print(f"  Chapters (by index): {chapter_filter}")
    if chapter_name:
        console.print(f"  Chapter (by name): {chapter_name}")
    if single_chapter:
        console.print(f"  Single chapter (TOC bypassed): {single_chapter}")
    if persona:
        console.print(f"  Persona: {persona} (v{resolved_persona.persona_version if resolved_persona else '?'})")
    elif style_source:
        console.print(
            f"  Style source: {style_source} ({len(style_context or '')} chars) "
            "[yellow](deprecated — use --persona)[/yellow]"
        )
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
            single_chapter_title=single_chapter,
            force=force,
            skip_neo4j=skip_neo4j,
            skip_embeddings=skip_embeddings,
            skip_tts=skip_tts,
            skip_visuals=skip_visuals,
            skip_questions=skip_questions,
            skip_prereqs=skip_prereqs,
            skip_beat_narration=skip_beat_narration,
            skip_diagram_qa=skip_diagram_qa,
            persona=resolved_persona,
            style_context=style_context,
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
        quality_path, les_score = _save_quality_report(
            path,
            persona_id=persona,
            elapsed_seconds=report.total_elapsed_seconds,
        )
        les_msg = f" (LES={les_score:.1f})" if les_score is not None else ""
        console.print(f"  Quality report saved: {quality_path}{les_msg}")


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


@app.command("realign-highlights")
def realign_highlights(
    extraction_path: str = typer.Argument(..., help="Path to extraction.json"),
    chapter: Optional[str] = typer.Option(
        None,
        "--chapter",
        help="Chapter title substring (case-insensitive); realign all chapters if omitted.",
    ),
    skip_neo4j: bool = typer.Option(
        False, "--skip-neo4j", help="Skip writing the updated manifest to Neo4j."
    ),
    skip_audio: bool = typer.Option(
        False,
        "--skip-audio",
        help="Only rewrite markers in narration_text; don't re-TTS or rebuild the manifest.",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Re-decide diagram highlights (FOCUS/POINT/TRACE) semantically, post-hoc.

    The lesson planner authored highlight markers BEFORE the diagrams existed,
    guessing which element to point at — so they're wrong most of the time. This
    command strips them and re-decides each one against the REAL on-screen
    diagram: per narration sentence, an LLM picks the element that sentence is
    actually explaining (semantically, even when unnamed) or nothing. Sustained
    highlights hold across consecutive sentences about the same part.

    Cheap: ~1 LLM call per topic, local Kokoro TTS, no planner/diagram re-run.
    """
    _setup_logging(verbose)

    if not Path(extraction_path).exists():
        console.print(f"[red]File not found: {extraction_path}[/red]")
        raise typer.Exit(1)

    from .curriculum.ingestion.cypher_generator import CypherGenerator
    from .curriculum.ingestion.neo4j_writer import Neo4jWriter
    from .curriculum.lecture_plan.highlight_aligner import (
        AlignerReport,
        SemanticHighlightAligner,
        _split_topic_blocks,
    )
    from .curriculum.lecture_script.models import ChapterScript
    from .curriculum.media.audio_pipeline import AudioPipeline
    from .curriculum.models import CurriculumExtractionResult
    from .tts.factory import create_tts_provider

    cfg = _load_config(config)
    extraction = CurriculumExtractionResult.load(extraction_path)

    if chapter:
        needle = chapter.lower()
        targets = [ch for ch in extraction.chapters if needle in ch.title.lower()]
        if not targets:
            console.print(
                f"[red]No chapter matches {chapter!r}.[/red] Available: "
                + ", ".join(f"'{c.title}'" for c in extraction.chapters)
            )
            raise typer.Exit(1)
    else:
        targets = list(extraction.chapters)

    # render_data per diagram is the aligner's ground truth (dictionary + title).
    diagrams_by_id = {d.diagram_id: (d.render_data or {}) for d in extraction.diagrams}

    console.print(
        f"\n[bold]realign-highlights[/bold] — {len(targets)} chapter(s) from {extraction_path}"
    )

    async def _run() -> None:
        aligner = SemanticHighlightAligner(cfg.llm)

        # 1. Re-decide markers in each chapter's narration_text.
        chapter_scripts: dict[str, ChapterScript] = {}
        for ch in targets:
            if not ch.narration_text:
                console.print(
                    f"  [yellow]skip {ch.chapter_id}: no narration_text[/yellow]"
                )
                continue
            report = AlignerReport()
            new_text = await aligner.realign_chapter_narration(
                ch.narration_text, diagrams_by_id, report
            )
            console.print(f"  • {ch.title}: {report.summary()}")
            for w in report.warnings[:3]:
                console.print(f"      [yellow]{w}[/yellow]")

            # 2. Rebuild ChapterScript segments from the realigned narration.
            segments = []
            for header, body in _split_topic_blocks(new_text):
                if not header:
                    continue  # leading preamble (none in practice)
                tid = header[len("<<TOPIC_START:") : -2]
                text = body.strip()
                segments.append(
                    {
                        "topic_id": tid,
                        "narration_chapter": text,
                        "narration_standalone": text,
                    }
                )
            ch.assembled_chapter_script = {
                "chapter_id": ch.chapter_id,
                "segments": segments,
            }
            chapter_scripts[ch.chapter_id] = ChapterScript(
                chapter_id=ch.chapter_id, segments=segments
            )
            # audio_pipeline APPENDS to narration_text, so clear it first to
            # avoid doubling the recovered text on re-run.
            ch.narration_text = ""

        if skip_audio:
            extraction.save(extraction_path)
            console.print(
                f"\n  [yellow]--skip-audio: markers rewritten only.[/yellow] "
                f"saved → {extraction_path}"
            )
            return

        if not chapter_scripts:
            console.print("[red]Nothing to realign.[/red]")
            raise typer.Exit(1)

        # 3. Re-TTS + rebuild manifest from the realigned scripts (local Kokoro).
        tts = create_tts_provider(cfg.tts)
        audio_pipeline = AudioPipeline(tts, cfg.tts, cfg.artifacts, layout=cfg.layout)
        report = await audio_pipeline.build_for_book(
            targets,
            extraction.topics,
            chapter_scripts,
            diagrams=extraction.diagrams,
        )
        console.print(f"\n  {report.summary()}")

        # 4. Persist + (optionally) re-hydrate Neo4j so the preview picks it up.
        extraction.save(extraction_path)
        console.print(f"  extraction saved → {extraction_path}")
        if skip_neo4j:
            console.print("  [yellow]skipping Neo4j write (--skip-neo4j)[/yellow]")
            return
        cypher_gen = CypherGenerator()
        statements = cypher_gen.generate(extraction)
        async with Neo4jWriter(cfg.neo4j) as writer:
            ingest_report = await writer.ingest(
                statements, embedding_dimensions=cfg.embedding.dimensions
            )
            console.print(f"  {ingest_report.summary()}")

    asyncio.run(_run())
    console.print("\n[bold green]Done.[/bold green]")


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


@app.command("ingest-spine")
def ingest_spine(
    pdf_path: str = typer.Argument(..., help="Path to PDF textbook"),
    subject: str = typer.Option(..., "--subject", "-s"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    chapters: Optional[str] = typer.Option(None, "--chapters"),
    chapter_name: Optional[str] = typer.Option(None, "--chapter"),
    single_chapter: Optional[str] = typer.Option(None, "--single-chapter"),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Checkpoint JSON path (default: artifacts/spine/extraction_{subject}.json)",
    ),
    force: bool = typer.Option(False, "--force"),
    skip_questions: bool = typer.Option(False, "--skip-questions"),
    skip_prereqs: bool = typer.Option(False, "--skip-prereqs"),
    skip_visuals: bool = typer.Option(False, "--skip-visuals"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run spine phases 1–7 only; write SpineCheckpoint JSON."""
    _setup_logging(verbose)
    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        raise typer.Exit(1)

    cfg = _load_config(config)
    chapter_filter = None
    if chapters:
        chapter_filter = [int(c.strip()) for c in chapters.split(",")]

    out_path = Path(output) if output else (
        Path(cfg.artifacts.base_dir) / "spine" / f"extraction_{subject}.json"
    )

    from .pipeline import CurriculumPipelineV2

    pipeline = CurriculumPipelineV2(cfg)

    def on_stage(stage: str, detail: str) -> None:
        console.print(f"  [dim][{stage}] {detail}[/dim]")

    checkpoint = asyncio.run(
        pipeline.run_spine(
            pdf_path,
            subject,
            chapters=chapter_filter,
            chapter_name=chapter_name,
            single_chapter_title=single_chapter,
            force=force,
            skip_questions=skip_questions,
            skip_prereqs=skip_prereqs,
            skip_visuals=skip_visuals,
            checkpoint_path=out_path,
            on_stage=on_stage,
        )
    )
    console.print(f"\n[bold green]Spine checkpoint written[/bold green]")
    console.print(f"  version: {checkpoint.spine_version}")
    console.print(f"  path: {out_path}")


@app.command("generate-variant")
def generate_variant(
    checkpoint: str = typer.Option(..., "--checkpoint", help="Spine checkpoint JSON"),
    persona: Optional[str] = typer.Option(
        None, "--persona", help="Persona id (default.yaml if omitted)"
    ),
    style_source: Optional[str] = typer.Option(None, "--style-source"),
    chapters: Optional[str] = typer.Option(
        None,
        "--chapters",
        help="Comma-separated chapter_ids (all chapters if omitted)",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    skip_neo4j: bool = typer.Option(False, "--skip-neo4j"),
    skip_embeddings: bool = typer.Option(False, "--skip-embeddings"),
    skip_tts: bool = typer.Option(False, "--skip-tts"),
    skip_visuals: bool = typer.Option(False, "--skip-visuals"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run variant phases 7a–12 from a spine checkpoint (no PDF)."""
    _setup_logging(verbose)
    if not Path(checkpoint).exists():
        console.print(f"[red]Checkpoint not found: {checkpoint}[/red]")
        raise typer.Exit(1)

    cfg = _load_config(config)
    from .curriculum.ingestion.spine_checkpoint import load_checkpoint

    ckpt_subject = load_checkpoint(checkpoint).subject
    resolved_persona, style_context = _resolve_persona(
        persona, style_source, subject=ckpt_subject
    )
    chapter_ids = (
        [c.strip() for c in chapters.split(",") if c.strip()] if chapters else None
    )

    from .pipeline import CurriculumPipelineV2

    pipeline = CurriculumPipelineV2(cfg)

    def on_stage(stage: str, detail: str) -> None:
        console.print(f"  [dim][{stage}] {detail}[/dim]")

    report = asyncio.run(
        pipeline.run_variant(
            checkpoint,
            persona=resolved_persona,
            style_context=style_context,
            chapter_ids=chapter_ids,
            skip_neo4j=skip_neo4j,
            skip_embeddings=skip_embeddings,
            skip_tts=skip_tts,
            skip_visuals=skip_visuals,
            on_stage=on_stage,
        )
    )

    console.print("\n[bold green]Variant generation complete[/bold green]\n")
    console.print(report.summary())
    for w in report.warnings:
        console.print(f"  [yellow]warning:[/yellow] {w}")

    if output and report.extraction:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        report.extraction.save(out)
        console.print(f"\n  Extraction saved: {out}")
        quality_path, les_score = _save_quality_report(
            out,
            persona_id=persona,
            elapsed_seconds=report.total_elapsed_seconds,
        )
        les_msg = f" (LES={les_score:.1f})" if les_score is not None else ""
        console.print(f"  Quality report saved: {quality_path}{les_msg}")


@app.command("generate-variants")
def generate_variants(
    checkpoint: str = typer.Option(..., "--checkpoint", help="Spine checkpoint JSON"),
    personas: str = typer.Option(
        ...,
        "--personas",
        help="Comma-separated persona ids (e.g. default,feynman,finance_teacher)",
    ),
    style_source: Optional[str] = typer.Option(None, "--style-source"),
    chapters: Optional[str] = typer.Option(
        None,
        "--chapters",
        help="Comma-separated chapter_ids (all chapters if omitted)",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    output_dir: Optional[str] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Base directory; each persona writes {dir}/{persona}/extraction.json",
    ),
    skip_neo4j: bool = typer.Option(False, "--skip-neo4j"),
    skip_embeddings: bool = typer.Option(False, "--skip-embeddings"),
    skip_tts: bool = typer.Option(False, "--skip-tts"),
    skip_visuals: bool = typer.Option(False, "--skip-visuals"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate multiple persona variants from one spine checkpoint."""
    persona_ids = [p.strip() for p in personas.split(",") if p.strip()]
    if not persona_ids:
        console.print("[red]No personas provided (use --personas a,b,c)[/red]")
        raise typer.Exit(1)

    for persona_id in persona_ids:
        console.print(f"\n[bold cyan]── Persona: {persona_id} ──[/bold cyan]")
        out_path = None
        if output_dir:
            out_path = str(Path(output_dir) / persona_id / "extraction.json")
        generate_variant(
            checkpoint=checkpoint,
            persona=persona_id,
            style_source=style_source,
            chapters=chapters,
            config=config,
            output=out_path,
            skip_neo4j=skip_neo4j,
            skip_embeddings=skip_embeddings,
            skip_tts=skip_tts,
            skip_visuals=skip_visuals,
            verbose=verbose,
        )


@app.command("evaluate-quality")
def evaluate_quality(
    extraction_path: str = typer.Argument(..., help="Path to extraction.json"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Write quality report JSON"
    ),
    label: Optional[str] = typer.Option(
        None, "--label", help="Run label for A/B comparison"
    ),
    persona: Optional[str] = typer.Option(
        None, "--persona", help="Persona id (stored in report metadata)"
    ),
    elapsed: Optional[float] = typer.Option(
        None, "--elapsed", help="Pipeline elapsed seconds (P-14)"
    ),
    with_judges: bool = typer.Option(
        False,
        "--with-judges",
        help="Run NarrationJudge LLM rubric (EDU-domain-fit, etc.)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Compute ULQF quality metrics from a saved extraction.json."""
    import asyncio

    _setup_logging(verbose)
    path = Path(extraction_path)
    if not path.exists():
        console.print(f"[red]File not found: {extraction_path}[/red]")
        raise typer.Exit(1)

    from .curriculum.models import CurriculumExtractionResult
    from .quality import RunMetadata, evaluate_extraction, evaluate_extraction_async

    extraction = CurriculumExtractionResult.load(path)
    run = RunMetadata(
        label=label or path.parent.name,
        persona_id=persona,
        source_path=str(path),
        total_elapsed_seconds=elapsed,
    )
    if with_judges:
        report = asyncio.run(
            evaluate_extraction_async(extraction, run=run, with_judges=True)
        )
    else:
        report = evaluate_extraction(extraction, run=run)

    table = Table(title="ULQF Quality Indices")
    table.add_column("Index", style="cyan")
    table.add_column("Score", justify="right")
    for key, attr in (
        ("LES", "lecture_excellence_score"),
        ("TQI", "technical_quality_index"),
        ("EQI", "educational_quality_index"),
        ("LEI", "learning_effectiveness_index"),
    ):
        val = getattr(report.indices, attr)
        table.add_row(key, f"{val:.1f}" if val is not None else "—")
    console.print(table)

    run_metrics = [m for m in report.metrics if m.level == "run"]
    detail = Table(title="Key Metrics")
    detail.add_column("ID", style="dim")
    detail.add_column("Metric")
    detail.add_column("Value", justify="right")
    for mid in (
        "CE-01",
        "LP-01",
        "LP-08",
        "LP-16",
        "LP-31",
        "CE-12",
        "NR-48",
        "EDU-62",
        "EDU-domain-fit",
        "BE-01",
    ):
        m = next((x for x in run_metrics if x.metric_id == mid), None)
        if m:
            detail.add_row(mid, m.name, str(m.value))
    console.print(detail)

    out_path = output or str(path.parent / "quality_report.json")
    report.save(out_path)
    console.print(f"\n[green]Quality report saved:[/green] {out_path}")


@app.command("compare-quality")
def compare_quality(
    baseline: str = typer.Argument(..., help="Baseline quality_report.json"),
    candidate: str = typer.Argument(..., help="Candidate quality_report.json"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Write comparison JSON"
    ),
    baseline_label: Optional[str] = typer.Option(None, "--baseline-label"),
    candidate_label: Optional[str] = typer.Option(None, "--candidate-label"),
) -> None:
    """Compare two ULQF quality reports (e.g. persona A vs B)."""
    for p in (baseline, candidate):
        if not Path(p).exists():
            console.print(f"[red]File not found: {p}[/red]")
            raise typer.Exit(1)

    from .quality import QualityReport, compare_reports

    base_report = QualityReport.load(baseline)
    cand_report = QualityReport.load(candidate)
    comparison = compare_reports(
        base_report,
        cand_report,
        baseline_label=baseline_label,
        candidate_label=candidate_label,
    )

    table = Table(
        title=f"Quality Comparison: {comparison.baseline_label} → {comparison.candidate_label}"
    )
    table.add_column("Index", style="cyan")
    table.add_column("Δ", justify="right")
    for key, delta in comparison.index_deltas.items():
        style = "green" if delta > 0 else "red" if delta < 0 else ""
        table.add_row(key, f"{delta:+.1f}", style=style)
    console.print(table)

    movers = Table(title="Notable Metric Changes")
    movers.add_column("ID", style="dim")
    movers.add_column("Metric")
    movers.add_column("Baseline", justify="right")
    movers.add_column("Candidate", justify="right")
    movers.add_column("Δ", justify="right")
    scored = [
        d
        for d in comparison.metric_deltas
        if d.delta is not None and d.delta != 0 and d.metric_id not in ("TQI", "EQI", "LEI", "LES")
    ]
    scored.sort(key=lambda d: abs(d.delta or 0), reverse=True)
    for d in scored[:12]:
        style = "green" if d.improved else "red" if d.improved is False else ""
        movers.add_row(
            d.metric_id,
            d.name,
            str(d.baseline),
            str(d.candidate),
            f"{d.delta:+.4g}",
            style=style,
        )
    console.print(movers)

    out_path = output or "quality_comparison.json"
    comparison.save(out_path)
    console.print(f"\n[green]Comparison saved:[/green] {out_path}")


if __name__ == "__main__":
    app()
