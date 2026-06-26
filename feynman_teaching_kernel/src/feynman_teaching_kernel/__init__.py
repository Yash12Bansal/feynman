"""Shared teaching-planner kernel — public API."""

from feynman_teaching_kernel.format import format_plan_for_prompt
from feynman_teaching_kernel.models import (
    ChecklistItem,
    ConceptTeachingPlan,
    TeachingBeat,
    VisualBeatAction,
)
from feynman_teaching_kernel.persona import (
    ExamplePolicy,
    TeacherPersona,
    VoiceProfile,
    format_style_for_planner,
    merge_persona,
)
from feynman_teaching_kernel.persona_registry import PersonaNotFoundError, load_persona
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
    "ExamplePolicy",
    "PLANNING_SYSTEM_PROMPT",
    "PersonaNotFoundError",
    "ChecklistItem",
    "ConceptTeachingPlan",
    "TeachingBeat",
    "VisualBeatAction",
    "TeacherPersona",
    "VoiceProfile",
    "format_plan_for_prompt",
    "format_style_for_planner",
    "load_persona",
    "merge_persona",
    "plan_concept",
    "plan_doubt",
]
