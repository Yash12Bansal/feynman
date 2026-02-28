/**
 * Mock visual instructions for the dev harness.
 *
 * Realistic classroom content exercising every instruction type and field variant.
 * Kept separate from DevHarness.tsx so the UI code stays focused.
 */

import type { VisualInstruction } from "../types/visuals";

export const FIXTURE_SHOW_TEXT: VisualInstruction = {
  type: "show_text",
  element_id: "newton-first-law",
  title: "Newton's First Law of Motion",
  text: "An object at rest stays at rest, and an object in motion stays in motion at a constant velocity, unless acted upon by a net external force. This is also known as the Law of Inertia.",
  style: "definition",
};

export const FIXTURE_SHOW_TEXT_KEY_POINT: VisualInstruction = {
  type: "show_text",
  element_id: "inertia-key-point",
  text: "Inertia is NOT a force. It is a property of matter — the tendency to resist changes in motion. More mass means more inertia.",
  style: "key_point",
};

export const FIXTURE_SHOW_EQUATION: VisualInstruction = {
  type: "show_equation",
  element_id: "newtons-second-law",
  latex: "F = ma",
  label: "Newton's Second Law",
  animation: "fade_in",
};

export const FIXTURE_SHOW_EQUATION_COMPLEX: VisualInstruction = {
  type: "show_equation",
  element_id: "quadratic-formula",
  latex: "x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}",
  label: "The Quadratic Formula",
  animation: "term_by_term",
};

export const FIXTURE_DRAW_DIAGRAM: VisualInstruction = {
  type: "draw_diagram",
  element_id: "free-body-diagram",
  diagram_type: "force_diagram",
  title: "Free Body Diagram — Block on Inclined Plane",
  description:
    "A block sits on a 30-degree inclined plane. Forces acting on it: weight (mg) downward, normal force (N) perpendicular to the surface, and friction (f) along the surface opposing potential motion.",
  nodes: [
    { id: "block", label: "Block (m)", shape: "rectangle", color: "#60a5fa" },
    { id: "weight", label: "mg", shape: "circle", color: "#ef4444" },
    { id: "normal", label: "N", shape: "circle", color: "#4ade80" },
    { id: "friction", label: "f", shape: "circle", color: "#fbbf24" },
  ],
  edges: [
    { from_id: "block", to_id: "weight", label: "gravity", directed: true },
    {
      from_id: "block",
      to_id: "normal",
      label: "perpendicular",
      directed: true,
    },
    {
      from_id: "block",
      to_id: "friction",
      label: "along surface",
      style: "dashed",
      directed: true,
    },
  ],
  progressive: true,
};

export const FIXTURE_SHOW_GRAPH: VisualInstruction = {
  type: "show_graph",
  element_id: "projectile-motion",
  graph_type: "function",
  title: "Projectile Motion — Height vs Time",
  x_axis: { label: "Time (s)", min: 0, max: 5 },
  y_axis: { label: "Height (m)", min: 0, max: 35 },
  functions: [
    {
      expression: "-4.9*t^2 + 20*t + 5",
      label: "h(t) = -4.9t\u00B2 + 20t + 5",
      color: "#60a5fa",
      domain_min: 0,
      domain_max: 4.3,
    },
  ],
  animated: true,
};

export const FIXTURE_HIGHLIGHT: VisualInstruction = {
  type: "highlight",
  target_id: "newtons-second-law",
  style: "glow",
  color: "#fbbf24",
  duration_ms: 2000,
};

export const FIXTURE_CLEAR: VisualInstruction = {
  type: "clear",
};

/** All fixtures in a good default display order. */
export const ALL_FIXTURES: VisualInstruction[] = [
  FIXTURE_SHOW_TEXT,
  FIXTURE_SHOW_TEXT_KEY_POINT,
  FIXTURE_SHOW_EQUATION,
  FIXTURE_SHOW_EQUATION_COMPLEX,
  FIXTURE_DRAW_DIAGRAM,
  FIXTURE_SHOW_GRAPH,
  FIXTURE_HIGHLIGHT,
];

/** Map of type → fixture(s), for the toggle UI. */
export const FIXTURES_BY_TYPE: Record<string, VisualInstruction[]> = {
  show_text: [FIXTURE_SHOW_TEXT, FIXTURE_SHOW_TEXT_KEY_POINT],
  show_equation: [FIXTURE_SHOW_EQUATION, FIXTURE_SHOW_EQUATION_COMPLEX],
  draw_diagram: [FIXTURE_DRAW_DIAGRAM],
  show_graph: [FIXTURE_SHOW_GRAPH],
  highlight: [FIXTURE_HIGHLIGHT],
  clear: [FIXTURE_CLEAR],
};
