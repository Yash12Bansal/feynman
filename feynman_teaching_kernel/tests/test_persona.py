"""Tests for TeacherPersona load, merge, and registry."""

from __future__ import annotations

from pathlib import Path

import pytest
from feynman_teaching_kernel.persona import (
    ExamplePolicy,
    TeacherPersona,
    VoiceProfile,
    format_style_for_planner,
    merge_persona,
)
from feynman_teaching_kernel.persona_registry import PersonaNotFoundError, load_persona

PERSONAS_DIR = Path(__file__).resolve().parents[2] / "data_pre_compute_v2" / "personas"


def test_load_default_persona() -> None:
    p = load_persona("default", PERSONAS_DIR)
    assert p.persona_id == "default"
    assert p.persona_version == 1
    assert "13–15" in p.style_block


def test_load_feynman_extends_default() -> None:
    p = load_persona("feynman", PERSONAS_DIR)
    assert p.persona_id == "feynman"
    assert p.diagram_policy == "overlay_allowed"
    assert "trains" in p.example_policy.domains
    assert p.voice_profile.tts_voice == "af_bella"
    assert "Michelson" in p.style_block


def test_load_missing_persona_raises() -> None:
    with pytest.raises(PersonaNotFoundError):
        load_persona("nonexistent", PERSONAS_DIR)


def test_merge_persona_overrides_style() -> None:
    base = TeacherPersona(
        persona_id="default",
        style_block="base voice",
        example_policy=ExamplePolicy(domains=["a"]),
    )
    override = TeacherPersona(
        persona_id="custom",
        extends="default",
        style_block="custom voice",
        example_policy=ExamplePolicy(domains=["b", "c"]),
    )
    merged = merge_persona(base, override)
    assert merged.persona_id == "custom"
    assert merged.style_block == "custom voice"
    assert merged.example_policy.domains == ["b", "c"]


def test_format_style_for_planner_includes_figure_prefs() -> None:
    p = TeacherPersona(
        persona_id="x",
        style_block="teach well",
        figure_preferences="reproduce_named_figures",
    )
    text = format_style_for_planner(p)
    assert text is not None
    assert "Figure preference: reproduce_named_figures" in text
    assert "teach well" in text


def test_format_style_for_planner_none_when_empty() -> None:
    p = TeacherPersona(persona_id="x", style_block="   ")
    assert format_style_for_planner(p) is None


def test_load_finance_teacher_persona() -> None:
    p = load_persona("finance_teacher", PERSONAS_DIR)
    assert p.persona_id == "finance_teacher"
    assert p.extends == "default"
    assert "timeline" in p.style_block.lower()
    assert "savings_account" in p.example_policy.domains
    assert len(p.pedagogical_moves) >= 3

