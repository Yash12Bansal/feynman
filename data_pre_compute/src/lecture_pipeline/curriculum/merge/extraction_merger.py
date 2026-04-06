"""Within-chapter chunk merging for curriculum extraction results.

When a chapter exceeds ~50K chars, Pass A runs on each ~25K-char chunk
independently. This module merges the per-chunk CurriculumExtractionResult
objects into a single result BEFORE Pass B runs.

Merge strategy (from design doc):
  - summary: concatenate, then LLM reconciliation (or plain concat as fallback)
  - source_text: concatenate (preserve all source material)
  - page_start: min across chunks
  - page_end: max across chunks
  - relationships: union, dedup by relationship_key

Usage:
    merger = ExtractionMerger(llm=llm_provider)  # or llm=None for no-LLM mode
    merged, report = merger.merge_chunks(chunk_results)
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from ...llm.base import LLMProvider
from ..id_generator import generate_relationship_key
from ..models import (
    CurriculumExtractionResult,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
)
from .entity_resolver import group_by_identity
from .prompts import (
    build_summary_reconciliation_prompt,
    get_summary_reconciliation_system_prompt,
)

logger = logging.getLogger(__name__)

# Difficulty ordering for tie-breaking (higher index = harder)
_DIFFICULTY_ORDER = {
    Difficulty.BEGINNER: 0,
    Difficulty.INTERMEDIATE: 1,
    Difficulty.ADVANCED: 2,
}


@dataclass
class MergeReport:
    """Diagnostic report from a merge operation."""

    total_input_nodes: int = 0
    unique_identity_keys: int = 0
    merged_node_count: int = 0  # nodes that matched across chunks
    singleton_node_count: int = 0  # nodes unique to one chunk
    total_output_nodes: int = 0
    total_input_relationships: int = 0
    total_output_relationships: int = 0
    uid_rewrites: int = 0
    llm_reconciliations: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line summary for logging."""
        status = "MERGED" if self.merged_node_count > 0 else "NO_MERGES"
        return (
            f"Merge: {status} ({self.total_input_nodes} in → "
            f"{self.total_output_nodes} out, "
            f"{self.merged_node_count} merged, "
            f"{self.uid_rewrites} UID rewrites)"
        )


class ExtractionMerger:
    """Merges multiple per-chunk CurriculumExtractionResult into one.

    Constructor pattern matches GapFiller(llm, validator).
    LLM is optional — without it, summaries are concatenated with a separator.
    """

    SUMMARY_SEPARATOR = "\n\n---\n\n"

    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm

    def merge_chunks(
        self,
        chunk_results: list[CurriculumExtractionResult],
    ) -> tuple[CurriculumExtractionResult, MergeReport]:
        """Merge multiple chunk extraction results into a single result.

        Args:
            chunk_results: Ordered list of per-chunk results (chunk 0, 1, 2...).
                           Must all be from the same chapter.

        Returns:
            Tuple of (merged result, merge diagnostic report).

        Raises:
            ValueError: If chunk_results is empty or chunks are from
                        different chapters.
        """
        if not chunk_results:
            raise ValueError("chunk_results must not be empty")

        self._validate_chunks(chunk_results)

        report = MergeReport()

        # Trivial case: single chunk
        if len(chunk_results) == 1:
            result = chunk_results[0]
            report.total_input_nodes = len(result.nodes)
            report.unique_identity_keys = len(result.nodes)
            report.singleton_node_count = len(result.nodes)
            report.total_output_nodes = len(result.nodes)
            report.total_input_relationships = len(result.relationships)
            report.total_output_relationships = len(result.relationships)
            return result, report

        # Collect all nodes from all chunks
        all_nodes = self._collect_all_nodes(chunk_results)
        report.total_input_nodes = len(all_nodes)
        report.total_input_relationships = sum(
            len(r.relationships) for r in chunk_results
        )

        # Group by identity key
        identity_groups = group_by_identity(all_nodes)
        report.unique_identity_keys = len(identity_groups)

        # Merge each group
        merged_nodes: list[ExtractionNode] = []
        for key, group in identity_groups.items():
            if len(group) == 1:
                merged_nodes.append(group[0])
                report.singleton_node_count += 1
            else:
                merged_node = self._merge_node_group(group, report)
                merged_nodes.append(merged_node)
                report.merged_node_count += 1

        # Build UID remap
        uid_remap = self._build_uid_remap(identity_groups)
        report.uid_rewrites = len(uid_remap)

        # Merge relationships
        merged_rels = self._merge_relationships(chunk_results, uid_remap)
        report.total_output_relationships = len(merged_rels)

        # Rewire hierarchy
        self._rewire_hierarchy(merged_nodes, uid_remap)

        # Reassign within_chapter_order
        merged_nodes = self._reassign_within_chapter_order(merged_nodes)
        report.total_output_nodes = len(merged_nodes)

        # Collect warnings from all chunks
        all_warnings = []
        for cr in chunk_results:
            all_warnings.extend(cr.warnings)

        logger.info(report.summary())

        # Assemble result from first chunk's metadata
        result = chunk_results[0].model_copy(
            update={
                "nodes": merged_nodes,
                "relationships": merged_rels,
                "warnings": all_warnings,
            }
        )

        return result, report

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_chunks(
        self,
        chunk_results: list[CurriculumExtractionResult],
    ) -> None:
        """Ensure all chunks belong to the same chapter."""
        first = chunk_results[0]
        for i, cr in enumerate(chunk_results[1:], 1):
            if cr.subject != first.subject:
                raise ValueError(
                    f"Chunk {i} has subject '{cr.subject}', "
                    f"expected '{first.subject}'"
                )
            if cr.chapter_title != first.chapter_title:
                raise ValueError(
                    f"Chunk {i} has chapter_title '{cr.chapter_title}', "
                    f"expected '{first.chapter_title}'"
                )

    # ------------------------------------------------------------------
    # Node collection
    # ------------------------------------------------------------------

    def _collect_all_nodes(
        self,
        chunk_results: list[CurriculumExtractionResult],
    ) -> list[ExtractionNode]:
        """Flatten all nodes from all chunks, preserving chunk order."""
        all_nodes: list[ExtractionNode] = []
        for cr in chunk_results:
            all_nodes.extend(cr.nodes)
        return all_nodes

    # ------------------------------------------------------------------
    # Node merging
    # ------------------------------------------------------------------

    def _merge_node_group(
        self,
        nodes: list[ExtractionNode],
        report: MergeReport,
    ) -> ExtractionNode:
        """Merge a group of nodes that share the same identity key.

        The first node (earliest chunk) is treated as canonical.
        """
        canonical = nodes[0]

        # topic_name: longest variant
        topic_name = max(
            (n.topic_name for n in nodes), key=len
        )

        # summary: concatenate non-empty, then optionally LLM reconcile
        summaries = [n.summary for n in nodes if n.summary]
        summary = self._reconcile_summaries(summaries, topic_name, report)

        # source_text: concatenate
        source_texts = [n.source_text for n in nodes if n.source_text]
        source_text = self.SUMMARY_SEPARATOR.join(source_texts)

        # page range
        page_start = min(n.page_start for n in nodes)
        page_end = max(n.page_end for n in nodes)

        # section_number: first non-None
        section_number = next(
            (n.section_number for n in nodes if n.section_number is not None),
            None,
        )

        # difficulty: most common, tie-break harder
        difficulty = self._merge_difficulty(nodes)

        # estimated_duration_minutes: max (conservative)
        estimated_duration = max(n.estimated_duration_minutes for n in nodes)

        # visual_hint: first non-None, prefer longest
        visual_hints = [n.visual_hint for n in nodes if n.visual_hint]
        visual_hint = max(visual_hints, key=len) if visual_hints else None

        # parent_uid: first non-None from earliest chunk
        parent_uid = next(
            (n.parent_uid for n in nodes if n.parent_uid is not None),
            None,
        )

        # children_uids: union
        all_children: list[str] = []
        seen_children: set[str] = set()
        for n in nodes:
            for child_uid in n.children_uids:
                if child_uid not in seen_children:
                    seen_children.add(child_uid)
                    all_children.append(child_uid)

        # metadata: shallow merge + provenance
        merged_metadata: dict = {}
        for n in nodes:
            merged_metadata.update(n.metadata)
        merged_metadata["chunk_merged"] = True
        merged_metadata["merge_sources"] = len(nodes)

        # within_chapter_order: min (reassigned later)
        within_chapter_order = min(n.within_chapter_order for n in nodes)

        return ExtractionNode(
            uid=canonical.uid,
            topic_name=topic_name,
            concept_type=canonical.concept_type,
            resolution_level=canonical.resolution_level,
            section_number=section_number,
            summary=summary,
            source_text=source_text,
            page_start=page_start,
            page_end=page_end,
            chapter_order=canonical.chapter_order,
            within_chapter_order=within_chapter_order,
            difficulty=difficulty,
            estimated_duration_minutes=estimated_duration,
            visual_hint=visual_hint,
            parent_uid=parent_uid,
            children_uids=all_children,
            metadata=merged_metadata,
        )

    def _reconcile_summaries(
        self,
        summaries: list[str],
        topic_name: str,
        report: MergeReport,
    ) -> str:
        """Merge multiple summaries into one coherent summary.

        If LLM is available, uses it for reconciliation.
        Otherwise, concatenates with separator.
        """
        if not summaries:
            return ""
        if len(summaries) == 1:
            return summaries[0]

        # Try LLM reconciliation
        if self.llm is not None:
            try:
                system_prompt = get_summary_reconciliation_system_prompt()
                user_prompt = build_summary_reconciliation_prompt(
                    topic_name, summaries
                )
                response = self.llm.generate(system_prompt, user_prompt)
                if response.content.strip():
                    report.llm_reconciliations += 1
                    return response.content.strip()
            except Exception:
                logger.warning(
                    "LLM summary reconciliation failed for '%s', "
                    "falling back to concatenation",
                    topic_name,
                    exc_info=True,
                )

        # Fallback: concatenate
        return self.SUMMARY_SEPARATOR.join(summaries)

    def _merge_difficulty(self, nodes: list[ExtractionNode]) -> Difficulty:
        """Pick most common difficulty, tie-break toward harder."""
        counts = Counter(n.difficulty for n in nodes)
        max_count = max(counts.values())
        candidates = [d for d, c in counts.items() if c == max_count]
        # Tie-break: pick hardest
        return max(candidates, key=lambda d: _DIFFICULTY_ORDER.get(d, 1))

    # ------------------------------------------------------------------
    # UID remapping
    # ------------------------------------------------------------------

    def _build_uid_remap(
        self,
        identity_groups: dict[str, list[ExtractionNode]],
    ) -> dict[str, str]:
        """Build old_uid → canonical_uid mapping.

        For each identity group, the canonical UID is the first node's UID.
        All other UIDs in the group map to this canonical UID.
        """
        remap: dict[str, str] = {}
        for group in identity_groups.values():
            if len(group) <= 1:
                continue
            canonical_uid = group[0].uid
            for node in group[1:]:
                if node.uid != canonical_uid:
                    remap[node.uid] = canonical_uid
        return remap

    # ------------------------------------------------------------------
    # Relationship merging
    # ------------------------------------------------------------------

    def _merge_relationships(
        self,
        chunk_results: list[CurriculumExtractionResult],
        uid_remap: dict[str, str],
    ) -> list[ExtractionRelationship]:
        """Union all relationships, dedup by relationship_key.

        Applies uid_remap to from_uid and to_uid before deduping.
        """
        seen_keys: set[str] = set()
        merged: list[ExtractionRelationship] = []

        for cr in chunk_results:
            for rel in cr.relationships:
                from_uid = uid_remap.get(rel.from_uid, rel.from_uid)
                to_uid = uid_remap.get(rel.to_uid, rel.to_uid)

                # Regenerate key with remapped UIDs
                new_key = generate_relationship_key(
                    rel.type.value, from_uid, to_uid
                )

                if new_key in seen_keys:
                    continue
                seen_keys.add(new_key)

                merged.append(
                    ExtractionRelationship(
                        relationship_key=new_key,
                        type=rel.type,
                        from_uid=from_uid,
                        to_uid=to_uid,
                        label=rel.label,
                        properties=dict(rel.properties),
                    )
                )

        return merged

    # ------------------------------------------------------------------
    # Hierarchy rewiring
    # ------------------------------------------------------------------

    def _rewire_hierarchy(
        self,
        nodes: list[ExtractionNode],
        uid_remap: dict[str, str],
    ) -> None:
        """Rewrite parent_uid and children_uids through uid_remap.

        Also ensures bidirectional consistency.
        """
        node_uids = {n.uid for n in nodes}
        uid_to_node = {n.uid: n for n in nodes}

        for node in nodes:
            # Remap parent_uid
            if node.parent_uid and node.parent_uid in uid_remap:
                node.parent_uid = uid_remap[node.parent_uid]

            # Remap children_uids
            new_children: list[str] = []
            seen: set[str] = set()
            for child_uid in node.children_uids:
                remapped = uid_remap.get(child_uid, child_uid)
                if remapped not in seen:
                    seen.add(remapped)
                    new_children.append(remapped)
            node.children_uids = new_children

        # Ensure bidirectional consistency
        for node in nodes:
            if node.parent_uid and node.parent_uid in uid_to_node:
                parent = uid_to_node[node.parent_uid]
                if node.uid not in parent.children_uids:
                    parent.children_uids.append(node.uid)

    # ------------------------------------------------------------------
    # Order reassignment
    # ------------------------------------------------------------------

    def _reassign_within_chapter_order(
        self,
        nodes: list[ExtractionNode],
    ) -> list[ExtractionNode]:
        """Reassign sequential within_chapter_order 1..N.

        Sort by the node's current within_chapter_order (which was set
        to min of its group during merge), then assign 1, 2, 3...
        """
        sorted_nodes = sorted(nodes, key=lambda n: n.within_chapter_order)

        for i, node in enumerate(sorted_nodes, 1):
            node.within_chapter_order = i
            node.global_teaching_order = node.chapter_order * 1000 + i

        return sorted_nodes
