"""Shared teaching-planner kernel — public API."""

from feynman_teaching_kernel.format import format_plan_for_prompt
from feynman_teaching_kernel.models import (
    ChecklistItem,
    ConceptTeachingPlan,
    TeachingBeat,
    VisualBeatAction,
)
from feynman_teaching_kernel.planner import (
    DEFAULT_PLANNING_MODEL,
    plan_concept,
    plan_doubt,
)
from feynman_teaching_kernel.prompts import PLANNING_SYSTEM_PROMPT
from feynman_teaching_kernel.style_guide import BANNED_OPENERS

__all__ = [
    "BANNED_OPENERS",
    "DEFAULT_PLANNING_MODEL",
    "PLANNING_SYSTEM_PROMPT",
    "ChecklistItem",
    "ConceptTeachingPlan",
    "TeachingBeat",
    "VisualBeatAction",
    "format_plan_for_prompt",
    "plan_concept",
    "plan_doubt",
]
