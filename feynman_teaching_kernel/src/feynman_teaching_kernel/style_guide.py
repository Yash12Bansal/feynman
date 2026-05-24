"""Style constraints for narration writing.

Phase 4d's BeatNarrationWriter validator consumes BANNED_OPENERS. Phase 4b
ships only the constant; validators that use it are introduced in Phase 4d.
"""

from __future__ import annotations

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
