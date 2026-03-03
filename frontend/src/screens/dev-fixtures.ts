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

export const FIXTURE_DRAW_SCENE_SEMANTIC: VisualInstruction = {
  type: "draw_scene",
  element_id: "free-body-semantic",
  title: "Free Body Diagram (Semantic)",
  description:
    "Block on surface with weight, normal, and friction — built from semantic spec",
  scene_type: "free_body",
  elements: [
    { id: "block", kind: "box", label: "m" },
    {
      id: "weight",
      kind: "force_arrow",
      from: "block",
      direction: "down",
      label: "W",
      color: "#ef4444",
    },
    {
      id: "normal",
      kind: "force_arrow",
      from: "block",
      direction: "up",
      label: "N",
      color: "#4ade80",
    },
    {
      id: "friction",
      kind: "force_arrow",
      from: "block",
      direction: "left",
      label: "f",
      color: "#fbbf24",
      magnitude: 0.7,
    },
    { id: "ground", kind: "surface" },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_SEMANTIC_SPRING: VisualInstruction = {
  type: "draw_scene",
  element_id: "free-body-semantic-spring",
  title: "Block on Spring (Semantic)",
  description: "Spring system from semantic elements",
  scene_type: "free_body",
  elements: [
    { id: "block", kind: "box", label: "m" },
    {
      id: "weight",
      kind: "force_arrow",
      from: "block",
      direction: "down",
      label: "W",
      color: "#ef4444",
    },
    {
      id: "normal",
      kind: "force_arrow",
      from: "block",
      direction: "up",
      label: "N",
      color: "#4ade80",
    },
    {
      id: "friction",
      kind: "force_arrow",
      from: "block",
      direction: "left",
      label: "f",
      color: "#fbbf24",
      magnitude: 0.7,
    },
    {
      id: "applied",
      kind: "force_arrow",
      from: "block",
      direction: "right",
      label: "F",
      color: "#a78bfa",
    },
    { id: "ground", kind: "surface" },
    { id: "spring", kind: "spring" },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_OPTICS_CONVEX: VisualInstruction = {
  type: "draw_scene",
  element_id: "optics-convex-lens",
  title: "Convex Lens — Image Formation",
  description:
    "Object placed at 2f from a convex lens. Real, inverted, same-size image formed at 2f on the other side.",
  scene_type: "optics",
  elements: [
    {
      id: "lens",
      kind: "convex_lens",
      label: "L",
      extras: { focal_length: 80 },
    },
    {
      id: "object",
      kind: "force_arrow",
      label: "Object",
      color: "#60a5fa",
      extras: { object_distance: 160, object_height: 50 },
    },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_OPTICS_CONCAVE: VisualInstruction = {
  type: "draw_scene",
  element_id: "optics-concave-lens",
  title: "Concave Lens — Virtual Image",
  description:
    "Object in front of a concave lens. Virtual, upright, diminished image formed on the same side.",
  scene_type: "optics",
  elements: [
    {
      id: "lens",
      kind: "concave_lens",
      label: "L",
      extras: { focal_length: 80 },
    },
    {
      id: "object",
      kind: "force_arrow",
      label: "Object",
      color: "#60a5fa",
      extras: { object_distance: 120, object_height: 50 },
    },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_OPTICS_DOUBLE_SLIT: VisualInstruction = {
  type: "draw_scene",
  element_id: "optics-double-slit",
  title: "Double-Slit Experiment (Semantic)",
  description:
    "Light source, barrier with two slits, wavefronts, and interference pattern — built from semantic spec.",
  scene_type: "optics",
  elements: [
    { id: "source", kind: "point_source", label: "Light source" },
    {
      id: "wall",
      kind: "barrier",
      extras: { slit_count: 2, slit_separation: 50 },
    },
    { id: "detector", kind: "screen", label: "Screen" },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_CIRCUIT_SERIES: VisualInstruction = {
  type: "draw_scene",
  element_id: "circuit-series-resistors",
  title: "Series Resistors",
  description:
    "Battery with two resistors in series — Ohm's law demonstration circuit.",
  scene_type: "circuit",
  elements: [
    { id: "V", kind: "battery", label: "12V" },
    { id: "R1", kind: "resistor", label: "100\u03A9" },
    { id: "R2", kind: "resistor", label: "200\u03A9" },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_CIRCUIT_BULB: VisualInstruction = {
  type: "draw_scene",
  element_id: "circuit-switch-bulb",
  title: "Battery + Switch + Bulb",
  description: "Simple circuit with a battery, closed switch, and light bulb.",
  scene_type: "circuit",
  elements: [
    { id: "V", kind: "battery", label: "9V" },
    { id: "S", kind: "switch", label: "S\u2081", extras: { closed: true } },
    { id: "L", kind: "bulb", label: "Bulb" },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_GEOMETRY_ALTITUDE: VisualInstruction = {
  type: "draw_scene",
  element_id: "geometry-triangle-altitude",
  title: "Triangle with Altitude",
  description:
    "Triangle ABC with altitude from A to foot H on BC, plus right-angle mark.",
  scene_type: "geometry",
  elements: [
    { id: "A", kind: "point", label: "A", extras: { x: 250, y: 80 } },
    { id: "B", kind: "point", label: "B", extras: { x: 100, y: 320 } },
    { id: "C", kind: "point", label: "C", extras: { x: 400, y: 320 } },
    {
      id: "tri",
      kind: "triangle",
      label: "ABC",
      extras: { v1: "A", v2: "B", v3: "C" },
    },
    { id: "H", kind: "point", label: "H", extras: { x: 250, y: 320 } },
    {
      id: "altitude",
      kind: "line_segment",
      from: "A",
      to: "H",
      color: "#60a5fa",
    },
    {
      id: "ra",
      kind: "right_angle_mark",
      extras: { vertex: "H", ray1: "A", ray2: "C" },
    },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_GEOMETRY_ISOSCELES: VisualInstruction = {
  type: "draw_scene",
  element_id: "geometry-isosceles",
  title: "Isosceles Triangle",
  description:
    "Isosceles triangle with congruence marks on equal sides and angle arc at the apex.",
  scene_type: "geometry",
  elements: [
    { id: "A", kind: "point", label: "A", extras: { x: 250, y: 60 } },
    { id: "B", kind: "point", label: "B", extras: { x: 120, y: 320 } },
    { id: "C", kind: "point", label: "C", extras: { x: 380, y: 320 } },
    { id: "tri", kind: "triangle", extras: { v1: "A", v2: "B", v3: "C" } },
    {
      id: "cm1",
      kind: "congruence_mark",
      from: "A",
      to: "B",
      extras: { count: 1 },
    },
    {
      id: "cm2",
      kind: "congruence_mark",
      from: "A",
      to: "C",
      extras: { count: 1 },
    },
    {
      id: "apex-angle",
      kind: "angle_arc",
      label: "α",
      extras: { vertex: "A", ray1: "B", ray2: "C" },
    },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_GEOMETRY_INSCRIBED: VisualInstruction = {
  type: "draw_scene",
  element_id: "geometry-inscribed-angle",
  title: "Circle with Inscribed Angle",
  description:
    "Center O, circle, 3 points on circumference, chords forming inscribed angle.",
  scene_type: "geometry",
  elements: [
    { id: "O", kind: "point", label: "O", extras: { x: 250, y: 200 } },
    { id: "circ", kind: "circle_shape", extras: { center: "O", radius: 120 } },
    { id: "P", kind: "point", label: "P", extras: { x: 162, y: 116 } },
    { id: "Q", kind: "point", label: "Q", extras: { x: 338, y: 116 } },
    { id: "R", kind: "point", label: "R", extras: { x: 250, y: 320 } },
    { id: "chord1", kind: "line_segment", from: "R", to: "P" },
    { id: "chord2", kind: "line_segment", from: "R", to: "Q" },
    {
      id: "inscribed",
      kind: "angle_arc",
      label: "θ",
      extras: { vertex: "R", ray1: "P", ray2: "Q", radius: 25 },
      color: "#a78bfa",
    },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_CHEMISTRY_REACTION: VisualInstruction = {
  type: "draw_scene",
  element_id: "chemistry-combustion",
  title: "Combustion of Hydrogen",
  description:
    "Balanced equation: 2H₂ + O₂ → 2H₂O. Hydrogen gas reacts with oxygen to form water.",
  scene_type: "chemistry",
  elements: [
    {
      id: "r1",
      kind: "molecule",
      label: "H₂",
      extras: { coefficient: 2, state: "g" },
    },
    { id: "r2", kind: "molecule", label: "O₂", extras: { state: "g" } },
    { id: "arr", kind: "arrow_label", label: "Spark" },
    {
      id: "p1",
      kind: "molecule",
      label: "H₂O",
      extras: { coefficient: 2, state: "l" },
    },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_CHEMISTRY_HEATING: VisualInstruction = {
  type: "draw_scene",
  element_id: "chemistry-heating",
  title: "Heating a Test Tube",
  description:
    "A test tube containing CaCO₃ + HCl heated over a Bunsen burner with thermometer.",
  scene_type: "chemistry",
  elements: [
    { id: "burner", kind: "bunsen_burner", extras: { flame: true } },
    {
      id: "tube",
      kind: "test_tube",
      label: "CaCO₃ + HCl",
      extras: { fill_level: 0.3 },
    },
    { id: "therm", kind: "thermometer", from: "tube" },
  ],
  progressive: true,
};

export const FIXTURE_DRAW_SCENE_CHEMISTRY_DISTILLATION: VisualInstruction = {
  type: "draw_scene",
  element_id: "chemistry-distillation",
  title: "Simple Distillation Setup",
  description:
    "Round-bottom flask heated over a Bunsen burner, with thermometer and collection beaker.",
  scene_type: "chemistry",
  elements: [
    {
      id: "rbf",
      kind: "flask",
      label: "Mixture",
      extras: { variant: "round_bottom", side_arm: true, fill_level: 0.4 },
    },
    { id: "burner", kind: "bunsen_burner", extras: { flame: true } },
    { id: "therm", kind: "thermometer", from: "rbf", label: "78°C" },
    { id: "collector", kind: "beaker", label: "Distillate" },
  ],
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
    FIXTURE_DRAW_SCENE_SEMANTIC,
    FIXTURE_DRAW_SCENE_SEMANTIC_SPRING,
    FIXTURE_DRAW_SCENE_OPTICS_CONVEX,
    FIXTURE_DRAW_SCENE_OPTICS_CONCAVE,
    FIXTURE_DRAW_SCENE_OPTICS_DOUBLE_SLIT,
    FIXTURE_DRAW_SCENE_CIRCUIT_SERIES,
    FIXTURE_DRAW_SCENE_CIRCUIT_BULB,
    FIXTURE_DRAW_SCENE_GEOMETRY_ALTITUDE,
    FIXTURE_DRAW_SCENE_GEOMETRY_ISOSCELES,
    FIXTURE_DRAW_SCENE_GEOMETRY_INSCRIBED,
    FIXTURE_DRAW_SCENE_CHEMISTRY_REACTION,
    FIXTURE_DRAW_SCENE_CHEMISTRY_HEATING,
    FIXTURE_DRAW_SCENE_CHEMISTRY_DISTILLATION,
  ],
  highlight: [FIXTURE_HIGHLIGHT],
  clear: [FIXTURE_CLEAR],
};
