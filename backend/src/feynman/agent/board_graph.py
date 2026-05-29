# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Board relationship graph — semantic edges between board elements.

# Complements SceneGraph (spatial/pixel relationships from frontend bounds)
# with pedagogical relationships declared by the teaching agent. Enables:
# - Cluster detection (connected components of related elements)
# - Grouped summaries for the LLM (clusters, not flat lists)
# - Lifecycle management (clear a full cluster at once)
# - Anchor detection (the main visual in each cluster)
# """

# from __future__ import annotations

# from collections import deque
# from enum import StrEnum

# from pydantic import BaseModel


# class BoardRelation(StrEnum):
#     """Semantic relationship types between board elements."""

#     ILLUSTRATES = "illustrates"  # equation/text describes a diagram
#     DERIVES_FROM = "derives_from"  # next step in a derivation chain
#     COMPARES_WITH = "compares_with"  # parallel comparison
#     SUPPORTS = "supports"  # supporting detail for a main visual
#     ANNOTATES = "annotates"  # annotation/highlight (ephemeral)


# class BoardEdge(BaseModel):
#     """A directed semantic edge between two board elements."""

#     source_id: str
#     target_id: str
#     relation: BoardRelation
#     label: str = ""


# # Element types considered "anchors" — main visuals that others support.
# _ANCHOR_TYPES = frozenset({
#     "draw_design_diagram",
#     "draw_scene",
#     "draw_diagram",
#     "show_graph",
# })


# class BoardGraph:
#     """Semantic relationship graph of board elements.

#     Complements SceneGraph (spatial) with pedagogical relationships.
#     Enables: cluster detection, grouped summaries, lifecycle management.

#     Not thread-safe — same guarantee as BoardState (sequential tool-call
#     processing within a single LiveKit agent turn).
#     """

#     def __init__(self) -> None:
#         self._edges: list[BoardEdge] = []

#     def add_edge(
#         self,
#         source_id: str,
#         target_id: str,
#         relation: BoardRelation,
#         label: str = "",
#     ) -> None:
#         """Declare a semantic relationship between two elements."""
#         self._edges.append(
#             BoardEdge(
#                 source_id=source_id,
#                 target_id=target_id,
#                 relation=relation,
#                 label=label,
#             )
#         )

#     def remove_element(self, element_id: str) -> None:
#         """Remove all edges involving this element."""
#         self._edges = [
#             e
#             for e in self._edges
#             if e.source_id != element_id and e.target_id != element_id
#         ]

#     def clear(self) -> None:
#         """Remove all edges."""
#         self._edges.clear()

#     @property
#     def edge_count(self) -> int:
#         return len(self._edges)

#     def get_edges(self, element_id: str) -> list[BoardEdge]:
#         """All edges involving this element (as source or target)."""
#         return [
#             e
#             for e in self._edges
#             if e.source_id == element_id or e.target_id == element_id
#         ]

#     def get_cluster(self, element_id: str) -> set[str]:
#         """All elements transitively connected to this one (BFS).

#         Returns the full connected component. If the element has no edges,
#         returns a set containing just the element itself.
#         """
#         # Build adjacency from current edges.
#         adj: dict[str, set[str]] = {}
#         for e in self._edges:
#             adj.setdefault(e.source_id, set()).add(e.target_id)
#             adj.setdefault(e.target_id, set()).add(e.source_id)

#         if element_id not in adj:
#             return {element_id}

#         visited: set[str] = set()
#         queue = deque([element_id])
#         while queue:
#             node = queue.popleft()
#             if node in visited:
#                 continue
#             visited.add(node)
#             for neighbor in adj.get(node, ()):
#                 if neighbor not in visited:
#                     queue.append(neighbor)
#         return visited

#     def get_clusters(self, element_ids: set[str]) -> list[set[str]]:
#         """All connected components among the given element IDs.

#         Elements with no edges form singleton clusters.
#         """
#         # Build adjacency from current edges, restricted to known elements.
#         adj: dict[str, set[str]] = {}
#         for e in self._edges:
#             if e.source_id in element_ids and e.target_id in element_ids:
#                 adj.setdefault(e.source_id, set()).add(e.target_id)
#                 adj.setdefault(e.target_id, set()).add(e.source_id)

#         visited: set[str] = set()
#         clusters: list[set[str]] = []

#         for eid in element_ids:
#             if eid in visited:
#                 continue
#             # BFS from this element.
#             cluster: set[str] = set()
#             queue = deque([eid])
#             while queue:
#                 node = queue.popleft()
#                 if node in visited:
#                     continue
#                 visited.add(node)
#                 cluster.add(node)
#                 for neighbor in adj.get(node, ()):
#                     if neighbor not in visited:
#                         queue.append(neighbor)
#             clusters.append(cluster)

#         return clusters

#     def get_anchor(
#         self,
#         cluster: set[str],
#         board_elements: dict[str, object],
#     ) -> str | None:
#         """Find the 'anchor' of a cluster — the main visual others support.

#         Heuristic:
#         1. Element with the most incoming edges in this cluster.
#         2. Tie-break: first diagram/scene/graph type element.
#         3. Tie-break: first element by creation order.
#         """
#         if not cluster:
#             return None

#         # Count incoming edges within this cluster.
#         incoming: dict[str, int] = {eid: 0 for eid in cluster}
#         for e in self._edges:
#             if e.target_id in cluster and e.source_id in cluster:
#                 incoming[e.target_id] = incoming.get(e.target_id, 0) + 1

#         max_incoming = max(incoming.values()) if incoming else 0

#         # Candidates with max incoming edges.
#         candidates = [eid for eid, count in incoming.items() if count == max_incoming]

#         # Prefer anchor types (diagrams, scenes, graphs).
#         for eid in candidates:
#             el = board_elements.get(eid)
#             if el is not None and getattr(el, "type", "") in _ANCHOR_TYPES:
#                 return eid

#         # Fall back to earliest creation order.
#         best = None
#         best_created = float("inf")
#         for eid in candidates:
#             el = board_elements.get(eid)
#             created = getattr(el, "created_at", 0) if el else 0
#             if created < best_created:
#                 best = eid
#                 best_created = created

#         return best

#     def summary(
#         self,
#         board_elements: dict[str, object],
#         scene_graph: object | None = None,
#     ) -> str:
#         """Clustered summary merging semantic relationships with spatial data.

#         Returns "" when no edges exist (enables graceful fallback to
#         SceneGraph or flat summary).

#         Output format:
#           Cluster: [anchor label] [anchor: design-1]
#             design-1 (Free body diagram) — center-left
#               ├── eq-2 (F = ma) ──illustrates── center-right
#               └── text-1 (Key insight) ──supports── top-center

#           Standalone:
#             graph-1 (a vs F plot) — bottom-right

#           Open zones: top-left, top-right, bottom-left
#         """
#         if not self._edges:
#             return ""

#         element_ids = set(board_elements.keys())
#         clusters = self.get_clusters(element_ids)

#         # Separate multi-element clusters from singletons.
#         grouped: list[set[str]] = []
#         standalone: list[str] = []
#         for cluster in clusters:
#             if len(cluster) > 1:
#                 grouped.append(cluster)
#             else:
#                 standalone.extend(cluster)

#         lines: list[str] = []

#         for cluster in grouped:
#             anchor_id = self.get_anchor(cluster, board_elements)
#             anchor_el = board_elements.get(anchor_id) if anchor_id else None
#             anchor_label = getattr(anchor_el, "label", "") if anchor_el else ""
#             anchor_concept = (
#                 getattr(anchor_el, "concept_title", "") if anchor_el else ""
#             )

#             header = f"Cluster: {anchor_label}" if anchor_label else "Cluster"
#             if anchor_id:
#                 header += f" [anchor: {anchor_id}]"
#             if anchor_concept:
#                 header += f" ({anchor_concept})"
#             lines.append(header)

#             # Show anchor first, then related elements.
#             if anchor_id:
#                 zone = getattr(anchor_el, "zone", None) if anchor_el else None
#                 zone_str = f" — {zone}" if zone else ""
#                 lines.append(f"  {anchor_id} ({anchor_label}){zone_str}")

#             # Other elements with their relation to the anchor or to each other.
#             others = sorted(cluster - {anchor_id}) if anchor_id else sorted(cluster)
#             for i, eid in enumerate(others):
#                 el = board_elements.get(eid)
#                 label = getattr(el, "label", "") if el else eid
#                 zone = getattr(el, "zone", None) if el else None
#                 zone_str = f" — {zone}" if zone else ""

#                 # Find relationship edge for this element.
#                 rel_str = ""
#                 for e in self._edges:
#                     if e.source_id == eid and e.target_id in cluster:
#                         rel_str = f" ──{e.relation.value}──"
#                         break
#                     if e.target_id == eid and e.source_id in cluster:
#                         rel_str = f" ──{e.relation.value}──"
#                         break

#                 connector = "└──" if i == len(others) - 1 else "├──"
#                 lines.append(f"    {connector} {eid} ({label}){rel_str}{zone_str}")

#             lines.append("")

#         if standalone:
#             lines.append("Standalone:")
#             for eid in sorted(standalone):
#                 el = board_elements.get(eid)
#                 label = getattr(el, "label", "") if el else eid
#                 zone = getattr(el, "zone", None) if el else None
#                 zone_str = f" — {zone}" if zone else ""
#                 lines.append(f"  {eid} ({label}){zone_str}")
#             lines.append("")

#         return "\n".join(lines).rstrip()
