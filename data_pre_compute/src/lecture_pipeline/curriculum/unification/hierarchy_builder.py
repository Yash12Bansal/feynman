"""Hierarchy builder — creates Subject→Unit→Chapter tree and wires edges.

After chapter-level extraction, concepts exist as flat lists per chapter.
This module creates the higher-level hierarchy nodes (Subject, Unit, Chapter)
and wires CONTAINS/SUMMARIZES edges to form the full resolution tree:

    Subject → Unit → Chapter → Concept → Detail
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lecture_pipeline.curriculum.id_generator import (
    generate_chapter_uid,
    generate_relationship_key,
    generate_subject_uid,
    generate_unit_uid,
)
from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    Difficulty,
    ExtractionNode,
    ExtractionRelationship,
    ResolutionLevel,
)


@dataclass
class HierarchyResult:
    """Output of hierarchy building."""

    hierarchy_nodes: list[ExtractionNode] = field(default_factory=list)
    hierarchy_relationships: list[ExtractionRelationship] = field(default_factory=list)
    updated_nodes: list[ExtractionNode] = field(default_factory=list)


def _make_contains_edge(
    from_uid: str, to_uid: str
) -> ExtractionRelationship:
    """Create a CONTAINS relationship."""
    return ExtractionRelationship(
        relationship_key=generate_relationship_key("contains", from_uid, to_uid),
        type=CurriculumRelationType.CONTAINS,
        from_uid=from_uid,
        to_uid=to_uid,
        label="contains",
    )


def _make_summarizes_edge(
    from_uid: str, to_uid: str
) -> ExtractionRelationship:
    """Create a SUMMARIZES relationship."""
    return ExtractionRelationship(
        relationship_key=generate_relationship_key("summarizes", from_uid, to_uid),
        type=CurriculumRelationType.SUMMARIZES,
        from_uid=from_uid,
        to_uid=to_uid,
        label="summarizes",
    )


class HierarchyBuilder:
    """Builds Subject→Unit→Chapter hierarchy from BookSkeleton and chapter results."""

    def __init__(self, book_skeleton: BookSkeleton, subject: str) -> None:
        self._skeleton = book_skeleton
        self._subject = subject

    def build(
        self,
        chapter_results: list[CurriculumExtractionResult],
    ) -> HierarchyResult:
        """Create hierarchy nodes and wire CONTAINS/SUMMARIZES edges.

        Returns hierarchy nodes, edges, and updated concept nodes
        (with parent_uid set to their chapter node).
        """
        result = HierarchyResult()

        # Collect all concept nodes from chapter results
        all_concept_nodes: list[ExtractionNode] = []
        for cr in chapter_results:
            all_concept_nodes.extend(cr.nodes)

        # Compute global page range
        if all_concept_nodes:
            global_page_start = min(n.page_start for n in all_concept_nodes)
            global_page_end = max(n.page_end for n in all_concept_nodes)
        else:
            global_page_start = 1
            global_page_end = 1

        # --- Subject node ---
        subject_uid = generate_subject_uid(self._subject)
        subject_node = ExtractionNode(
            uid=subject_uid,
            topic_name=self._subject,
            concept_type=ConceptType.TOPIC,
            resolution_level=ResolutionLevel.SYLLABUS,
            summary=self._skeleton.subject_overview,
            source_text="",
            page_start=global_page_start,
            page_end=global_page_end,
            chapter_order=0,
            within_chapter_order=0,
            difficulty=Difficulty.INTERMEDIATE,
            children_uids=[],
            metadata={"hierarchy_node": True},
        )

        # --- Build chapter_index → chapter_title mapping ---
        chapter_title_by_index: dict[int, str] = {}
        for ch in self._skeleton.chapters:
            chapter_title_by_index[ch.chapter_index] = ch.title

        # --- Build chapter_index → unit mapping ---
        chapter_to_unit: dict[int, str] = {}
        for unit in self._skeleton.units:
            for ch_idx in unit.chapter_indices:
                chapter_to_unit[ch_idx] = unit.unit_name

        # --- Unit nodes ---
        unit_nodes: dict[str, ExtractionNode] = {}
        has_units = len(self._skeleton.units) > 0

        if has_units:
            for unit in self._skeleton.units:
                unit_uid = generate_unit_uid(self._subject, unit.unit_name)

                # Compute page range from constituent chapters
                unit_page_start = global_page_end
                unit_page_end = global_page_start
                unit_min_chapter = 999
                for ch_idx in unit.chapter_indices:
                    ch_summary = self._skeleton.chapter_by_index(ch_idx)
                    if ch_summary:
                        unit_page_start = min(unit_page_start, ch_summary.page_start)
                        unit_page_end = max(unit_page_end, ch_summary.page_end)
                        unit_min_chapter = min(unit_min_chapter, ch_idx)

                unit_node = ExtractionNode(
                    uid=unit_uid,
                    topic_name=unit.unit_name,
                    concept_type=ConceptType.TOPIC,
                    resolution_level=ResolutionLevel.UNIT,
                    summary=unit.theme,
                    source_text="",
                    page_start=unit_page_start,
                    page_end=unit_page_end,
                    chapter_order=unit_min_chapter,
                    within_chapter_order=0,
                    difficulty=Difficulty.INTERMEDIATE,
                    parent_uid=subject_uid,
                    children_uids=[],
                    metadata={"hierarchy_node": True},
                )
                unit_nodes[unit.unit_name] = unit_node

                # Subject → Unit edges
                subject_node.children_uids.append(unit_uid)
                result.hierarchy_relationships.append(
                    _make_contains_edge(subject_uid, unit_uid)
                )
                result.hierarchy_relationships.append(
                    _make_summarizes_edge(subject_uid, unit_uid)
                )

        # --- Chapter nodes ---
        chapter_nodes: dict[int, ExtractionNode] = {}

        for cr in chapter_results:
            if not cr.chapter_title:
                continue

            # Determine chapter_index — prefer the actual chapter_order from
            # the extraction's concept nodes (reliable), fall back to skeleton
            # title lookup (can fail when PDF TOC names differ from skeleton).
            ch_index_from_nodes = None
            if cr.nodes:
                # All concepts in a chapter share the same chapter_order
                ch_index_from_nodes = cr.nodes[0].chapter_order

            ch_summary = self._skeleton.chapter_by_title(cr.chapter_title)
            if not ch_summary and ch_index_from_nodes:
                # Title lookup failed — try by index instead
                ch_summary = self._skeleton.chapter_by_index(ch_index_from_nodes)

            ch_index = ch_index_from_nodes or (ch_summary.chapter_index if ch_summary else 0)
            ch_page_start = ch_summary.page_start if ch_summary else (cr.nodes[0].page_start if cr.nodes else 1)
            ch_page_end = ch_summary.page_end if ch_summary else (cr.nodes[-1].page_end if cr.nodes else 1)
            ch_skeleton_summary = ch_summary.summary if ch_summary else ""

            # Use human-readable title from skeleton when available,
            # otherwise keep the PDF bookmark name
            ch_display_title = ch_summary.title if ch_summary else cr.chapter_title

            chapter_uid = generate_chapter_uid(self._subject, cr.chapter_title)

            # Determine parent: unit or subject
            unit_name = chapter_to_unit.get(ch_index)
            if has_units and unit_name and unit_name in unit_nodes:
                parent_uid = unit_nodes[unit_name].uid
                unit_nodes[unit_name].children_uids.append(chapter_uid)
                # Unit → Chapter edges
                result.hierarchy_relationships.append(
                    _make_contains_edge(parent_uid, chapter_uid)
                )
                result.hierarchy_relationships.append(
                    _make_summarizes_edge(parent_uid, chapter_uid)
                )
            else:
                parent_uid = subject_uid
                subject_node.children_uids.append(chapter_uid)
                # Subject → Chapter edges (no units)
                result.hierarchy_relationships.append(
                    _make_contains_edge(subject_uid, chapter_uid)
                )
                result.hierarchy_relationships.append(
                    _make_summarizes_edge(subject_uid, chapter_uid)
                )

            chapter_node = ExtractionNode(
                uid=chapter_uid,
                topic_name=ch_display_title,
                concept_type=ConceptType.TOPIC,
                resolution_level=ResolutionLevel.CHAPTER,
                summary=ch_skeleton_summary,
                source_text="",
                page_start=ch_page_start,
                page_end=ch_page_end,
                chapter_order=ch_index,
                within_chapter_order=0,
                difficulty=Difficulty.INTERMEDIATE,
                parent_uid=parent_uid,
                children_uids=[],
                metadata={
                    "hierarchy_node": True,
                    "pdf_toc_title": cr.chapter_title,  # preserve original PDF name
                },
            )
            chapter_nodes[ch_index] = chapter_node

        # --- Wire concepts to chapter nodes ---
        # Create Chapter→Concept CONTAINS for concept-level nodes
        # (resolution_level in {concept, detail with no parent concept}).
        # Details that already point to a parent concept keep that parent,
        # but still get a Chapter→Concept edge for traversal.
        updated_nodes: list[ExtractionNode] = []
        wired_to_chapter: set[str] = set()

        for node in all_concept_nodes:
            ch_node = chapter_nodes.get(node.chapter_order)
            if not ch_node:
                updated_nodes.append(node)
                continue

            # Set parent_uid to chapter for top-level concepts (no parent yet)
            if node.parent_uid is None:
                updated = node.model_copy(update={"parent_uid": ch_node.uid})
                updated_nodes.append(updated)
            else:
                updated_nodes.append(node)

            # Create Chapter → Node CONTAINS edge for ALL nodes in this chapter
            # (not just orphans). This ensures the teaching agent can traverse
            # Chapter → Concept/Detail via CONTAINS relationships.
            if node.uid not in wired_to_chapter:
                ch_node.children_uids.append(node.uid)
                result.hierarchy_relationships.append(
                    _make_contains_edge(ch_node.uid, node.uid)
                )
                result.hierarchy_relationships.append(
                    _make_summarizes_edge(ch_node.uid, node.uid)
                )
                wired_to_chapter.add(node.uid)

        # Assemble result
        result.hierarchy_nodes = [subject_node]
        result.hierarchy_nodes.extend(unit_nodes.values())
        result.hierarchy_nodes.extend(chapter_nodes.values())
        result.updated_nodes = updated_nodes

        return result
