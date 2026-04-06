"""Deterministic Cypher generation from CurriculumExtractionResult.

Converts extraction nodes and relationships into parameterized Cypher
statements ready for Neo4j execution. All statements use MERGE for
idempotent re-ingestion.

Adapted from PMG's json_to_cypher.py — parameterized queries instead of
string interpolation for safety and query plan caching.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from lecture_pipeline.curriculum.models import (
    CurriculumExtractionResult,
    CurriculumRelationType,
    ExtractionNode,
    ExtractionRelationship,
    ResolutionLevel,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolution level → Neo4j label (matches schema.py constraints)
# ---------------------------------------------------------------------------

RESOLUTION_TO_LABEL: dict[ResolutionLevel, str] = {
    ResolutionLevel.SYLLABUS: "Subject",
    ResolutionLevel.UNIT: "Unit",
    ResolutionLevel.CHAPTER: "Chapter",
    ResolutionLevel.CONCEPT: "Concept",
    ResolutionLevel.DETAIL: "Detail",
}

# Ordering: hierarchy nodes first so they exist before relationships reference them
_LABEL_PRIORITY: dict[str, int] = {
    "Subject": 0,
    "Unit": 1,
    "Chapter": 2,
    "Concept": 3,
    "Detail": 4,
}

# Relationship ordering: structural first, then pedagogical, then cross-chapter
_REL_PRIORITY: dict[str, int] = {
    CurriculumRelationType.CONTAINS.value: 0,
    CurriculumRelationType.SUMMARIZES.value: 1,
    CurriculumRelationType.PREREQUISITE.value: 2,
    CurriculumRelationType.LEADS_TO.value: 3,
    CurriculumRelationType.EXAMPLE_OF.value: 4,
    CurriculumRelationType.DERIVED_FROM.value: 5,
    CurriculumRelationType.MISCONCEPTION_OF.value: 6,
    CurriculumRelationType.ANALOGY_FOR.value: 7,
    CurriculumRelationType.APPLICATION_OF.value: 8,
    CurriculumRelationType.CROSS_REFERENCES.value: 9,
    CurriculumRelationType.SHARED_FOUNDATION.value: 10,
    CurriculumRelationType.HAS_VISUAL.value: 11,
    CurriculumRelationType.CO_ACTIVATED_WITH.value: 12,
    CurriculumRelationType.COMMONLY_CONFUSED.value: 13,
}

# Relationship type enum value → Cypher relationship type (UPPER_CASE)
_REL_TYPE_TO_CYPHER: dict[str, str] = {
    rt.value: rt.value.upper() for rt in CurriculumRelationType
}


# ---------------------------------------------------------------------------
# CypherStatement — the output unit
# ---------------------------------------------------------------------------


@dataclass
class CypherStatement:
    """A single parameterized Cypher statement ready for execution."""

    query: str
    params: dict[str, Any]
    category: str  # "node" or "relationship"
    label_or_type: str  # Neo4j label (e.g. "Concept") or rel type (e.g. "PREREQUISITE")
    uid_hint: str  # Primary UID for debugging/logging


# ---------------------------------------------------------------------------
# CypherGenerator
# ---------------------------------------------------------------------------


class CypherGenerator:
    """Converts a CurriculumExtractionResult into deterministic Cypher statements.

    Deterministic: same input always produces the same output in the same order.
    All queries use MERGE for idempotent re-ingestion.
    All values are parameterized ($uid, $summary, etc.) — no string interpolation.
    """

    def generate(
        self, extraction: CurriculumExtractionResult
    ) -> list[CypherStatement]:
        """Generate all Cypher statements for the extraction result.

        Returns nodes first (sorted hierarchy-first), then relationships
        (sorted structural-first). Same input always produces identical output.
        """
        warnings: list[str] = []

        # Build uid → label index for relationship MATCH clauses
        uid_to_label = self._build_uid_index(extraction.nodes)

        # Generate node statements
        node_stmts = []
        for node in extraction.nodes:
            stmt = self._node_to_cypher(node)
            if stmt:
                node_stmts.append(stmt)

        # Sort nodes: hierarchy-first, then by uid for determinism
        node_stmts.sort(
            key=lambda s: (_LABEL_PRIORITY.get(s.label_or_type, 99), s.uid_hint)
        )

        # Generate relationship statements
        rel_stmts = []
        node_uids = {n.uid for n in extraction.nodes}
        for rel in extraction.relationships:
            stmt = self._relationship_to_cypher(rel, uid_to_label, node_uids, warnings)
            if stmt:
                rel_stmts.append(stmt)

        # Sort relationships: structural-first, then by relationship_key
        rel_stmts.sort(
            key=lambda s: (
                _REL_PRIORITY.get(s.label_or_type.lower(), 99),
                s.uid_hint,
            )
        )

        for w in warnings:
            logger.warning(w)

        return node_stmts + rel_stmts

    def generate_text(self, extraction: CurriculumExtractionResult) -> str:
        """Human-readable Cypher text for debugging. Not for execution."""
        statements = self.generate(extraction)
        lines = []
        for stmt in statements:
            lines.append(f"// [{stmt.category}] {stmt.label_or_type} — {stmt.uid_hint}")
            # Inline params for readability
            query = stmt.query
            for key, val in sorted(stmt.params.items()):
                placeholder = f"${key}"
                if isinstance(val, str):
                    display = f"'{val[:80]}{'...' if len(val) > 80 else ''}'"
                elif val is None:
                    display = "null"
                else:
                    display = str(val)
                query = query.replace(placeholder, display, 1)
            lines.append(query)
            lines.append("")
        return "\n".join(lines)

    # -- internal --

    def _build_uid_index(
        self, nodes: list[ExtractionNode]
    ) -> dict[str, str]:
        """Map uid → Neo4j label for all nodes."""
        index: dict[str, str] = {}
        for node in nodes:
            label = RESOLUTION_TO_LABEL.get(node.resolution_level)
            if label:
                index[node.uid] = label
        return index

    def _node_to_cypher(self, node: ExtractionNode) -> CypherStatement | None:
        """Convert an ExtractionNode to a MERGE statement."""
        label = RESOLUTION_TO_LABEL.get(node.resolution_level)
        if not label:
            logger.warning("Unknown resolution level %s for %s", node.resolution_level, node.uid)
            return None

        # Build SET properties — exclude None values
        params: dict[str, Any] = {"uid": node.uid}
        set_parts: list[str] = []

        # Always-present string fields
        for field_name in ("topic_name", "summary", "source_text"):
            val = getattr(node, field_name)
            params[field_name] = val
            set_parts.append(f"n.{field_name} = ${field_name}")

        # Enum fields → .value
        params["concept_type"] = node.concept_type.value
        set_parts.append("n.concept_type = $concept_type")

        params["resolution_level"] = node.resolution_level.value
        set_parts.append("n.resolution_level = $resolution_level")

        params["difficulty"] = node.difficulty.value
        set_parts.append("n.difficulty = $difficulty")

        # Numeric fields
        for field_name in (
            "page_start",
            "page_end",
            "chapter_order",
            "within_chapter_order",
            "global_teaching_order",
        ):
            params[field_name] = getattr(node, field_name)
            set_parts.append(f"n.{field_name} = ${field_name}")

        # Float field
        params["estimated_duration_minutes"] = node.estimated_duration_minutes
        set_parts.append("n.estimated_duration_minutes = $estimated_duration_minutes")

        # Optional string fields — only include if not None
        if node.section_number is not None:
            params["section_number"] = node.section_number
            set_parts.append("n.section_number = $section_number")

        if node.visual_hint is not None:
            params["visual_hint"] = node.visual_hint
            set_parts.append("n.visual_hint = $visual_hint")

        if node.parent_uid is not None:
            params["parent_uid"] = node.parent_uid
            set_parts.append("n.parent_uid = $parent_uid")

        # List field
        if node.children_uids:
            params["children_uids"] = node.children_uids
            set_parts.append("n.children_uids = $children_uids")

        # Metadata dict → JSON string
        if node.metadata:
            params["metadata_json"] = json.dumps(node.metadata, default=str)
            set_parts.append("n.metadata_json = $metadata_json")

        # Timestamp
        set_parts.append("n.updated_at = datetime()")

        set_clause = ",\n    ".join(set_parts)

        # Label is inlined (Cypher doesn't support parameterized labels).
        # Safe because label comes from RESOLUTION_TO_LABEL enum mapping.
        query = f"MERGE (n:{label} {{uid: $uid}})\nSET {set_clause}"

        return CypherStatement(
            query=query,
            params=params,
            category="node",
            label_or_type=label,
            uid_hint=node.uid,
        )

    def _relationship_to_cypher(
        self,
        rel: ExtractionRelationship,
        uid_to_label: dict[str, str],
        node_uids: set[str],
        warnings: list[str],
    ) -> CypherStatement | None:
        """Convert an ExtractionRelationship to a MATCH+MERGE statement."""
        # Skip dangling relationships
        if rel.from_uid not in node_uids:
            warnings.append(
                f"Skipping relationship {rel.relationship_key}: "
                f"from_uid '{rel.from_uid}' not found in nodes"
            )
            return None
        if rel.to_uid not in node_uids:
            warnings.append(
                f"Skipping relationship {rel.relationship_key}: "
                f"to_uid '{rel.to_uid}' not found in nodes"
            )
            return None

        # Resolve labels for MATCH performance
        from_label = uid_to_label.get(rel.from_uid, "")
        to_label = uid_to_label.get(rel.to_uid, "")

        from_match = f"(a:{from_label} {{uid: $from_uid}})" if from_label else "(a {uid: $from_uid})"
        to_match = f"(b:{to_label} {{uid: $to_uid}})" if to_label else "(b {uid: $to_uid})"

        # Relationship type — inlined, from controlled enum
        cypher_rel_type = _REL_TYPE_TO_CYPHER.get(rel.type.value, rel.type.value.upper())

        params: dict[str, Any] = {
            "from_uid": rel.from_uid,
            "to_uid": rel.to_uid,
        }

        set_parts: list[str] = []

        # Relationship key for dedup tracking
        params["relationship_key"] = rel.relationship_key
        set_parts.append("r.relationship_key = $relationship_key")

        if rel.label:
            params["label"] = rel.label
            set_parts.append("r.label = $label")

        if rel.properties:
            params["properties_json"] = json.dumps(rel.properties, default=str)
            set_parts.append("r.properties_json = $properties_json")

        set_parts.append("r.updated_at = datetime()")

        set_clause = ",\n    ".join(set_parts)

        query = (
            f"MATCH {from_match}\n"
            f"MATCH {to_match}\n"
            f"MERGE (a)-[r:{cypher_rel_type}]->(b)\n"
            f"SET {set_clause}"
        )

        return CypherStatement(
            query=query,
            params=params,
            category="relationship",
            label_or_type=cypher_rel_type,
            uid_hint=rel.relationship_key,
        )
