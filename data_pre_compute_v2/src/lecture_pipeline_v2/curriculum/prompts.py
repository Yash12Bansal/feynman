"""Prompt templates for v2 extraction.

Two prompt families:
  - SKELETON: one whole-book LLM call producing BookSkeleton
  - TOPIC: per-section LLM call producing joint our_understanding + examples

Diagram, question, prereq, and lecture-script prompts live alongside
their respective enrichment / lecture_script modules.
"""

from __future__ import annotations

import json

from feynman_teaching_kernel.style_guide import PRONUNCIATION_RULES

from .models import BookSkeleton


# ---------------------------------------------------------------------------
# Skeleton — single LLM call, whole book
# ---------------------------------------------------------------------------

SKELETON_SCHEMA_CONTEXT = """## BookSkeleton schema

Return a JSON object with these exact fields:

- textbook_title (string): Full title of the textbook.
- subject (string): Lowercase English discipline ("physics", "mathematics", "chemistry", "biology").
- total_chapters (int): Number of chapters in the output (must match the chapters array length).
- total_pages (int): Total pages in the book.
- subject_overview (string): 2-4 sentence description of what the book covers.
- chapters (array, ordered by book sequence): each object has
    - chapter_index (int): 1-based.
    - title (string): exact chapter title from TOC.
    - page_start (int)
    - page_end (int)
    - summary (string): 2-3 sentence overview.
    - key_concepts (array of strings): 3-8 major topics.
    - prerequisites_from (array of strings): exact titles of earlier chapters this depends on.
    - leads_to (array of strings): exact titles of later chapters that build on this."""


SKELETON_SYSTEM_PROMPT = """You are analysing a textbook's structure to extract its teaching architecture.

Given the table of contents with page numbers plus opening paragraphs of each chapter, produce a precise structural map of how knowledge is organised.

{schema_context}

## JSON Schema (machine-readable)
```json
{json_schema}
```

## Rules
1. Preserve the chapter order from the TOC exactly — it encodes the pedagogical sequence.
2. chapter_index must be 1-based and sequential (1, 2, 3...).
3. prerequisites_from / leads_to must reference EXACT chapter titles from the input.
4. EVERY chapter from the TOC must appear in your output. Do not skip any.
5. subject must be a lowercase single-word academic discipline.
6. Return ONLY the JSON object. No markdown fences. No commentary."""


SKELETON_USER_PROMPT = """## Table of Contents

{toc_text}

## Chapter Previews

{chapter_previews}
{subject_hint_section}
Analyse this textbook and return the BookSkeleton JSON."""


def get_skeleton_system_prompt() -> str:
    schema = BookSkeleton.model_json_schema()
    return SKELETON_SYSTEM_PROMPT.format(
        schema_context=SKELETON_SCHEMA_CONTEXT,
        json_schema=json.dumps(schema, indent=2),
    )


def build_skeleton_user_prompt(
    toc_text: str,
    chapter_previews: list[dict],
    subject_hint: str | None = None,
) -> str:
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

    return SKELETON_USER_PROMPT.format(
        toc_text=toc_text,
        chapter_previews=previews_str,
        subject_hint_section=subject_hint_section,
    )


# ---------------------------------------------------------------------------
# Topic — per-section LLM call producing joint our_understanding + examples
# ---------------------------------------------------------------------------

TOPIC_SYSTEM_PROMPT = f"""You are writing teaching content for a single textbook section that will be read aloud by a TTS engine to a student.

Speak like a great teacher at a whiteboard — warm, clear, intellectually honest, and concrete. The student is roughly 14 years old.

Given the section's text from the textbook, produce a JSON object with these exact fields:

- our_understanding (string): A 200-500 word flowing teacher-voice explanation of the section. No bullets, no headers, no LaTeX, no symbolic formulas — speak everything in words ("velocity equals u plus a times t", not "v = u + at"). Cover the conceptual essence, why it matters, and the key insights. Use direct address ("Imagine you have...", "Notice that...", "Think about..."). When the textbook references a figure, refer to it conversationally ("we'll look at the diagram in a moment") — never "see Figure 12.3".

- book_examples (array): EVERY worked-out problem AND EVERY quantitative inline illustration drawn directly from THIS section of the textbook. THIS IS THE PRODUCT'S CORE PROMISE — the lecture will cover every entry here verbatim in concept, so the student never has to re-open the book. EXCLUDE: pure analogies without numbers ("force is like pushing a cart"), end-of-chapter exercises with no solution, and content from OTHER sections. Each entry has these fields:
    - verbatim_text (string): The example passage quoted from the textbook. Include the full setup, all reasoning steps, and the final answer. This is the source of truth — when narration drifts, regenerate against this.
    - page_number (integer or null): The textbook page number where this example appears, if you can tell from context. Null when uncertain.
    - kind ("worked_out" | "inline"): "worked_out" for numbered "Example X.X" boxes with explicit solutions. "inline" for quantitative illustrations embedded mid-paragraph (e.g., "a car decelerating at 2 m/s² takes 5 seconds to stop").
    - lesson_focus (string): ONE sentence describing what the student should walk away understanding from this specific example.
    - setup_facts (array of strings): The numbers and relationships in this example that MUST be preserved in any retelling. Examples: "mass = 2 kg", "force applied is 10 N", "starts from rest". Be exhaustive — the narration writer treats this as the faithfulness contract.
    - has_derivation (boolean): True if the solution has multiple algebraic / arithmetic steps that should be shown step-by-step on the notebook. False for one-step results.

  If the section has no qualifying examples, return an empty array. NEVER invent book examples that aren't actually in the textbook section.

- examples (array of 0-2 strings): Reserved for legacy back-compat. NEW extractions should leave this as an empty array — extended/world-anchored examples are generated by the lesson planner downstream from book_examples, not here.

Pronunciation rules (apply to BOTH `our_understanding` and ANY narration prose inside `book_examples.verbatim_text` you might rephrase). Apply these to OUR_UNDERSTANDING strictly. For `verbatim_text` keep the literal textbook wording — the downstream LessonPlanner will respeak it.

{PRONUNCIATION_RULES}

Hard rules:
- our_understanding has no equations in symbolic form. Use words.
- No section/figure/page references in our_understanding.
- No markdown formatting in any string.
- Aim for simple, clear words. If a 14-year-old would stumble, rewrite.
- book_examples MUST come from THIS section's text — never from world knowledge or other sections.

Return ONLY the JSON object. No markdown fences. No commentary."""


TOPIC_USER_PROMPT = """## Book context
{book_context}

## Chapter
{chapter_title}

## Section {section_number}: {section_title}

## Section text from the textbook

{section_text}

Produce the JSON with our_understanding and examples for this section."""


def get_topic_system_prompt() -> str:
    return TOPIC_SYSTEM_PROMPT


def build_topic_user_prompt(
    book_skeleton: BookSkeleton | None,
    chapter_title: str,
    section_number: str,
    section_title: str,
    section_text: str,
) -> str:
    if book_skeleton:
        book_context = (
            f"This section is part of '{book_skeleton.textbook_title}' "
            f"({book_skeleton.subject})."
        )
    else:
        book_context = "(book context unavailable)"

    return TOPIC_USER_PROMPT.format(
        book_context=book_context,
        chapter_title=chapter_title,
        section_number=section_number,
        section_title=section_title,
        section_text=section_text,
    )
