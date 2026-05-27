"""Example-beat allocator — enforces the book-coverage USP.

Locked spec (2026-05-27):
  - Every Topic.book_examples entry becomes a faithful beat (source="book").
  - On top of that, N extended (LLM-invented, real-world) example beats are
    added based on Topic.n_extended_examples() — the rule that makes us win
    on hard book-skipped topics.
  - Order within a topic: existing concept beats → book example beats → extended
    example beats. Any LLM-generated "example" beats already in the plan get
    REMOVED first so we control allocation deterministically.

This is a pure-Python post-pass over an existing ConceptTeachingPlan. No LLM
calls — the writer fleshes out the speech_guidance at narration time. The
allocator just decides WHICH beats exist and in what order.

Called from pipeline.py right after ConceptPlanner produces concept_plans.
"""

from __future__ import annotations

import logging
from copy import deepcopy

from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat

from ..models import Topic

logger = logging.getLogger(__name__)

# Terminal beat types we slot example beats IN FRONT OF. Examples land before
# summarisation so the student sees concrete instances before the wrap-up.
_TRAILING_BEAT_TYPES = frozenset({"summarize", "transition"})


def allocate_example_beats(plan: ConceptTeachingPlan, topic: Topic) -> ConceptTeachingPlan:
    """Return a new ConceptTeachingPlan with example beats deterministically allocated.

    The input plan is not mutated. Allocation:
      1. Remove any beats with beat_type == "example" (LLM-generated examples
         get dropped — we own this slot).
      2. Insert one beat per Topic.book_examples (source="book", ref=index).
      3. Append N extended example beats (source="extended"), N from
         topic.n_extended_examples().
      4. Slot the bundle right before the first trailing beat (summarize /
         transition); if there's no trailing beat, append at the end.

    Beats marked example_source="book" carry the book_example_ref index so
    the BeatNarrationWriter can look up the verbatim text + setup_facts.
    Extended beats get a one-line speech_guidance hint; the writer invents
    the real-world anchor at render time (it sees Topic.our_understanding +
    has_book_examples context).
    """
    plan_copy = deepcopy(plan)
    base_beats = [b for b in plan_copy.beats if b.beat_type != "example"]

    book_beats: list[TeachingBeat] = []
    for ref_idx, book_ex in enumerate(topic.book_examples):
        target_seconds = 60 if book_ex.has_derivation else 35
        book_beats.append(
            TeachingBeat(
                beat_type="example",
                speech_guidance=(
                    f"Render this textbook example faithfully. "
                    f"Lesson focus: {book_ex.lesson_focus}. "
                    f"Preserve setup_facts ({', '.join(book_ex.setup_facts) or 'see verbatim_text'}) "
                    f"and the answer."
                ),
                target_duration_seconds=target_seconds,
                example_source="book",
                book_example_ref=ref_idx,
            )
        )

    extended_beats: list[TeachingBeat] = []
    n_extras = topic.n_extended_examples()
    for i in range(n_extras):
        extended_beats.append(
            TeachingBeat(
                beat_type="example",
                speech_guidance=(
                    "Invent ONE fresh real-world example that strengthens this "
                    "concept beyond the textbook. The example MUST anchor in a "
                    "concrete real-world scenario (delivery routes, savings, "
                    "mobile data, sports, cooking, traffic — pick what fits). "
                    "MUST NOT duplicate any book example's setup. Numbers small "
                    "enough to compute mentally."
                ),
                target_duration_seconds=30,
                example_source="extended",
            )
        )

    insert_idx = _trailing_insertion_index(base_beats)
    new_beats = (
        base_beats[:insert_idx] + book_beats + extended_beats + base_beats[insert_idx:]
    )
    plan_copy.beats = new_beats

    logger.info(
        "example_allocator: topic=%s book=%d extended=%d (complexity=%d)",
        topic.topic_id,
        len(book_beats),
        len(extended_beats),
        topic.complexity_score,
    )
    return plan_copy


def _trailing_insertion_index(beats: list[TeachingBeat]) -> int:
    """Index at which to insert example bundle — before first summarize/transition.

    No trailing beat → append at end (returns len(beats)).
    """
    for i, beat in enumerate(beats):
        if beat.beat_type in _TRAILING_BEAT_TYPES:
            return i
    return len(beats)
