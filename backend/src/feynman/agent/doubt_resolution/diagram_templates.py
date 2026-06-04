"""Canonical diagram-template catalog for the doubt path.

Mirror of the frontend registry
(`frontend/src/engine/whiteboard/diagram-templates/registry.ts`) and the
precompute `template_catalog` — the SAME 7 hand-built IGCSE figures. When the
doubt planner picks a `template` directive, delivery publishes the concept id
(no spec) and the frontend builds the figure instantly via `buildTemplateSpec`
(zero-LLM, <1 frame). A cross-repo parity test
(`tests/unit/test_diagram_templates.py`) keeps the concept ids in lock-step with
the frontend registry, so an id that would silently render a blank slide fails
CI on either side.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DoubtTemplate:
    concept_id: str
    description: str  # what the figure depicts (shown to the planner)
    roles: tuple[str, ...]  # semantic roles the planner can focus by (target_role)
    params: tuple[str, ...]  # parameter names for set_param / animate_param


_TEMPLATES: tuple[DoubtTemplate, ...] = (
    DoubtTemplate(
        "right-triangle-trig",
        "A right-angled triangle labelled opposite / adjacent / hypotenuse with "
        "the angle theta — for SOHCAHTOA, Pythagoras, angles of elevation.",
        ("hypotenuse", "opposite", "adjacent", "angle", "right_angle_marker"),
        ("theta",),
    ),
    DoubtTemplate(
        "vector-addition-2d",
        "Two vectors added tip-to-tail with their resultant — for vector "
        "addition and resultant force / displacement.",
        ("vector", "resultant", "point"),
        ("theta_b",),
    ),
    DoubtTemplate(
        "lens-ray-diagram",
        "A converging (convex) lens with principal axis, focal points, an object "
        "and the real image formed by the standard rays.",
        (
            "lens",
            "principal_axis",
            "focal_point",
            "object",
            "image",
            "ray_incident",
            "ray_refracted",
        ),
        ("object_distance",),
    ),
    DoubtTemplate(
        "dc-circuit-series",
        "A series DC circuit: battery, two resistors and an ammeter on one loop, "
        "with the current direction marked.",
        ("battery", "resistor", "ammeter", "wire", "current"),
        (),
    ),
    DoubtTemplate(
        "unit-circle-sine",
        "The unit circle linked to the sine curve — the rotating radius' height "
        "plotted as sin(theta).",
        ("unit_circle", "radius", "sine", "curve", "axis", "angle"),
        ("theta",),
    ),
    DoubtTemplate(
        "projectile-motion",
        "A projectile's parabolic trajectory with launch velocity, launch angle, "
        "apex horizontal velocity and gravity.",
        ("curve", "velocity", "angle", "acceleration", "surface"),
        (),
    ),
    DoubtTemplate(
        "circuit-parallel",
        "A parallel DC circuit: a battery feeding two resistors on separate "
        "branches between common rails.",
        ("battery", "resistor", "wire"),
        (),
    ),
)

_BY_ID: dict[str, DoubtTemplate] = {t.concept_id: t for t in _TEMPLATES}

# The closed set of valid concept ids. Mirrors `listTemplateConceptIds()`.
TEMPLATE_CONCEPT_IDS: frozenset[str] = frozenset(_BY_ID)


def is_known(concept_id: str) -> bool:
    return concept_id in _BY_ID


def get_template(concept_id: str) -> DoubtTemplate | None:
    return _BY_ID.get(concept_id)


def list_templates() -> tuple[DoubtTemplate, ...]:
    return _TEMPLATES


def format_templates_for_prompt() -> str:
    """Render the catalog into the planner prompt's AVAILABLE TEMPLATES block.

    Generated from `_TEMPLATES` so it can't drift from the real concept ids /
    parameters the frontend renders.
    """
    lines: list[str] = []
    for t in _TEMPLATES:
        params = ", ".join(t.params) if t.params else "none"
        roles = ", ".join(t.roles)
        lines.append(
            f"- `{t.concept_id}` — {t.description}\n  focus roles: {roles}; parameters: {params}"
        )
    return "\n".join(lines)
