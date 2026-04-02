"""Mode 1: Naive lecture script generator — full text to LLM."""

from __future__ import annotations

import logging
from typing import Literal

from ..config import LectureConfig
from ..llm.base import LLMProvider
from ..pdf.parser import PDFContent
from ..pdf.toc import Chapter

logger = logging.getLogger(__name__)

QUALITY_INSTRUCTIONS = {
    "beginner": """AUDIENCE: Complete beginners with no prior knowledge.
- Use everyday language, avoid jargon unless you define it first
- Explain every term as if the student has never heard it before
- Use simple, relatable analogies (cooking, sports, daily life)
- Break every concept into the smallest possible steps
- Add "Think of it this way..." moments frequently
- Reassure students when topics get complex ("Don't worry, this is simpler than it sounds")""",

    "advanced": """AUDIENCE: Serious students aiming for deep mastery and exam readiness.
- Go deep into the WHY behind every concept — don't just state facts, explain the reasoning
- Include complete mathematical derivations step-by-step, explaining each manipulation
- Highlight subtle points, edge cases, and common misconceptions that catch students off guard
- Add "Exam tip" or "Important insight" callouts for tricky concepts
- Connect concepts across topics — show how ideas link together
- Include challenging thought experiments and "What if..." scenarios
- Discuss where formulas come from and when they break down
- Add intuition-building explanations alongside rigorous math""",
}

LECTURE_SYSTEM_PROMPT = """You are a world-class educator known for making complex topics crystal clear while keeping students deeply engaged. You are creating a lecture script that a teacher will deliver directly to students.

Your lectures are legendary because you:
1. **Never skip anything** — every concept, definition, formula, derivation, and example from the source is covered
2. **Build intuition first** — before diving into math/formulas, explain the physical/conceptual meaning
3. **Use vivid examples** — real-world scenarios, thought experiments, "imagine you are..." situations
4. **Create "aha moments"** — connect new ideas to what students already know
5. **Ask rhetorical questions** — "But wait, what happens if we...?", "Why do you think this works?"
6. **Smooth transitions** — each section flows naturally into the next with connecting sentences
7. **Emphasize key insights** — bold or highlight the most important takeaways
8. **Address confusion proactively** — "Now you might be wondering..." or "A common mistake here is..."

{quality_instructions}

Output format: Markdown with clear section headings (##, ###). Include all formulas, equations, and worked examples. The lecture should feel alive — like the best teacher you've ever had is speaking directly to you."""

LECTURE_USER_PROMPT = """Create a complete, engaging lecture script for the following chapter.

Chapter: {chapter_title}

--- TEXTBOOK CONTENT START ---
{content}
--- TEXTBOOK CONTENT END ---

Generate a comprehensive lecture script in markdown. Cover EVERY concept from the text. Make it highly engaging — the teacher will read this directly to students. Include all formulas, derivations, examples, and worked problems from the source."""

TOPIC_SYSTEM_PROMPT = """You are a world-class educator creating a deep-dive lecture on a specific topic within a chapter. The student wants to understand this one topic thoroughly.

Your goal:
1. **Exhaustive coverage** — leave no stone unturned on this specific topic
2. **Build from ground up** — start with foundational intuition, then layer on complexity
3. **Multiple perspectives** — explain the same concept from different angles
4. **Rich examples** — at least 3-4 worked examples ranging from simple to challenging
5. **Common pitfalls** — explicitly address where students typically get confused
6. **Connections** — show how this topic connects to the broader chapter
7. **Practice thinking** — include "try this yourself" moments and thought exercises
8. **Visual descriptions** — describe diagrams, graphs, or mental models the student should build

{quality_instructions}

Output format: Markdown with clear structure. This should be a self-contained deep-dive that a student can study independently."""

TOPIC_USER_PROMPT = """Create an in-depth lecture on the specific topic "{topic}" from the chapter "{chapter_title}".

Here is the full chapter content for context:

--- TEXTBOOK CONTENT START ---
{content}
--- TEXTBOOK CONTENT END ---

Focus specifically on "{topic}". Extract ALL information related to this topic from the chapter. Go deep — explain every concept, derivation, formula, and example related to this topic. Add additional intuition, examples, and explanations beyond what's in the text to ensure complete understanding."""


class ScriptGenerator:
    """Generate lecture scripts directly from chapter text (Mode 1)."""

    def __init__(self, llm: LLMProvider, config: LectureConfig | None = None):
        self.llm = llm
        self.config = config or LectureConfig()

    def generate(self, chapter: Chapter, pdf_content: PDFContent) -> str:
        """Generate a lecture script for a single chapter."""
        text = chapter.get_text(pdf_content)

        if not text.strip():
            logger.warning(f"No text found for chapter: {chapter.title}")
            return f"# {chapter.title}\n\n*No content found for this chapter.*"

        logger.info(f"Chapter text length: {len(text)} chars (~{len(text)//4} tokens)")

        if len(text) > 50000:
            return self._generate_chunked(chapter.title, text)

        logger.info("Sending to LLM for lecture generation... (this may take 30-90 seconds)")
        return self._generate_single(chapter.title, text)

    def generate_topic(self, topic: str, chapter: Chapter, pdf_content: PDFContent) -> str:
        """Generate a deep-dive lecture on a specific topic within a chapter."""
        text = chapter.get_text(pdf_content)

        if not text.strip():
            logger.warning(f"No text found for chapter: {chapter.title}")
            return f"# {topic}\n\n*No content found.*"

        logger.info(f"Generating deep-dive on topic: '{topic}'")
        logger.info(f"Chapter text length: {len(text)} chars (~{len(text)//4} tokens)")

        quality = self.config.audience_level
        quality_inst = QUALITY_INSTRUCTIONS.get(quality, QUALITY_INSTRUCTIONS["advanced"])

        system = TOPIC_SYSTEM_PROMPT.format(quality_instructions=quality_inst)
        user = TOPIC_USER_PROMPT.format(
            topic=topic,
            chapter_title=chapter.title,
            content=text,
        )

        logger.info("Sending to LLM for topic deep-dive... (this may take 30-90 seconds)")
        response = self.llm.generate(system, user)
        return response.content

    def _generate_single(self, chapter_title: str, content: str) -> str:
        quality = self.config.audience_level
        quality_inst = QUALITY_INSTRUCTIONS.get(quality, QUALITY_INSTRUCTIONS["advanced"])

        system = LECTURE_SYSTEM_PROMPT.format(quality_instructions=quality_inst)
        user = LECTURE_USER_PROMPT.format(
            chapter_title=chapter_title,
            content=content,
        )
        response = self.llm.generate(system, user)
        return response.content

    def _generate_chunked(self, chapter_title: str, content: str) -> str:
        chunk_size = 40000
        overlap = 3000
        chunks = []
        start = 0
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunks.append(content[start:end])
            start = end - overlap

        quality = self.config.audience_level
        quality_inst = QUALITY_INSTRUCTIONS.get(quality, QUALITY_INSTRUCTIONS["advanced"])
        system = LECTURE_SYSTEM_PROMPT.format(quality_instructions=quality_inst)

        parts = []
        for i, chunk in enumerate(chunks):
            part_title = chapter_title if i == 0 else f"{chapter_title} (continued)"
            context_note = ""
            if i > 0:
                context_note = (
                    "\n\nNOTE: This is a continuation. Do not repeat introductions. "
                    "Continue naturally from where the previous section ended."
                )

            user = LECTURE_USER_PROMPT.format(
                chapter_title=part_title,
                content=chunk,
            ) + context_note

            logger.info(f"Generating chunk {i+1}/{len(chunks)}...")
            response = self.llm.generate(system, user)
            parts.append(response.content)

        return "\n\n---\n\n".join(parts)
