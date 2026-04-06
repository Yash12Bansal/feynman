"""Prompt templates for curriculum graph extraction.

Phase 2: Book Skeleton extraction prompts.
Phase 4: Chapter extraction prompts (Pass A: structure, Pass B: content).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .models import BookSkeleton

if TYPE_CHECKING:
    from .anchors.models import ExtractionAnchors


# ---------------------------------------------------------------------------
# Schema context — injected into every extraction prompt
# ---------------------------------------------------------------------------

BOOK_SKELETON_SCHEMA_CONTEXT = """## BookSkeleton Schema

You must return a JSON object with these exact fields:

### Top-level fields
- **textbook_title** (string): Full title of the textbook.
- **subject** (string): Academic discipline in lowercase English (e.g. "physics", "mathematics", "chemistry", "biology").
- **total_chapters** (int): Number of chapters in the output.
- **total_pages** (int): Total pages in the book.
- **subject_overview** (string): 2-4 sentence description of what the book covers and its pedagogical approach.

### chapters (array of objects, ordered by book sequence)
Each chapter object:
- **chapter_index** (int): 1-based position in the book. Must match the book's ordering.
- **title** (string): Exact chapter title from the table of contents.
- **page_start** (int): First page of the chapter.
- **page_end** (int): Last page of the chapter.
- **summary** (string): 2-3 sentence overview of what the chapter teaches.
- **key_concepts** (array of strings): 3-8 major topics/concepts covered.
- **prerequisites_from** (array of strings): Titles of earlier chapters this chapter depends on. Use EXACT chapter titles.
- **leads_to** (array of strings): Titles of later chapters that build on this one. Use EXACT chapter titles.

### units (array of objects)
Group chapters into thematic units:
- **unit_name** (string): Name of the unit (e.g. "Oscillations & Waves").
- **chapter_indices** (array of ints): 1-based indices of chapters in this unit.
- **theme** (string): 1-2 sentence description of the unifying theme.

### cross_chapter_prerequisites (array of objects)
Explicit dependencies between chapters:
- **from_chapter** (string): Title of the prerequisite chapter.
- **to_chapter** (string): Title of the dependent chapter.
- **reason** (string): Why this dependency exists."""


# ---------------------------------------------------------------------------
# Skeleton extraction prompts
# ---------------------------------------------------------------------------

SKELETON_SYSTEM_PROMPT = """You are analyzing a textbook's structure to extract its teaching architecture.

Given the full table of contents with page numbers and the opening paragraphs of each chapter, extract the book's pedagogical skeleton — the map of how knowledge is organized and connected.

{schema_context}

## JSON Schema (machine-readable)
```json
{json_schema}
```

## Critical Rules
1. The chapter order in the book is an INTENTIONAL pedagogical design. Preserve it exactly as-is.
2. chapter_index must be 1-based and sequential (1, 2, 3, ...).
3. prerequisites_from and leads_to must reference EXACT chapter titles from the table of contents.
4. EVERY chapter in the table of contents must appear in your output. Do not skip any.
5. Units should group chapters by theme (e.g. "Mechanics", "Thermodynamics", "Oscillations & Waves").
6. cross_chapter_prerequisites should capture conceptual dependencies the author assumes between chapters.
7. subject must be a lowercase English academic discipline name.
8. Return ONLY the JSON object. No markdown fences, no explanatory text."""


SKELETON_USER_PROMPT_TEMPLATE = """## Table of Contents

{toc_text}

## Chapter Previews

{chapter_previews}
{subject_hint_section}
Analyze this textbook and return the BookSkeleton JSON."""


def get_skeleton_system_prompt() -> str:
    """Build the full system prompt with schema context injected."""
    schema = BookSkeleton.model_json_schema()
    return SKELETON_SYSTEM_PROMPT.format(
        schema_context=BOOK_SKELETON_SCHEMA_CONTEXT,
        json_schema=json.dumps(schema, indent=2),
    )


def build_skeleton_user_prompt(
    toc_text: str,
    chapter_previews: list[dict[str, str]],
    subject_hint: str | None = None,
) -> str:
    """Format the user prompt from structured inputs.

    Args:
        toc_text: Formatted table of contents string.
        chapter_previews: List of dicts with keys: title, preview_text,
            page_start, page_end, chapter_index.
        subject_hint: Optional subject override (e.g. "physics").
    """
    preview_parts = []
    for p in chapter_previews:
        preview_parts.append(
            f"### Chapter {p['chapter_index']}: {p['title']} "
            f"(pages {p['page_start']}-{p['page_end']})\n"
            f"{p['preview_text']}"
        )
    previews_str = "\n\n".join(preview_parts)

    subject_hint_section = ""
    if subject_hint:
        subject_hint_section = (
            f"\n## Subject\nThe subject of this textbook is: {subject_hint}\n\n"
        )

    return SKELETON_USER_PROMPT_TEMPLATE.format(
        toc_text=toc_text,
        chapter_previews=previews_str,
        subject_hint_section=subject_hint_section,
    )


# ---------------------------------------------------------------------------
# Curriculum Schema Context — shared across all extraction prompts
# ---------------------------------------------------------------------------

CURRICULUM_SCHEMA_CONTEXT = """## Curriculum Graph Schema

### Hierarchy (NOT flat — concepts are nested):
  Subject → Unit → Chapter → Concept → Detail
  Each level connected by CONTAINS edges.

### Concept Types (every node MUST have exactly one):
  TOPIC          — broad teaching topic
  DEFINITION     — precise definition of a key term
  FORMULA        — mathematical relationship (MUST include the equation)
  DERIVATION     — step-by-step mathematical proof
  EXAMPLE        — worked problem or concrete instance
  APPLICATION    — real-world use case
  MISCONCEPTION  — common student mistake (MUST describe the wrong belief)
  ANALOGY        — intuitive comparison
  EXPERIMENT     — demonstration or lab procedure
  VISUALIZATION  — diagram, graph, or animation description

### Relationship Types (only these are valid):
  PREREQUISITE     — A must be understood before B
  LEADS_TO         — A naturally flows into B (teaching sequence)
  EXAMPLE_OF       — B is a worked example of concept A
  DERIVED_FROM     — B is mathematically derived from A
  MISCONCEPTION_OF — B is a common mistake about A
  ANALOGY_FOR      — B is an intuitive analogy for A
  APPLICATION_OF   — B is a real-world application of A
  CROSS_REFERENCES — concept in chapter X relates to concept in chapter Y

### Mandatory Extraction Rules (do NOT merge or skip these):
  - Every named equation → SEPARATE FORMULA node (F=ma is one, v=u+at is another, NEVER combine)
  - Every bolded/key term with a definition → SEPARATE DEFINITION node
  - Every worked example or solved problem → SEPARATE EXAMPLE node
  - Every figure, diagram, or graph referenced in the text → SEPARATE VISUALIZATION node
  - Every step-by-step proof or derivation → DERIVATION node
  - Every "common mistake", "caution", or "note" callout → MISCONCEPTION node
  - Every real-world application mentioned → APPLICATION node
  - If a single page has 3 equations, that's 3 FORMULA nodes. Do NOT combine them.
  - Every FORMULA node MUST contain the actual equation in its topic_name or summary
  - Every MISCONCEPTION node MUST describe what students wrongly believe

### Visual Hint Rules (when to generate visual_hint):
  - FORMULA      → ALWAYS. Show equation with labeled diagram of variables.
  - DERIVATION   → ALWAYS. Step-by-step visual with equations appearing sequentially.
  - EXAMPLE      → ALWAYS. Problem setup diagram (free body diagram, circuit, geometry, etc.)
  - EXPERIMENT   → ALWAYS. Apparatus/setup diagram.
  - VISUALIZATION→ ALWAYS. This IS the visual — describe the diagram the textbook shows.
  - DEFINITION   → IF it has physical/geometric meaning (e.g., "amplitude" → sine wave with A marked).
  - MISCONCEPTION→ IF visual helps (side-by-side "wrong vs right" diagram).
  - APPLICATION  → IF it describes a physical scenario (e.g., "car suspension" → spring-damper diagram).
  - ANALOGY      → IF the analogy is visual (e.g., "energy like water in connected vessels").
  - TOPIC        → Usually null (too broad for a single visual).

### Other Rules:
  - Cross-chapter references use format "ChapterTitle::ConceptName"
  - No circular prerequisites (A→B→C→A is forbidden)
  - Teaching order within a chapter follows the book's sequence"""


# ---------------------------------------------------------------------------
# Pass A — Structure Extraction
# ---------------------------------------------------------------------------

CHAPTER_STRUCTURE_SYSTEM_PROMPT = """You are extracting a curriculum concept graph from a textbook chapter.

{schema_context}

For each concept, return a JSON object with:
- topic_name (string): concise name for the concept
- concept_type (string): MUST be one of the types listed above
- resolution_level (string): "concept" or "detail"
- section_number (string|null): the textbook section this belongs to ("12.1", "12.1.3", etc.)
- parent (string|null): topic_name of the parent concept within this chapter, or null if top-level
- page_start (int): first page where this concept appears
- page_end (int): last page where this concept appears
- visual_hint (string|null): one-line description of what to draw on the board, or null
- estimated_duration_minutes (float): how long a teacher should spend on this

For relationships, return objects with:
- from_node (string): topic_name of the source concept
- to_node (string): topic_name of the target concept (use "ChapterTitle::ConceptName" for cross-chapter)
- type (string): MUST be one of the relationship types listed above
- label (string): brief human-readable explanation

Return JSON with exactly two top-level keys: "nodes" and "relationships".

CRITICAL — Mandatory extraction:
- EVERY named equation → separate FORMULA node (if a page has 3 equations, that's 3 nodes)
- EVERY bolded/key term with a definition → separate DEFINITION node
- EVERY worked example or "Example X.Y" → separate EXAMPLE node
- EVERY figure/diagram referenced ("Fig. 12.3", "see diagram") → separate VISUALIZATION node
- EVERY step-by-step proof → DERIVATION node
- EVERY "common mistake"/"caution"/"note" callout → MISCONCEPTION node
- EVERY real-world application → APPLICATION node
- Do NOT merge small concepts into bigger ones. If it's separately teachable, it's a separate node.
- Cross-chapter PREREQUISITE edges where this chapter builds on earlier chapters
- Cross-chapter LEADS_TO edges where this chapter feeds into later chapters
- Preserve the book's teaching order within the chapter

Visual hints — follow the visual hint rules from the schema:
- FORMULA/DERIVATION/EXAMPLE/EXPERIMENT/VISUALIZATION → ALWAYS provide visual_hint
- DEFINITION → provide visual_hint IF the concept has physical/geometric meaning
- MISCONCEPTION → provide visual_hint IF a "wrong vs right" diagram would help
- APPLICATION → provide visual_hint IF it describes a physical scenario

Expected output: a 15-page physics chapter typically yields 50-100 nodes.
If you're producing fewer than 40, you're likely merging concepts that should be separate.

Return ONLY the JSON object. No markdown fences, no explanatory text."""


CHAPTER_STRUCTURE_USER_PROMPT_TEMPLATE = """## Book Context (for awareness only — do NOT extract concepts from this)

{book_skeleton_summary}

## Previous Chapter Context

{previous_chapter_section}

## Next Chapter Context

{next_chapter_section}

## Extraction Floor (do NOT skip any of these)

{anchor_checklist}

## Chapter Text (extract ONLY from this)

{chapter_text}

Extract the curriculum concept graph for this chapter. Return JSON with "nodes" and "relationships"."""


# ---------------------------------------------------------------------------
# Pass B — Content Enrichment
# ---------------------------------------------------------------------------

CHAPTER_CONTENT_SYSTEM_PROMPT = """You are writing exhaustive teaching summaries for curriculum concepts.

{schema_context}

Each summary must contain ALL information a teacher needs to deliver a complete explanation — every formula, derivation step, example, and insight.

For each concept below, provide a JSON object with:
- topic_name (string): EXACT name from the list (used for matching — do not rename)
- summary (string): exhaustive teaching content (include all formulas with variable meanings, all steps, all key points)
- source_text (string): verbatim excerpt from the chapter text that this concept comes from (copy the relevant sentences/paragraphs exactly)
- difficulty (string): "beginner", "intermediate", or "advanced"

Return JSON with exactly one top-level key: "nodes" (array of objects).

Rules:
- summary must be thorough enough that a teacher could explain the concept without the textbook
- source_text must be a direct quote from the chapter text provided — not paraphrased
- Match concepts by EXACT topic_name — do not skip any
- If a concept spans multiple paragraphs, include all relevant text in source_text

Return ONLY the JSON object. No markdown fences, no explanatory text."""


CHAPTER_CONTENT_USER_PROMPT_TEMPLATE = """## Chapter Text (pages {page_start}-{page_end})

{chapter_text}

## Concepts to Summarize

{concept_list}

Write exhaustive teaching summaries for each concept above. Return JSON with "nodes"."""


# ---------------------------------------------------------------------------
# Chapter extraction prompt builders
# ---------------------------------------------------------------------------


def get_chapter_structure_system_prompt() -> str:
    """Build the Pass A system prompt with curriculum schema injected."""
    return CHAPTER_STRUCTURE_SYSTEM_PROMPT.format(
        schema_context=CURRICULUM_SCHEMA_CONTEXT,
    )


def build_chapter_structure_user_prompt(
    skeleton: BookSkeleton,
    chapter_index: int,
    chapter_text: str,
    anchors: ExtractionAnchors,
    previous_concepts: list[str] | None = None,
    next_chapter_summary: str | None = None,
) -> str:
    """Format the Pass A user prompt from structured inputs.

    Args:
        skeleton: Book-level structure for context.
        chapter_index: 1-based index of the chapter being extracted.
        chapter_text: Full text of the chapter.
        anchors: Deterministic anchors (extraction floor).
        previous_concepts: Concept names from the previous chapter.
            If None, auto-derived from skeleton.
        next_chapter_summary: Summary of the next chapter.
            If None, auto-derived from skeleton.
    """
    # Book skeleton summary (compact — just titles, key concepts, prerequisites)
    skeleton_lines = [f"Book: {skeleton.textbook_title} ({skeleton.subject})"]
    for ch in skeleton.chapters:
        marker = " ← THIS CHAPTER" if ch.chapter_index == chapter_index else ""
        skeleton_lines.append(
            f"  Ch {ch.chapter_index}: {ch.title} "
            f"(pp. {ch.page_start}-{ch.page_end}){marker}"
        )
    book_skeleton_summary = "\n".join(skeleton_lines)

    # Auto-derive previous/next from skeleton if not provided
    if previous_concepts is None:
        prev_ch = skeleton.chapter_by_index(chapter_index - 1)
        if prev_ch:
            previous_concepts = prev_ch.key_concepts

    if next_chapter_summary is None:
        next_ch = skeleton.chapter_by_index(chapter_index + 1)
        if next_ch:
            next_chapter_summary = next_ch.summary

    # Previous chapter context
    if previous_concepts:
        prev_section = (
            "The student has just learned these concepts:\n"
            + "\n".join(f"- {c}" for c in previous_concepts)
        )
    else:
        prev_section = "This is the first chapter — no previous concepts."

    # Next chapter context
    if next_chapter_summary:
        next_section = f"The next chapter covers: {next_chapter_summary}"
    else:
        next_section = "This is the last chapter."

    # Anchor checklist — the extraction floor
    anchor_parts = []
    if anchors.section_numbers:
        anchor_parts.append(
            "SECTION NUMBERING FOUND IN THIS CHAPTER "
            "(extraction floor — do NOT skip any):"
        )
        for s in anchors.section_numbers:
            anchor_parts.append(f"  {s.section_number} — {s.title}")
        anchor_parts.append(
            "\nEVERY numbered section above MUST have AT LEAST ONE concept node."
        )

    if anchors.figure_refs:
        anchor_parts.append(f"\nFIGURES FOUND: {', '.join(anchors.figure_refs)}")
        anchor_parts.append(
            "Each figure above MUST have its own VISUALIZATION node."
        )

    if anchors.example_refs:
        anchor_parts.append(f"\nEXAMPLES FOUND: {', '.join(anchors.example_refs)}")
        anchor_parts.append("Each example above MUST have its own EXAMPLE node.")

    if anchors.equations:
        anchor_parts.append(f"\nEQUATIONS FOUND: {', '.join(anchors.equations)}")
        anchor_parts.append(
            "Each equation above SHOULD have a corresponding FORMULA node."
        )

    if not anchor_parts:
        anchor_parts.append("No structural anchors detected in this chapter.")

    anchor_checklist = "\n".join(anchor_parts)

    return CHAPTER_STRUCTURE_USER_PROMPT_TEMPLATE.format(
        book_skeleton_summary=book_skeleton_summary,
        previous_chapter_section=prev_section,
        next_chapter_section=next_section,
        anchor_checklist=anchor_checklist,
        chapter_text=chapter_text,
    )


def get_chapter_content_system_prompt() -> str:
    """Build the Pass B system prompt with curriculum schema injected."""
    return CHAPTER_CONTENT_SYSTEM_PROMPT.format(
        schema_context=CURRICULUM_SCHEMA_CONTEXT,
    )


def build_chapter_content_user_prompt(
    chapter_text: str,
    nodes_to_enrich: list[dict],
    page_start: int,
    page_end: int,
) -> str:
    """Format the Pass B user prompt for a batch of nodes.

    Args:
        chapter_text: Text for the relevant page range.
        nodes_to_enrich: Node dicts from Pass A (need topic_name, concept_type).
        page_start: First page of this batch's text.
        page_end: Last page of this batch's text.
    """
    concept_lines = []
    for i, node in enumerate(nodes_to_enrich, 1):
        concept_lines.append(
            f"{i}. {node['topic_name']} (type: {node['concept_type']})"
        )
    concept_list = "\n".join(concept_lines)

    return CHAPTER_CONTENT_USER_PROMPT_TEMPLATE.format(
        page_start=page_start,
        page_end=page_end,
        chapter_text=chapter_text,
        concept_list=concept_list,
    )
