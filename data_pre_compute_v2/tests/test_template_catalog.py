"""Guards for the backend diagram-template catalog and the generator skip.

The catalog MUST stay in lock-step with the frontend template registry — the
parity test parses the .ts template files so drift fails CI on either side.
"""

from __future__ import annotations

import re
from pathlib import Path

from lecture_pipeline_v2.curriculum.lecture_plan import template_catalog as tc
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_generator import (
    _build_template_diagram,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    DiagramRequirement,
    ElementRequirement,
)

_FRONTEND_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2]
    / "frontend/src/engine/whiteboard/diagram-templates"
)


def _frontend_concept_ids() -> set[str]:
    """Extract every `conceptId: "..."` from the frontend template .ts files."""
    ids: set[str] = set()
    for ts in _FRONTEND_TEMPLATES_DIR.glob("*.ts"):
        if ts.name in {"types.ts", "registry.ts"} or ts.name.endswith(".test.ts"):
            continue
        for m in re.finditer(r'conceptId:\s*"([^"]+)"', ts.read_text()):
            ids.add(m.group(1))
    return ids


def test_catalog_matches_frontend_registry_exactly() -> None:
    """Cross-repo parity: backend ids == frontend conceptIds (no drift)."""
    frontend = _frontend_concept_ids()
    assert frontend, "found no frontend template conceptIds — path wrong?"
    assert set(tc.TEMPLATE_CONCEPT_IDS) == frontend, (
        f"catalog drift — backend-only={set(tc.TEMPLATE_CONCEPT_IDS) - frontend}, "
        f"frontend-only={frontend - set(tc.TEMPLATE_CONCEPT_IDS)}"
    )


def test_every_template_has_elements_and_valid_shape() -> None:
    for t in tc.list_templates():
        assert t.elements, f"{t.concept_id} has no elements"
        assert t.subject in {"math", "physics"}
        # element ids unique within a template
        ids = [e.element_id for e in t.elements]
        assert len(ids) == len(set(ids)), f"{t.concept_id} has duplicate element ids"
        for p in t.parameters:
            assert p.min <= p.default <= p.max, f"{t.concept_id}:{p.name} default OOB"


def test_match_template_keywords() -> None:
    assert (
        tc.match_template(topic="Right-angled triangles", purpose="introduce SOHCAHTOA")
        == "right-triangle-trig"
    )
    assert (
        tc.match_template(topic="Resistors in parallel", purpose="two-branch circuit")
        == "circuit-parallel"
    )
    assert (
        tc.match_template(topic="Projectile motion", purpose="the parabolic path")
        == "projectile-motion"
    )
    # No canonical figure → None (falls back to LLM generation).
    assert tc.match_template(topic="Photosynthesis", purpose="the Calvin cycle") is None


def test_build_template_diagram_has_empty_render_data_and_id() -> None:
    req = DiagramRequirement(
        diagram_id="trig_fig",
        purpose="show the sides of a right triangle",
        required_elements=[
            ElementRequirement(
                element_id="hypotenuse", role="hypotenuse", description="longest side"
            )
        ],
        template_concept_id="right-triangle-trig",
    )
    d = _build_template_diagram(req, topic_id="topic_1")
    assert d.template_concept_id == "right-triangle-trig"
    assert d.render_data == {}  # frontend builds it from the registry
    assert d.diagram_id  # pinned via generate_diagram_uid
    assert d.presentation_mode == req.presentation_mode


def test_diagram_requirement_rejects_unknown_template() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown template_concept_id"):
        DiagramRequirement(
            diagram_id="x",
            purpose="y",
            required_elements=[
                ElementRequirement(element_id="a", role="b", description="c")
            ],
            template_concept_id="not-a-real-template",
        )


def test_format_templates_for_prompt_lists_every_concept_id() -> None:
    """The prompt block must surface every template + its element vocab, so the
    planner can author required_elements against the REAL ids. Generated from
    the catalog → can't drift."""
    block = tc.format_templates_for_prompt()
    for t in tc.list_templates():
        assert t.concept_id in block, f"{t.concept_id} missing from prompt block"
        assert any(e.element_id in block for e in t.elements), (
            f"{t.concept_id} contributes no element ids to the prompt block"
        )
    # Parameter names surface (needed later for set_param/animate_param authoring);
    # parameterless templates render their parameters as "none".
    assert "theta" in block
    assert "none" in block


def test_templated_requirement_rejects_out_of_vocab_element() -> None:
    """A valid template id but an invented element id must fail loudly — the
    planner cannot point at an id the pre-built figure doesn't contain."""
    import pytest

    with pytest.raises(ValueError, match="outside the template"):
        DiagramRequirement(
            diagram_id="trig_fig",
            purpose="show the right triangle",
            required_elements=[
                ElementRequirement(
                    element_id="totally-made-up",
                    role="hypotenuse",
                    description="x",
                )
            ],
            template_concept_id="right-triangle-trig",
        )


def test_templated_requirement_accepts_in_vocab_subset() -> None:
    """Declaring a SUBSET of the template's real element ids is valid — the
    planner declares only the ids its choreography points at."""
    req = DiagramRequirement(
        diagram_id="trig_fig",
        purpose="show the right triangle",
        required_elements=[
            ElementRequirement(
                element_id="hypotenuse", role="hypotenuse", description="x"
            ),
            ElementRequirement(element_id="opposite", role="opposite", description="y"),
        ],
        template_concept_id="right-triangle-trig",
    )
    assert req.template_concept_id == "right-triangle-trig"
    assert {e.element_id for e in req.required_elements} == {"hypotenuse", "opposite"}
