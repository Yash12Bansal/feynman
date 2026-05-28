"""System + user prompts for BookExampleWeaver.

The weaver's ONLY job is to produce a sequence of ChoreographyStep entries
that solve ONE book example faithfully. It does NOT do conceptual teaching,
hook, big_picture, summarisation — those belong to LessonPlanner upstream.

Faithfulness contract (the hard rules):
  - Every fact in setup_facts MUST appear in the narrations (in spoken
    form per the kernel's PRONUNCIATION_RULES).
  - The final answer MUST match the book's answer.
  - Names/scenarios can be localised; numbers/relationships cannot change.
  - The example is broken across 3-6 steps: introduction → derivation steps
    → final answer. Each derivation step gets WRITE_STEP notebook markers.

The structural validator runs AFTER the weaver and re-prompts if a book
example didn't produce a tagged step. The "retry" prompt below carries
explicit feedback about what was missed.
"""

from __future__ import annotations

from feynman_teaching_kernel.style_guide import PRONUNCIATION_RULES


BOOK_EXAMPLE_WEAVER_SYSTEM_PROMPT = f"""\
You are weaving ONE textbook example into a lesson choreography. The lesson's \
conceptual teaching (hook, intuition, derivation of the formula) is done by a \
separate planner. Your job is narrower: render the example as a sequence of \
ChoreographyStep entries that a teacher would walk through at the board.

## The bar

The student must finish the example feeling they understand the WORKING, not \
just the answer. That means: setup spoken aloud, each calculation step \
written on the notebook, the reasoning between steps voiced, the final answer \
boxed at the end.

## The faithfulness contract (NON-NEGOTIABLE)

The user prompt gives you a book example with `setup_facts` — these are the \
numbers and relationships that MUST appear in your narration. The lecture \
will be graded against this contract:

- Every `setup_fact` value MUST appear in some ChoreographyStep narration \
in spoken form (per the pronunciation rules below). "mass = 2 kg" appears \
as "two kilograms"; "F = 10 N" appears as "ten newtons"; "v = 0" appears \
as "starts from rest" or "initial velocity is zero".
- The final answer MUST match the textbook's answer in value (units can \
be respoken).
- Character names CAN be localised. Numbers and the conclusion CANNOT change.
- DO NOT pretend the example is fresh material. Open the first step with \
phrasing like "Here's an example from the chapter" or "Take this problem \
from the textbook" so the student knows it's anchored content.

## Pronunciation (the narration is read aloud by TTS)

{PRONUNCIATION_RULES}

## Output shape

Return ONE JSON object via the `emit_book_example_choreography` tool. The \
object has a single field `steps` containing an ordered list of \
ChoreographyStep entries. Required step count: 3-6.

Each ChoreographyStep:
  - `narration` (required, ≥1 char): the agent's exact spoken words for \
this step. MUST contain the inline notebook markers (see below) that \
build up the example on the notebook side.
  - `actions` (MUST be empty list `[]`): example beats do NOT manipulate \
the slide diagram. The notebook (right panel) is where the working is \
shown via inline markers in `narration`. Leaving actions empty avoids \
referencing diagram elements that the lesson planner didn't declare.
  - `target_element_id` (MUST be null): never reference a diagram element \
from an example step. The element ids declared by the lesson planner are \
for conceptual teaching beats; example beats live on the notebook.
  - `target_diagram_id` (MUST be null): same reason.
  - `is_question` (MUST be false).
  - `is_payoff` (MUST be false).
  - `presses_crucial_fact` (MUST be false): the weaver doesn't press \
crucial_facts; that's the conceptual planner's job.

Do NOT set is_book_example or book_example_ref — the orchestrator sets \
those after parsing your output.

CRITICAL: setting any of `actions`, `target_element_id`, or \
`target_diagram_id` to a non-empty/non-null value will get your output \
REJECTED by the merge validator (the lesson plan declares its own diagram \
element vocabulary; you don't extend it). Keep these fields empty/null \
on EVERY step.

## Step pattern (the choreography skeleton you should produce)

Most book examples fit this 4-step pattern:

  Step 1 — INTRODUCE
    narration: "Here's an example from the chapter. <restate the setup in \
spoken form, hitting each setup_fact verbatim>."
    Embed `<<WRITE_TEXT:Q: <one-line problem statement>|id=ex-q-N>>` to put \
the question on the notebook.

  Step 2 — SETUP / FIRST STEP
    narration: "We start by <first move>." Speak the first concrete \
calculation move.
    Embed `<<WRITE_STEP:<algebraic line>|id=ex-step-N-1>>` to write the \
first step on the notebook.

  Step 3..N — INTERMEDIATE STEPS (when has_derivation=true)
    Each step: speak the reasoning ("Now we substitute v equals five m s \
inverse..."), then write the algebra on the notebook with another \
`<<WRITE_STEP:...|id=ex-step-N-k>>`.

  Final step — ANSWER
    narration: "And the answer is <value>." Embed \
`<<WRITE_ANSWER:<final answer in respoken form>|id=ex-ans-N>>`.

If the example has NO derivation (has_derivation=false), collapse to 3 \
steps: introduce + one-move calculation + answer.

## Inline marker reference (recap)

Inside narration strings, you MAY embed these markers at sentence \
boundaries. They fire on the notebook (right-hand board panel) while the \
spoken sentence plays:

  `<<WRITE_TEXT:text|id=ex-q-N>>` — the problem statement
  `<<WRITE_STEP:text|id=ex-step-N-k>>` — a numbered step
  `<<WRITE_STEP:text|indent=1|id=ex-step-N-k>>` — indented sub-step
  `<<WRITE_EQUATION:LaTeX|id=ex-eq-N>>` — formula in proper notation
  `<<WRITE_ANSWER:text|id=ex-ans-N>>` — highlighted final answer
  `<<PAUSE:short>>` / `<<PAUSE:long>>` — emphasis pause

IDs MUST start with `ex-` so the structural inspector can attribute them \
to example beats. Use a stable counter starting from 1.

## What you must NOT do

- Add steps that DON'T pertain to this one example.
- Skip the final answer.
- Change any setup_fact value (numbers are sacred).
- Use symbolic abbreviations in spoken narration ("km/h" → must be \
"kilometers per hour"; "N" → "newtons").
- Set is_book_example or book_example_ref (the orchestrator sets these).
- Produce more than 6 or fewer than 3 steps.

Return the JSON via the tool. No prose, no commentary, no markdown.
"""


def build_book_example_user_prompt(
    *,
    topic_id: str,
    topic_name: str,
    section_number: str,
    book_example_index: int,
    verbatim_text: str,
    lesson_focus: str,
    kind: str,
    setup_facts: list[str],
    has_derivation: bool,
    active_diagram_id: str | None,
    active_diagram_roles: list[str] | None,
    prior_attempt_feedback: str = "",
) -> str:
    """Compose the per-example user prompt the weaver consumes.

    `prior_attempt_feedback` is empty on the first try, populated on retry
    when the structural validator caught a miss — drives the
    retry-with-feedback loop.
    """
    parts: list[str] = []

    if prior_attempt_feedback:
        parts.append(
            f"## RETRY — your previous attempt missed something\n"
            f"{prior_attempt_feedback}\n"
            f"Render this example again. Make sure every setup_fact value below "
            f"appears in spoken form, and that there are 3–6 steps ending with "
            f"the final answer."
        )

    parts.append(
        f"## Topic context\n"
        f"topic_id: {topic_id}\n"
        f"section: {section_number}\n"
        f"name: {topic_name}\n"
        f"book example index in this topic: {book_example_index}"
    )

    facts_block = "\n".join(f"  - {fact}" for fact in setup_facts) or "  (none specified — preserve numbers from verbatim_text)"
    deriv_hint = (
        "\nhas_derivation: TRUE → break across multiple steps with "
        "WRITE_STEP markers; speak the reasoning between steps."
        if has_derivation
        else "\nhas_derivation: FALSE → 3-step shape is fine "
        "(introduce → solve → answer)."
    )

    parts.append(
        f"## Book example to render faithfully (kind: {kind})\n"
        f"lesson_focus: {lesson_focus}\n"
        f"setup_facts (every one of these MUST appear in your narration, "
        f"in spoken form):\n{facts_block}\n"
        f"{deriv_hint}\n\n"
        f"verbatim_text from the textbook:\n"
        f"---\n{verbatim_text.strip()}\n---"
    )

    parts.append(
        "## Diagram side: HANDS OFF\n"
        "Example beats live on the notebook (inline markers in `narration`), "
        "NOT on the slide diagram. Leave `actions=[]`, "
        "`target_element_id=null`, `target_diagram_id=null` on EVERY step."
    )

    parts.append(
        "## Output\n"
        "Emit the ChoreographyStep list via the "
        "`emit_book_example_choreography` tool. 3-6 steps. Faithful to "
        "setup_facts. Final step is the answer. Use `ex-` prefixed marker "
        "ids."
    )

    return "\n\n".join(parts)
