/**
 * Series DC circuit (IGCSE 0625, electricity): a cell driving current through
 * two resistors in series, with an ammeter. A static reference figure — the
 * recurring "draw a series circuit" need — rendered instantly with zero LLM.
 *
 * (Live current readout I = V/R needs computed-label support the renderer
 * doesn't have yet; that lands with the generation-side work. This template
 * stays static and correct rather than faking it.)
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import { type DiagramTemplate, INK, MUTED, BLUE, GREEN, AMBER } from "./types";

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
    title: "Series circuit",
    width: 900,
    height: 650,
    presentation_mode: "overview",
    elements: [
      // Loop wires (gaps left for the components).
      wire("wire_top_left", 200, 180, 410, 180),
      wire("wire_top_right", 490, 180, 700, 180),
      wire("wire_right_top", 700, 180, 700, 300),
      wire("wire_right_bottom", 700, 380, 700, 480),
      wire("wire_bottom_right", 700, 480, 472, 480),
      wire("wire_bottom_left", 428, 480, 200, 480),
      wire("wire_left_bottom", 200, 480, 200, 342),
      wire("wire_left_top", 200, 318, 200, 180),
      // Cell (battery): long line = +, short thick line = −.
      {
        type: "svg_line",
        id: "battery_pos",
        x1: 176,
        y1: 318,
        x2: 224,
        y2: 318,
        stroke: AMBER,
        strokeWidth: 2.5,
      },
      {
        type: "svg_line",
        id: "battery_neg",
        x1: 188,
        y1: 342,
        x2: 212,
        y2: 342,
        stroke: AMBER,
        strokeWidth: 5,
      },
      // Resistor R1 (top edge) and R2 (right edge) — IEC boxes.
      {
        type: "svg_rect",
        id: "resistor_1",
        x: 410,
        y: 164,
        width: 80,
        height: 32,
        stroke: GREEN,
        fill: "none",
        strokeWidth: 2.5,
      },
      {
        type: "svg_rect",
        id: "resistor_2",
        x: 684,
        y: 300,
        width: 32,
        height: 80,
        stroke: GREEN,
        fill: "none",
        strokeWidth: 2.5,
      },
      // Ammeter.
      {
        type: "svg_circle",
        id: "ammeter",
        cx: 450,
        cy: 480,
        r: 22,
        stroke: BLUE,
        fill: "none",
        strokeWidth: 2.5,
      },
      // Conventional current direction (cell + terminal, clockwise out the top).
      {
        type: "svg_arrow",
        id: "current",
        x1: 290,
        y1: 180,
        x2: 340,
        y2: 180,
        stroke: MUTED,
        strokeWidth: 2,
      },
      // Labels.
      {
        type: "svg_text",
        id: "label_battery",
        x: 150,
        y: 336,
        text: "V",
        fontSize: 18,
        fill: AMBER,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_r1",
        x: 450,
        y: 150,
        text: "R₁",
        fontSize: 18,
        fill: GREEN,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_r2",
        x: 744,
        y: 346,
        text: "R₂",
        fontSize: 18,
        fill: GREEN,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_ammeter",
        x: 450,
        y: 480,
        text: "A",
        fontSize: 18,
        fill: BLUE,
        fontWeight: "600",
      },
      {
        type: "svg_text",
        id: "label_current",
        x: 315,
        y: 165,
        text: "I",
        fontSize: 16,
        fill: MUTED,
      },
    ],
    dictionary: {
      wire_top_left: {
        role: "wire",
        semantic: "top wire from the cell to R₁",
        position: "top",
      },
      wire_top_right: {
        role: "wire",
        semantic: "top wire from R₁ to the corner",
        position: "top",
      },
      wire_right_top: {
        role: "wire",
        semantic: "right wire to R₂",
        position: "right",
      },
      wire_right_bottom: {
        role: "wire",
        semantic: "right wire from R₂",
        position: "right",
      },
      wire_bottom_right: {
        role: "wire",
        semantic: "bottom wire to the ammeter",
        position: "bottom",
      },
      wire_bottom_left: {
        role: "wire",
        semantic: "bottom wire from the ammeter",
        position: "bottom",
      },
      wire_left_bottom: {
        role: "wire",
        semantic: "left wire to the cell",
        position: "left",
      },
      wire_left_top: {
        role: "wire",
        semantic: "left wire from the cell",
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
      resistor_1: {
        role: "resistor",
        semantic: "resistor R₁",
        position: "top",
      },
      resistor_2: {
        role: "resistor",
        semantic: "resistor R₂",
        position: "right",
      },
      ammeter: {
        role: "ammeter",
        semantic: "the ammeter measuring current",
        position: "bottom",
      },
      current: {
        role: "current",
        semantic: "conventional current direction",
        position: "top",
      },
      label_battery: {
        role: "label",
        semantic: "cell e.m.f. V",
        position: "left",
      },
      label_r1: { role: "label", semantic: "R₁ label", position: "top" },
      label_r2: { role: "label", semantic: "R₂ label", position: "right" },
      label_ammeter: {
        role: "label",
        semantic: "ammeter A label",
        position: "bottom",
      },
      label_current: {
        role: "label",
        semantic: "current I label",
        position: "top",
      },
    },
  };
}

export const dcCircuitSeries: DiagramTemplate = {
  conceptId: "dc-circuit-series",
  title: "Series circuit",
  subject: "physics",
  build,
};
