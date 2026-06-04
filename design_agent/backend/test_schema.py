"""Schema guards for the diagram DSL — focused on the staged-reveal contract.

design_agent is a standalone service with no pytest harness; these tests are
written to run either under pytest (`pytest test_schema.py`) or directly
(`python test_schema.py`). They lock the cognitive-load invariants that the
`animations` schema must satisfy — most importantly INV-2 (no autoplay): the
schema must make a self-advancing animation *unrepresentable*.
"""

from schema import AnimationStep, DiagramSpec


def test_animation_step_has_no_timing_trigger() -> None:
    """INV-2: there must be no field that lets a step advance on its own.

    `loop`/`autoplay`/`delay`/`interval` would let a diagram animate without a
    narration or interaction event. The old stub had `loop=True`; it's gone.
    """
    forbidden = {"loop", "autoplay", "delay", "interval", "repeat"}
    assert forbidden.isdisjoint(AnimationStep.model_fields), (
        "AnimationStep must not expose a self-advancing field (INV-2)"
    )


def test_clean_declarative_steps_validate() -> None:
    spec = DiagramSpec.model_validate(
        {
            "title": "Projectile",
            "presentation_mode": "build_up",
            "elements": [{"type": "svg_path", "id": "traj", "d": "M0 0"}],
            "animations": [
                {"step": 1, "role_targets": ["surface"], "cue": "the ground"},
                {"step": 2, "element_targets": ["traj"], "duration_ms": 600},
            ],
        }
    )
    assert spec.presentation_mode == "build_up"
    assert spec.animations[0].role_targets == ["surface"]
    assert spec.animations[0].cue == "the ground"
    assert spec.animations[1].element_targets == ["traj"]
    assert spec.animations[1].duration_ms == 600


def test_backward_compatible_with_empty_and_legacy_animations() -> None:
    """The ubiquitous `animations: []` and any legacy varied dict must still
    parse — a no-op step, never a hard validation failure that blanks a
    diagram. (Persisted precompute specs flow as raw dicts, but live generation
    parses through this model, so leniency here protects the transition.)"""
    assert DiagramSpec.model_validate({"animations": []}).animations == []
    legacy = DiagramSpec.model_validate(
        {"animations": [{"duration": 2.0, "loop": True, "type": "fade"}]}
    )
    # Legacy extras are tolerated (extra="allow") but carry no targets → no-op.
    assert legacy.animations[0].role_targets == []
    assert legacy.animations[0].element_targets == []


def test_presentation_mode_optional_and_constrained() -> None:
    assert DiagramSpec().presentation_mode is None
    try:
        DiagramSpec.model_validate({"presentation_mode": "wiggle"})
    except Exception:
        pass
    else:  # pragma: no cover - guard
        raise AssertionError("presentation_mode must reject values outside the Literal")


if __name__ == "__main__":  # pragma: no cover - allow `python test_schema.py`
    test_animation_step_has_no_timing_trigger()
    test_clean_declarative_steps_validate()
    test_backward_compatible_with_empty_and_legacy_animations()
    test_presentation_mode_optional_and_constrained()
    print("all schema guards passed")
