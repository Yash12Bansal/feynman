"""Graduate-mode prompt overrides — SEPARATE from the IGCSE path.

We re-pitch the audience + depth of the existing lesson/judge/chapter prompts
WITHOUT editing them: import each canonical prompt, swap the audience phrasing,
and append a depth addendum. Every structural rule (hook, Q->P, press-twice,
element-id coupling, the action catalog, pronunciation, templates, length and
failure-mode guidance) is inherited verbatim — ONLY the level changes. That is
deliberate: the craft of great teaching is audience-agnostic; the ceiling isn't.

Nothing here mutates the imported strings in place — `.replace()` returns new
strings, so the canonical IGCSE prompts are untouched.
"""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_prompts import (
    LESSON_PLANNING_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge_prompts import (
    LESSON_JUDGE_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.lecture_plan.prompts import (
    CHAPTER_PLANNING_SYSTEM_PROMPT,
)

_ADVANCED = (
    "advanced student studying at the level this material is written for "
    "(a strong undergraduate or graduate student)"
)

# Audience-phrase swaps applied to every inherited prompt. Longest / most
# specific first so they win over the shorter ones. Covers en-dash + hyphen.
_SWAPS: list[tuple[str, str]] = [
    ("13–15 year old IGCSE student", _ADVANCED),
    ("13-15 year old IGCSE student", _ADVANCED),
    ("a 13-year-old", "an advanced student"),
    ("13-year-old", "advanced student"),
    ("canonical IGCSE figures", "canonical figures"),
    ("IGCSE-level content", "graduate-level content"),
    ("IGCSE figures", "canonical figures"),
]


def regrade(prompt: str) -> str:
    """Re-pitch an IGCSE prompt's audience phrasing to advanced/graduate."""
    for needle, repl in _SWAPS:
        prompt = prompt.replace(needle, repl)
    return prompt


_DEPTH_ADDENDUM = """

## Teaching at THIS level (advanced / graduate) — read this LAST; it overrides any lingering "keep it simple" instinct above

The reader is an advanced student who already holds the prerequisites this source assumes. Teach UP to them. Everything above — hook, insight-first, question→payoff, pressing the crucial fact, choreographed visuals, the element-id coupling contract — STILL HOLDS. Those are the craft of great teaching at every level. What changes is only the ceiling:

- **Do not dumb it down. Do not skip the mechanism.** At this level the mathematics IS the insight, not an afterthought. If the topic is back-propagation, you DERIVE the chain rule across the computational graph — you do not gesture at it. The "smallest, sharpest version" still contains the real machinery; cut padding, never substance.
- **The Feynman move still applies, just higher up.** Build the intuition first — a concrete instance, a picture, the "why would anyone even want this" — and THEN state and derive the formalism precisely. Earn the rigor; never replace it with a vibe. Plain-language "why" before every symbol (the equations-after-picture rule), then the actual symbols and the actual derivation.
- **Assume the prerequisites; define the new.** Use the field's real vocabulary. Introduce notation the moment it first appears. Don't re-teach high-school math; DO make every genuinely new idea feel inevitable.
- **Visuals for THIS domain.** Within the same 0–2 diagram contract and the same element-id coupling, pick the figure the mechanism actually needs — a computational graph, a network architecture, a feature-space transformation, a loss landscape, a decision boundary. The diagram earns its place by making the mechanism click, never by decoration. Same rule as above: if it is on the board, the choreography MUST use it.
- **Rigor is now part of the bar.** A lesson that is charming but hand-waves the derivation FAILS here. Correct, complete mechanism PLUS the intuition that makes it obvious = the bar.
- **Length:** a dense topic may use the upper end of the step budget. Never truncate a real derivation just to hit a lower step count.
"""

_JUDGE_ADDENDUM = """

## Judging at THIS level (advanced / graduate)

This lesson targets an advanced student who holds the prerequisites. Adjust the bar:

- **Reward rigor; penalize hand-waving.** At this level, a charming lesson that skips, fudges, or merely gestures at the real mechanism/derivation is a FAILURE, not a pass. The mathematics must be explained and derived, not name-dropped.
- **Do NOT penalize a lesson for being advanced or mathematical.** Depth appropriate to the source is expected and good. "Too hard for a beginner" / "a novice wouldn't follow" are NOT valid criticisms here — read it as an advanced student seeing THIS idea (not the prerequisites) for the first time.
- The four dimensions above still apply. Add a FIFTH, weighted heavily: **mechanism completeness** — does the lesson actually build/derive the real thing, or wave at it? Incomplete or hand-waved mechanism caps the score at 2.
"""

_CHAPTER_ADDENDUM = """

## At THIS level (advanced / graduate)

Budgets are larger. A dense graduate chapter can spend longer per concept — 90–240 seconds is reasonable for a topic that carries a genuine derivation. Order topics by conceptual dependency: a later section's machinery often needs an earlier section's idea made solid first. Do NOT compress the chapter so hard that the mechanism gets squeezed out — depth is the point at this level.
"""

GRADUATE_LESSON_PROMPT = regrade(LESSON_PLANNING_SYSTEM_PROMPT) + _DEPTH_ADDENDUM
GRADUATE_JUDGE_PROMPT = regrade(LESSON_JUDGE_SYSTEM_PROMPT) + _JUDGE_ADDENDUM
GRADUATE_CHAPTER_PROMPT = regrade(CHAPTER_PLANNING_SYSTEM_PROMPT) + _CHAPTER_ADDENDUM
