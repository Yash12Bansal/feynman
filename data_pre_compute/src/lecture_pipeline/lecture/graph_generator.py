"""Mode 2: Graph-based lecture generator — concept graph to structured lecture."""

from __future__ import annotations

import logging

from ..config import LectureConfig
from ..graph.models import ConceptGraph, ConceptNode, RelationType
from ..llm.base import LLMProvider

logger = logging.getLogger(__name__)

QUALITY_INSTRUCTIONS = {
    "beginner": """AUDIENCE: Complete beginners.
- Use everyday language, define all jargon
- Simple analogies from daily life
- Break into smallest possible steps
- Reassure when topics get complex""",

    "advanced": """AUDIENCE: Serious students aiming for deep mastery.
- Explain the WHY behind every concept
- Include full derivations with step-by-step reasoning
- Highlight subtle points, edge cases, common misconceptions
- Add "Exam tip" and "Key insight" callouts
- Connect concepts across topics
- Include thought experiments and "What if..." scenarios""",
}

NODE_LECTURE_SYSTEM = """You are a world-class educator creating a section of a lecture. You are given a concept with its summary and context within the broader chapter.

Your teaching style:
1. **Build intuition first** — conceptual understanding before formulas
2. **Vivid examples** — real-world scenarios, "imagine you are..." situations
3. **Rhetorical questions** — "But what happens if...?", "Why does this work?"
4. **Address confusion proactively** — "A common mistake here is...", "Don't confuse this with..."
5. **Every detail matters** — cover ALL information from the summary, skip nothing
6. **Key insights in bold** — highlight the most important takeaways
7. **Smooth flow** — the content should feel like a natural conversation

{quality_instructions}

Output: Markdown lecture content for this topic. Do NOT include a top-level heading (the system adds it). Start directly with teaching content."""

NODE_LECTURE_USER = """Topic: {topic_name}
Level: {level_desc}

Summary (cover EVERYTHING here — do not skip any detail):
{summary}

{context_section}

Generate engaging, thorough lecture content for this topic."""

GRAPH_INTRO_SYSTEM = """You are a world-class educator. Write a compelling introduction for a chapter lecture that gets students excited to learn.

Your introduction should:
- Hook the student immediately — start with a fascinating question, real-world scenario, or surprising fact
- Give a roadmap of what will be covered (without spoiling the "aha moments")
- Explain why this topic matters — how it connects to the real world or other subjects
- Set the right mindset for learning

{quality_instructions}

Keep it 3-5 paragraphs. Output in markdown."""

GRAPH_INTRO_USER = """Chapter: {chapter_title}

Topics that will be covered (in order):
{topic_list}

Write a compelling introduction for this lecture."""


class GraphLectureGenerator:
    """Generate structured lectures from concept graphs (Mode 2)."""

    def __init__(self, llm: LLMProvider, config: LectureConfig | None = None):
        self.llm = llm
        self.config = config or LectureConfig()

    def generate(self, graph: ConceptGraph) -> str:
        """Generate a full lecture script from a concept graph."""
        teaching_order = graph.get_teaching_order()

        if not teaching_order:
            return f"# {graph.chapter_title}\n\n*No concepts found.*"

        quality = self.config.audience_level
        quality_inst = QUALITY_INSTRUCTIONS.get(quality, QUALITY_INSTRUCTIONS["advanced"])

        sections: list[str] = []

        # Generate chapter introduction
        intro = self._generate_intro(graph, teaching_order, quality_inst)
        sections.append(f"# {graph.chapter_title}\n\n{intro}")

        # Generate content for each node in teaching order
        for i, node in enumerate(teaching_order):
            logger.info(f"Generating section {i+1}/{len(teaching_order)}: {node.topic_name}")
            section = self._generate_node_section(graph, node, quality_inst)
            sections.append(section)

        # Add summary/recap
        recap = self._generate_recap(graph, teaching_order, quality_inst)
        sections.append(f"## Summary & Recap\n\n{recap}")

        return "\n\n---\n\n".join(sections)

    def _generate_intro(self, graph: ConceptGraph, nodes: list[ConceptNode], quality_inst: str) -> str:
        topic_list = "\n".join(
            f"{'  ' * n.level}- {n.topic_name}" for n in nodes
        )
        system = GRAPH_INTRO_SYSTEM.format(quality_instructions=quality_inst)
        user = GRAPH_INTRO_USER.format(
            chapter_title=graph.chapter_title,
            topic_list=topic_list,
        )
        response = self.llm.generate(system, user)
        return response.content

    def _generate_node_section(self, graph: ConceptGraph, node: ConceptNode, quality_inst: str) -> str:
        context_parts = []

        # Prerequisite info
        prereq_edges = [
            e for e in graph.edges
            if e.target_id == node.node_id and e.relation == RelationType.PREREQUISITE
        ]
        if prereq_edges:
            prereqs = []
            for e in prereq_edges:
                src = graph.nodes.get(e.source_id)
                if src:
                    prereqs.append(f"{src.topic_name} — {e.label}" if e.label else src.topic_name)
            if prereqs:
                context_parts.append(
                    f"Prerequisites (briefly remind students of these): {'; '.join(prereqs)}"
                )

        # Related concepts
        related_edges = [
            e for e in graph.edges
            if (e.source_id == node.node_id or e.target_id == node.node_id)
            and e.relation in (RelationType.RELATED, RelationType.LEADS_TO)
        ]
        if related_edges:
            related = []
            for e in related_edges:
                other_id = e.target_id if e.source_id == node.node_id else e.source_id
                other = graph.nodes.get(other_id)
                if other:
                    related.append(f"{other.topic_name} ({e.relation.value}: {e.label})" if e.label else f"{other.topic_name} ({e.relation.value})")
            if related:
                context_parts.append(
                    f"Related concepts to weave in naturally: {'; '.join(related)}"
                )

        if node.parent_id:
            parent = graph.nodes.get(node.parent_id)
            if parent:
                context_parts.append(f"This is a subtopic of: {parent.topic_name}")

        context_section = "\n".join(context_parts) if context_parts else "No additional context."

        level_desc = {0: "Main topic", 1: "Subtopic", 2: "Sub-subtopic", 3: "Detail"}.get(
            node.level, "Detail"
        )

        system = NODE_LECTURE_SYSTEM.format(quality_instructions=quality_inst)
        user = NODE_LECTURE_USER.format(
            topic_name=node.topic_name,
            level_desc=level_desc,
            summary=node.summary,
            context_section=context_section,
        )

        response = self.llm.generate(system, user)

        heading_level = min(node.level + 2, 6)
        heading = "#" * heading_level
        return f"{heading} {node.topic_name}\n\n{response.content}"

    def _generate_recap(self, graph: ConceptGraph, nodes: list[ConceptNode], quality_inst: str) -> str:
        root_topics = [n for n in nodes if n.level == 0]
        topic_summaries = "\n".join(
            f"- {n.topic_name}: {n.summary[:200]}..." for n in root_topics
        )

        recap_prompt = (
            f"Write a powerful recap for the chapter '{graph.chapter_title}'. "
            f"Key topics covered:\n{topic_summaries}\n\n"
            f"Reinforce the most important concepts, highlight connections between topics, "
            f"and leave students feeling confident about what they learned."
        )

        response = self.llm.generate(
            f"You are a world-class educator writing a chapter recap. {quality_inst}",
            recap_prompt,
        )
        return response.content
