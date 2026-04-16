"""Structural validation for curriculum extraction results.

Deterministic checks — no LLM calls. Validates CurriculumExtractionResult
against structural rules and (optionally) anchor-based completeness.

Usage:
    validator = StructuralValidator()
    report = validator.validate(extraction, anchors)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from ..anchors.models import ExtractionAnchors
from ..models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
)
from .models import ValidationReport

logger = logging.getLogger(__name__)


class StructuralValidator:
    """Pure validation — input in, report out. No mutations, no LLM calls.

    Checks are split into:
    - Structural checks (always run): duplicates, referential integrity,
      required properties, hierarchy, teaching order, circular deps
    - Completeness checks (require anchors): section/equation/figure/example
      coverage, visual hints, density
    """

    # Completeness thresholds (from design doc)
    EQUATION_COVERAGE_THRESHOLD = 0.70
    EXAMPLE_COVERAGE_THRESHOLD = 0.80
    MIN_CONCEPTS_PER_PAGE = 3.0

    # Concept types that MUST have visual_hint
    VISUAL_HINT_REQUIRED_TYPES = frozenset({
        ConceptType.FORMULA,
        ConceptType.DERIVATION,
        ConceptType.EXAMPLE,
        ConceptType.EXPERIMENT,
        ConceptType.VISUALIZATION,
    })

    def validate(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors | None = None,
    ) -> ValidationReport:
        """Run all validation checks and return a report.

        Args:
            extraction: The extraction result to validate.
            anchors: If provided, also run completeness checks against anchors.

        Returns:
            ValidationReport with all issues found.
        """
        report = ValidationReport(
            node_count=len(extraction.nodes),
            relationship_count=len(extraction.relationships),
        )

        # Structural checks (always run)
        self._check_duplicate_uids(extraction, report)
        self._check_duplicate_relationship_keys(extraction, report)
        self._check_referential_integrity(extraction, report)
        self._check_required_properties(extraction, report)
        self._check_type_consistency(extraction, report)
        self._check_hierarchy_integrity(extraction, report)
        self._check_teaching_order_continuity(extraction, report)
        self._check_circular_dependencies(extraction, report)

        # Completeness checks (require anchors)
        if anchors is not None:
            self._check_page_coverage(extraction, anchors, report)
            self._check_extraction_completeness(extraction, anchors, report)

        logger.info(report.summary())
        return report

    # ------------------------------------------------------------------
    # Structural checks
    # ------------------------------------------------------------------

    def _check_duplicate_uids(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Every node UID must be unique."""
        seen: set[str] = set()
        for node in extraction.nodes:
            if node.uid in seen:
                report.add_error(
                    "DUPLICATE_UID",
                    f"Duplicate node UID: {node.uid}",
                    entity_key=node.uid,
                )
            seen.add(node.uid)

    def _check_duplicate_relationship_keys(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Every relationship key must be unique."""
        seen: set[str] = set()
        for rel in extraction.relationships:
            if rel.relationship_key in seen:
                report.add_error(
                    "DUPLICATE_RELATIONSHIP_KEY",
                    f"Duplicate relationship key: {rel.relationship_key}",
                    relationship_key=rel.relationship_key,
                )
            seen.add(rel.relationship_key)

    def _check_referential_integrity(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """All relationship endpoints must reference existing nodes.

        Cross-chapter references (containing '::') are excluded — they're
        resolved in Phase 7 (Book Unification).
        """
        node_uids = extraction.node_uids

        for rel in extraction.relationships:
            if rel.from_uid not in node_uids:
                report.add_error(
                    "DANGLING_REFERENCE",
                    f"Relationship '{rel.relationship_key}' references "
                    f"nonexistent from_uid: {rel.from_uid}",
                    relationship_key=rel.relationship_key,
                )

            # Skip cross-chapter references (resolved in Phase 7)
            if "::" in rel.to_uid:
                continue

            if rel.to_uid not in node_uids:
                report.add_error(
                    "DANGLING_REFERENCE",
                    f"Relationship '{rel.relationship_key}' references "
                    f"nonexistent to_uid: {rel.to_uid}",
                    relationship_key=rel.relationship_key,
                )

    def _check_required_properties(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Verify required node properties are present and valid."""
        for node in extraction.nodes:
            if not node.topic_name or not node.topic_name.strip():
                report.add_error(
                    "EMPTY_TOPIC_NAME",
                    f"Node '{node.uid}' has empty topic_name",
                    entity_key=node.uid,
                )

            if not node.summary:
                report.add_warning(
                    "EMPTY_SUMMARY",
                    f"Node '{node.uid}' ({node.topic_name}) has empty summary",
                    entity_key=node.uid,
                )

            if node.page_start > node.page_end:
                report.add_error(
                    "INVALID_PAGE_RANGE",
                    f"Node '{node.uid}' has page_start ({node.page_start}) > "
                    f"page_end ({node.page_end})",
                    entity_key=node.uid,
                )

    def _check_type_consistency(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Heuristic checks that concept types match their content.

        Warnings only — heuristics can false-positive.
        """
        for node in extraction.nodes:
            if node.concept_type == ConceptType.FORMULA:
                text = f"{node.topic_name} {node.summary}".lower()
                if not _has_equation_content(text):
                    report.add_warning(
                        "FORMULA_NO_EQUATION",
                        f"FORMULA node '{node.topic_name}' has no equation-like "
                        f"content in topic_name or summary",
                        entity_key=node.uid,
                    )

    def _check_hierarchy_integrity(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Verify parent-child references are consistent."""
        node_uids = extraction.node_uids

        for node in extraction.nodes:
            # Check parent_uid exists
            if node.parent_uid and node.parent_uid not in node_uids:
                report.add_error(
                    "BROKEN_HIERARCHY",
                    f"Node '{node.topic_name}' has parent_uid "
                    f"'{node.parent_uid}' that doesn't exist",
                    entity_key=node.uid,
                )

            # Check children_uids exist
            for child_uid in node.children_uids:
                if child_uid not in node_uids:
                    report.add_error(
                        "BROKEN_HIERARCHY",
                        f"Node '{node.topic_name}' lists child "
                        f"'{child_uid}' that doesn't exist",
                        entity_key=node.uid,
                    )

        # Check bidirectional consistency: if A lists B as child, B should have A as parent
        uid_to_node = {n.uid: n for n in extraction.nodes}
        for node in extraction.nodes:
            if node.parent_uid and node.parent_uid in uid_to_node:
                parent = uid_to_node[node.parent_uid]
                if node.uid not in parent.children_uids:
                    report.add_error(
                        "BROKEN_HIERARCHY",
                        f"Node '{node.topic_name}' has parent "
                        f"'{parent.topic_name}' but parent doesn't list it as child",
                        entity_key=node.uid,
                    )

    def _check_teaching_order_continuity(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Check for gaps in within_chapter_order sequence."""
        if not extraction.nodes:
            return

        orders = sorted(n.within_chapter_order for n in extraction.nodes)
        expected = list(range(orders[0], orders[0] + len(orders)))

        if orders != expected:
            missing = set(expected) - set(orders)
            if missing:
                report.add_warning(
                    "TEACHING_ORDER_GAP",
                    f"Gap in within_chapter_order: missing positions {sorted(missing)}",
                )

    def _check_circular_dependencies(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Detect cycles in PREREQUISITE edges via DFS.

        Only checks edges where both endpoints are in this extraction
        (cross-chapter refs are excluded).
        """
        node_uids = extraction.node_uids

        # Build adjacency list for PREREQUISITE edges
        graph: dict[str, list[str]] = defaultdict(list)
        for rel in extraction.relationships:
            if rel.type != CurriculumRelationType.PREREQUISITE:
                continue
            if rel.from_uid in node_uids and rel.to_uid in node_uids:
                graph[rel.from_uid].append(rel.to_uid)

        if not graph:
            return

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {uid: WHITE for uid in node_uids}
        parent_map: dict[str, str | None] = {}

        def dfs(u: str) -> list[str] | None:
            color[u] = GRAY
            for v in graph.get(u, []):
                if color.get(v) == GRAY:
                    # Back edge found — reconstruct cycle
                    cycle = [v, u]
                    cur = u
                    while cur != v and cur in parent_map and parent_map[cur] is not None:
                        cur = parent_map[cur]  # type: ignore[assignment]
                        cycle.append(cur)
                    cycle.reverse()
                    return cycle
                if color.get(v) == WHITE:
                    parent_map[v] = u
                    result = dfs(v)
                    if result:
                        return result
            color[u] = BLACK
            return None

        for uid in node_uids:
            if color.get(uid) == WHITE and uid in graph:
                parent_map[uid] = None
                cycle = dfs(uid)
                if cycle:
                    cycle_names = []
                    uid_to_name = {n.uid: n.topic_name for n in extraction.nodes}
                    for c in cycle:
                        cycle_names.append(uid_to_name.get(c, c))

                    report.add_error(
                        "CIRCULAR_PREREQUISITE",
                        f"Circular prerequisite chain: "
                        f"{' → '.join(cycle_names)}",
                        details={"cycle": cycle},
                    )
                    return  # One cycle is enough to flag

    # ------------------------------------------------------------------
    # Completeness checks (require anchors)
    # ------------------------------------------------------------------

    def _check_page_coverage(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        report: ValidationReport,
    ) -> None:
        """Check that every page in the chapter range has at least one concept."""
        if not extraction.nodes or anchors.page_count == 0:
            return

        all_page_starts = [n.page_start for n in extraction.nodes]
        all_page_ends = [n.page_end for n in extraction.nodes]
        chapter_start = min(all_page_starts)
        chapter_end = max(all_page_ends)

        uncovered: list[int] = []
        for page in range(chapter_start, chapter_end + 1):
            covered = any(
                n.page_start <= page <= n.page_end for n in extraction.nodes
            )
            if not covered:
                uncovered.append(page)

        if uncovered:
            report.add_warning(
                "UNCOVERED_PAGES",
                f"{len(uncovered)} pages have no concept coverage: "
                f"{uncovered[:10]}{'...' if len(uncovered) > 10 else ''}",
                details={"uncovered_pages": uncovered},
            )

    def _check_extraction_completeness(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        report: ValidationReport,
    ) -> None:
        """Compare extraction against deterministic anchors.

        This is the critical completeness check — LLMs systematically
        under-extract, and anchors are what we KNOW exists in the source.
        """
        self._check_section_coverage(extraction, anchors, report)
        self._check_equation_coverage(extraction, anchors, report)
        self._check_figure_coverage(extraction, anchors, report)
        self._check_example_coverage(extraction, anchors, report)
        self._check_visual_hint_coverage(extraction, report)
        self._check_density(extraction, anchors, report)

    def _check_section_coverage(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        report: ValidationReport,
    ) -> None:
        """Every section number in anchors must have at least one node."""
        if not anchors.section_numbers:
            return

        extracted_sections = {
            n.section_number for n in extraction.nodes if n.section_number
        }

        missing = []
        for section in anchors.section_numbers:
            if section.section_number not in extracted_sections:
                missing.append({
                    "section_number": section.section_number,
                    "title": section.title,
                })

        if missing:
            report.add_error(
                "MISSING_SECTIONS",
                f"{len(missing)}/{len(anchors.section_numbers)} textbook sections "
                f"have no concept node. Missing: "
                f"{[f'{s['section_number']} {s['title']}' for s in missing[:5]]}",
                details={"missing_sections": missing},
            )

    def _check_equation_coverage(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        report: ValidationReport,
    ) -> None:
        """At least 70% of anchor equations should have FORMULA nodes."""
        if not anchors.equations:
            return

        formula_nodes = extraction.nodes_by_type(ConceptType.FORMULA)
        formula_text = " ".join(
            f"{n.topic_name} {n.summary} {n.source_text}".lower()
            for n in formula_nodes
        )

        matched = []
        unmatched = []
        for eq_ref in anchors.equations:
            num = _extract_numeric_ref(eq_ref)
            if num and num in formula_text:
                matched.append(eq_ref)
            else:
                unmatched.append(eq_ref)

        if not anchors.equations:
            return

        coverage = len(matched) / len(anchors.equations)
        if coverage < self.EQUATION_COVERAGE_THRESHOLD:
            report.add_error(
                "MISSING_FORMULAS",
                f"Equation coverage {coverage:.0%} < {self.EQUATION_COVERAGE_THRESHOLD:.0%}. "
                f"Source has {len(anchors.equations)} equations, "
                f"{len(formula_nodes)} FORMULA nodes matched {len(matched)}. "
                f"Unmatched: {unmatched[:5]}",
                details={
                    "missing_equations": unmatched,
                    "coverage": coverage,
                },
            )

    def _check_figure_coverage(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        report: ValidationReport,
    ) -> None:
        """100% of figure references should have VISUALIZATION nodes."""
        if not anchors.figure_refs:
            return

        viz_nodes = extraction.nodes_by_type(ConceptType.VISUALIZATION)
        viz_text = " ".join(
            f"{n.topic_name} {n.summary} {n.source_text}".lower()
            for n in viz_nodes
        )

        unmatched = []
        for fig_ref in anchors.figure_refs:
            num = _extract_numeric_ref(fig_ref)
            if not (num and num in viz_text):
                unmatched.append(fig_ref)

        if unmatched:
            report.add_error(
                "MISSING_FIGURES",
                f"{len(unmatched)}/{len(anchors.figure_refs)} figures have no "
                f"VISUALIZATION node: {unmatched[:5]}",
                details={"missing_figures": unmatched},
            )

    def _check_example_coverage(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        report: ValidationReport,
    ) -> None:
        """At least 80% of example references should have EXAMPLE nodes."""
        if not anchors.example_refs:
            return

        example_nodes = extraction.nodes_by_type(ConceptType.EXAMPLE)
        example_text = " ".join(
            f"{n.topic_name} {n.summary} {n.source_text}".lower()
            for n in example_nodes
        )

        matched = []
        unmatched = []
        for ex_ref in anchors.example_refs:
            num = _extract_numeric_ref(ex_ref)
            if num and num in example_text:
                matched.append(ex_ref)
            else:
                unmatched.append(ex_ref)

        coverage = len(matched) / len(anchors.example_refs)
        if coverage < self.EXAMPLE_COVERAGE_THRESHOLD:
            report.add_error(
                "MISSING_EXAMPLES",
                f"Example coverage {coverage:.0%} < {self.EXAMPLE_COVERAGE_THRESHOLD:.0%}. "
                f"Source has {len(anchors.example_refs)} examples, "
                f"matched {len(matched)}. Unmatched: {unmatched[:5]}",
                details={
                    "missing_examples": unmatched,
                    "coverage": coverage,
                },
            )

    def _check_visual_hint_coverage(
        self,
        extraction: CurriculumExtractionResult,
        report: ValidationReport,
    ) -> None:
        """Visual-mandatory concept types must have visual_hint."""
        needing_visuals = [
            n
            for n in extraction.nodes
            if n.concept_type in self.VISUAL_HINT_REQUIRED_TYPES
        ]
        missing = [n for n in needing_visuals if not n.visual_hint]

        if missing:
            report.add_warning(
                "MISSING_VISUAL_HINTS",
                f"{len(missing)}/{len(needing_visuals)} visual-mandatory concepts "
                f"have no visual_hint: "
                f"{[n.topic_name for n in missing[:5]]}",
                details={
                    "nodes_missing_visual_hint": [n.uid for n in missing],
                },
            )

    def _check_density(
        self,
        extraction: CurriculumExtractionResult,
        anchors: ExtractionAnchors,
        report: ValidationReport,
    ) -> None:
        """Check concepts-per-page density."""
        if anchors.page_count == 0:
            return

        density = len(extraction.nodes) / anchors.page_count
        if density < self.MIN_CONCEPTS_PER_PAGE:
            report.add_warning(
                "LOW_CONCEPT_DENSITY",
                f"Only {density:.1f} concepts/page (expected >= "
                f"{self.MIN_CONCEPTS_PER_PAGE:.1f}). "
                f"LLM may be merging concepts that should be separate.",
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_numeric_ref(ref: str) -> str | None:
    """Extract the numeric part from a reference string.

    'Eq. (12.1)' → '12.1'
    'Figure 12.3a' → '12.3'
    'Example 12.1' → '12.1'
    """
    nums = re.findall(r"\d+(?:\.\d+)*", ref)
    return nums[0] if nums else None


def _has_equation_content(text: str) -> bool:
    """Heuristic: does this text contain equation-like content?

    Checks for '=', common math operators, or Greek letter names.
    """
    if "=" in text:
        return True
    math_indicators = [
        "equation", "formula", "f =", "v =", "x =", "e =",
        "sin", "cos", "tan", "sqrt", "integral",
        "omega", "theta", "alpha", "beta", "delta",
        "²", "³", "π", "∫", "∑",
    ]
    return any(ind in text for ind in math_indicators)
