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
from typing import Any, Callable

from neo4j import AsyncGraphDatabase

from .config import PipelineConfig
from .curriculum.anchors import DeterministicAnchorExtractor
from .curriculum.anchors.models import ExtractionAnchors
from .curriculum.beat_narration import BeatNarrationWriter
from .curriculum.enrichment.diagram_qa import DiagramQA, QAResult
from .curriculum.enrichment.diagram_spec_generator import (
    DESIGN_DIAGRAM_TOOLS,
    DiagramSpecGenerator,
)
from .curriculum.enrichment.orchestrator import EnrichmentOrchestrator
from .curriculum.enrichment.prereqs import PrereqLinker
from .curriculum.id_generator import generate_chapter_uid
from .curriculum.ingestion.cypher_generator import CypherGenerator
from .curriculum.ingestion.embedding_generator import (
    EmbeddingGenerator,
    create_embedding_provider,
)
from .curriculum.ingestion.idempotency import IdempotencySnapshot, take_snapshot
from .curriculum.ingestion.neo4j_writer import Neo4jWriter
from .curriculum.lecture_plan.chapter_planner import ChapterLecturePlanner
from .curriculum.lecture_plan.concept_planner import ConceptPlanner
from .curriculum.lecture_plan.curriculum_adapter import CurriculumAdapter
from .curriculum.lecture_plan.book_example_weaver import BookExampleWeaver
from .curriculum.lecture_plan.lesson_diagram_generator import LessonDiagramGenerator
from .curriculum.lecture_plan.lesson_judge import PlanJudge
from .curriculum.lecture_plan.lesson_narrator import LessonNarrator, TopicNarration
from .curriculum.lecture_plan.lesson_planner import LessonPlanner
from .curriculum.lecture_plan.lesson_prosody import LessonProsody
from .curriculum.lecture_plan.lesson_quality_gate import _diagram_id_short_to_long
from .curriculum.validation.book_coverage import validate_book_coverage
from .curriculum.lecture_plan.lesson_quality_gate import (
    GateReport as LessonGateReport,
    LessonQualityGate,
)
from .curriculum.lecture_script.models import ChapterScript
from .curriculum.length_enforcer import LengthEnforcer
from .curriculum.script_assembler import ScriptAssembler
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
        single_chapter_title: str | None = None,
        force: bool = False,
        skip_neo4j: bool = False,
        skip_embeddings: bool = False,
        skip_tts: bool = False,
        skip_visuals: bool = False,
        skip_questions: bool = False,
        skip_prereqs: bool = False,
        skip_lecture_plan: bool = False,
        skip_diagram_qa: bool = False,
        skip_beat_narration: bool = False,
        on_stage: StageCallback | None = None,
    ) -> PipelineReport:
        start = time.monotonic()
        report = PipelineReport(pdf_path=str(pdf_path), subject=subject)
        notify = on_stage or (lambda _s, _d: None)

        # --- Phase 1: parse PDF + TOC ---
        notify("parse", "Parsing PDF...")
        pdf_content = self.pdf_parser.parse(Path(pdf_path))
        if single_chapter_title:
            # Standalone-chapter PDF: skip TOC detection entirely and treat
            # the whole document as one chapter with the caller-supplied
            # title. Used for NCERT-style per-chapter PDFs and any other
            # single-chapter document where TOC parsing can't help.
            synthetic = PdfChapter(
                title=single_chapter_title,
                level=1,
                start_page=1,
                end_page=pdf_content.total_pages,
            )
            all_detected = [synthetic]
        else:
            all_detected = self.toc_extractor.extract_chapters(pdf_content)
        # Preserve each chapter's ORIGINAL position before filtering so that
        # Chapter.chapter_index in Neo4j always matches the book's TOC.
        indexed_chapters = list(enumerate(all_detected, 1))
        indexed_chapters = self._filter_indexed_chapters(
            indexed_chapters,
            chapters,
            chapter_name,
        )
        logger.info(
            "Parsed %d pages, %d chapters to process",
            pdf_content.total_pages,
            len(indexed_chapters),
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
            pdf_content,
            detected_chapters,
            subject_hint=subject,
        )

        # --- Phase 4: Topics per chapter ---
        notify("topics", "Extracting topics per section...")
        topic_extractor = TopicExtractor(self.llm)
        all_topics = []
        chapter_nodes: list[ChapterNode] = []
        for ch_index, chapter in indexed_chapters:
            chapter_id = generate_chapter_uid(subject, chapter.title)
            chapter_text = pdf_content.get_text_for_range(
                chapter.start_page, chapter.end_page
            )
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
            chapter_nodes.append(
                ChapterNode(
                    chapter_id=chapter_id,
                    chapter_index=ch_index,
                    title=chapter.title,
                    summary=(skel_chapter.summary if skel_chapter else ""),
                    page_start=chapter.start_page,
                    page_end=chapter.end_page,
                    topic_ids=[t.topic_id for t in topics],
                )
            )

        # --- Phase 5: enrichment (diagrams + questions) ---
        diagrams = []
        questions = []
        topics_needing_enrichment = [
            t
            for t in all_topics
            if (not t.has_diagram_ids and not skip_visuals)
            or (not t.has_question_ids and not skip_questions)
        ]
        if topics_needing_enrichment and not (skip_visuals and skip_questions):
            notify(
                "enrichment",
                f"Enriching {len(topics_needing_enrichment)} topics (diagrams + questions)...",
            )
            orchestrator = EnrichmentOrchestrator(self.llm, self.config.validation)
            diagrams, questions, _ = await orchestrator.enrich(
                topics_needing_enrichment,
                existing_diagram_ids=snapshot.existing_diagram_ids,
                existing_question_ids=snapshot.existing_question_ids,
                # Phase H: when doc-19 lesson pipeline is on, skip legacy
                # per-topic diagram generation. LessonDiagramGenerator owns
                # diagrams downstream; the legacy ones would be dead weight
                # in extraction.diagrams + Neo4j.
                skip_diagrams=self.config.enrichment.use_lesson_pipeline,
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

        # --- Phase 7a + 7b: lecture planning (NEW Phase 4b) ---
        # Chapter-level arc (sync) + per-concept teaching plans via the shared
        # feynman_teaching_kernel (async). Sidecar artifacts stored on each
        # Chapter; Phase 4c-4d stages consume them; Phase 8 (ScriptAssembler)
        # stitches the resulting per-beat narrations into the ChapterScript.
        lecture_plans: dict[str, Any] = {}
        if not skip_lecture_plan:
            notify("chapter_plan", "Planning chapter arcs...")
            topics_by_chapter_for_plan = self._group_topics(all_topics)
            diagrams_by_topic_for_plan = self._group_diagrams(diagrams)
            chapter_planner = ChapterLecturePlanner(self.llm)
            lecture_plans = chapter_planner.plan_for_all(
                chapter_nodes,
                topics_by_chapter_for_plan,
            )
            for ch in chapter_nodes:
                if ch.chapter_id in lecture_plans:
                    ch.lecture_plan = lecture_plans[ch.chapter_id]

            if lecture_plans:
                # ─── Phase H (doc 19): doc-19 stack OR legacy 7b-7g ────────
                # `use_lesson_pipeline=True` (default): runs LessonQualityGate
                # per topic, applies LessonProsody, builds assembled_chapter_
                # script from TopicNarrations. Legacy 7b-7g is bypassed.
                # `use_lesson_pipeline=False`: legacy ConceptPlanner →
                # DiagramSpecGenerator → BeatNarrationWriter → ScriptAssembler.
                if self.config.enrichment.use_lesson_pipeline:
                    notify(
                        "lesson_pipeline",
                        "Running doc-19 lesson pipeline (Phase H)...",
                    )
                    topics_by_id_global: dict[str, Any] = {
                        t.topic_id: t for t in all_topics
                    }
                    existing_diagram_ids_global: set[str] = {
                        d.diagram_id for d in diagrams
                    }
                    for ch in chapter_nodes:
                        ch_lecture_plan = lecture_plans.get(ch.chapter_id)
                        if ch_lecture_plan is None:
                            continue
                        ch_topics = topics_by_chapter_for_plan.get(ch.chapter_id, [])
                        new_diagrams = await self._run_lesson_pipeline_for_chapter(
                            chapter=ch,
                            topics_for_chapter=ch_topics,
                            lecture_plan=ch_lecture_plan,
                            diagrams_by_topic=diagrams_by_topic_for_plan,
                            existing_diagram_ids=existing_diagram_ids_global,
                            notify=notify,
                        )
                        for d in new_diagrams:
                            diagrams.append(d)
                            existing_diagram_ids_global.add(d.diagram_id)
                            for tid in d.linked_topic_ids:
                                t = topics_by_id_global.get(tid)
                                if (
                                    t is not None
                                    and d.diagram_id not in t.has_diagram_ids
                                ):
                                    t.has_diagram_ids.append(d.diagram_id)
                    extraction.diagrams = diagrams
                    # The legacy 7c-7g sub-phases below check
                    # `if not ch.concept_plans: continue` per chapter, so
                    # leaving concept_plans empty naturally skips them.
                    report.skipped_phases.append("concept_plan_legacy")
                else:
                    notify("concept_plan", "Planning per-concept teaching beats...")
                    concept_planner = ConceptPlanner(self.config)
                    concept_plans_by_chapter = await concept_planner.plan_for_all(
                        chapter_nodes,
                        topics_by_chapter_for_plan,
                        lecture_plans,
                        diagrams_by_topic_for_plan,
                    )
                    # Book-coverage USP post-pass: enforce the example
                    # allocation rule per topic. The kernel ConceptTeachingPlan
                    # doesn't carry topic_id, but plans come back in the same
                    # order as `lecture_plan.concept_sequence` (a list of
                    # topic_ids), so we zip them. Pure function — zero LLM cost.
                    from .curriculum.lecture_plan.example_allocator import (
                        allocate_example_beats,
                    )
                    for ch in chapter_nodes:
                        plans = concept_plans_by_chapter.get(ch.chapter_id, [])
                        lp = lecture_plans.get(ch.chapter_id)
                        topic_lookup = {
                            t.topic_id: t
                            for t in topics_by_chapter_for_plan.get(ch.chapter_id, [])
                        }
                        sequence = lp.concept_sequence if lp else []
                        reallocated: list[ConceptTeachingPlan] = []
                        for plan, topic_id in zip(plans, sequence, strict=False):
                            topic = topic_lookup.get(topic_id)
                            if topic is None:
                                reallocated.append(plan)
                                continue
                            reallocated.append(allocate_example_beats(plan, topic))
                        ch.concept_plans = reallocated

                # --- Phase 7c + 7d: per-beat diagrams + DiagramQA (NEW Phase 4c) ---
                # Per-beat DiagramSpecGenerator iterates each Chapter.concept_plans,
                # finds beats with visual.tool in {"draw_design_diagram",
                # "modify_design_diagram"}, and generates one Diagram per such
                # beat. DiagramQA scores each via Claude Sonnet vision; score <
                # min_score triggers regeneration with the QA's suggestion as a
                # corrective hint. Final diagrams (incl. needs_review flagged
                # ones) join the chapter-wide diagrams list and topic.has_diagram_ids.
                per_beat_cfg = self.config.enrichment.per_beat_diagrams
                qa_cfg = self.config.enrichment.diagram_qa
                if per_beat_cfg.enabled:
                    notify(
                        "per_beat_diagrams",
                        "Generating per-beat design diagrams...",
                    )
                    new_diagrams = await self._run_per_beat_diagram_stage(
                        chapter_nodes=chapter_nodes,
                        topics_by_chapter=topics_by_chapter_for_plan,
                        existing_diagram_ids={d.diagram_id for d in diagrams},
                        per_beat_cfg=per_beat_cfg,
                        qa_cfg=qa_cfg,
                        skip_qa=skip_diagram_qa,
                        notify=notify,
                    )
                    # Append per-beat diagrams to the chapter-wide list and to
                    # each parent topic's has_diagram_ids so existing render
                    # paths (Phase 10 fallback) pick them up.
                    topics_by_id: dict[str, Any] = {t.topic_id: t for t in all_topics}
                    for d in new_diagrams:
                        diagrams.append(d)
                        for tid in d.linked_topic_ids:
                            t = topics_by_id.get(tid)
                            if t is not None and d.diagram_id not in t.has_diagram_ids:
                                t.has_diagram_ids.append(d.diagram_id)
                    extraction.diagrams = diagrams
                else:
                    report.skipped_phases.append("per_beat_diagrams")

                # --- Phase 7e + 7f + 7g: per-beat narration + length trim +
                # script assembly (NEW Phase 4d, promoted to playback in 4e).
                # ScriptAssembler's output (`chapter.assembled_chapter_script`)
                # is consumed by Phase 8 to build the ChapterScript fed into
                # the TTS layer.
                bn_cfg = self.config.enrichment.beat_narration
                le_cfg = self.config.enrichment.length_enforcer
                sa_cfg = self.config.enrichment.script_assembler
                if (not skip_beat_narration) and bn_cfg.enabled:
                    diagrams_by_beat_id = {
                        d.linked_beat_id: d for d in diagrams if d.linked_beat_id
                    }
                    notify("beat_narration", "Writing per-beat narrations...")
                    bn_writer = BeatNarrationWriter(self.llm, config=bn_cfg)
                    # `rewrite_context` is populated by `write_for_chapter` as
                    # a side-effect so `LengthEnforcer` Pass 3 can re-invoke
                    # the writer on the longest non-structural beat.
                    rewrite_context: dict[str, Any] = {}
                    for ch in chapter_nodes:
                        if not ch.concept_plans or ch.lecture_plan is None:
                            continue
                        ch_topics = topics_by_chapter_for_plan.get(ch.chapter_id, [])
                        ch_topics_by_id = {t.topic_id: t for t in ch_topics}
                        narrations, bn_report = await bn_writer.write_for_chapter(
                            chapter=ch,
                            topics_by_id=ch_topics_by_id,
                            diagrams_by_beat_id=diagrams_by_beat_id,
                            rewrite_context_out=rewrite_context,
                        )
                        ch.beat_narrations = narrations
                        logger.info(bn_report.summary())

                    # Book-coverage validator (soft-warn v1). Logs structured
                    # gaps for any Topic.book_examples that didn't land in a
                    # faithful book-source beat. Promote to hard-fail once we
                    # have signal on real ingests.
                    from .curriculum.validation.example_coverage import (
                        validate_example_coverage,
                    )
                    for ch in chapter_nodes:
                        if not ch.beat_narrations:
                            continue
                        ch_topics = topics_by_chapter_for_plan.get(ch.chapter_id, [])
                        narrations_by_topic: dict[str, list] = {}
                        for n in ch.beat_narrations:
                            narrations_by_topic.setdefault(n.topic_id, []).append(n)
                        cov = validate_example_coverage(ch_topics, narrations_by_topic)
                        logger.info(
                            "example_coverage chapter=%s: %s",
                            ch.chapter_id, cov.summary(),
                        )

                    if le_cfg.enabled:
                        notify(
                            "length_enforcer",
                            "Enforcing length budget per chapter...",
                        )
                        enforcer = LengthEnforcer(config=le_cfg)
                        for ch in chapter_nodes:
                            if not ch.beat_narrations:
                                continue
                            le_report = await enforcer.trim(
                                chapter=ch,
                                rewriter=bn_writer,
                                rewrite_context=rewrite_context,
                            )
                            logger.info(le_report.summary())
                    else:
                        report.skipped_phases.append("length_enforcer")

                    if sa_cfg.enabled:
                        notify(
                            "script_assembler",
                            "Assembling per-topic narration strings...",
                        )
                        assembler = ScriptAssembler(config=sa_cfg)
                        for ch in chapter_nodes:
                            if not ch.beat_narrations:
                                continue
                            ch_topics = topics_by_chapter_for_plan.get(
                                ch.chapter_id, []
                            )
                            ch_topics_by_id = {t.topic_id: t for t in ch_topics}
                            ch.assembled_chapter_script = assembler.assemble_chapter(
                                chapter=ch,
                                topics_by_id=ch_topics_by_id,
                            )
                    else:
                        report.skipped_phases.append("script_assembler")
                else:
                    report.skipped_phases.append("beat_narration")
        else:
            report.skipped_phases.append("lecture_plan")

        # --- Phase 8 + 9: lecture script + TTS ---
        # Phase 4e: ScriptWriter (the monolith) was deleted. Chapter scripts
        # come from ScriptAssembler's output stitched in Phase 7g
        # (`ch.assembled_chapter_script`). AudioPipeline consumes the same
        # `dict[str, ChapterScript]` shape as before.
        chapter_scripts: dict[str, ChapterScript] = {}
        if not skip_tts:
            notify("script", "Assembling lecture scripts from beat narrations...")
            for ch in chapter_nodes:
                if ch.assembled_chapter_script is None:
                    continue
                chapter_scripts[ch.chapter_id] = ChapterScript(
                    **ch.assembled_chapter_script
                )
            if not chapter_scripts:
                logger.warning(
                    "Phase 8: no chapters produced assembled scripts; TTS will be skipped"
                )
            else:
                logger.info(
                    "Phase 8: assembled %d chapter scripts", len(chapter_scripts)
                )

            if chapter_scripts:
                notify("tts", "Rendering TTS audio...")
                audio_pipeline = AudioPipeline(
                    self.tts,
                    self.config.tts,
                    self.config.artifacts,
                    layout=self.config.layout,
                )
                await audio_pipeline.build_for_book(
                    chapter_nodes,
                    all_topics,
                    chapter_scripts,
                    diagrams=diagrams,
                )
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
            notify(
                "embed", f"Generating embeddings ({self.config.embedding.provider})..."
            )
            try:
                provider = create_embedding_provider(self.config.embedding)
                embedder = EmbeddingGenerator(
                    provider, batch_size=self.config.embedding.batch_size
                )
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

    async def _run_lesson_pipeline_for_chapter(
        self,
        *,
        chapter: ChapterNode,
        topics_for_chapter: list,
        lecture_plan,
        diagrams_by_topic: dict[str, list],
        existing_diagram_ids: set[str],
        notify: StageCallback,
    ) -> list:
        """Doc-19 Phase H — runs LessonQualityGate per topic, applies prosody,
        and populates chapter.lesson_plans + chapter.lesson_narrations +
        chapter.assembled_chapter_script. Returns the new Diagrams produced
        by the lesson pipeline (caller appends to extraction.diagrams and to
        each topic.has_diagram_ids).

        Replaces the legacy 7b–7g chain for this chapter when
        cfg.enrichment.use_lesson_pipeline is True. Each topic is gated
        sequentially (concept_sequence order); failure of one topic does
        not abort the chapter — its slot is left empty and needs_review is
        flagged.
        """
        lesson_cfg = self.config.enrichment.lesson_pipeline

        planner = LessonPlanner(self.config)
        diagram_generator = LessonDiagramGenerator(self.config)
        narrator = LessonNarrator(self.config)
        plan_judge = PlanJudge(self.config, min_score=lesson_cfg.plan_min_score)
        diagram_qa = DiagramQA(
            api_key=self.config.llm.api_key or "",
            model=self.config.enrichment.diagram_qa.model,
            min_score=lesson_cfg.diagram_min_score,
        )
        prosody = LessonProsody()

        gate = LessonQualityGate(
            self.config,
            planner=planner,
            diagram_generator=diagram_generator,
            narrator=narrator,
            plan_judge=plan_judge,
            diagram_qa=diagram_qa,
            max_quality_retries=lesson_cfg.max_quality_retries,
        )

        adapter = CurriculumAdapter(
            chapter, topics_for_chapter, lecture_plan, diagrams_by_topic
        )

        gate_report = LessonGateReport()
        new_diagrams: list = []
        new_diagram_ids: set[str] = set(existing_diagram_ids)

        for concept_index, topic_id in enumerate(lecture_plan.concept_sequence):
            notify(
                "lesson_gate",
                f"Gating topic {topic_id} ({concept_index + 1}/"
                f"{len(lecture_plan.concept_sequence)})...",
            )
            topic_name = _topic_name_for(topics_for_chapter, topic_id) or topic_id
            try:
                gate_result = await gate.gate_one_topic(
                    chapter_id=chapter.chapter_id,
                    topic_id=topic_id,
                    topic_name=topic_name,
                    concept_index=concept_index,
                    curriculum=adapter,
                    report=gate_report,
                )
            except Exception as exc:  # noqa: BLE001 — boundary
                logger.warning(
                    "lesson_pipeline.gate_failed chapter=%s topic=%s err=%s",
                    chapter.chapter_id,
                    topic_id,
                    exc,
                )
                continue

            if gate_result.plan is not None:
                chapter.lesson_plans.append(gate_result.plan)
            if gate_result.narration is not None:
                applied = prosody.apply(gate_result.narration)
                chapter.lesson_narrations.append(applied)
            for d in gate_result.diagrams:
                if d.diagram_id not in new_diagram_ids:
                    new_diagrams.append(d)
                    new_diagram_ids.add(d.diagram_id)

        # BookExampleWeaver — owns the book-coverage USP. Runs AFTER the
        # gate has produced concept-only LessonPlans; for each topic with
        # Topic.book_examples, generates ChoreographyStep entries that
        # solve each example faithfully and inserts them into the plan.
        # Re-runs the narrator over the woven plans (pure function, free)
        # so chapter.lesson_narrations reflects the new steps before the
        # script assembler stitches everything.
        notify(
            "book_example_weaver",
            "Weaving book examples into per-topic choreographies...",
        )
        plans_by_tid: dict[str, Any] = {
            p.topic_id: p for p in chapter.lesson_plans
        }
        topics_by_tid = {t.topic_id: t for t in topics_for_chapter}
        # All diagrams that exist for this chapter (existing + freshly minted)
        diagrams_by_id_for_weaver = {d.diagram_id: d for d in new_diagrams}
        weaver = BookExampleWeaver(self.config)
        weaver_report = await weaver.weave_for_chapter(
            chapter_lesson_plans=plans_by_tid,
            topics_by_id=topics_by_tid,
            diagrams_by_id=diagrams_by_id_for_weaver,
        )

        # Replace chapter.lesson_plans with woven plans in original order.
        chapter.lesson_plans = [
            plans_by_tid[p.topic_id]
            for p in chapter.lesson_plans
            if p.topic_id in plans_by_tid
        ]

        # Re-render narration ONLY for topics whose plans the weaver
        # actually modified (i.e., any step now has is_book_example=True).
        # Untouched topics keep the gate-produced narration — that's
        # important because the gate's narration may carry prosody / other
        # adjustments that a fresh render wouldn't reproduce.
        narrations_by_tid: dict[str, Any] = {
            n.topic_id: n for n in chapter.lesson_narrations
        }
        for plan in chapter.lesson_plans:
            woven = any(
                step.is_book_example for step in plan.choreography
            )
            if not woven:
                continue
            short_to_long = _diagram_id_short_to_long(plan, plan.topic_id)
            try:
                renarrated = narrator.render(
                    topic_id=plan.topic_id,
                    plan=plan,
                    diagram_id_resolver=lambda s, _m=short_to_long: _m.get(s, s),
                )
                narrations_by_tid[plan.topic_id] = prosody.apply(renarrated)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "book_example_weaver.renarrate_failed",
                    topic_id=plan.topic_id,
                    error=str(exc)[:200],
                )
        # Rebuild lesson_narrations in plan order (preserve sequencing).
        chapter.lesson_narrations = [
            narrations_by_tid[p.topic_id]
            for p in chapter.lesson_plans
            if p.topic_id in narrations_by_tid
        ]

        # Hard structural validator + chapter-level coverage gate. Logs
        # loudly and adds a warning to the pipeline report; doesn't abort
        # the chapter (a partially-covered lecture is still better than
        # none). We tighten the gate to abort once the loop is stable.
        coverage_report = validate_book_coverage(
            topics_for_chapter, plans_by_tid
        )
        logger.info(
            "book_coverage_chapter %s: %s",
            chapter.chapter_id,
            coverage_report.summary(),
        )
        if not coverage_report.is_passing:
            logger.error(
                "book_coverage_chapter.below_floor "
                "chapter=%s coverage=%.0f%% gaps=%d",
                chapter.chapter_id,
                coverage_report.coverage_pct * 100,
                len(coverage_report.gaps),
            )

        chapter.assembled_chapter_script = _build_chapter_script_from_narrations(
            chapter_id=chapter.chapter_id,
            narrations=chapter.lesson_narrations,
        )
        logger.info(gate_report.summary())
        return new_diagrams

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

    async def _run_per_beat_diagram_stage(
        self,
        *,
        chapter_nodes: list,
        topics_by_chapter: dict[str, list],
        existing_diagram_ids: set[str],
        per_beat_cfg,
        qa_cfg,
        skip_qa: bool,
        notify: StageCallback,
    ) -> list:
        """Phase 7c + 7d: generate per-beat diagrams and optionally QA them.

        Returns the newly generated diagrams (already QA-filtered + needs_review
        flagged). Caller is responsible for appending them to the chapter-wide
        diagrams list and to each parent topic's has_diagram_ids.
        """
        spec_gen = DiagramSpecGenerator(
            self.llm,
            concurrency=per_beat_cfg.concurrency,
            mode=per_beat_cfg.mode,
        )
        qa: DiagramQA | None = None
        if qa_cfg.enabled and not skip_qa:
            qa = DiagramQA(
                api_key=self.config.llm.api_key or "",
                model=qa_cfg.model,
                min_score=qa_cfg.min_score,
            )

        result: list = []
        for ch in chapter_nodes:
            if not ch.concept_plans:
                continue
            lp = ch.lecture_plan
            if lp is None:
                continue
            ch_topics = topics_by_chapter.get(ch.chapter_id, [])
            topics_by_id = {t.topic_id: t for t in ch_topics}
            # cp.concept_index is the position in lp.concept_sequence; map
            # list-index → topic_id via that.
            topic_id_by_plan_index: dict[int, str] = {}
            for i, cp in enumerate(ch.concept_plans):
                if 0 <= cp.concept_index < len(lp.concept_sequence):
                    topic_id_by_plan_index[i] = lp.concept_sequence[cp.concept_index]
            new_diagrams, _gen_report = await spec_gen.generate_for_chapter(
                topics_by_id,
                ch.concept_plans,
                topic_id_by_plan_index,
                existing_diagram_ids,
            )
            if qa is not None and new_diagrams:
                notify(
                    "diagram_qa",
                    f"QA scoring {len(new_diagrams)} per-beat diagrams "
                    f"for chapter {ch.chapter_id}...",
                )
                new_diagrams = await self._run_diagram_qa_loop(
                    qa=qa,
                    spec_gen=spec_gen,
                    diagrams=new_diagrams,
                    concept_plans=ch.concept_plans,
                    topic_id_by_plan_index=topic_id_by_plan_index,
                    topics_by_id=topics_by_id,
                    max_retries=qa_cfg.max_retries,
                )
            for d in new_diagrams:
                existing_diagram_ids.add(d.diagram_id)
            result.extend(new_diagrams)
        return result

    @staticmethod
    async def _run_diagram_qa_loop(
        *,
        qa: DiagramQA,
        spec_gen: DiagramSpecGenerator,
        diagrams: list,
        concept_plans: list,
        topic_id_by_plan_index: dict[int, str],
        topics_by_id: dict[str, Any],
        max_retries: int,
    ) -> list:
        """Score each diagram; retry up to max_retries on score < qa.min_score.

        Tracks the best-ever score across attempts; if no attempt clears the
        threshold, accepts the best one and flags needs_review=True. Never
        drops a diagram — Phase 4c is additive.
        """
        # Build beat-lookup: linked_beat_id → (topic, plan, beat, beat_index)
        beat_lookup: dict[str, tuple[Any, Any, Any, int]] = {}
        for i, cp in enumerate(concept_plans):
            topic_id = topic_id_by_plan_index.get(i)
            topic = topics_by_id.get(topic_id or "")
            if topic is None:
                continue
            for beat_index, beat in enumerate(cp.beats):
                if beat.visual and beat.visual.tool in DESIGN_DIAGRAM_TOOLS:
                    beat_lookup[f"{topic.topic_id}_b{beat_index}"] = (
                        topic,
                        cp,
                        beat,
                        beat_index,
                    )

        final: list = []
        for original in diagrams:
            best = original
            best_score = -1
            current = original
            last_result: QAResult | None = None
            for attempt in range(max_retries + 1):  # 1 initial + max_retries
                result = await qa.verify(current, current.description)
                last_result = result
                if result.score > best_score:
                    best_score = result.score
                    best = current
                if result.passed and result.score >= qa.min_score:
                    final.append(current)
                    break
                if attempt >= max_retries:
                    if best_score < qa.min_score:
                        best.needs_review = True
                        logger.warning(
                            "DiagramQA.exhausted for %s — best score %d, flagging needs_review",
                            original.linked_beat_id,
                            best_score,
                        )
                    final.append(best)
                    break
                lookup = beat_lookup.get(original.linked_beat_id)
                if lookup is None:
                    logger.warning(
                        "DiagramQA.no_beat_for_retry %s — accepting current",
                        original.linked_beat_id,
                    )
                    current.needs_review = True
                    final.append(current)
                    break
                topic, plan, beat, beat_index = lookup
                hint = (
                    f"Prior attempt scored {result.score}/5. "
                    f"Issue: {result.issue}\nSuggestion: {result.suggestion}"
                )
                try:
                    regen = await spec_gen.regenerate_for_beat(
                        topic,
                        plan,
                        beat,
                        beat_index,
                        hint=hint,
                    )
                except Exception as e:  # noqa: BLE001 — regen failure is recoverable
                    logger.warning(
                        "DiagramQA.regenerate_failed for %s: %s — accepting best",
                        original.linked_beat_id,
                        e,
                    )
                    if best_score < qa.min_score:
                        best.needs_review = True
                    final.append(best)
                    break
                if regen is None:
                    logger.warning(
                        "DiagramQA.regenerate_returned_none for %s — accepting best",
                        original.linked_beat_id,
                    )
                    if best_score < qa.min_score:
                        best.needs_review = True
                    final.append(best)
                    break
                # Stable diagram_id across attempts so downstream references hold.
                regen.diagram_id = original.diagram_id
                current = regen
            _ = last_result  # silence unused
        return final

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


# ─────────────────────────────────────────────────────────────────────────────
# Doc-19 Phase H helpers (module-level so tests can hit them directly).
# ─────────────────────────────────────────────────────────────────────────────


def _topic_name_for(topics: list, topic_id: str) -> str | None:
    """Look up a topic's `topic_name` by topic_id from a list of Topic objects."""
    for t in topics:
        if getattr(t, "topic_id", None) == topic_id:
            return getattr(t, "topic_name", None)
    return None


def _build_chapter_script_from_narrations(
    *,
    chapter_id: str,
    narrations: list[TopicNarration],
) -> dict[str, Any]:
    """Phase H adapter: turn a list of prosody-applied `TopicNarration`s into
    the dict shape the legacy `ChapterScript` dataclass expects (Pipeline
    Phase 8 reconstructs the dataclass from this).

    Mirrors `ScriptAssembler.assemble_chapter()` output shape:

        {
            "chapter_id": "...",
            "segments": [
                {
                    "topic_id": "...",
                    "narration_chapter": "...",
                    "narration_standalone": "...",
                },
                ...
            ],
        }

    For now `narration_standalone` == `narration_chapter` — Phase H.1 cleanup
    can split them if standalone playback needs different scoping.
    """
    segments: list[dict[str, Any]] = []
    for nar in narrations:
        text = nar.full_text_with_markers.strip()
        if not text:
            continue
        segments.append(
            {
                "topic_id": nar.topic_id,
                "narration_chapter": text,
                "narration_standalone": text,
            }
        )
    return {"chapter_id": chapter_id, "segments": segments}
