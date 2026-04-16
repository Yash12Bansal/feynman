"""Gap-filling sub-agent for curriculum extraction.

When structural validation detects missing items (sections, figures, examples),
the GapFiller makes targeted LLM calls to extract ONLY what was missed.
Owns the validate → fill → revalidate loop (max 2 retries).

Usage:
    validator = StructuralValidator()
    gap_filler = GapFiller(llm, validator)
    result, report = gap_filler.fill_gaps(extraction, anchors, chapter_text)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ...llm.base import LLMProvider
from ..anchors.models import ExtractionAnchors
from ..id_generator import generate_concept_uid, generate_relationship_key
from ..models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ResolutionLevel,
)
from .models import COMPLETENESS_ISSUE_CODES, ValidationReport
from .prompts import build_gap_fill_user_prompt, get_gap_fill_system_prompt
from .structural import StructuralValidator

logger = logging.getLogger(__name__)


class GapFiller:
    """LLM-powered gap-filling agent with self-correcting loop.

    Follows the same encapsulated-retry pattern as
    ChapterExtractor._call_llm_with_model.
    """

    MAX_RETRIES = 2

    def __init__(self, llm: LLMProvider, validator: StructuralValidator):
        self.llm = llm
        self.validator = validator

    def fill_gaps(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        chapter_text: str,
    ) -> tuple[CurriculumExtractionResult, ValidationReport]:
        """Run the validate → fill → revalidate loop.

        Args:
            extraction: The extraction result to gap-fill.
            anchors: Deterministic anchors (completeness checklist).
            chapter_text: Full chapter text for the LLM to search.

        Returns:
            Tuple of (potentially modified result, final validation report).
            After max retries, remaining completeness errors are downgraded
            to warnings.
        """
        report = self.validator.validate(extraction, anchors)

        for attempt in range(self.MAX_RETRIES):
            if not report.has_completeness_errors():
                break

            gaps = self._collect_gaps(report)
            if not gaps:
                break

            logger.info(
                "Gap-fill attempt %d/%d: %s",
                attempt + 1,
                self.MAX_RETRIES,
                _summarize_gaps(gaps),
            )

            new_nodes_raw, new_rels_raw = self._call_gap_fill_llm(
                extraction, chapter_text, gaps
            )

            if new_nodes_raw:
                extraction = self._merge_into_extraction(
                    extraction, new_nodes_raw, new_rels_raw
                )

            report = self.validator.validate(extraction, anchors)

        # After max retries: accept what we have, flag remaining for human review
        if report.has_completeness_errors():
            logger.warning(
                "Gap-fill exhausted %d retries. Downgrading remaining "
                "completeness errors to warnings.",
                self.MAX_RETRIES,
            )
            report.downgrade_completeness_errors()

        return extraction, report

    # ------------------------------------------------------------------
    # Gap collection
    # ------------------------------------------------------------------

    def _collect_gaps(self, report: ValidationReport) -> dict[str, Any]:
        """Extract structured gap data from completeness error issues.

        Returns a dict with keys like 'missing_sections', 'missing_figures', etc.
        Empty dict if no completeness gaps.
        """
        gaps: dict[str, Any] = {}

        for issue in report.issues:
            if issue.level != "error" or issue.code not in COMPLETENESS_ISSUE_CODES:
                continue
            if not issue.details:
                continue

            if issue.code == "MISSING_SECTIONS":
                gaps["missing_sections"] = issue.details.get("missing_sections", [])
            elif issue.code == "MISSING_FORMULAS":
                gaps["missing_equations"] = issue.details.get("missing_equations", [])
            elif issue.code == "MISSING_FIGURES":
                gaps["missing_figures"] = issue.details.get("missing_figures", [])
            elif issue.code == "MISSING_EXAMPLES":
                gaps["missing_examples"] = issue.details.get("missing_examples", [])

        return gaps

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_gap_fill_llm(
        self,
        extraction: CurriculumExtractionResult,
        chapter_text: str,
        gaps: dict[str, Any],
    ) -> tuple[list[dict], list[dict]]:
        """Make a targeted LLM call for missing items.

        Returns (raw_node_dicts, raw_relationship_dicts).
        Returns empty lists on parse failure.
        """
        existing_names = [n.topic_name for n in extraction.nodes]

        system_prompt = get_gap_fill_system_prompt()
        user_prompt = build_gap_fill_user_prompt(
            chapter_text=chapter_text,
            existing_concept_names=existing_names,
            gaps=gaps,
        )

        response = self.llm.generate_json(system_prompt, user_prompt)
        raw = response.content

        if response.usage:
            logger.info(
                "Gap-fill LLM call: %s tokens in, %s tokens out",
                response.usage.get("input_tokens", "?"),
                response.usage.get("output_tokens", "?"),
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Gap-fill LLM returned invalid JSON: %s", e)
            return [], []

        nodes = data.get("nodes", [])
        rels = data.get("relationships", [])

        if not isinstance(nodes, list):
            logger.warning("Gap-fill 'nodes' is not a list")
            return [], []

        logger.info(
            "Gap-fill LLM returned %d nodes, %d relationships",
            len(nodes),
            len(rels) if isinstance(rels, list) else 0,
        )

        return nodes, rels if isinstance(rels, list) else []

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def _merge_into_extraction(
        self,
        extraction: CurriculumExtractionResult,
        new_nodes_raw: list[dict],
        new_rels_raw: list[dict],
    ) -> CurriculumExtractionResult:
        """Merge gap-fill results into the existing extraction.

        Generates UIDs, assigns teaching order, creates typed models,
        and returns a new CurriculumExtractionResult.
        """
        existing_uids = set(extraction.node_uids)
        existing_names = {n.topic_name.lower() for n in extraction.nodes}
        max_order = max(
            (n.within_chapter_order for n in extraction.nodes),
            default=0,
        )

        subject = extraction.subject
        chapter_title = extraction.chapter_title or ""
        chapter_order = (
            extraction.nodes[0].chapter_order if extraction.nodes else 1
        )

        # Build name→uid map for existing + new nodes (for relationship wiring)
        name_to_uid: dict[str, str] = {
            n.topic_name: n.uid for n in extraction.nodes
        }

        new_typed_nodes: list[ExtractionNode] = []
        for raw in new_nodes_raw:
            topic_name = raw.get("topic_name", "")
            if not topic_name:
                continue

            # Skip if a node with the same name already exists
            if topic_name.lower() in existing_names:
                continue

            parent_name = raw.get("parent")
            uid = generate_concept_uid(
                subject=subject,
                chapter_title=chapter_title,
                concept_name=topic_name,
                parent_concept_name=parent_name,
            )

            # Skip if UID already exists
            if uid in existing_uids:
                continue

            max_order += 1

            node = ExtractionNode(
                uid=uid,
                topic_name=topic_name,
                concept_type=_parse_concept_type(raw.get("concept_type", "topic")),
                resolution_level=_parse_resolution_level(
                    raw.get("resolution_level", "concept")
                ),
                section_number=raw.get("section_number"),
                summary=raw.get("summary", ""),
                source_text=raw.get("source_text", ""),
                page_start=raw.get("page_start", 0),
                page_end=raw.get("page_end", 0),
                chapter_order=chapter_order,
                within_chapter_order=max_order,
                difficulty=_parse_difficulty(raw.get("difficulty", "intermediate")),
                estimated_duration_minutes=raw.get("estimated_duration_minutes", 3.0),
                visual_hint=raw.get("visual_hint"),
                parent_uid=name_to_uid.get(parent_name) if parent_name else None,
                metadata={"gap_filled": True},
            )

            new_typed_nodes.append(node)
            name_to_uid[topic_name] = uid
            existing_uids.add(uid)

        # Wire children_uids for gap-filled nodes with parents
        uid_to_node = {n.uid: n for n in extraction.nodes}
        for node in new_typed_nodes:
            uid_to_node[node.uid] = node

        for node in new_typed_nodes:
            if node.parent_uid and node.parent_uid in uid_to_node:
                parent = uid_to_node[node.parent_uid]
                if node.uid not in parent.children_uids:
                    parent.children_uids.append(node.uid)

        # Build new relationships
        new_typed_rels: list[ExtractionRelationship] = []
        existing_rel_keys = {r.relationship_key for r in extraction.relationships}

        for raw in new_rels_raw:
            if not isinstance(raw, dict):
                continue

            from_name = raw.get("from_node", "")
            to_name = raw.get("to_node", "")
            rel_type = _parse_relationship_type(raw.get("type", ""))
            if rel_type is None:
                continue

            from_uid = name_to_uid.get(from_name, "")
            if "::" in to_name:
                to_uid = to_name
            else:
                to_uid = name_to_uid.get(to_name, "")

            if not from_uid or not to_uid:
                continue

            key = generate_relationship_key(rel_type.value, from_uid, to_uid)
            if key in existing_rel_keys:
                continue
            existing_rel_keys.add(key)

            new_typed_rels.append(
                ExtractionRelationship(
                    relationship_key=key,
                    type=rel_type,
                    from_uid=from_uid,
                    to_uid=to_uid,
                    label=raw.get("label", ""),
                )
            )

        logger.info(
            "Merged %d new nodes, %d new relationships into extraction",
            len(new_typed_nodes),
            len(new_typed_rels),
        )

        # Return updated extraction
        all_nodes = list(extraction.nodes) + new_typed_nodes
        all_rels = list(extraction.relationships) + new_typed_rels

        return extraction.model_copy(
            update={
                "nodes": all_nodes,
                "relationships": all_rels,
            }
        )


# ---------------------------------------------------------------------------
# Parsing helpers (same pattern as ChapterExtractor)
# ---------------------------------------------------------------------------


def _parse_concept_type(raw: str) -> ConceptType:
    try:
        return ConceptType(raw.lower())
    except ValueError:
        return ConceptType.TOPIC


def _parse_resolution_level(raw: str) -> ResolutionLevel:
    try:
        return ResolutionLevel(raw.lower())
    except ValueError:
        return ResolutionLevel.CONCEPT


def _parse_difficulty(raw: str) -> Difficulty:
    try:
        return Difficulty(raw.lower())
    except ValueError:
        return Difficulty.INTERMEDIATE


def _parse_relationship_type(raw: str) -> CurriculumRelationType | None:
    try:
        return CurriculumRelationType(raw.lower())
    except ValueError:
        return None


def _summarize_gaps(gaps: dict[str, Any]) -> str:
    """One-line summary of gaps for logging."""
    parts = []
    for key, items in gaps.items():
        if items:
            parts.append(f"{len(items)} {key.replace('_', ' ')}")
    return ", ".join(parts) if parts else "no gaps"
