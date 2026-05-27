"""Style constraints for narration writing.

Phase 4d's BeatNarrationWriter validator consumes BANNED_OPENERS. Phase 4b
ships only the constant; validators that use it are introduced in Phase 4d.

`PRONUNCIATION_RULES` is the single source of truth for "narration → TTS"
rendering rules. Every prompt that produces text destined for speech
synthesis (v2 BeatNarrationWriter, backend doubt planner, any future
narration consumer) injects this block so rules-drift across prompts never
opens up. The bar is deliberately tight (~10 lines, examples per rule) —
long rule lists get ignored by LLMs.
"""

from __future__ import annotations

PRONUNCIATION_RULES: str = """\
PRONUNCIATION RULES — the narration is read aloud by a TTS engine. Write \
what should be HEARD, not what should be READ:

- NUMBERS are words. "four thousand nineteen", not "4019". "three point \
one four", not "3.14". "one half", not "1/2".
- UNITS are spelled out in prose. "kilometers per hour", not "km/h". \
"meters per second squared", not "m/s²". "kilograms", not "kg". \
"newtons", not "N". "joules", not "J".
- SYMBOLS pronounced by name. "delta v", not "Δv". "theta", not "θ". \
"pi", not "π". "approximately", not "≈".
- EQUATIONS in spoken sentences read as English. "v equals m times a", \
not "v = ma". "x squared", not "x²". "log of x", not "log(x)".
- ABBREVIATIONS expanded. "for example", not "e.g.". "with respect to", \
not "w.r.t.". "right-hand side", not "RHS". "compared to", not "vs".

Single-letter math variables (F, m, a, v, x) ARE acceptable in spoken \
prose — they're pronounceable as themselves. Never spell out a single \
variable letter as a word.\
"""


BANNED_OPENERS: list[str] = [
    "Let's",
    "Let me",
    "Now,",
    "So,",
    "Alright",
    "Okay",
    "Great",
    "So basically",
    "First of all",
    "In this section",
    "We're going to",
    "We will",
    "Today we",
    "Today, we",
    "I want to",
    "I would like to",
    "It's important to note",
    "Keep in mind",
    "Remember that",
]
