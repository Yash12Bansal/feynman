"""Teacher persona models — shared by precompute pipeline and runtime doubt."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

_STYLE_CLIP = 6000


class ExamplePolicy(BaseModel):
    """Guides extended-example generation for a persona."""

    domains: list[str] = Field(default_factory=list)
    fun_fact_rate: Literal["low", "medium", "high"] = "medium"


class VoiceProfile(BaseModel):
    """TTS voice selection for a persona variant."""

    tts_voice: str | None = None


class TeacherPersona(BaseModel):
    """Declarative teaching persona loaded from personas/*.yaml."""

    persona_id: str
    extends: str | None = None
    persona_version: int = 1
    style_block: str = ""
    example_policy: ExamplePolicy = Field(default_factory=ExamplePolicy)
    voice_profile: VoiceProfile = Field(default_factory=VoiceProfile)
    figure_preferences: str | None = None
    diagram_policy: Literal["shared", "overlay_allowed"] = "shared"
    pedagogical_moves: list[str] = Field(default_factory=list)
    render_profile: dict[str, Any] | None = None


def merge_persona(base: TeacherPersona, override: TeacherPersona) -> TeacherPersona:
    """Merge override onto base (used for `extends` in YAML)."""
    data = base.model_dump()
    over = override.model_dump(exclude_defaults=True)

    for key, val in over.items():
        if key in ("persona_id", "extends"):
            continue
        if key == "example_policy" and isinstance(val, dict):
            data["example_policy"] = {**data["example_policy"], **val}
        elif key == "voice_profile" and isinstance(val, dict):
            data["voice_profile"] = {**data["voice_profile"], **val}
        elif val not in (None, "", [], {}):
            data[key] = val

    data["persona_id"] = override.persona_id
    data["extends"] = override.extends
    data["persona_version"] = override.persona_version
    return TeacherPersona.model_validate(data)


def merge_domain_overlay(base: TeacherPersona, overlay: TeacherPersona) -> TeacherPersona:
    """Merge a subject domain file onto a pedagogy persona; keep base persona_id."""
    style_parts = [p for p in (base.style_block.strip(), overlay.style_block.strip()) if p]
    ep = base.example_policy.model_copy()
    if overlay.example_policy.domains:
        combined = list(dict.fromkeys([*ep.domains, *overlay.example_policy.domains]))
        ep = ep.model_copy(update={"domains": combined})
    if overlay.example_policy.fun_fact_rate != "medium":
        ep = ep.model_copy(update={"fun_fact_rate": overlay.example_policy.fun_fact_rate})
    return base.model_copy(
        update={
            "style_block": "\n\n".join(style_parts),
            "example_policy": ep,
        }
    )


def format_style_for_planner(persona: TeacherPersona | None) -> str | None:
    """Build the lesson-planner style block from a persona."""
    if persona is None or not persona.style_block.strip():
        return None

    parts: list[str] = []
    if persona.figure_preferences:
        parts.append(f"Figure preference: {persona.figure_preferences}")
    if persona.pedagogical_moves:
        parts.append("Pedagogical moves:\n" + "\n".join(f"- {m}" for m in persona.pedagogical_moves))
    parts.append(persona.style_block.strip())

    text = "\n\n".join(parts)
    if len(text) > _STYLE_CLIP:
        return text[:_STYLE_CLIP]
    return text
