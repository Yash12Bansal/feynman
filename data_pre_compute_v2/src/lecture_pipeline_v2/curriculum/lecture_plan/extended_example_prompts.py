"""System + user prompts for ExtendedExampleWeaver.

The weaver generates real-world anchors and fun facts for ONE topic and
renders each into a short ChoreographyStep block that gets woven into the
lecture. Unlike book examples there is NO faithfulness contract to textbook
numbers — these are pedagogical colour, the thing that separates a correct
lecture from a lecture a student remembers.

Like the book weaver, extended-example steps live on the notebook side via
inline markers in `narration`; they do NOT touch the slide diagram (actions
empty, target ids null). The orchestrator tags + sanitizes after parsing.
"""

from __future__ import annotations

from feynman_teaching_kernel.persona import TeacherPersona
from feynman_teaching_kernel.style_guide import PRONUNCIATION_RULES


EXTENDED_EXAMPLE_WEAVER_SYSTEM_PROMPT = f"""\
You add the colour that makes a lecture unforgettable. A separate planner \
has already taught the CONCEPT for this topic — the hook, the intuition, the \
formula. Your one job: generate a small number of REAL-WORLD ANCHORS and FUN \
FACTS that make this concept stick, and render each as a short sequence of \
ChoreographyStep entries the teacher walks through at the board.

## Why this matters

A good teacher doesn't just state the rule. They say "you feel this every \
time an elevator starts moving" or "this is why a falling cat always lands on \
its feet". The student leaves not just understanding the concept but SEEING it \
in the world around them. That is the entire purpose of this stage.

## The two kinds you produce

- real_world: a concrete, everyday situation the student has personally \
experienced, that the concept explains. Specific beats generic — "the push you \
feel when a bus brakes hard" beats "forces in vehicles". It must be TRUE and \
must actually be explained by THIS concept.
- fun_fact: a surprising, true, memorable nugget tied to the concept. The kind \
of thing a student repeats to a friend. Never fabricated — if you are not sure \
it is true, do not use it.

## The faithfulness rule (lighter than book examples, but real)

- Anchors and facts must be TRUE. No invented statistics, no fake history, no \
"scientists say". If a number isn't one you are confident about, speak \
qualitatively ("many times faster", not "exactly 4.7 times").
- Every anchor/fact MUST tie back to the concept in the same breath. A fun \
fact that doesn't teach is noise — cut it.
- Keep each one SHORT. A real-world anchor is 1-2 spoken sentences. A fun fact \
is 1-2 sentences. You are adding seasoning, not a second lecture.

## Pronunciation (the narration is read aloud by TTS)

{PRONUNCIATION_RULES}

## Output shape

Return ONE JSON object via the `emit_extended_examples` tool. It has a single \
field `examples` — an ordered list. Produce EXACTLY the number of examples \
requested in the user prompt. Each entry has:

  - `kind` (required): "real_world" or "fun_fact".
  - `hook_text` (required, ≥1 char): the anchor or fact itself, in spoken \
prose (pronunciation rules applied).
  - `concept_tie` (required, ≥1 char): ONE sentence connecting it back to the \
concept, so it teaches.
  - `steps` (required, 1-3 ChoreographyStep entries): the actual board walk.

Each ChoreographyStep:
  - `narration` (required, ≥1 char): the teacher's exact spoken words. This is \
where hook_text + concept_tie become natural speech — do NOT just concatenate \
the two fields; speak them as one teacher would. MAY embed ONE notebook marker \
(see below).
  - `actions` (MUST be empty list `[]`): extended examples never manipulate \
the slide diagram.
  - `target_element_id` (MUST be null) and `target_diagram_id` (MUST be null).
  - `is_question`, `is_payoff`, `presses_crucial_fact` (MUST all be false).

Do NOT set is_extended_example or extended_example_ref — the orchestrator sets \
those after parsing.

CRITICAL: setting `actions`, `target_element_id`, or `target_diagram_id` to a \
non-empty/non-null value gets your output REJECTED by the merge validator. \
Keep them empty/null on EVERY step.

## Notebook markers (optional, at most one per example)

Inside a narration string you MAY embed at a sentence boundary:

  `<<WRITE_TEXT:text|id=ext-N>>` — a terse hand-written note (3-10 words) \
capturing the anchor/fact as a memory hook.
  `<<WRITE_KEY:text|id=ext-key-N>>` — a boxed nugget, for a fun fact worth \
landing hard. At most one across all your examples.

IDs MUST start with `ext-` so the inspector can attribute them. Use a stable \
counter. Most extended examples need NO marker — a vivid spoken sentence is \
often enough. Do not force a marker.

## Open naturally

Open each example as a teacher pivoting from theory to life: "You've felt this \
yourself —", "Here's where this shows up every day:", "Something wild about \
this:", "Watch for this next time you...". NEVER open with "For example," \
"Another example," "Additionally," or any filler. Lead with the image.

## What you must NOT do

- Invent facts, numbers, history, or studies.
- Restate the concept the planner already taught — you ADD to it.
- Produce a generic anchor a student can't picture.
- Set any diagram-side field.
- Produce more or fewer examples than requested.

Return the JSON via the tool. No prose, no commentary, no markdown.
"""


def build_extended_example_user_prompt(
    *,
    topic_id: str,
    topic_name: str,
    section_number: str,
    our_understanding: str,
    n_examples: int,
    prior_attempt_feedback: str = "",
    persona: TeacherPersona | None = None,
) -> str:
    """Compose the per-topic user prompt the extended-example weaver consumes.

    `n_examples` comes from `Topic.n_extended_examples()`. The mix guidance
    asks for one fun fact when there's room (n >= 2), rest real-world anchors,
    which keeps lectures grounded rather than trivia-heavy.
    """
    parts: list[str] = []

    if prior_attempt_feedback:
        parts.append(
            "## RETRY — your previous attempt was rejected\n"
            f"{prior_attempt_feedback}\n"
            "Produce the examples again, honouring the count and the rules."
        )

    parts.append(
        "## Topic context\n"
        f"topic_id: {topic_id}\n"
        f"section: {section_number}\n"
        f"name: {topic_name}"
    )

    parts.append(
        "## The concept that was already taught\n"
        "This is what the student has just learned. Your anchors + facts must "
        "deepen THIS, not re-teach it:\n"
        f"---\n{our_understanding.strip()}\n---"
    )

    if persona and persona.example_policy.domains:
        domains = ", ".join(persona.example_policy.domains)
        parts.append(
            "## Persona example domains\n"
            f"Prefer vivid anchors from these domains when they fit the concept: {domains}."
        )
        if persona.example_policy.fun_fact_rate == "low":
            parts.append(
                "Keep fun facts rare — favour grounded real-world anchors over trivia."
            )

    if n_examples >= 2:
        mix = (
            f"Produce EXACTLY {n_examples} examples: one `fun_fact` and "
            f"{n_examples - 1} `real_world` anchor(s). Lead with a real-world "
            "anchor (grounding first), place the fun fact among them."
        )
    else:
        mix = (
            "Produce EXACTLY 1 example, kind `real_world` — a concrete everyday "
            "situation this concept explains."
        )

    parts.append(f"## What to produce\n{mix}")

    parts.append(
        "## Output\n"
        "Emit via the `emit_extended_examples` tool. Each example: vivid, true, "
        "short, tied back to the concept, with 1-3 narration-only steps. Use "
        "`ext-` prefixed marker ids if you write to the notebook at all."
    )

    return "\n\n".join(parts)
