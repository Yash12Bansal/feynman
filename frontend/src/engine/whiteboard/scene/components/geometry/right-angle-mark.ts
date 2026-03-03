/**
 * Right angle mark component — small square at a vertex.
 *
 * Open path (no Z) — two segments forming a square corner: M P1 L P3 L P2.
 * Pure function: given vertex + two ray points → SceneGeometry.
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { GEOMETRY_ANNOTATION } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { unitVector } from "./utils";

export interface RightAngleMarkParams {
  /** Vertex */
  x1: number;
  y1: number;
  /** Point on ray 1 */
  x2: number;
  y2: number;
  /** Point on ray 2 */
  x3: number;
  y3: number;
  /** Mark size (default 12) */
  size?: number;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function rightAngleMark(params: RightAngleMarkParams): SceneGeometry {
  const { x1, y1, x2, y2, x3, y3, size = 12, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];

  const uv1 = unitVector(x1, y1, x2, y2);
  const uv2 = unitVector(x1, y1, x3, y3);

  if (!uv1 || !uv2) {
    return {
      paths: [],
      labels: [],
      bounds: { x: x1, y: y1, width: 0, height: 0 },
      anchors: { vertex: { x: x1, y: y1 } },
    };
  }

  // P1: size along ray1 from vertex
  const p1x = x1 + uv1.ux * size;
  const p1y = y1 + uv1.uy * size;

  // P2: size along ray2 from vertex
  const p2x = x1 + uv2.ux * size;
  const p2y = y1 + uv2.uy * size;

  // P3: corner of the square (offset from vertex along both rays)
  const p3x = x1 + uv1.ux * size + uv2.ux * size;
  const p3y = y1 + uv1.uy * size + uv2.uy * size;

  // Open path: M P1 L P3 L P2 (no Z — not closed)
  const d = `M ${p1x} ${p1y} L ${p3x} ${p3y} L ${p2x} ${p2y}`;

  paths.push({
    id: `${id}-mark`,
    d,
    roughOptions: { ...GEOMETRY_ANNOTATION, stroke: strokeColor },
  });

  const allX = [p1x, p2x, p3x, x1];
  const allY = [p1y, p2y, p3y, y1];
  const minX = Math.min(...allX);
  const minY = Math.min(...allY);
  const maxX = Math.max(...allX);
  const maxY = Math.max(...allY);

  return {
    paths,
    labels: [],
    bounds: {
      x: minX,
      y: minY,
      width: maxX - minX || 1,
      height: maxY - minY || 1,
    },
    anchors: { vertex: { x: x1, y: y1 } },
  };
}

export const rightAngleMarkDef: ComponentDef<RightAngleMarkParams> = {
  kind: "right-angle-mark",
  render: rightAngleMark,
  anchorNames: ["vertex"],
  defaultStyle: GEOMETRY_ANNOTATION,
};

registerComponent(rightAngleMarkDef);
