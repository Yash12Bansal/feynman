/**
 * 2D vector addition (tip-to-tail) — IGCSE 0580 (vectors) AND 0625 (resultant
 * forces). Vector a is fixed; vector b pivots by the slider angle θ_b; the
 * resultant a + b redraws live from O to b's tip.
 *
 * Bounds: |b| = 150, θ_b ∈ [10°, 80°] keeps b's tip well inside 900×650.
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import { type DiagramTemplate, INK, BLUE, GREEN, PINK } from "./types";

// b's tip = P1 + |b|·(cos θ_b, −sin θ_b); origin O = (250,420); P1 = (430,360).
const BX = "430 + 150 * cos(theta_b * PI / 180)";
const BY = "360 - 150 * sin(theta_b * PI / 180)";

function build(params?: Record<string, number>): DesignDiagramSpec {
  const thetaB = params?.theta_b ?? 45;
  return {
    title: "Vector addition",
    width: 900,
    height: 650,
    presentation_mode: "overview",
    parameters: [
      {
        name: "theta_b",
        min: 10,
        max: 80,
        default: thetaB,
        step: 1,
        label: "Direction of b (°)",
      },
    ],
    elements: [
      {
        type: "svg_circle",
        id: "origin",
        cx: 250,
        cy: 420,
        r: 4,
        fill: INK,
        stroke: INK,
      },
      // Vector a (fixed) O→P1.
      {
        type: "svg_arrow",
        id: "vector_a",
        x1: 250,
        y1: 420,
        x2: 430,
        y2: 360,
        stroke: BLUE,
        strokeWidth: 3,
      },
      // Vector b (pivots) P1→tip, tail-to-tip with a.
      {
        type: "svg_arrow",
        id: "vector_b",
        x1: 430,
        y1: 360,
        x2: BX,
        y2: BY,
        stroke: GREEN,
        strokeWidth: 3,
      },
      // Resultant O→tip of b.
      {
        type: "svg_arrow",
        id: "resultant",
        x1: 250,
        y1: 420,
        x2: BX,
        y2: BY,
        stroke: PINK,
        strokeWidth: 4,
      },
      {
        type: "svg_text",
        id: "label_a",
        x: 330,
        y: 405,
        text: "a",
        fontSize: 20,
        fill: BLUE,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_b",
        x: "445 + 75 * cos(theta_b * PI / 180)",
        y: "352 - 75 * sin(theta_b * PI / 180)",
        text: "b",
        fontSize: 20,
        fill: GREEN,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_r",
        x: "330 + 75 * cos(theta_b * PI / 180)",
        y: "408 - 75 * sin(theta_b * PI / 180)",
        text: "a + b",
        fontSize: 20,
        fill: PINK,
        fontWeight: "600",
      },
    ],
    dictionary: {
      origin: {
        role: "point",
        semantic: "the common tail O",
        position: "left",
      },
      vector_a: { role: "vector", semantic: "vector a", position: "center" },
      vector_b: {
        role: "vector",
        semantic: "vector b, drawn tip-to-tail from a",
        position: "center",
      },
      resultant: {
        role: "resultant",
        semantic: "the resultant a + b",
        position: "center",
      },
      label_a: {
        role: "label",
        semantic: "label for vector a",
        position: "center",
      },
      label_b: {
        role: "label",
        semantic: "label for vector b",
        position: "center",
      },
      label_r: {
        role: "label",
        semantic: "label for the resultant",
        position: "center",
      },
    },
  };
}

export const vectorAddition2d: DiagramTemplate = {
  conceptId: "vector-addition-2d",
  title: "Vector addition",
  subject: "math",
  build,
};
