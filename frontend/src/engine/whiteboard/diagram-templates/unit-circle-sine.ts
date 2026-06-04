/**
 * Unit circle ↔ sine curve (IGCSE 0580 trig + 0625 waves). The single best
 * "aha" figure for trigonometry: a radius sweeps the unit circle by the slider
 * angle θ, and its vertical height is plotted live as the point on the sine
 * curve to the right. A horizontal connector ties the two together so the
 * student SEES that sin θ *is* the height of the rotating radius.
 *
 * Parametric on θ ∈ [0°, 360°]: the radius, the vertical sine-leg, the angle
 * arc, the moving curve point, and the connector all redraw together.
 *
 * Geometry: circle centre C = (240, 330), r = 150. A point at angle θ sits at
 * (240 + 150·cosθ, 330 − 150·sinθ) — math convention (CCW, y-up), so the angle
 * arc sweeps with endAngle = -θ to match arcPath's clockwise-positive screen
 * convention. The curve maps θ ∈ [0,360] → x ∈ [430, 860] at the same height.
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import { type DiagramTemplate, INK, MUTED, BLUE, GREEN, PINK } from "./types";

// Point on the circle at angle θ (degrees → radians inside).
const PX = "240 + 150 * cos(theta * PI / 180)";
const PY = "330 - 150 * sin(theta * PI / 180)";
// Matching point on the sine curve: x scales linearly with θ, same height.
const DOT_X = "430 + 430 * theta / 360";
const DOT_Y = "330 - 150 * sin(theta * PI / 180)";

// Static sine polyline, sampled every 30°, mapped with the SAME transform as
// the moving dot so the dot rides exactly on the curve.
const SINE_PATH =
  "M 430 330 L 466 255 L 502 200 L 538 180 L 573 200 L 609 255 " +
  "L 645 330 L 681 405 L 717 460 L 753 480 L 788 460 L 824 405 L 860 330";

function build(params?: Record<string, number>): DesignDiagramSpec {
  const theta = params?.theta ?? 45;
  return {
    title: "Unit circle and sine",
    width: 900,
    height: 650,
    presentation_mode: "overview",
    parameters: [
      {
        name: "theta",
        min: 0,
        max: 360,
        default: theta,
        step: 1,
        label: "Angle θ (°)",
      },
    ],
    elements: [
      {
        type: "svg_circle",
        id: "unit_circle",
        cx: 240,
        cy: 330,
        r: 150,
        stroke: MUTED,
        fill: "none",
        strokeWidth: 2,
      },
      {
        type: "svg_line",
        id: "axis_x",
        x1: 70,
        y1: 330,
        x2: 410,
        y2: 330,
        stroke: MUTED,
        strokeWidth: 1,
      },
      {
        type: "svg_line",
        id: "axis_y",
        x1: 240,
        y1: 168,
        x2: 240,
        y2: 492,
        stroke: MUTED,
        strokeWidth: 1,
      },
      // Angle arc at the centre — endAngle = -theta to sweep CCW like the radius.
      {
        type: "svg_arc",
        id: "angle_arc",
        cx: 240,
        cy: 330,
        r: 44,
        startAngle: 0,
        endAngle: "-theta",
        stroke: INK,
        strokeWidth: 2,
      },
      // Rotating radius C → point.
      {
        type: "svg_line",
        id: "radius",
        x1: 240,
        y1: 330,
        x2: PX,
        y2: PY,
        stroke: BLUE,
        strokeWidth: 3,
      },
      // The sine height: vertical leg from the x-axis up to the point.
      {
        type: "svg_line",
        id: "sine_leg",
        x1: PX,
        y1: 330,
        x2: PX,
        y2: PY,
        stroke: GREEN,
        strokeWidth: 2.5,
      },
      // The sine curve (static) and the live point that rides it.
      {
        type: "svg_path",
        id: "sine_curve",
        d: SINE_PATH,
        stroke: INK,
        strokeWidth: 2,
        fill: "none",
      },
      {
        type: "svg_circle",
        id: "curve_point",
        cx: DOT_X,
        cy: DOT_Y,
        r: 7,
        stroke: PINK,
        fill: PINK,
        strokeWidth: 2,
      },
      // Horizontal connector — same height on both sides (the whole point).
      {
        type: "svg_line",
        id: "connector",
        x1: PX,
        y1: PY,
        x2: DOT_X,
        y2: DOT_Y,
        stroke: MUTED,
        strokeWidth: 1.5,
        strokeDasharray: "5 5",
      },
      {
        type: "svg_text",
        id: "theta_label",
        x: 300,
        y: 318,
        text: "θ",
        fontSize: 20,
        fill: INK,
      },
      {
        type: "svg_text",
        id: "sine_label",
        x: 645,
        y: 156,
        text: "sin θ",
        fontSize: 16,
        fill: GREEN,
        fontWeight: "600",
      },
    ],
    dictionary: {
      unit_circle: {
        role: "unit_circle",
        semantic: "the unit circle, radius 1",
        position: "left",
      },
      axis_x: {
        role: "axis",
        semantic: "the horizontal axis",
        position: "center",
      },
      axis_y: {
        role: "axis",
        semantic: "the vertical axis",
        position: "center",
      },
      angle_arc: {
        role: "angle",
        semantic: "the angle θ measured from the positive x-axis",
        position: "left",
      },
      radius: {
        role: "radius",
        semantic: "the rotating radius at angle θ",
        position: "left",
      },
      sine_leg: {
        role: "sine",
        semantic: "the height of the radius — this is sin θ",
        position: "left",
      },
      sine_curve: {
        role: "curve",
        semantic: "the sine curve y = sin θ",
        position: "right",
      },
      curve_point: {
        role: "data_point",
        semantic: "the point on the sine curve for the current θ",
        position: "right",
      },
      connector: {
        role: "construction",
        semantic: "ties the radius height to the curve value",
        position: "center",
      },
      theta_label: { role: "label", semantic: "θ symbol", position: "left" },
      sine_label: {
        role: "label",
        semantic: "sine curve label",
        position: "right",
      },
    },
  };
}

export const unitCircleSine: DiagramTemplate = {
  conceptId: "unit-circle-sine",
  title: "Unit circle and sine",
  subject: "math",
  build,
};
