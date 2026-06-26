"""Load TeacherPersona definitions from YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from feynman_teaching_kernel.persona import TeacherPersona, merge_persona

MAX_EXTENDS_DEPTH = 3


class PersonaNotFoundError(FileNotFoundError):
    """Raised when a persona YAML file does not exist."""


def load_persona(persona_id: str, personas_dir: Path) -> TeacherPersona:
    """Load persona by id, resolving `extends` chain (max depth 3)."""
    return _load_chain(persona_id, personas_dir, depth=0)


def _load_chain(persona_id: str, personas_dir: Path, depth: int) -> TeacherPersona:
    if depth > MAX_EXTENDS_DEPTH:
        msg = f"Persona extends chain too deep (>{MAX_EXTENDS_DEPTH}): {persona_id}"
        raise ValueError(msg)

    path = personas_dir / f"{persona_id}.yaml"
    if not path.is_file():
        raise PersonaNotFoundError(f"No persona file: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"Invalid persona YAML (expected mapping): {path}"
        raise ValueError(msg)

    persona = TeacherPersona.model_validate(raw)
    if persona.extends and persona.extends != persona.persona_id:
        base = _load_chain(persona.extends, personas_dir, depth + 1)
        persona = merge_persona(base, persona)
    return persona
