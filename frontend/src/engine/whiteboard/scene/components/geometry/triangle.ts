/**
 * Triangle component — closed three-vertex polygon.
 *
 * Pure function: given three vertices → SceneGeometry.
 * Degenerate guard: collinear points (area ≈ 0) produce empty geometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { GEOMETRY_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { midpoint } from "./utils";

export interface TriangleParams {
  /** Vertex A */
  x1: number;
  y1: number;
  /** Vertex B */
  x2: number;
  y2: number;
  /** Vertex C */
  x3: number;
  y3: number;
  /** Optional label */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function triangle(params: TriangleParams): SceneGeometry {
  const { x1, y1, x2, y2, x3, y3, label, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Degenerate guard: signed area ≈ 0 means collinear
  const area = Math.abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2;
  if (area < 0.5) {
    return {
      paths: [],
      labels: [],
      bounds: { x: x1, y: y1, width: 0, height: 0 },
      anchors: {
        A: { x: x1, y: y1 },
        B: { x: x2, y: y2 },
        C: { x: x3, y: y3 },
        centroid: { x: (x1 + x2 + x3) / 3, y: (y1 + y2 + y3) / 3 },
        AB_mid: midpoint(x1, y1, x2, y2),
        BC_mid: midpoint(x2, y2, x3, y3),
        CA_mid: midpoint(x3, y3, x1, y1),
      },
    };
  }

  const d = `M ${x1} ${y1} L ${x2} ${y2} L ${x3} ${y3} Z`;

  paths.push({
    id: `${id}-triangle`,
    d,
    roughOptions: { ...GEOMETRY_STROKE, stroke: strokeColor },
  });

  const centroid = {
    x: (x1 + x2 + x3) / 3,
    y: (y1 + y2 + y3) / 3,
  };

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: centroid.x,
      y: centroid.y,
      anchor: "middle",
      fontSize: 14,
      color: strokeColor,
    });
  }

  const xs = [x1, x2, x3];
  const ys = [y1, y2, y3];
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);

  return {
    paths,
    labels,
    bounds: {
      x: minX,
      y: minY,
      width: maxX - minX || 1,
      height: maxY - minY || 1,
    },
    anchors: {
      A: { x: x1, y: y1 },
      B: { x: x2, y: y2 },
      C: { x: x3, y: y3 },
      centroid,
      AB_mid: midpoint(x1, y1, x2, y2),
      BC_mid: midpoint(x2, y2, x3, y3),
      CA_mid: midpoint(x3, y3, x1, y1),
    },
  };
}

export const triangleDef: ComponentDef<TriangleParams> = {
  kind: "triangle",
  render: triangle,
  anchorNames: ["A", "B", "C", "centroid", "AB_mid", "BC_mid", "CA_mid"],
  defaultStyle: GEOMETRY_STROKE,
};

registerComponent(triangleDef);
