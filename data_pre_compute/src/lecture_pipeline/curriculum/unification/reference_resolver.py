"""Cross-chapter reference resolver.

Chapter extractions produce placeholder references like "ChapterTitle::ConceptName"
for cross-chapter edges (see chapter_extractor.py:386). This module resolves those
placeholders to real UIDs by matching against the BookSkeleton and extracted nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lecture_pipeline.curriculum.id_generator import generate_relationship_key
from lecture_pipeline.curriculum.merge.entity_resolver import normalize_topic_name
from lecture_pipeline.curriculum.models import (
    BookSkeleton,
    ExtractionNode,
    ExtractionRelationship,
)


@dataclass
class ResolutionResult:
    """Output of cross-chapter reference resolution."""

    resolved_relationships: list[ExtractionRelationship]
    resolved_count: int = 0
    unresolved_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _is_cross_chapter_ref(uid: str) -> bool:
    """Check if a UID is a cross-chapter placeholder (contains '::')."""
    return "::" in uid


def _parse_cross_chapter_ref(ref: str) -> tuple[str, str]:
    """Parse 'ChapterTitle::ConceptName' into (chapter_ref, concept_name).

    Splits on the first '::' only, so concept names containing '::' are safe.
    """
    parts = ref.split("::", 1)
    return parts[0].strip(), parts[1].strip()


def _build_chapter_node_index(
    all_nodes: list[ExtractionNode],
    book_skeleton: BookSkeleton,
) -> dict[int, dict[str, ExtractionNode]]:
    """Build a per-chapter index: chapter_order → {normalized_name → node}.

    Uses the first node encountered for each normalized name (preserves
    chapter-internal ordering).
    """
    # Group nodes by chapter_order
    by_chapter: dict[int, list[ExtractionNode]] = {}
    for node in all_nodes:
        by_chapter.setdefault(node.chapter_order, []).append(node)

    # Build normalized name → node index per chapter
    index: dict[int, dict[str, ExtractionNode]] = {}
    for ch_order, nodes in by_chapter.items():
        name_map: dict[str, ExtractionNode] = {}
        for node in nodes:
            norm = normalize_topic_name(node.topic_name)
            if norm and norm not in name_map:
                name_map[norm] = node
        index[ch_order] = name_map

    return index


def _find_chapter_order(
    chapter_ref: str,
    book_skeleton: BookSkeleton,
) -> int | None:
    """Match a chapter reference string to a chapter_order (1-based index).

    Uses BookSkeleton.chapter_by_title() for fuzzy matching.
    """
    chapter = book_skeleton.chapter_by_title(chapter_ref)
    if chapter is not None:
        return chapter.chapter_index
    return None


def _find_node_in_chapter(
    concept_name: str,
    chapter_order: int,
    chapter_index: dict[int, dict[str, ExtractionNode]],
) -> ExtractionNode | None:
    """Find a node in a chapter by normalized name matching."""
    name_map = chapter_index.get(chapter_order)
    if name_map is None:
        return None

    norm = normalize_topic_name(concept_name)
    if not norm:
        return None

    return name_map.get(norm)


def _resolve_uid(
    uid: str,
    book_skeleton: BookSkeleton,
    chapter_index: dict[int, dict[str, ExtractionNode]],
    warnings: list[str],
    resolved_count: list[int],
    unresolved_count: list[int],
) -> str:
    """Resolve a single UID if it's a cross-chapter placeholder.

    Returns the resolved UID or the original if resolution fails.
    """
    if not _is_cross_chapter_ref(uid):
        return uid

    chapter_ref, concept_name = _parse_cross_chapter_ref(uid)

    chapter_order = _find_chapter_order(chapter_ref, book_skeleton)
    if chapter_order is None:
        warnings.append(
            f"Unresolved cross-chapter reference: could not match "
            f"chapter '{chapter_ref}' in '{uid}'"
        )
        unresolved_count[0] += 1
        return uid

    node = _find_node_in_chapter(concept_name, chapter_order, chapter_index)
    if node is None:
        warnings.append(
            f"Unresolved cross-chapter reference: concept '{concept_name}' "
            f"not found in chapter '{chapter_ref}' (order={chapter_order}) "
            f"for ref '{uid}'"
        )
        unresolved_count[0] += 1
        return uid

    resolved_count[0] += 1
    return node.uid


class ReferenceResolver:
    """Resolves cross-chapter placeholder UIDs to real concept UIDs."""

    def __init__(self, book_skeleton: BookSkeleton) -> None:
        self._skeleton = book_skeleton

    def resolve(
        self,
        relationships: list[ExtractionRelationship],
        all_nodes: list[ExtractionNode],
    ) -> ResolutionResult:
        """Resolve all cross-chapter references in the relationship list.

        Cross-chapter references have the format "ChapterTitle::ConceptName"
        in either from_uid or to_uid. These are resolved to real UIDs by
        matching against the BookSkeleton and extracted nodes.

        Returns a new list of relationships (does not mutate input).
        """
        chapter_index = _build_chapter_node_index(all_nodes, self._skeleton)
        warnings: list[str] = []
        # Use lists for mutable counters passed into helper
        resolved_count = [0]
        unresolved_count = [0]

        resolved_rels: list[ExtractionRelationship] = []
        for rel in relationships:
            new_from = _resolve_uid(
                rel.from_uid,
                self._skeleton,
                chapter_index,
                warnings,
                resolved_count,
                unresolved_count,
            )
            new_to = _resolve_uid(
                rel.to_uid,
                self._skeleton,
                chapter_index,
                warnings,
                resolved_count,
                unresolved_count,
            )

            if new_from != rel.from_uid or new_to != rel.to_uid:
                # UID(s) changed — regenerate relationship key
                new_key = generate_relationship_key(
                    rel.type.value, new_from, new_to
                )
                resolved_rels.append(
                    rel.model_copy(
                        update={
                            "from_uid": new_from,
                            "to_uid": new_to,
                            "relationship_key": new_key,
                        }
                    )
                )
            else:
                resolved_rels.append(rel)

        return ResolutionResult(
            resolved_relationships=resolved_rels,
            resolved_count=resolved_count[0],
            unresolved_count=unresolved_count[0],
            warnings=warnings,
        )
