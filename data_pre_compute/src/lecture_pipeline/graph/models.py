"""Data models for the concept graph."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RelationType(str, Enum):
    """Types of relationships between concept nodes."""
    PARENT_CHILD = "parent_child"       # Hierarchical: topic contains subtopic
    PREREQUISITE = "prerequisite"        # A must be understood before B
    RELATED = "related"                  # Concepts are related but neither is parent
    LEADS_TO = "leads_to"               # Sequential: A naturally flows into B
    EXAMPLE_OF = "example_of"           # B is an example of concept A


@dataclass
class ConceptNode:
    """A single concept/topic node in the graph."""
    node_id: str
    topic_name: str
    summary: str                         # Detailed summary without context loss
    content: str                         # Original source text for this concept
    level: int = 0                       # Depth in hierarchy (0 = root)
    order: int = 0                       # Sequence order as it appears in text
    page_start: int = 0
    page_end: int = 0
    children_ids: list[str] = field(default_factory=list)
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "topic_name": self.topic_name,
            "summary": self.summary,
            "content": self.content,
            "level": self.level,
            "order": self.order,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "children_ids": self.children_ids,
            "parent_id": self.parent_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConceptNode:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ConceptEdge:
    """A directed edge between two concept nodes."""
    source_id: str
    target_id: str
    relation: RelationType
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation.value,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConceptEdge:
        data = dict(data)
        data["relation"] = RelationType(data["relation"])
        return cls(**data)


@dataclass
class ConceptGraph:
    """A directed graph of concepts for a chapter."""
    chapter_title: str
    nodes: dict[str, ConceptNode] = field(default_factory=dict)
    edges: list[ConceptEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: ConceptNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: ConceptEdge) -> None:
        self.edges.append(edge)

    def get_root_nodes(self) -> list[ConceptNode]:
        """Get top-level nodes (no parent)."""
        return sorted(
            [n for n in self.nodes.values() if n.parent_id is None],
            key=lambda n: n.order,
        )

    def get_children(self, node_id: str) -> list[ConceptNode]:
        """Get direct children of a node, ordered by sequence."""
        node = self.nodes.get(node_id)
        if not node:
            return []
        return sorted(
            [self.nodes[cid] for cid in node.children_ids if cid in self.nodes],
            key=lambda n: n.order,
        )

    def get_related_edges(self, node_id: str) -> list[ConceptEdge]:
        """Get all edges involving this node."""
        return [e for e in self.edges if e.source_id == node_id or e.target_id == node_id]

    def get_teaching_order(self) -> list[ConceptNode]:
        """Return nodes in teaching order (DFS preserving book order)."""
        visited: set[str] = set()
        ordered: list[ConceptNode] = []

        def dfs(node_id: str):
            if node_id in visited:
                return
            visited.add(node_id)
            node = self.nodes[node_id]
            ordered.append(node)
            for child in self.get_children(node_id):
                dfs(child.node_id)

        for root in self.get_root_nodes():
            dfs(root.node_id)

        return ordered

    def to_dict(self) -> dict:
        return {
            "chapter_title": self.chapter_title,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConceptGraph:
        graph = cls(
            chapter_title=data["chapter_title"],
            metadata=data.get("metadata", {}),
        )
        for nid, ndata in data.get("nodes", {}).items():
            graph.add_node(ConceptNode.from_dict(ndata))
        for edata in data.get("edges", []):
            graph.add_edge(ConceptEdge.from_dict(edata))
        return graph

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> ConceptGraph:
        return cls.from_dict(json.loads(json_str))
