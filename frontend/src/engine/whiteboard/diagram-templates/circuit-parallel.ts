/**
 * Parallel DC circuit (IGCSE 0625, electricity): a cell driving two resistors
 * wired in parallel — each bridges the same pair of rails, so each sees the
 * full cell voltage. The companion to dc-circuit-series; the recurring "draw a
 * parallel circuit" need, rendered instantly with zero LLM.
 *
 * Static for the same reason as the series template — a live current readout
 * needs computed-label support the renderer doesn't have yet.
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import { type DiagramTemplate, INK, GREEN, AMBER } from "./types";

function wire(id: string, x1: number, y1: number, x2: number, y2: number) {
  return {
    type: "svg_line" as const,
    id,
    x1,
    y1,
    x2,
    y2,
    stroke: INK,
    strokeWidth: 2.5,
  };
}

function build(): DesignDiagramSpec {
  return {
    title: "Parallel circuit",
    width: 900,
    height: 650,
    presentation_mode: "overview",
    elements: [
      // Top + bottom rails — the two shared nodes.
      wire("rail_top", 250, 200, 650, 200),
      wire("rail_bottom", 250, 460, 650, 460),
      // Left side carries the cell.
      wire("wire_left_top", 250, 200, 250, 300),
      wire("wire_left_bottom", 250, 340, 250, 460),
      {
        type: "svg_line",
        id: "battery_pos",
        x1: 226,
        y1: 310,
        x2: 274,
        y2: 310,
        stroke: AMBER,
        strokeWidth: 2.5,
      },
      {
        type: "svg_line",
        id: "battery_neg",
        x1: 238,
        y1: 330,
        x2: 262,
        y2: 330,
        stroke: AMBER,
        strokeWidth: 5,
      },
      // Right side closes the loop.
      wire("wire_right", 650, 200, 650, 460),
      // Branch 1 — resistor R₁ bridging the rails at x = 430.
      wire("wire_r1_top", 430, 200, 430, 300),
      {
        type: "svg_rect",
        id: "resistor_1",
        x: 414,
        y: 300,
        width: 32,
        height: 68,
        stroke: GREEN,
        fill: "none",
        strokeWidth: 2.5,
      },
      wire("wire_r1_bottom", 430, 368, 430, 460),
      // Branch 2 — resistor R₂ bridging the rails at x = 540.
      wire("wire_r2_top", 540, 200, 540, 300),
      {
        type: "svg_rect",
        id: "resistor_2",
        x: 524,
        y: 300,
        width: 32,
        height: 68,
        stroke: GREEN,
        fill: "none",
        strokeWidth: 2.5,
      },
      wire("wire_r2_bottom", 540, 368, 540, 460),
      // Labels.
      {
        type: "svg_text",
        id: "label_battery",
        x: 206,
        y: 326,
        text: "V",
        fontSize: 18,
        fill: AMBER,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_r1",
        x: 466,
        y: 340,
        text: "R₁",
        fontSize: 18,
        fill: GREEN,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_r2",
        x: 576,
        y: 340,
        text: "R₂",
        fontSize: 18,
        fill: GREEN,
        fontWeight: "600",
      },
    ],
    dictionary: {
      rail_top: {
        role: "wire",
        semantic: "the top rail — one shared node",
        position: "top",
      },
      rail_bottom: {
        role: "wire",
        semantic: "the bottom rail — the other shared node",
        position: "bottom",
      },
      wire_left_top: {
        role: "wire",
        semantic: "left wire from the top rail to the cell",
        position: "left",
      },
      wire_left_bottom: {
        role: "wire",
        semantic: "left wire from the cell to the bottom rail",
        position: "left",
      },
      battery_pos: {
        role: "battery",
        semantic: "the cell's positive terminal",
        position: "left",
      },
      battery_neg: {
        role: "battery",
        semantic: "the cell's negative terminal",
        position: "left",
      },
      wire_right: {
        role: "wire",
        semantic: "right wire closing the loop",
        position: "right",
      },
      wire_r1_top: {
        role: "wire",
        semantic: "wire from the top rail into R₁",
        position: "center",
      },
      resistor_1: {
        role: "resistor",
        semantic: "resistor R₁ on the first branch",
        position: "center",
      },
      wire_r1_bottom: {
        role: "wire",
        semantic: "wire from R₁ to the bottom rail",
        position: "center",
      },
      wire_r2_top: {
        role: "wire",
        semantic: "wire from the top rail into R₂",
        position: "center",
      },
      resistor_2: {
        role: "resistor",
        semantic: "resistor R₂ on the second branch",
        position: "center",
      },
      wire_r2_bottom: {
        role: "wire",
        semantic: "wire from R₂ to the bottom rail",
        position: "center",
      },
      label_battery: {
        role: "label",
        semantic: "cell e.m.f. V",
        position: "left",
      },
      label_r1: { role: "label", semantic: "R₁ label", position: "center" },
      label_r2: { role: "label", semantic: "R₂ label", position: "center" },
    },
  };
}

export const dcCircuitParallel: DiagramTemplate = {
  conceptId: "circuit-parallel",
  title: "Parallel circuit",
  subject: "physics",
  build,
};
