"""Book-aware two-pass chapter extraction — structure then content.

Pass A (1 LLM call): Extract concept hierarchy, types, relationships.
Pass B (batched LLM calls): Enrich each node with exhaustive summary + source text.

Usage:
    extractor = ChapterExtractor(llm_provider)
    result = extractor.extract_chapter(
        pdf_content, chapter, chapter_index, skeleton, anchors, subject
    )
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from ..llm.base import LLMProvider
from ..pdf.parser import PDFContent
from ..pdf.toc import Chapter
from .anchors.models import ExtractionAnchors
from .id_generator import generate_concept_uid, generate_relationship_key
from .models import (
    BookSkeleton,
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)
from .prompts import (
    build_chapter_content_user_prompt,
    build_chapter_structure_user_prompt,
    get_chapter_content_system_prompt,
    get_chapter_structure_system_prompt,
)

logger = logging.getLogger(__name__)


class ChapterExtractionError(Exception):
    """Raised when chapter extraction fails after retries."""

    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


class ChapterExtractor:
    """Two-pass chapter extraction: structure (Pass A) then content (Pass B).

    Follows the same constructor pattern as SkeletonExtractor.
    """

    MAX_RETRIES = 1
    PASS_B_BATCH_SIZE = 8

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def extract_chapter(
        self,
        pdf_content: PDFContent,
        chapter: Chapter,
        chapter_index: int,
        skeleton: BookSkeleton,
        anchors: ExtractionAnchors,
        subject: str,
    ) -> CurriculumExtractionResult:
        """Full two-pass extraction for a single chapter.

        Args:
            pdf_content: Parsed PDF with all pages.
            chapter: The chapter to extract.
            chapter_index: 1-based position in the book.
            skeleton: Book-level structure for context.
            anchors: Deterministic anchors (extraction floor).
            subject: Academic subject (e.g. "physics").

        Returns:
            CurriculumExtractionResult with typed concept nodes.

        Raises:
            ChapterExtractionError: If extraction fails.
        """
        chapter_text = pdf_content.get_text_for_range(
            chapter.start_page, chapter.end_page
        )

        if not chapter_text.strip():
            raise ChapterExtractionError(
                f"Empty text for chapter '{chapter.title}' "
                f"(pages {chapter.start_page}-{chapter.end_page})"
            )

        logger.info(
            "Extracting chapter %d: '%s' (pages %d-%d, %d chars)",
            chapter_index,
            chapter.title,
            chapter.start_page,
            chapter.end_page,
            len(chapter_text),
        )

        # Pass A: structure
        raw_nodes, raw_relationships, model_name = self._extract_structure(
            chapter_text, chapter, chapter_index, skeleton, anchors, subject
        )

        logger.info(
            "Pass A complete: %d nodes, %d relationships",
            len(raw_nodes),
            len(raw_relationships),
        )

        # Pass B: content enrichment
        enriched_nodes = self._extract_content(
            chapter_text, raw_nodes, chapter, chapter_index, subject
        )

        logger.info("Pass B complete: %d nodes enriched", len(enriched_nodes))

        return self._assemble_result(
            enriched_nodes,
            raw_relationships,
            chapter,
            chapter_index,
            skeleton,
            subject,
            model_name,
        )

    # ------------------------------------------------------------------
    # Pass A: Structure Extraction
    # ------------------------------------------------------------------

    def _extract_structure(
        self,
        chapter_text: str,
        chapter: Chapter,
        chapter_index: int,
        skeleton: BookSkeleton,
        anchors: ExtractionAnchors,
        subject: str,
    ) -> tuple[list[dict], list[dict], str]:
        """Pass A — extract concept hierarchy and relationships.

        Returns:
            Tuple of (raw_nodes, raw_relationships, model_name) as dicts.
        """
        system_prompt = get_chapter_structure_system_prompt()
        user_prompt = build_chapter_structure_user_prompt(
            skeleton=skeleton,
            chapter_index=chapter_index,
            chapter_text=chapter_text,
            anchors=anchors,
        )

        raw_json, model_name = self._call_llm_with_model(system_prompt, user_prompt)

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ChapterExtractionError(
                f"Invalid JSON from Pass A: {e}",
                raw_response=raw_json,
            ) from e

        nodes = data.get("nodes", [])
        relationships = data.get("relationships", [])

        if not isinstance(nodes, list):
            raise ChapterExtractionError(
                "Pass A 'nodes' is not a list",
                raw_response=raw_json,
            )

        return nodes, relationships, model_name

    # ------------------------------------------------------------------
    # Pass B: Content Enrichment
    # ------------------------------------------------------------------

    def _extract_content(
        self,
        chapter_text: str,
        structure_nodes: list[dict],
        chapter: Chapter,
        chapter_index: int,
        subject: str,
    ) -> list[dict]:
        """Pass B — enrich nodes with summaries and source text.

        Batches nodes by page range to minimize context sent per call.
        Returns nodes with summary, source_text, and difficulty added.
        """
        if not structure_nodes:
            return []

        batches = self._batch_nodes_by_page_range(
            structure_nodes, self.PASS_B_BATCH_SIZE
        )

        system_prompt = get_chapter_content_system_prompt()

        # Build lookup for enrichment merging
        enrichment_by_name: dict[str, dict] = {}

        for batch_idx, batch in enumerate(batches):
            # Determine page range for this batch
            batch_page_start = min(
                n.get("page_start", chapter.start_page) for n in batch
            )
            batch_page_end = max(
                n.get("page_end", chapter.end_page) for n in batch
            )

            # Get chapter text for this page range
            batch_text = chapter_text  # full text — simpler and more robust

            user_prompt = build_chapter_content_user_prompt(
                chapter_text=batch_text,
                nodes_to_enrich=batch,
                page_start=batch_page_start,
                page_end=batch_page_end,
            )

            raw_json = self._call_llm(system_prompt, user_prompt)

            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError as e:
                raise ChapterExtractionError(
                    f"Invalid JSON from Pass B batch {batch_idx}: {e}",
                    raw_response=raw_json,
                ) from e

            for enriched in data.get("nodes", []):
                name = enriched.get("topic_name", "")
                if name:
                    enrichment_by_name[name] = enriched

            logger.info(
                "Pass B batch %d/%d: %d nodes enriched",
                batch_idx + 1,
                len(batches),
                len(data.get("nodes", [])),
            )

        # Merge enrichment into structure nodes
        result = []
        for node in structure_nodes:
            enriched = enrichment_by_name.get(node.get("topic_name", ""), {})
            merged = {**node}
            merged["summary"] = enriched.get("summary", "")
            merged["source_text"] = enriched.get("source_text", "")
            merged["difficulty"] = enriched.get("difficulty", "intermediate")
            result.append(merged)

        return result

    # ------------------------------------------------------------------
    # Assembly — raw dicts → typed CurriculumExtractionResult
    # ------------------------------------------------------------------

    def _assemble_result(
        self,
        enriched_nodes: list[dict],
        raw_relationships: list[dict],
        chapter: Chapter,
        chapter_index: int,
        skeleton: BookSkeleton,
        subject: str,
        model_name: str,
    ) -> CurriculumExtractionResult:
        """Convert raw LLM output into a typed CurriculumExtractionResult."""
        # Build name → UID mapping as we process nodes
        name_to_uid: dict[str, str] = {}
        typed_nodes: list[ExtractionNode] = []

        for order, raw in enumerate(enriched_nodes, 1):
            topic_name = raw.get("topic_name", f"unnamed_{order}")
            parent_name = raw.get("parent")

            uid = generate_concept_uid(
                subject=subject,
                chapter_title=chapter.title,
                concept_name=topic_name,
                parent_concept_name=parent_name,
            )
            name_to_uid[topic_name] = uid

            # Parse concept type safely
            concept_type = self._parse_concept_type(
                raw.get("concept_type", "topic")
            )
            resolution_level = self._parse_resolution_level(
                raw.get("resolution_level", "concept")
            )
            difficulty = self._parse_difficulty(
                raw.get("difficulty", "intermediate")
            )

            node = ExtractionNode(
                uid=uid,
                topic_name=topic_name,
                concept_type=concept_type,
                resolution_level=resolution_level,
                section_number=raw.get("section_number"),
                summary=raw.get("summary", ""),
                source_text=raw.get("source_text", ""),
                page_start=raw.get("page_start", chapter.start_page),
                page_end=raw.get("page_end", chapter.end_page),
                chapter_order=chapter_index,
                within_chapter_order=order,
                difficulty=difficulty,
                estimated_duration_minutes=raw.get(
                    "estimated_duration_minutes", 3.0
                ),
                visual_hint=raw.get("visual_hint"),
                parent_uid=name_to_uid.get(parent_name) if parent_name else None,
                metadata={"raw_parent_name": parent_name} if parent_name else {},
            )
            typed_nodes.append(node)

        # Wire children_uids from parent_uid
        uid_to_node: dict[str, ExtractionNode] = {n.uid: n for n in typed_nodes}
        for node in typed_nodes:
            if node.parent_uid and node.parent_uid in uid_to_node:
                parent = uid_to_node[node.parent_uid]
                if node.uid not in parent.children_uids:
                    parent.children_uids.append(node.uid)

        # Build relationships
        typed_rels = self._build_relationships(
            raw_relationships, name_to_uid, chapter.title
        )

        return CurriculumExtractionResult(
            subject=subject,
            textbook_title=skeleton.textbook_title,
            scope="chapter",
            chapter_title=chapter.title,
            source=ExtractionSource(
                textbook_title=skeleton.textbook_title,
                chapter_title=chapter.title,
                page_range=f"{chapter.start_page}-{chapter.end_page}",
                extractor_model=model_name,
                extraction_timestamp=datetime.now().isoformat(),
            ),
            book_skeleton=skeleton,
            nodes=typed_nodes,
            relationships=typed_rels,
        )

    def _build_relationships(
        self,
        raw_relationships: list[dict],
        name_to_uid: dict[str, str],
        chapter_title: str,
    ) -> list[ExtractionRelationship]:
        """Convert raw relationship dicts to typed ExtractionRelationship."""
        typed_rels: list[ExtractionRelationship] = []
        seen_keys: set[str] = set()

        for raw in raw_relationships:
            if not isinstance(raw, dict):
                continue

            from_name = raw.get("from_node", "")
            to_name = raw.get("to_node", "")
            rel_type_str = raw.get("type", "")
            label = raw.get("label", "")

            rel_type = self._parse_relationship_type(rel_type_str)
            if rel_type is None:
                continue

            # Resolve UIDs — cross-chapter refs stay as-is (resolved in Phase 7)
            from_uid = name_to_uid.get(from_name, "")
            if "::" in to_name:
                # Cross-chapter reference: "ChapterTitle::ConceptName"
                to_uid = to_name
            else:
                to_uid = name_to_uid.get(to_name, "")

            if not from_uid or not to_uid:
                continue

            key = generate_relationship_key(rel_type.value, from_uid, to_uid)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            typed_rels.append(
                ExtractionRelationship(
                    relationship_key=key,
                    type=rel_type,
                    from_uid=from_uid,
                    to_uid=to_uid,
                    label=label,
                )
            )

        return typed_rels

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM and return raw JSON string. Retries once on parse failure."""
        raw, _ = self._call_llm_with_model(system_prompt, user_prompt)
        return raw

    def _call_llm_with_model(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[str, str]:
        """Call LLM and return (raw_json, model_name). Retries on parse failure."""
        last_error = None
        raw = None
        model_name = "unknown"

        for attempt in range(self.MAX_RETRIES + 1):
            response = self.llm.generate_json(system_prompt, user_prompt)
            raw = response.content
            model_name = response.model

            if response.usage:
                logger.info(
                    "LLM call (attempt %d): %s tokens in, %s tokens out",
                    attempt + 1,
                    response.usage.get("input_tokens", "?"),
                    response.usage.get("output_tokens", "?"),
                )

            try:
                json.loads(raw)
                return raw, model_name
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(
                    "JSON parse failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES + 1,
                    str(e),
                )

        raise ChapterExtractionError(
            f"LLM returned invalid JSON after {self.MAX_RETRIES + 1} attempts: {last_error}",
            raw_response=raw,
        )

    def _batch_nodes_by_page_range(
        self, nodes: list[dict], batch_size: int = 8
    ) -> list[list[dict]]:
        """Group nodes into batches of ~batch_size, keeping nearby pages together.

        Sorts by page_start, then splits into groups.
        """
        sorted_nodes = sorted(nodes, key=lambda n: n.get("page_start", 0))
        batches = []
        for i in range(0, len(sorted_nodes), batch_size):
            batches.append(sorted_nodes[i : i + batch_size])
        return batches

    @staticmethod
    def _parse_concept_type(raw: str) -> ConceptType:
        """Parse concept type string, defaulting to TOPIC."""
        try:
            return ConceptType(raw.lower())
        except ValueError:
            return ConceptType.TOPIC

    @staticmethod
    def _parse_resolution_level(raw: str) -> ResolutionLevel:
        """Parse resolution level string, defaulting to CONCEPT."""
        try:
            return ResolutionLevel(raw.lower())
        except ValueError:
            return ResolutionLevel.CONCEPT

    @staticmethod
    def _parse_difficulty(raw: str) -> Difficulty:
        """Parse difficulty string, defaulting to INTERMEDIATE."""
        try:
            return Difficulty(raw.lower())
        except ValueError:
            return Difficulty.INTERMEDIATE

    @staticmethod
    def _parse_relationship_type(raw: str) -> CurriculumRelationType | None:
        """Parse relationship type string, returning None if invalid."""
        try:
            return CurriculumRelationType(raw.lower())
        except ValueError:
            return None
