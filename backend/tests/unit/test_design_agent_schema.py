"""Tests for the design_agent's DiagramSpec extensions (ElementMeta, dictionary).

The design_agent module lives in a sibling project and is not installed as a
backend dependency. We load its schema module by absolute path so the backend
test suite can validate the contract.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_design_agent_schema():
    """Load design_agent/backend/schema.py without polluting global sys.path."""
    schema_path = Path(__file__).resolve().parents[3] / "design_agent" / "backend" / "schema.py"
    if not schema_path.exists():
        pytest.skip(f"design_agent schema not present at {schema_path}")
    spec = importlib.util.spec_from_file_location("design_agent_schema", schema_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["design_agent_schema"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


schema_module = _load_design_agent_schema()
ElementMeta = schema_module.ElementMeta
DiagramSpec = schema_module.DiagramSpec


# ── ElementMeta validation ────────────────────────────────────


def test_element_meta_validation_accepts_valid_fields() -> None:
    meta = ElementMeta(
        role="hypotenuse",
        semantic="the ladder, 10 meters long",
        position="diagonal",
        spatial_relations=["from:vertex_A", "to:vertex_B", "longest_side"],
        bounds=(120, 100, 280, 360),
    )
    assert meta.role == "hypotenuse"
    assert meta.position == "diagonal"
    assert meta.bounds == (120, 100, 280, 360)
    assert "longest_side" in meta.spatial_relations


def test_element_meta_validation_rejects_invalid_position() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ElementMeta(
            role="hypotenuse",
            semantic="the ladder",
            position="askew",  # not a valid Literal
        )


def test_element_meta_defaults() -> None:
    meta = ElementMeta(
        role="leg",
        semantic="left leg",
        position="left",
    )
    assert meta.spatial_relations == []
    assert meta.bounds is None


# ── DiagramSpec round-trip ────────────────────────────────────


def test_diagram_spec_dictionary_round_trip() -> None:
    """A DiagramSpec with a populated dictionary survives JSON round-trip."""
    original = DiagramSpec(
        title="Ladder",
        elements=[],
        dictionary={
            "side_AB": ElementMeta(
                role="hypotenuse",
                semantic="the ladder, 10 m",
                position="diagonal",
                spatial_relations=["from:vertex_A", "to:vertex_B"],
                bounds=(120, 100, 280, 360),
            ),
            "vertex_A": ElementMeta(
                role="angle",
                semantic="60° angle at the foot",
                position="bottom-left",
            ),
        },
    )
    raw = original.model_dump_json()
    restored = DiagramSpec.model_validate_json(raw)
    assert "side_AB" in restored.dictionary
    assert restored.dictionary["side_AB"].role == "hypotenuse"
    assert restored.dictionary["side_AB"].bounds == (120, 100, 280, 360)
    assert restored.dictionary["vertex_A"].role == "angle"


def test_diagram_spec_dictionary_default_is_empty() -> None:
    """Legacy specs (no dictionary) are still valid."""
    spec = DiagramSpec(title="Legacy")
    assert spec.dictionary == {}
