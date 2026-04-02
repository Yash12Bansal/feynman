"""LLM-powered concept graph builder."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..config import GraphConfig
from ..llm.base import LLMProvider
from ..pdf.parser import PDFContent
from ..pdf.toc import Chapter
from .models import ConceptEdge, ConceptGraph, ConceptNode, RelationType

logger = logging.getLogger(__name__)

EXTRACT_CONCEPTS_SYSTEM = """You are an expert educator and knowledge architect. Your task is to analyze educational text and extract a hierarchical concept graph that will be used to generate lectures.

For the given text content, identify:
1. Main topics and subtopics in hierarchical order
2. The relationships between topics (prerequisite, related, leads_to, example_of)
3. A comprehensive summary for each topic that preserves ALL important information

Rules:
- Preserve the order topics appear in the text
- Summaries must be EXHAUSTIVE — a teacher must be able to deliver a complete, engaging lecture from just the summary
- Every key term, definition, formula, derivation step, process, example, and worked problem must be captured
- Include the REASONING behind concepts, not just the facts ("this works because...")
- Capture real-world applications, analogies, and connections mentioned in the text
- Children topics must be genuinely contained within their parent topic
- Identify cross-references between topics where one concept depends on or relates to another
- For formulas: include the formula, what each variable means, when to use it, and any derivation steps

Respond with a JSON object in this exact format:
{
  "nodes": [
    {
      "topic_name": "Topic Name",
      "summary": "Exhaustive summary with all details, formulas, derivations, examples, and reasoning...",
      "level": 0,
      "children": [
        {
          "topic_name": "Subtopic Name",
          "summary": "Detailed summary with complete information...",
          "level": 1,
          "children": []
        }
      ]
    }
  ],
  "relationships": [
    {
      "from_topic": "Topic A",
      "to_topic": "Topic B",
      "relation": "prerequisite",
      "label": "Understanding A is needed for B because..."
    }
  ]
}"""

EXTRACT_CONCEPTS_USER = """Chapter: {chapter_title}
Pages {start_page} to {end_page}

Content:
{content}

Extract the complete concept hierarchy. The summaries will be used to generate lectures, so they must be detailed enough that a world-class teacher can deliver a comprehensive, engaging lecture from them alone — including all formulas, derivations, examples, and conceptual explanations."""


class GraphBuilder:
    """Builds concept graphs from chapter content using LLM extraction."""

    def __init__(self, llm: LLMProvider, config: GraphConfig | None = None):
        self.llm = llm
        self.config = config or GraphConfig()

    def build_chapter_graph(
        self,
        chapter: Chapter,
        pdf_content: PDFContent,
    ) -> ConceptGraph:
        """Build a concept graph for a single chapter."""
        text = chapter.get_text(pdf_content)

        if not text.strip():
            logger.warning(f"No text found for chapter: {chapter.title}")
            return ConceptGraph(chapter_title=chapter.title)

        logger.info(f"Chapter text length: {len(text)} chars (~{len(text)//4} tokens)")

        # For very long chapters, process in segments
        if len(text) > 50000:
            return self._build_chunked_graph(chapter, text)

        logger.info("Sending to LLM for concept extraction... (this may take 30-90 seconds)")
        return self._extract_graph(chapter.title, text, chapter.start_page, chapter.end_page)

    def _extract_graph(
        self,
        chapter_title: str,
        content: str,
        start_page: int,
        end_page: int,
    ) -> ConceptGraph:
        """Extract concept graph from content using LLM."""
        user_prompt = EXTRACT_CONCEPTS_USER.format(
            chapter_title=chapter_title,
            start_page=start_page,
            end_page=end_page,
            content=content,
        )

        response = self.llm.generate_json(EXTRACT_CONCEPTS_SYSTEM, user_prompt)
        logger.info("LLM response received. Parsing graph...")

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM JSON response for chapter: {chapter_title}")
            logger.debug(f"Raw response: {response.content[:500]}")
            # Create a minimal single-node graph as fallback
            return self._fallback_graph(chapter_title, content, start_page, end_page)

        return self._parse_llm_output(data, chapter_title, content, start_page, end_page)

    def _parse_llm_output(
        self,
        data: dict,
        chapter_title: str,
        content: str,
        start_page: int,
        end_page: int,
    ) -> ConceptGraph:
        """Parse the LLM's JSON output into a ConceptGraph."""
        graph = ConceptGraph(chapter_title=chapter_title)
        node_counter = [0]
        topic_to_id: dict[str, str] = {}

        def process_node(
            node_data: dict,
            parent_id: str | None,
            level: int,
        ) -> str:
            node_id = f"n_{node_counter[0]:04d}"
            node_counter[0] += 1

            node = ConceptNode(
                node_id=node_id,
                topic_name=node_data.get("topic_name", f"Topic {node_counter[0]}"),
                summary=node_data.get("summary", ""),
                content="",  # Content stored at graph level
                level=level,
                order=node_counter[0] - 1,
                page_start=start_page,
                page_end=end_page,
                parent_id=parent_id,
            )

            topic_to_id[node.topic_name] = node_id
            graph.add_node(node)

            # Process children
            children = node_data.get("children", [])
            for child_data in children:
                if level < self.config.max_depth:
                    child_id = process_node(child_data, node_id, level + 1)
                    node.children_ids.append(child_id)

            # Add parent-child edge
            if parent_id:
                graph.add_edge(ConceptEdge(
                    source_id=parent_id,
                    target_id=node_id,
                    relation=RelationType.PARENT_CHILD,
                    label=f"contains",
                ))

            return node_id

        # Process top-level nodes
        for node_data in data.get("nodes", []):
            process_node(node_data, None, 0)

        # Process cross-relationships
        for rel in data.get("relationships", []):
            from_id = topic_to_id.get(rel.get("from_topic", ""))
            to_id = topic_to_id.get(rel.get("to_topic", ""))
            if from_id and to_id:
                relation_str = rel.get("relation", "related")
                try:
                    relation = RelationType(relation_str)
                except ValueError:
                    relation = RelationType.RELATED

                graph.add_edge(ConceptEdge(
                    source_id=from_id,
                    target_id=to_id,
                    relation=relation,
                    label=rel.get("label", ""),
                ))

        return graph

    def _build_chunked_graph(self, chapter: Chapter, text: str) -> ConceptGraph:
        """Handle very long chapters by processing in segments and merging."""
        chunk_size = 25000
        overlap = 2000
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - overlap

        # Process first chunk to get the initial graph
        graph = self._extract_graph(
            chapter.title, chunks[0], chapter.start_page, chapter.end_page
        )

        # For subsequent chunks, extract and merge
        for i, chunk in enumerate(chunks[1:], 1):
            chunk_graph = self._extract_graph(
                f"{chapter.title} (continued {i})",
                chunk,
                chapter.start_page,
                chapter.end_page,
            )
            self._merge_graphs(graph, chunk_graph)

        graph.chapter_title = chapter.title
        return graph

    def _merge_graphs(self, target: ConceptGraph, source: ConceptGraph) -> None:
        """Merge source graph nodes and edges into target graph."""
        # Remap IDs to avoid collisions
        max_order = max((n.order for n in target.nodes.values()), default=-1) + 1
        existing_ids = set(target.nodes.keys())
        id_remap: dict[str, str] = {}

        for old_id, node in source.nodes.items():
            new_id = old_id
            while new_id in existing_ids:
                new_id = f"{new_id}_m"
            id_remap[old_id] = new_id
            node.node_id = new_id
            node.order += max_order
            if node.parent_id and node.parent_id in id_remap:
                node.parent_id = id_remap[node.parent_id]
            node.children_ids = [id_remap.get(c, c) for c in node.children_ids]
            target.add_node(node)

        for edge in source.edges:
            edge.source_id = id_remap.get(edge.source_id, edge.source_id)
            edge.target_id = id_remap.get(edge.target_id, edge.target_id)
            target.add_edge(edge)

    def _fallback_graph(
        self,
        chapter_title: str,
        content: str,
        start_page: int,
        end_page: int,
    ) -> ConceptGraph:
        """Create a minimal single-node graph when LLM extraction fails."""
        graph = ConceptGraph(chapter_title=chapter_title)
        node = ConceptNode(
            node_id="n_0000",
            topic_name=chapter_title,
            summary=content[:2000] + ("..." if len(content) > 2000 else ""),
            content=content,
            level=0,
            order=0,
            page_start=start_page,
            page_end=end_page,
        )
        graph.add_node(node)
        return graph
