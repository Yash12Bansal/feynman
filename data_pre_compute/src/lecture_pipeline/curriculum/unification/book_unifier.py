"""Book unifier — merges all chapter extractions into one unified book graph.

Orchestrates:
1. Cross-chapter reference resolution (placeholder UIDs → real UIDs)
2. Hierarchy building (Subject → Unit → Chapter → Concept → Detail)
3. Shared concept detection (cross-chapter SHARED_FOUNDATION edges)
4. Referential integrity validation
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    CurriculumExtractionResult,
    ExtractionSource,
)
from lecture_pipeline.curriculum.unification.hierarchy_builder import HierarchyBuilder
from lecture_pipeline.curriculum.unification.reference_resolver import ReferenceResolver
from lecture_pipeline.curriculum.unification.shared_concept_detector import (
    SharedConceptDetector,
)


@dataclass
class UnificationReport:
    """Diagnostic report for the book unification process."""

    total_chapters: int = 0
    total_input_nodes: int = 0
    total_input_relationships: int = 0
    hierarchy_nodes_created: int = 0
    cross_chapter_refs_resolved: int = 0
    cross_chapter_refs_unresolved: int = 0
    shared_concepts_detected: int = 0
    total_output_nodes: int = 0
    total_output_relationships: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary of the unification."""
        lines = [
            f"Book Unification: {self.total_chapters} chapters merged",
            f"  Input:  {self.total_input_nodes} nodes, {self.total_input_relationships} relationships",
            f"  Output: {self.total_output_nodes} nodes, {self.total_output_relationships} relationships",
            f"  Hierarchy nodes created: {self.hierarchy_nodes_created}",
            f"  Cross-chapter refs resolved: {self.cross_chapter_refs_resolved}",
            f"  Cross-chapter refs unresolved: {self.cross_chapter_refs_unresolved}",
            f"  Shared concepts detected: {self.shared_concepts_detected}",
        ]
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
        return "\n".join(lines)


class BookUnifier:
    """Merges per-chapter extractions into a single unified book result."""

    def unify(
        self,
        chapter_results: list[CurriculumExtractionResult],
        book_skeleton: BookSkeleton,
    ) -> tuple[CurriculumExtractionResult, UnificationReport]:
        """Unify all chapter extractions into one book-level result.

        Args:
            chapter_results: Per-chapter CurriculumExtractionResult objects
                (scope="chapter"). Must all have the same subject/textbook_title.
            book_skeleton: The book's structural metadata.

        Returns:
            Tuple of (unified result with scope="book", diagnostic report).

        Raises:
            ValueError: If chapter_results is empty or has mismatched subjects.
        """
        report = UnificationReport()

        # --- Validate ---
        self._validate(chapter_results)

        report.total_chapters = len(chapter_results)
        subject = chapter_results[0].subject
        textbook_title = chapter_results[0].textbook_title

        # --- Collect all nodes and relationships ---
        all_nodes = []
        all_relationships = []
        for cr in chapter_results:
            all_nodes.extend(cr.nodes)
            all_relationships.extend(cr.relationships)

        report.total_input_nodes = len(all_nodes)
        report.total_input_relationships = len(all_relationships)

        # --- 1. Resolve cross-chapter references ---
        resolver = ReferenceResolver(book_skeleton)
        resolution = resolver.resolve(all_relationships, all_nodes)

        all_relationships = resolution.resolved_relationships
        report.cross_chapter_refs_resolved = resolution.resolved_count
        report.cross_chapter_refs_unresolved = resolution.unresolved_count
        report.warnings.extend(resolution.warnings)

        # --- 2. Build hierarchy ---
        hierarchy_builder = HierarchyBuilder(book_skeleton, subject)
        hierarchy = hierarchy_builder.build(chapter_results)

        # Replace concept nodes with updated versions (parent_uid rewired)
        all_nodes = hierarchy.updated_nodes
        # Add hierarchy nodes (Subject, Unit, Chapter)
        all_nodes = hierarchy.hierarchy_nodes + all_nodes
        # Add hierarchy edges
        all_relationships.extend(hierarchy.hierarchy_relationships)
        report.hierarchy_nodes_created = len(hierarchy.hierarchy_nodes)

        # --- 3. Detect shared concepts ---
        detector = SharedConceptDetector()
        shared = detector.detect(all_nodes)
        all_relationships.extend(shared.new_relationships)
        report.shared_concepts_detected = shared.shared_pairs_count

        # --- 4. Validate referential integrity ---
        node_uids = {n.uid for n in all_nodes}
        for rel in all_relationships:
            if rel.from_uid not in node_uids and "::" not in rel.from_uid:
                report.warnings.append(
                    f"Dangling from_uid: {rel.from_uid} in {rel.relationship_key}"
                )
            if rel.to_uid not in node_uids and "::" not in rel.to_uid:
                report.warnings.append(
                    f"Dangling to_uid: {rel.to_uid} in {rel.relationship_key}"
                )

        # --- 5. Assemble unified result ---
        report.total_output_nodes = len(all_nodes)
        report.total_output_relationships = len(all_relationships)

        # Build source from first chapter (scope updated)
        base_source = chapter_results[0].source
        unified_source = ExtractionSource(
            textbook_title=textbook_title,
            chapter_title="(book)",
            page_range=f"1-{book_skeleton.total_pages}",
            extractor_model=base_source.extractor_model,
            extraction_timestamp=base_source.extraction_timestamp,
            confidence=base_source.confidence,
        )

        unified = CurriculumExtractionResult(
            version=chapter_results[0].version,
            subject=subject,
            textbook_title=textbook_title,
            scope="book",
            chapter_title=None,
            source=unified_source,
            book_skeleton=book_skeleton,
            nodes=all_nodes,
            relationships=all_relationships,
            warnings=report.warnings.copy(),
        )

        return unified, report

    def _validate(
        self, chapter_results: list[CurriculumExtractionResult]
    ) -> None:
        """Validate inputs before unification."""
        if not chapter_results:
            raise ValueError("Cannot unify empty list of chapter results")

        subjects = {cr.subject for cr in chapter_results}
        if len(subjects) > 1:
            raise ValueError(
                f"All chapters must have the same subject, got: {subjects}"
            )

        titles = {cr.textbook_title for cr in chapter_results}
        if len(titles) > 1:
            raise ValueError(
                f"All chapters must have the same textbook_title, got: {titles}"
            )
