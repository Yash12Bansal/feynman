/**
 * Thin converging-lens ray diagram (IGCSE 0625, light). The object distance is
 * the slider; the image position + size redraw live via the thin-lens
 * equation (1/v − 1/u = 1/f), with f = 120, object height = 90.
 *
 *   image distance v = f·u / (u − f);  image height h' = h·f / (u − f).
 *
 * Bounds: u ∈ [185, 340] keeps a real, inverted image inside 900×650
 * (verified by the overflow sweep). The two principal rays — the parallel ray
 * refracting through F′, and the chief ray through the lens centre — meet at
 * the image tip.
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import {
  type DiagramTemplate,
  INK,
  MUTED,
  BLUE,
  GREEN,
  PINK,
  AMBER,
} from "./types";

const OBJ_X = "450 - object_distance";
const OBJ_TOP_Y = 260; // axis 350 − object height 90
// v = f·u/(u−f); image x = lens(450) + v.
const IMG_X = "450 + 120 * object_distance / (object_distance - 120)";
// h' = h·f/(u−f) = 90·120/(u−120) = 10800/(u−120); image tip below the axis.
const IMG_TOP_Y = "350 + 10800 / (object_distance - 120)";

function build(params?: Record<string, number>): DesignDiagramSpec {
  const u = params?.object_distance ?? 240;
  return {
    title: "Converging lens — ray diagram",
    width: 900,
    height: 650,
    presentation_mode: "overview",
    parameters: [
      {
        name: "object_distance",
        min: 185,
        max: 340,
        default: u,
        step: 5,
        label: "Object distance u",
      },
    ],
    elements: [
      {
        type: "svg_line",
        id: "principal_axis",
        x1: 90,
        y1: 350,
        x2: 840,
        y2: 350,
        stroke: MUTED,
        strokeWidth: 1.5,
        strokeDasharray: "6 6",
      },
      {
        type: "svg_ellipse",
        id: "lens",
        cx: 450,
        cy: 350,
        rx: 16,
        ry: 145,
        stroke: BLUE,
        fill: "rgba(127,212,255,0.08)",
        strokeWidth: 2,
      },
      {
        type: "svg_circle",
        id: "focal_left",
        cx: 330,
        cy: 350,
        r: 4,
        fill: INK,
        stroke: INK,
      },
      {
        type: "svg_circle",
        id: "focal_right",
        cx: 570,
        cy: 350,
        r: 4,
        fill: INK,
        stroke: INK,
      },
      {
        type: "svg_text",
        id: "label_f_left",
        x: 330,
        y: 378,
        text: "F",
        fontSize: 16,
        fill: MUTED,
      },
      {
        type: "svg_text",
        id: "label_f_right",
        x: 570,
        y: 378,
        text: "F′",
        fontSize: 16,
        fill: MUTED,
      },
      // Object — upright arrow on the left of the lens.
      {
        type: "svg_arrow",
        id: "object",
        x1: OBJ_X,
        y1: 350,
        x2: OBJ_X,
        y2: OBJ_TOP_Y,
        stroke: GREEN,
        strokeWidth: 3,
      },
      // Image — inverted arrow on the right of the lens.
      {
        type: "svg_arrow",
        id: "image",
        x1: IMG_X,
        y1: 350,
        x2: IMG_X,
        y2: IMG_TOP_Y,
        stroke: PINK,
        strokeWidth: 3,
      },
      // Ray 1a: parallel to the axis from the object tip to the lens.
      {
        type: "svg_line",
        id: "ray_parallel_in",
        x1: OBJ_X,
        y1: OBJ_TOP_Y,
        x2: 450,
        y2: OBJ_TOP_Y,
        stroke: AMBER,
        strokeWidth: 2,
      },
      // Ray 1b: refracts through F′ down to the image tip.
      {
        type: "svg_line",
        id: "ray_parallel_out",
        x1: 450,
        y1: OBJ_TOP_Y,
        x2: IMG_X,
        y2: IMG_TOP_Y,
        stroke: AMBER,
        strokeWidth: 2,
      },
      // Ray 2: chief ray straight through the lens centre to the image tip.
      {
        type: "svg_line",
        id: "ray_chief",
        x1: OBJ_X,
        y1: OBJ_TOP_Y,
        x2: IMG_X,
        y2: IMG_TOP_Y,
        stroke: "#c9a3ff",
        strokeWidth: 2,
      },
      {
        type: "svg_text",
        id: "label_object",
        x: OBJ_X,
        y: 244,
        text: "object",
        fontSize: 15,
        fill: GREEN,
      },
      {
        type: "svg_text",
        id: "label_image",
        x: IMG_X,
        y: "366 + 10800 / (object_distance - 120)",
        text: "image",
        fontSize: 15,
        fill: PINK,
      },
    ],
    dictionary: {
      principal_axis: {
        role: "principal_axis",
        semantic: "the optical axis",
        position: "center",
      },
      lens: {
        role: "lens",
        semantic: "the converging lens",
        position: "center",
      },
      focal_left: {
        role: "focal_point",
        semantic: "near focal point F",
        position: "center",
      },
      focal_right: {
        role: "focal_point",
        semantic: "far focal point F′",
        position: "center",
      },
      label_f_left: { role: "label", semantic: "F label", position: "center" },
      label_f_right: {
        role: "label",
        semantic: "F′ label",
        position: "center",
      },
      object: {
        role: "object",
        semantic: "the upright object",
        position: "left",
      },
      image: {
        role: "image",
        semantic: "the real, inverted image",
        position: "right",
      },
      ray_parallel_in: {
        role: "ray",
        semantic: "ray parallel to the axis",
        position: "top",
      },
      ray_parallel_out: {
        role: "ray",
        semantic: "ray refracted through F′",
        position: "right",
      },
      ray_chief: {
        role: "ray",
        semantic: "chief ray through the lens centre",
        position: "center",
      },
      label_object: {
        role: "label",
        semantic: "object label",
        position: "left",
      },
      label_image: {
        role: "label",
        semantic: "image label",
        position: "right",
      },
    },
  };
}

export const lensRayDiagram: DiagramTemplate = {
  conceptId: "lens-ray-diagram",
  title: "Converging lens — ray diagram",
  subject: "physics",
  build,
};
