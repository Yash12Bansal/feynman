/**
 * Projectile motion (IGCSE 0625 kinematics) — the canonical parabola: launch
 * velocity at angle θ, horizontal velocity surviving at the apex, gravity
 * pulling down throughout. A static reference figure (the trajectory is an SVG
 * path, which the renderer doesn't evaluate per-parameter, so a slider can't
 * reshape it — this stays correct rather than faking interactivity).
 *
 * Geometry is adapted from the design_agent's verified "projectile" worked
 * example so the figure matches what live generation produces.
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import { type DiagramTemplate, INK, MUTED, BLUE, GREEN, PINK } from "./types";

// Ground hatch — short ticks under the baseline at y = 500.
const HATCH =
  "M 110 500 L 100 515 M 150 500 L 140 515 M 190 500 L 180 515 " +
  "M 230 500 L 220 515 M 270 500 L 260 515 M 310 500 L 300 515 " +
  "M 350 500 L 340 515 M 390 500 L 380 515 M 430 500 L 420 515 " +
  "M 470 500 L 460 515 M 510 500 L 500 515 M 550 500 L 540 515 " +
  "M 590 500 L 580 515 M 630 500 L 620 515 M 670 500 L 660 515 " +
  "M 710 500 L 700 515 M 750 500 L 740 515 M 790 500 L 780 515";

function build(): DesignDiagramSpec {
  return {
    title: "Projectile motion",
    width: 900,
    height: 650,
    presentation_mode: "overview",
    elements: [
      {
        type: "svg_line",
        id: "ground",
        x1: 100,
        y1: 500,
        x2: 820,
        y2: 500,
        stroke: MUTED,
        strokeWidth: 1.5,
      },
      {
        type: "svg_path",
        id: "ground_hatch",
        d: HATCH,
        stroke: MUTED,
        strokeWidth: 1.2,
        fill: "none",
      },
      {
        type: "svg_path",
        id: "trajectory",
        d: "M 130 500 Q 450 120 770 500",
        stroke: INK,
        strokeWidth: 2.5,
        fill: "none",
      },
      {
        type: "svg_arc",
        id: "launch_angle",
        cx: 130,
        cy: 500,
        r: 42,
        startAngle: -52,
        endAngle: 0,
        stroke: BLUE,
        strokeWidth: 1.5,
        fill: "none",
      },
      {
        type: "svg_arrow",
        id: "v0",
        x1: 130,
        y1: 500,
        x2: 210,
        y2: 400,
        stroke: BLUE,
        strokeWidth: 2.5,
      },
      {
        type: "svg_arrow",
        id: "vx_apex",
        x1: 450,
        y1: 230,
        x2: 540,
        y2: 230,
        stroke: GREEN,
        strokeWidth: 2.5,
      },
      {
        type: "svg_arrow",
        id: "gravity",
        x1: 450,
        y1: 280,
        x2: 450,
        y2: 360,
        stroke: PINK,
        strokeWidth: 2.5,
      },
      {
        type: "svg_text",
        id: "v0_label",
        x: 216,
        y: 394,
        text: "v₀",
        fontSize: 15,
        fill: BLUE,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "angle_label",
        x: 182,
        y: 492,
        text: "θ",
        fontSize: 15,
        fill: BLUE,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "vx_label",
        x: 548,
        y: 228,
        text: "vₓ",
        fontSize: 15,
        fill: GREEN,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "gravity_label",
        x: 462,
        y: 330,
        text: "g",
        fontSize: 15,
        fill: PINK,
        fontWeight: "600",
      },
    ],
    dictionary: {
      ground: {
        role: "surface",
        semantic: "the ground the projectile launches from and lands on",
        position: "bottom",
      },
      trajectory: {
        role: "curve",
        semantic: "the parabolic path of the projectile",
        position: "center",
      },
      launch_angle: {
        role: "angle",
        semantic: "the launch angle θ from the ground",
        position: "bottom-left",
      },
      v0: {
        role: "velocity",
        semantic: "the initial launch velocity",
        position: "bottom-left",
      },
      vx_apex: {
        role: "velocity",
        semantic: "the horizontal velocity, unchanged, at the apex",
        position: "top",
      },
      gravity: {
        role: "acceleration",
        semantic: "gravitational acceleration pulling the projectile down",
        position: "center",
      },
      v0_label: {
        role: "label",
        semantic: "v₀ label",
        position: "bottom-left",
      },
      angle_label: {
        role: "label",
        semantic: "θ label",
        position: "bottom-left",
      },
      vx_label: { role: "label", semantic: "vₓ label", position: "top" },
      gravity_label: { role: "label", semantic: "g label", position: "center" },
    },
  };
}

export const projectileMotion: DiagramTemplate = {
  conceptId: "projectile-motion",
  title: "Projectile motion",
  subject: "physics",
  build,
};
