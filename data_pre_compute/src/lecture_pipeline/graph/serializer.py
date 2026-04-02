"""Serialization and visualization helpers for concept graphs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import ConceptGraph


class GraphSerializer:
    """Serialize and deserialize concept graphs."""

    @staticmethod
    def to_json(graph: ConceptGraph, path: str | Path | None = None) -> str:
        """Serialize graph to JSON string, optionally writing to file."""
        json_str = graph.to_json(indent=2)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json_str, encoding="utf-8")
        return json_str

    @staticmethod
    def from_json(json_str: str | None = None, path: str | Path | None = None) -> ConceptGraph:
        """Load graph from JSON string or file."""
        if path:
            json_str = Path(path).read_text(encoding="utf-8")
        if not json_str:
            raise ValueError("Provide either json_str or path")
        return ConceptGraph.from_json(json_str)

    @staticmethod
    def to_yaml(graph: ConceptGraph, path: str | Path | None = None) -> str:
        """Serialize graph to YAML string, optionally writing to file."""
        data = graph.to_dict()
        yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(yaml_str, encoding="utf-8")
        return yaml_str

    @staticmethod
    def from_yaml(yaml_str: str | None = None, path: str | Path | None = None) -> ConceptGraph:
        """Load graph from YAML string or file."""
        if path:
            yaml_str = Path(path).read_text(encoding="utf-8")
        if not yaml_str:
            raise ValueError("Provide either yaml_str or path")
        data = yaml.safe_load(yaml_str)
        return ConceptGraph.from_dict(data)

    @staticmethod
    def to_markdown_outline(graph: ConceptGraph) -> str:
        """Render graph as a markdown outline for quick inspection."""
        lines = [f"# {graph.chapter_title}\n"]

        def render_node(node_id: str, depth: int = 0):
            node = graph.nodes[node_id]
            indent = "  " * depth
            prefix = "#" * min(depth + 2, 6)
            lines.append(f"{indent}{prefix} {node.topic_name}")
            if node.summary:
                lines.append(f"\n{indent}{node.summary}\n")
            lines.append("")
            for child in graph.get_children(node_id):
                render_node(child.node_id, depth + 1)

        for root in graph.get_root_nodes():
            render_node(root.node_id)

        # Add relationships section
        non_parent_edges = [e for e in graph.edges if e.relation.value != "parent_child"]
        if non_parent_edges:
            lines.append("## Relationships\n")
            for edge in non_parent_edges:
                src = graph.nodes.get(edge.source_id)
                tgt = graph.nodes.get(edge.target_id)
                if src and tgt:
                    lines.append(
                        f"- **{src.topic_name}** --[{edge.relation.value}]--> "
                        f"**{tgt.topic_name}**"
                        + (f" ({edge.label})" if edge.label else "")
                    )

        return "\n".join(lines)
