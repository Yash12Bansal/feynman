"""Prompt templates for LLM-based summary reconciliation during chunk merging."""

from __future__ import annotations


SUMMARY_RECONCILIATION_SYSTEM = """You are a curriculum summarization expert.
You are given multiple summaries of the SAME concept, extracted from
overlapping chunks of the same textbook chapter. Your job is to merge
them into a single, exhaustive summary.

Rules:
- Preserve ALL information from both summaries — do not drop any detail.
- Remove duplicate sentences and redundant phrasing.
- Maintain a coherent narrative flow.
- Keep all formulas, derivations, examples, and key terms.
- The merged summary must be usable by a teacher to deliver a complete lecture.
- Return ONLY the merged summary text, no JSON wrapping."""


def get_summary_reconciliation_system_prompt() -> str:
    """Return the system prompt for summary reconciliation."""
    return SUMMARY_RECONCILIATION_SYSTEM


def build_summary_reconciliation_prompt(
    topic_name: str,
    summaries: list[str],
) -> str:
    """Build user prompt for merging multiple summaries of the same concept.

    Args:
        topic_name: The concept name being summarized.
        summaries: List of summaries to merge (2+).

    Returns:
        Formatted user prompt string.
    """
    parts = [f"## Concept: {topic_name}\n"]
    for i, summary in enumerate(summaries, 1):
        parts.append(f"### Summary {i}\n{summary}\n")
    parts.append(
        "Merge these summaries into a single exhaustive summary. "
        "Preserve all unique information. Remove redundancy."
    )
    return "\n".join(parts)
