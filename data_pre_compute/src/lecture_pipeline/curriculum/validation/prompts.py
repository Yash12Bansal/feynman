"""Prompt templates for gap-filling sub-agent.

The gap-filler runs a targeted LLM call to extract ONLY the items
that the initial extraction missed (detected by StructuralValidator).
"""

from __future__ import annotations

from typing import Any

from ..prompts import CURRICULUM_SCHEMA_CONTEXT


# ---------------------------------------------------------------------------
# Gap-Fill System Prompt
# ---------------------------------------------------------------------------

GAP_FILL_SYSTEM_PROMPT = """You are a gap-filling agent for a curriculum graph extraction.

A previous extraction of a textbook chapter MISSED some content.
Your job is to extract ONLY the missing items listed below.
Do NOT re-extract concepts that already exist.

{schema_context}

For each missing item, return a JSON object with ALL standard fields:
- topic_name (string): concise name for the concept
- concept_type (string): MUST be one of the types listed above
- resolution_level (string): "concept" or "detail"
- section_number (string|null): the textbook section this belongs to
- parent (string|null): topic_name of the parent concept, or null if top-level
- page_start (int): first page where this concept appears
- page_end (int): last page where this concept appears
- visual_hint (string|null): what to draw on the board
- estimated_duration_minutes (float): how long to teach this
- summary (string): exhaustive teaching summary (include all formulas, steps, key points)
- source_text (string): verbatim excerpt from the chapter text
- difficulty (string): "beginner", "intermediate", or "advanced"

For relationships to existing concepts, return objects with:
- from_node (string): topic_name of the source concept
- to_node (string): topic_name of the target concept
- type (string): one of the relationship types listed above
- label (string): brief explanation

Return JSON with exactly two top-level keys: "nodes" and "relationships".
Return ONLY the JSON object. No markdown fences, no explanatory text."""


# ---------------------------------------------------------------------------
# Gap-Fill User Prompt
# ---------------------------------------------------------------------------

GAP_FILL_USER_PROMPT_TEMPLATE = """## Chapter Text

{chapter_text}

## Already Extracted Concepts (DO NOT re-extract these)

{existing_concepts}

## Missing Items That MUST Be Extracted

{missing_items}

Extract ONLY the missing items listed above. Return JSON with "nodes" and "relationships"."""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def get_gap_fill_system_prompt() -> str:
    """Build the gap-fill system prompt with curriculum schema injected."""
    return GAP_FILL_SYSTEM_PROMPT.format(
        schema_context=CURRICULUM_SCHEMA_CONTEXT,
    )


def build_gap_fill_user_prompt(
    chapter_text: str,
    existing_concept_names: list[str],
    gaps: dict[str, Any],
) -> str:
    """Format the gap-fill user prompt.

    Args:
        chapter_text: Full chapter text for the LLM to search.
        existing_concept_names: Names of already-extracted concepts.
        gaps: Dict with keys like 'missing_sections', 'missing_figures', etc.
    """
    # Format existing concepts list
    if existing_concept_names:
        existing_lines = [f"- {name}" for name in existing_concept_names]
        existing_str = "\n".join(existing_lines)
    else:
        existing_str = "(none extracted yet)"

    # Format missing items by category
    missing_parts: list[str] = []

    sections = gaps.get("missing_sections", [])
    if sections:
        missing_parts.append("### Missing Sections (extraction floor — MUST extract)")
        for s in sections:
            missing_parts.append(
                f"- Section {s['section_number']}: {s['title']} "
                f"— extract at least one concept node for this section"
            )

    figures = gaps.get("missing_figures", [])
    if figures:
        missing_parts.append("\n### Missing Figures")
        for fig in figures:
            missing_parts.append(
                f"- {fig} — extract a VISUALIZATION node with visual_hint"
            )

    examples = gaps.get("missing_examples", [])
    if examples:
        missing_parts.append("\n### Missing Examples")
        for ex in examples:
            missing_parts.append(f"- {ex} — extract an EXAMPLE node")

    equations = gaps.get("missing_equations", [])
    if equations:
        missing_parts.append("\n### Missing Equations")
        for eq in equations:
            missing_parts.append(f"- {eq} — extract a FORMULA node")

    missing_str = "\n".join(missing_parts) if missing_parts else "(no gaps detected)"

    return GAP_FILL_USER_PROMPT_TEMPLATE.format(
        chapter_text=chapter_text,
        existing_concepts=existing_str,
        missing_items=missing_str,
    )
