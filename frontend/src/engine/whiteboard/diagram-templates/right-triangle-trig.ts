/**
 * Right-triangle trigonometry (IGCSE 0580) — the single most recurrent figure
 * in the syllabus (Pythagoras, SOHCAHTOA, angle of elevation/depression).
 *
 * Parametric on the angle θ at vertex C: the opposite side and hypotenuse
 * redraw live as θ changes. The right angle sits at B (bottom-left); the base
 * BC is the adjacent side; BA is the opposite side; CA is the hypotenuse.
 *
 * Bounds: base = 260, θ ∈ [20°, 55°] → opposite ∈ [95, 371] keeps vertex A
 * comfortably inside the 900×650 canvas (verified by the overflow sweep).
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import { type DiagramTemplate, INK, BLUE, GREEN, PINK } from "./types";

// Geometry: opposite = 260 * tan(θ); vertex A rises from B as θ grows.
const A_Y = "480 - 260 * tan(theta * PI / 180)";
const MID_HYP_Y = "480 - 130 * tan(theta * PI / 180)";

function build(params?: Record<string, number>): DesignDiagramSpec {
  const theta = params?.theta ?? 37;
  return {
    title: "Right-triangle trigonometry",
    width: 900,
    height: 650,
    // Reference figure → all elements visible (overview). Staged reveal is a
    // narrated-construction feature, not a template default.
    presentation_mode: "overview",
    parameters: [
      {
        name: "theta",
        min: 20,
        max: 55,
        default: theta,
        step: 1,
        label: "Angle θ (°)",
      },
    ],
    elements: [
      // Adjacent (base) — horizontal B→C.
      {
        type: "svg_line",
        id: "adjacent",
        x1: 280,
        y1: 480,
        x2: 540,
        y2: 480,
        stroke: BLUE,
        strokeWidth: 3,
      },
      // Opposite — vertical B→A.
      {
        type: "svg_line",
        id: "opposite",
        x1: 280,
        y1: 480,
        x2: 280,
        y2: A_Y,
        stroke: GREEN,
        strokeWidth: 3,
      },
      // Hypotenuse — C→A.
      {
        type: "svg_line",
        id: "hypotenuse",
        x1: 540,
        y1: 480,
        x2: 280,
        y2: A_Y,
        stroke: PINK,
        strokeWidth: 3,
      },
      // Right-angle marker at B.
      {
        type: "svg_path",
        id: "right_angle",
        d: "M 300 480 L 300 460 L 280 460",
        stroke: INK,
        strokeWidth: 2,
        fill: "none",
      },
      // Angle arc at C, sweeping θ from the base toward the hypotenuse.
      {
        type: "svg_arc",
        id: "angle_arc",
        cx: 540,
        cy: 480,
        r: 48,
        startAngle: 180,
        endAngle: "180 + theta",
        stroke: INK,
        strokeWidth: 2,
      },
      {
        type: "svg_text",
        id: "theta_label",
        x: 468,
        y: 466,
        text: "θ",
        fontSize: 22,
        fill: INK,
      },
      {
        type: "svg_text",
        id: "adjacent_label",
        x: 410,
        y: 506,
        text: "adjacent",
        fontSize: 16,
        fill: BLUE,
      },
      {
        type: "svg_text",
        id: "opposite_label",
        x: 250,
        y: "480 - 130 * tan(theta * PI / 180)",
        text: "opposite",
        fontSize: 16,
        fill: GREEN,
        angle: -90,
      },
      {
        type: "svg_text",
        id: "hypotenuse_label",
        x: 430,
        y: MID_HYP_Y,
        text: "hypotenuse",
        fontSize: 16,
        fill: PINK,
      },
    ],
    dictionary: {
      adjacent: {
        role: "adjacent",
        semantic: "the side next to angle θ",
        position: "bottom",
      },
      opposite: {
        role: "opposite",
        semantic: "the side across from angle θ",
        position: "left",
      },
      hypotenuse: {
        role: "hypotenuse",
        semantic: "the longest side, across from the right angle",
        position: "diagonal",
      },
      right_angle: {
        role: "right_angle_marker",
        semantic: "the 90° corner at B",
        position: "bottom-left",
      },
      angle_arc: {
        role: "angle",
        semantic: "the angle θ at vertex C",
        position: "bottom-right",
      },
      theta_label: {
        role: "label",
        semantic: "θ symbol",
        position: "bottom-right",
      },
      adjacent_label: {
        role: "label",
        semantic: "adjacent-side label",
        position: "bottom",
      },
      opposite_label: {
        role: "label",
        semantic: "opposite-side label",
        position: "left",
      },
      hypotenuse_label: {
        role: "label",
        semantic: "hypotenuse label",
        position: "diagonal",
      },
    },
  };
}

export const rightTriangleTrig: DiagramTemplate = {
  conceptId: "right-triangle-trig",
  title: "Right-triangle trigonometry",
  subject: "math",
  build,
};
