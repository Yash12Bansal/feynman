"""Cross-chapter shared concept detection.

Finds implicit connections between chapters by matching normalized concept
names. When "Force" in Chapter 3 and "Force" in Chapter 10 share the same
normalized name and concept_type, a SHARED_FOUNDATION edge is created.

Currently uses deterministic name matching via entity_resolver's normalization.
Embedding-based similarity detection can be added later as an enhancement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lecture_pipeline.curriculum.id_generator import generate_relationship_key
from lecture_pipeline.curriculum.merge.entity_resolver import normalize_topic_name
from lecture_pipeline.curriculum.models import (
    CurriculumRelationType,
    ExtractionNode,
    ExtractionRelationship,
    ResolutionLevel,
)


@dataclass
class SharedConceptResult:
    """Output of shared concept detection."""

    new_relationships: list[ExtractionRelationship] = field(default_factory=list)
    shared_pairs_count: int = 0


class SharedConceptDetector:
    """Detects shared concepts across chapters via normalized name matching."""

    def detect(
        self,
        all_nodes: list[ExtractionNode],
    ) -> SharedConceptResult:
        """Find cross-chapter shared concepts and create SHARED_FOUNDATION edges.

        Only matches CONCEPT-level nodes (not DETAIL, CHAPTER, UNIT, SYLLABUS).
        Both nodes must have the same concept_type for a match.
        Same-chapter nodes are never matched.
        """
        # Filter to matchable nodes (CONCEPT resolution level only)
        matchable = [
            n for n in all_nodes
            if n.resolution_level == ResolutionLevel.CONCEPT
        ]

        # Group by chapter_order
        by_chapter: dict[int, list[ExtractionNode]] = {}
        for node in matchable:
            by_chapter.setdefault(node.chapter_order, []).append(node)

        chapter_orders = sorted(by_chapter.keys())
        seen_keys: set[str] = set()
        result = SharedConceptResult()

        # Compare all chapter pairs (i < j)
        for idx_i, ch_i in enumerate(chapter_orders):
            nodes_i = by_chapter[ch_i]
            # Build index for chapter i: (normalized_name, concept_type) → node
            index_i: dict[tuple[str, str], ExtractionNode] = {}
            for node in nodes_i:
                norm = normalize_topic_name(node.topic_name)
                if norm:
                    key = (norm, node.concept_type.value)
                    if key not in index_i:
                        index_i[key] = node

            for ch_j in chapter_orders[idx_i + 1:]:
                nodes_j = by_chapter[ch_j]
                for node_j in nodes_j:
                    norm_j = normalize_topic_name(node_j.topic_name)
                    if not norm_j:
                        continue
                    match_key = (norm_j, node_j.concept_type.value)
                    node_i = index_i.get(match_key)
                    if node_i is None:
                        continue

                    # Create SHARED_FOUNDATION edge (earlier chapter → later)
                    rel_key = generate_relationship_key(
                        CurriculumRelationType.SHARED_FOUNDATION.value,
                        node_i.uid,
                        node_j.uid,
                    )
                    if rel_key in seen_keys:
                        continue
                    seen_keys.add(rel_key)

                    result.new_relationships.append(
                        ExtractionRelationship(
                            relationship_key=rel_key,
                            type=CurriculumRelationType.SHARED_FOUNDATION,
                            from_uid=node_i.uid,
                            to_uid=node_j.uid,
                            label=f"Shared concept: {node_i.topic_name}",
                        )
                    )
                    result.shared_pairs_count += 1

        return result
