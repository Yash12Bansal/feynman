"""Doubt-resolution pipeline.

When a student taps Ask Feynman during a precomputed lecture, this package
classifies their doubt, plans a resolution (with optional precomputed-diagram
reuse), and delivers it as live voice + visuals over LiveKit.

Phase 3 skeleton: `doubt_capture` runs STT on the student's audio after the
frontend signals intent; `doubt_classifier` returns a stubbed classification.
Phase 4 fleshes out classifier + planner + diagram-fit matcher.
"""

from feynman.agent.doubt_resolution.doubt_classifier import (
    DoubtClassification,
    DoubtType,
    classify_doubt,
)

__all__ = ["DoubtClassification", "DoubtType", "classify_doubt"]
