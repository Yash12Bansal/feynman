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

export const FIXTURE_DRAW_DIAGRAM_FLOWCHART: VisualInstruction = {
  type: "draw_diagram",
  element_id: "algorithm-flowchart",
  diagram_type: "flowchart",
  title: "Is the Number Even or Odd?",
  nodes: [
    { id: "start", label: "Start", shape: "circle", color: "#4ade80" },
    { id: "input", label: "Read N", shape: "rounded" },
    { id: "check", label: "N mod 2 = 0?", shape: "diamond", color: "#fbbf24" },
    { id: "even", label: "Print Even", shape: "rounded", color: "#60a5fa" },
    { id: "odd", label: "Print Odd", shape: "rounded", color: "#ef4444" },
    { id: "end", label: "End", shape: "circle", color: "#4ade80" },
  ],
  edges: [
    { from_id: "start", to_id: "input", directed: true },
    { from_id: "input", to_id: "check", directed: true },
    { from_id: "check", to_id: "even", label: "Yes", directed: true },
    { from_id: "check", to_id: "odd", label: "No", directed: true },
    { from_id: "even", to_id: "end", directed: true },
    { from_id: "odd", to_id: "end", directed: true },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_DIAGRAM_CYCLE: VisualInstruction = {
  type: "draw_diagram",
  element_id: "water-cycle",
  diagram_type: "cycle",
  title: "The Water Cycle",
  description:
    "Water moves through evaporation, condensation, precipitation, and collection in a continuous loop.",
  nodes: [
    { id: "evap", label: "Evaporation", shape: "rounded", color: "#60a5fa" },
    { id: "cond", label: "Condensation", shape: "rounded", color: "#a78bfa" },
    {
      id: "precip",
      label: "Precipitation",
      shape: "rounded",
      color: "#4ade80",
    },
    { id: "collect", label: "Collection", shape: "rounded", color: "#fbbf24" },
  ],
  edges: [
    { from_id: "evap", to_id: "cond", label: "rises", directed: true },
    { from_id: "cond", to_id: "precip", label: "cools", directed: true },
    { from_id: "precip", to_id: "collect", label: "falls", directed: true },
    { from_id: "collect", to_id: "evap", label: "heats", directed: true },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_DIAGRAM_DESCRIPTION_ONLY: VisualInstruction = {
  type: "draw_diagram",
  element_id: "cell-diagram",
  diagram_type: "free_form",
  description:
    "A typical animal cell showing the nucleus at the center, surrounded by cytoplasm containing mitochondria, endoplasmic reticulum, and Golgi apparatus, all enclosed by the cell membrane.",
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

export const FIXTURE_STEP_EQUATION: VisualInstruction = {
  type: "step_equation",
  element_id: "solve-linear-eq",
  title: "Solving for x",
  steps: [
    { latex: "2x + 4 = 10" },
    {
      latex: "2x = 6",
      annotation: "Subtract 4 from both sides",
      highlight_terms: ["term-result"],
    },
    {
      latex: "x = 3",
      annotation: "Divide both sides by 2",
    },
  ],
};

export const FIXTURE_HIGHLIGHT: VisualInstruction = {
  type: "highlight",
  target_id: "newtons-second-law",
  style: "glow",
  color: "#fbbf24",
  duration_ms: 2000,
};

export const FIXTURE_DRAW_SCENE: VisualInstruction = {
  type: "draw_scene",
  element_id: "free-body-1",
  title: "Free Body Diagram",
  description: "Forces acting on a block on a surface",
  template: {
    template_id: "free_body",
    params: { showWeight: true, showNormal: true, showFriction: true },
  },
  zone: "center-right",
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_SPRING: VisualInstruction = {
  type: "draw_scene",
  element_id: "free-body-spring",
  title: "Block on Spring",
  description:
    "A block connected to a wall by a spring, with weight and normal force",
  template: {
    template_id: "free_body",
    params: {
      showWeight: true,
      showNormal: true,
      showFriction: true,
      showApplied: true,
      showSpring: true,
    },
  },
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_DOUBLE_SLIT: VisualInstruction = {
  type: "draw_scene",
  element_id: "double-slit-1",
  title: "Double-Slit Experiment",
  description:
    "Light passes through two narrow slits and creates an interference pattern on the screen — bright and dark fringes.",
  template: {
    template_id: "double_slit",
    params: { showWaves: true, showPattern: true, showRays: true },
  },
  zone: "center-left",
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_DOUBLE_SLIT_RAYS_ONLY: VisualInstruction = {
  type: "draw_scene",
  element_id: "double-slit-rays",
  title: "Double-Slit — Rays Only",
  description:
    "Just the light rays and barrier, without wavefronts or interference pattern.",
  template: {
    template_id: "double_slit",
    params: { showWaves: false, showPattern: false, showRays: true },
  },
  progressive: true,
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
  FIXTURE_STEP_EQUATION,
  FIXTURE_DRAW_DIAGRAM,
  FIXTURE_SHOW_GRAPH,
  FIXTURE_DRAW_SCENE,
  FIXTURE_DRAW_SCENE_DOUBLE_SLIT,
  FIXTURE_HIGHLIGHT,
];

/** Map of type → fixture(s), for the toggle UI. */
export const FIXTURES_BY_TYPE: Record<string, VisualInstruction[]> = {
  show_text: [FIXTURE_SHOW_TEXT, FIXTURE_SHOW_TEXT_KEY_POINT],
  show_equation: [FIXTURE_SHOW_EQUATION, FIXTURE_SHOW_EQUATION_COMPLEX],
  step_equation: [FIXTURE_STEP_EQUATION],
  draw_diagram: [
    FIXTURE_DRAW_DIAGRAM,
    FIXTURE_DRAW_DIAGRAM_FLOWCHART,
    FIXTURE_DRAW_DIAGRAM_CYCLE,
    FIXTURE_DRAW_DIAGRAM_DESCRIPTION_ONLY,
  ],
  show_graph: [FIXTURE_SHOW_GRAPH],
  draw_scene: [
    FIXTURE_DRAW_SCENE,
    FIXTURE_DRAW_SCENE_SPRING,
    FIXTURE_DRAW_SCENE_DOUBLE_SLIT,
    FIXTURE_DRAW_SCENE_DOUBLE_SLIT_RAYS_ONLY,
  ],
  highlight: [FIXTURE_HIGHLIGHT],
  clear: [FIXTURE_CLEAR],
};
