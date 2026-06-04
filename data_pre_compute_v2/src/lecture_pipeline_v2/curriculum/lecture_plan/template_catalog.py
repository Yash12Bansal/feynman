"""Canonical diagram-template catalog — the backend mirror of the frontend
registry at `frontend/src/engine/whiteboard/diagram-templates/registry.ts`.

These are the hand-authored, correct-by-construction IGCSE figures the frontend
can build instantly (zero LLM, <1 frame) via `buildTemplateSpec(conceptId)`. When
the lesson planner marks a `DiagramRequirement` with a `template_concept_id`, the
diagram generator SKIPS the LLM call and the manifest carries the id so the
frontend renders the template directly.

This module is the single source of truth on the backend for:
  - which concept ids exist (kept in lock-step with the frontend via
    `tests/test_template_catalog.py`, which parses the .ts files);
  - each template's `element_ids` + roles (so a planner that chooses a template
    can declare `required_elements` against the REAL element vocabulary — the
    narrator focuses by element_id, so these must match exactly);
  - each template's `parameters` (so `set_param`/`animate_param` choreography can
    validate the parameter name before emitting an event);
  - keyword triggers for deterministic matching (a safety net; the primary path
    is the planner choosing the template explicitly with the right ids).

IMPORTANT: if you add/rename a template here you MUST mirror it in the frontend
registry (and vice-versa); the parity test fails otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TemplateParameter:
    """A slider parameter the template exposes (mirrors the .ts `parameters`)."""

    name: str
    min: float
    max: float
    default: float


@dataclass(frozen=True)
class TemplateElement:
    """One focusable element of a template (id + dictionary role)."""

    element_id: str
    role: str


@dataclass(frozen=True)
class DiagramTemplateInfo:
    concept_id: str
    title: str
    subject: str  # "math" | "physics"
    # Keyword triggers (lowercased substring match against topic + purpose).
    keywords: tuple[str, ...]
    elements: tuple[TemplateElement, ...]
    parameters: tuple[TemplateParameter, ...] = field(default_factory=tuple)

    @property
    def element_ids(self) -> list[str]:
        return [e.element_id for e in self.elements]


def _el(element_id: str, role: str) -> TemplateElement:
    return TemplateElement(element_id=element_id, role=role)


# ---------------------------------------------------------------------------
# The catalog. Element ids + roles are copied verbatim from each template's
# `dictionary` in frontend/src/engine/whiteboard/diagram-templates/*.ts.
# ---------------------------------------------------------------------------

_TEMPLATES: tuple[DiagramTemplateInfo, ...] = (
    DiagramTemplateInfo(
        concept_id="right-triangle-trig",
        title="Right-triangle trigonometry",
        subject="math",
        keywords=(
            "right triangle",
            "right-angled triangle",
            "right angled triangle",
            "sohcahtoa",
            "pythagoras",
            "pythagorean",
            "angle of elevation",
            "angle of depression",
            "sine cosine tangent",
        ),
        elements=(
            _el("adjacent", "adjacent"),
            _el("opposite", "opposite"),
            _el("hypotenuse", "hypotenuse"),
            _el("right_angle", "right_angle_marker"),
            _el("angle_arc", "angle"),
            _el("theta_label", "label"),
            _el("adjacent_label", "label"),
            _el("opposite_label", "label"),
            _el("hypotenuse_label", "label"),
        ),
        parameters=(TemplateParameter("theta", 20, 55, 37),),
    ),
    DiagramTemplateInfo(
        concept_id="vector-addition-2d",
        title="Vector addition",
        subject="math",
        keywords=(
            "vector addition",
            "adding vectors",
            "tip to tail",
            "tip-to-tail",
            "resultant vector",
            "resultant force",
            "resultant of two",
        ),
        elements=(
            _el("origin", "point"),
            _el("vector_a", "vector"),
            _el("vector_b", "vector"),
            _el("resultant", "resultant"),
            _el("label_a", "label"),
            _el("label_b", "label"),
            _el("label_r", "label"),
        ),
        parameters=(TemplateParameter("theta_b", 10, 80, 45),),
    ),
    DiagramTemplateInfo(
        concept_id="lens-ray-diagram",
        title="Converging lens — ray diagram",
        subject="physics",
        keywords=(
            "converging lens",
            "convex lens",
            "ray diagram",
            "thin lens",
            "real image",
            "image formation",
        ),
        elements=(
            _el("principal_axis", "principal_axis"),
            _el("lens", "lens"),
            _el("focal_left", "focal_point"),
            _el("focal_right", "focal_point"),
            _el("label_f_left", "label"),
            _el("label_f_right", "label"),
            _el("object", "object"),
            _el("image", "image"),
            _el("ray_parallel_in", "ray_incident"),
            _el("ray_parallel_out", "ray_refracted"),
            _el("ray_chief", "ray_incident"),
            _el("label_object", "label"),
            _el("label_image", "label"),
        ),
        parameters=(TemplateParameter("object_distance", 185, 340, 240),),
    ),
    DiagramTemplateInfo(
        concept_id="dc-circuit-series",
        title="Series circuit",
        subject="physics",
        keywords=("series circuit", "in series", "resistors in series"),
        elements=(
            _el("wire_top_left", "wire"),
            _el("wire_top_right", "wire"),
            _el("wire_right_top", "wire"),
            _el("wire_right_bottom", "wire"),
            _el("wire_bottom_right", "wire"),
            _el("wire_bottom_left", "wire"),
            _el("wire_left_bottom", "wire"),
            _el("wire_left_top", "wire"),
            _el("battery_pos", "battery"),
            _el("battery_neg", "battery"),
            _el("resistor_1", "resistor"),
            _el("resistor_2", "resistor"),
            _el("ammeter", "ammeter"),
            _el("current", "current"),
            _el("label_battery", "label"),
            _el("label_r1", "label"),
            _el("label_r2", "label"),
            _el("label_ammeter", "label"),
            _el("label_current", "label"),
        ),
    ),
    DiagramTemplateInfo(
        concept_id="unit-circle-sine",
        title="Unit circle and sine",
        subject="math",
        keywords=(
            "unit circle",
            "sine curve",
            "sine graph",
            "graph of sine",
            "sine function",
        ),
        elements=(
            _el("unit_circle", "unit_circle"),
            _el("axis_x", "axis"),
            _el("axis_y", "axis"),
            _el("angle_arc", "angle"),
            _el("radius", "radius"),
            _el("sine_leg", "sine"),
            _el("sine_curve", "curve"),
            _el("curve_point", "data_point"),
            _el("connector", "construction"),
            _el("theta_label", "label"),
            _el("sine_label", "label"),
        ),
        parameters=(TemplateParameter("theta", 0, 360, 45),),
    ),
    DiagramTemplateInfo(
        concept_id="projectile-motion",
        title="Projectile motion",
        subject="physics",
        keywords=(
            "projectile",
            "projectile motion",
            "parabolic path",
            "trajectory",
            "launch angle",
        ),
        elements=(
            _el("ground", "surface"),
            _el("trajectory", "curve"),
            _el("launch_angle", "angle"),
            _el("v0", "velocity"),
            _el("vx_apex", "velocity"),
            _el("gravity", "acceleration"),
            _el("v0_label", "label"),
            _el("angle_label", "label"),
            _el("vx_label", "label"),
            _el("gravity_label", "label"),
        ),
    ),
    DiagramTemplateInfo(
        concept_id="circuit-parallel",
        title="Parallel circuit",
        subject="physics",
        keywords=("parallel circuit", "in parallel", "resistors in parallel"),
        elements=(
            _el("rail_top", "wire"),
            _el("rail_bottom", "wire"),
            _el("wire_left_top", "wire"),
            _el("wire_left_bottom", "wire"),
            _el("battery_pos", "battery"),
            _el("battery_neg", "battery"),
            _el("wire_right", "wire"),
            _el("wire_r1_top", "wire"),
            _el("resistor_1", "resistor"),
            _el("wire_r1_bottom", "wire"),
            _el("wire_r2_top", "wire"),
            _el("resistor_2", "resistor"),
            _el("wire_r2_bottom", "wire"),
            _el("label_battery", "label"),
            _el("label_r1", "label"),
            _el("label_r2", "label"),
        ),
    ),
)

_BY_ID: dict[str, DiagramTemplateInfo] = {t.concept_id: t for t in _TEMPLATES}

# The closed set of valid concept ids. Mirrors `listTemplateConceptIds()`.
TEMPLATE_CONCEPT_IDS: frozenset[str] = frozenset(_BY_ID)


def get_template(concept_id: str) -> DiagramTemplateInfo | None:
    return _BY_ID.get(concept_id)


def list_templates() -> tuple[DiagramTemplateInfo, ...]:
    return _TEMPLATES


def match_template(*, topic: str, purpose: str) -> str | None:
    """Deterministic keyword match → concept id, or None.

    Substring match (lowercased) against the topic name + diagram purpose. This
    is a SAFETY NET for diagrams the planner didn't explicitly template; the
    primary path is the planner choosing the template itself (so it authors
    choreography against the template's real element ids). First match wins;
    order in `_TEMPLATES` therefore puts more-specific figures earlier.
    """
    haystack = f"{topic} {purpose}".lower()
    for t in _TEMPLATES:
        if any(kw in haystack for kw in t.keywords):
            return t.concept_id
    return None


def _fmt_num(value: float) -> str:
    """Render a parameter bound without a trailing `.0` (37.0 → "37")."""
    return str(int(value)) if float(value).is_integer() else str(value)


def format_templates_for_prompt() -> str:
    """Render the catalog into a markdown block for the lesson-planner prompt.

    Generated from `_TEMPLATES` so it can NEVER drift from the real element
    vocabulary the frontend renders. The planner uses this to (a) decide which
    template, if any, a topic's figure is, and (b) declare `required_elements`
    using the template's REAL element ids — the narrator focuses by element_id,
    so an invented id would never resolve against the pre-built figure.

    `tests/test_template_catalog.py` asserts every concept_id and a
    representative element id appears in the output.
    """
    blocks: list[str] = []
    for t in _TEMPLATES:
        element_str = ", ".join(f"`{e.element_id}` ({e.role})" for e in t.elements)
        if t.parameters:
            param_str = "; ".join(
                f"`{p.name}` in [{_fmt_num(p.min)}, {_fmt_num(p.max)}] "
                f"(default {_fmt_num(p.default)})"
                for p in t.parameters
            )
        else:
            param_str = "none"
        blocks.append(
            f"- **`{t.concept_id}`** — {t.title} ({t.subject})\n"
            f"  - element ids: {element_str}\n"
            f"  - parameters: {param_str}"
        )
    return "\n".join(blocks)
