"""End-to-end orchestrator for v2 precompute.

12 phases, each a discrete method, each guarded by the idempotency snapshot:

  [ 1] parse PDF + TOC
  [ 2] anchors per chapter
  [ 3] BookSkeleton (one LLM call)
  [ 4] Topics (per anchored section)
  [ 5] enrichment: Diagrams + Questions (with multi-model judge)
  [ 6] within-book PREREQ linking
  [ 7] validation gate (structural + semantic + render)
  [ 8] lecture script (chapter + standalone narrations)
  [ 9] TTS audio + manifests (Kokoro)
  [10] diagram fallback rendering (SVG → PNG)
  [11] embeddings (OpenAI)
  [12] Neo4j ingest + verify
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from neo4j import AsyncGraphDatabase

from .config import PipelineConfig
from .curriculum.anchors import DeterministicAnchorExtractor
from .curriculum.anchors.models import ExtractionAnchors
from .curriculum.enrichment.orchestrator import EnrichmentOrchestrator
from .curriculum.enrichment.prereqs import PrereqLinker
from .curriculum.id_generator import generate_chapter_uid
from .curriculum.ingestion.cypher_generator import CypherGenerator
from .curriculum.ingestion.embedding_generator import EmbeddingGenerator, create_embedding_provider
from .curriculum.ingestion.idempotency import IdempotencySnapshot, take_snapshot
from .curriculum.ingestion.neo4j_writer import Neo4jWriter
from .curriculum.lecture_script.script_writer import ChapterScript, ScriptWriter
from .curriculum.media.artifact_store import ArtifactStore
from .curriculum.media.audio_pipeline import AudioPipeline
from .curriculum.media.diagram_renderer import DiagramFallbackRenderer
from .curriculum.models import (
    Chapter as ChapterNode,
    CurriculumExtractionResult,
    ExtractionSource,
)
from .curriculum.schema import verify_ingestion
from .curriculum.skeleton_extractor import SkeletonExtractor
from .curriculum.topic_extractor import TopicExtractor
from .curriculum.validation.gate import GateReport, ValidationGate
from .llm.factory import create_llm_provider
from .pdf.parser import PDFParser
from .pdf.toc import Chapter as PdfChapter, TOCExtractor
from .tts.factory import create_tts_provider

logger = logging.getLogger(__name__)

StageCallback = Callable[[str, str], None]


@dataclass
class PipelineReport:
    pdf_path: str = ""
    subject: str = ""
    extraction: CurriculumExtractionResult | None = None
    snapshot: IdempotencySnapshot | None = None
    validation: GateReport | None = None
    total_elapsed_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)
    skipped_phases: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Pipeline complete — {self.pdf_path}", f"  Subject: {self.subject}"]
        if self.extraction:
            counts = self.extraction.counts()
            lines.append(
                f"  Counts: {counts['chapters']} chapters, "
                f"{counts['topics']} topics, "
                f"{counts['diagrams']} diagrams, "
                f"{counts['questions']} questions"
            )
        if self.skipped_phases:
            lines.append(f"  Skipped: {', '.join(self.skipped_phases)}")
        lines.append(f"  Total time: {self.total_elapsed_seconds:.1f}s")
        return "\n".join(lines)


class CurriculumPipelineV2:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.pdf_parser = PDFParser(config.pdf)
        self.toc_extractor = TOCExtractor()
        self.anchor_extractor = DeterministicAnchorExtractor()
        self._llm = None
        self._tts = None
        self._artifact_store: ArtifactStore | None = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = create_llm_provider(self.config.llm)
        return self._llm

    @property
    def tts(self):
        if self._tts is None:
            self._tts = create_tts_provider(self.config.tts)
        return self._tts

    @property
    def artifact_store(self) -> ArtifactStore:
        if self._artifact_store is None:
            self._artifact_store = ArtifactStore(self.config.artifacts)
        return self._artifact_store

    async def run(
        self,
        pdf_path: str | Path,
        subject: str,
        *,
        chapters: list[int] | None = None,
        chapter_name: str | None = None,
        force: bool = False,
        skip_neo4j: bool = False,
        skip_embeddings: bool = False,
        skip_tts: bool = False,
        skip_visuals: bool = False,
        skip_questions: bool = False,
        skip_prereqs: bool = False,
        on_stage: StageCallback | None = None,
    ) -> PipelineReport:
        start = time.monotonic()
        report = PipelineReport(pdf_path=str(pdf_path), subject=subject)
        notify = on_stage or (lambda _s, _d: None)

        # --- Phase 1: parse PDF + TOC ---
        notify("parse", "Parsing PDF...")
        pdf_content = self.pdf_parser.parse(Path(pdf_path))
        all_detected = self.toc_extractor.extract_chapters(pdf_content)
        # Preserve each chapter's ORIGINAL position before filtering so that
        # Chapter.chapter_index in Neo4j always matches the book's TOC.
        indexed_chapters = list(enumerate(all_detected, 1))
        indexed_chapters = self._filter_indexed_chapters(
            indexed_chapters, chapters, chapter_name,
        )
        logger.info(
            "Parsed %d pages, %d chapters to process",
            pdf_content.total_pages, len(indexed_chapters),
        )
        if not indexed_chapters:
            report.warnings.append("No chapters matched the filter; nothing to do")
            report.total_elapsed_seconds = time.monotonic() - start
            return report
        detected_chapters = [ch for _, ch in indexed_chapters]

        # --- Idempotency snapshot ---
        if force or skip_neo4j:
            snapshot = IdempotencySnapshot.empty()
        else:
            notify("snapshot", "Reading existing graph state from Neo4j...")
            snapshot = await self._take_snapshot_safely()
        report.snapshot = snapshot

        # --- Phase 2: anchors per chapter ---
        notify("anchors", "Extracting section anchors...")
        anchors_by_chapter: dict[str, ExtractionAnchors] = {}
        for chapter in detected_chapters:
            chapter_id = generate_chapter_uid(subject, chapter.title)
            anchors = self.anchor_extractor.extract_for_chapter(pdf_content, chapter)
            anchors_by_chapter[chapter_id] = anchors

        # --- Phase 3: BookSkeleton ---
        notify("skeleton", "Extracting BookSkeleton via LLM...")
        skeleton_extractor = SkeletonExtractor(self.llm)
        skeleton = skeleton_extractor.extract(
            pdf_content, detected_chapters, subject_hint=subject,
        )

        # --- Phase 4: Topics per chapter ---
        notify("topics", "Extracting topics per section...")
        topic_extractor = TopicExtractor(self.llm)
        all_topics = []
        chapter_nodes: list[ChapterNode] = []
        for ch_index, chapter in indexed_chapters:
            chapter_id = generate_chapter_uid(subject, chapter.title)
            chapter_text = pdf_content.get_text_for_range(chapter.start_page, chapter.end_page)
            anchors = anchors_by_chapter[chapter_id]
            topics, _ = topic_extractor.extract_chapter_topics(
                chapter_text=chapter_text,
                chapter_title=chapter.title,
                chapter_index=ch_index,
                anchors=anchors,
                skeleton=skeleton,
                subject=subject,
                existing_topic_ids=snapshot.existing_topic_ids,
            )
            all_topics.extend(topics)
            skel_chapter = skeleton.chapter_by_title(chapter.title)
            chapter_nodes.append(ChapterNode(
                chapter_id=chapter_id,
                chapter_index=ch_index,
                title=chapter.title,
                summary=(skel_chapter.summary if skel_chapter else ""),
                page_start=chapter.start_page,
                page_end=chapter.end_page,
                topic_ids=[t.topic_id for t in topics],
            ))

        # --- Phase 5: enrichment (diagrams + questions) ---
        diagrams = []
        questions = []
        topics_needing_enrichment = [
            t for t in all_topics
            if (not t.has_diagram_ids and not skip_visuals)
            or (not t.has_question_ids and not skip_questions)
        ]
        if topics_needing_enrichment and not (skip_visuals and skip_questions):
            notify("enrichment", f"Enriching {len(topics_needing_enrichment)} topics (diagrams + questions)...")
            orchestrator = EnrichmentOrchestrator(self.llm, self.config.validation)
            diagrams, questions, _ = await orchestrator.enrich(
                topics_needing_enrichment,
                existing_diagram_ids=snapshot.existing_diagram_ids,
                existing_question_ids=snapshot.existing_question_ids,
            )
        else:
            report.skipped_phases.append("enrichment")

        # --- Phase 6: PREREQ linking (full book) ---
        if not skip_prereqs and len(all_topics) > 1:
            notify("prereqs", "Linking prerequisites...")
            PrereqLinker(self.llm).link(all_topics)
        else:
            report.skipped_phases.append("prereqs")

        # --- Assemble interim extraction ---
        extraction = CurriculumExtractionResult(
            subject=subject,
            textbook_title=skeleton.textbook_title,
            source=ExtractionSource(
                textbook_title=skeleton.textbook_title,
                extractor_model=self.config.llm.model,
            ),
            book_skeleton=skeleton,
            chapters=chapter_nodes,
            topics=all_topics,
            diagrams=diagrams,
            questions=questions,
        )

        # --- Phase 7: validation gate ---
        notify("validate", "Running validation gate...")
        gate = ValidationGate(self.llm)
        report.validation = gate.run(extraction, anchors_by_chapter)

        # --- Phase 8 + 9: lecture script + TTS ---
        if not skip_tts:
            notify("script", "Writing lecture scripts...")
            script_writer = ScriptWriter(self.llm)
            diagrams_by_topic = self._group_diagrams(diagrams)
            topics_by_chapter = self._group_topics(all_topics)
            chapter_scripts, _ = script_writer.write_for_all(
                chapter_nodes, topics_by_chapter, diagrams_by_topic,
                existing_chapter_ids_with_audio=snapshot.chapter_ids_with_audio,
            )

            if chapter_scripts:
                notify("tts", "Rendering TTS audio...")
                audio_pipeline = AudioPipeline(
                    self.tts, self.config.tts, self.config.artifacts,
                )
                await audio_pipeline.build_for_book(chapter_nodes, all_topics, chapter_scripts)
        else:
            report.skipped_phases.extend(["lecture_script", "tts"])

        # --- Phase 10: diagram fallback rendering ---
        if not skip_visuals and diagrams:
            notify("diagram_render", "Rendering diagram fallback images...")
            DiagramFallbackRenderer(self.artifact_store).render_all(diagrams)
        else:
            report.skipped_phases.append("diagram_render")

        # --- Phase 11: embeddings ---
        if not skip_embeddings:
            notify("embed", f"Generating embeddings ({self.config.embedding.provider})...")
            try:
                provider = create_embedding_provider(self.config.embedding)
                embedder = EmbeddingGenerator(provider, batch_size=self.config.embedding.batch_size)
                await embedder.embed_extraction(
                    extraction,
                    existing_chapter_ids_with_embedding=snapshot.chapter_ids_with_embedding,
                    existing_topic_ids_with_embedding=snapshot.topic_ids_with_embedding,
                )
            except Exception as e:
                logger.exception("Embeddings failed (non-fatal): %s", e)
                report.warnings.append(f"embeddings failed: {e}")
        else:
            report.skipped_phases.append("embeddings")

        # --- Phase 12: Neo4j ingest + verify ---
        if not skip_neo4j:
            notify("ingest", "Ingesting to Neo4j...")
            await self._ingest(extraction, report)
        else:
            report.skipped_phases.append("ingest")

        report.extraction = extraction
        report.total_elapsed_seconds = time.monotonic() - start
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_indexed_chapters(
        indexed: list[tuple[int, PdfChapter]],
        chapter_indices: list[int] | None,
        chapter_name: str | None,
    ) -> list[tuple[int, PdfChapter]]:
        """Filter (index, chapter) pairs while preserving the original index."""
        if chapter_indices:
            return [(i, c) for (i, c) in indexed if i in chapter_indices]
        if chapter_name:
            name_lc = chapter_name.lower()
            return [(i, c) for (i, c) in indexed if name_lc in c.title.lower()]
        return indexed

    async def _take_snapshot_safely(self) -> IdempotencySnapshot:
        driver = AsyncGraphDatabase.driver(
            self.config.neo4j.uri,
            auth=(self.config.neo4j.username, self.config.neo4j.password),
        )
        try:
            return await take_snapshot(driver, database=self.config.neo4j.database)
        except Exception as e:
            logger.warning("Idempotency snapshot failed (treating as empty): %s", e)
            return IdempotencySnapshot.empty()
        finally:
            await driver.close()

    @staticmethod
    def _group_diagrams(diagrams: list) -> dict[str, list]:
        out: dict[str, list] = {}
        for d in diagrams:
            for tid in d.linked_topic_ids:
                out.setdefault(tid, []).append(d)
        return out

    @staticmethod
    def _group_topics(topics: list) -> dict[str, list]:
        out: dict[str, list] = {}
        for t in topics:
            out.setdefault(t.chapter_id, []).append(t)
        return out

    async def _ingest(
        self, extraction: CurriculumExtractionResult, report: PipelineReport
    ) -> None:
        cypher_gen = CypherGenerator()
        statements = cypher_gen.generate(extraction)

        async with Neo4jWriter(self.config.neo4j) as writer:
            await writer.ingest(
                statements,
                embedding_dimensions=self.config.embedding.dimensions,
            )
            try:
                expected_ids = (
                    {c.chapter_id for c in extraction.chapters}
                    | {t.topic_id for t in extraction.topics}
                    | {d.diagram_id for d in extraction.diagrams}
                    | {q.question_id for q in extraction.questions}
                )
                expected_rels = sum(
                    1 + (1 if t.next_topic_id else 0)
                    + len(t.prereq_topic_ids)
                    + len(t.has_diagram_ids)
                    + len(t.has_question_ids)
                    for t in extraction.topics
                )
                verification = await verify_ingestion(
                    writer.driver,
                    expected_node_ids=expected_ids,
                    expected_rel_count=expected_rels,
                    database=self.config.neo4j.database,
                )
                logger.info(verification.summary())
                if not verification.passed:
                    report.warnings.append(
                        f"verification failed: {verification.error_count} errors"
                    )
            except Exception as e:
                logger.exception("Verification failed (non-fatal): %s", e)
                report.warnings.append(f"verification error: {e}")
