/**
 * Line segment component — straight line between two points.
 *
 * Pure function: given two endpoints → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { GEOMETRY_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { midpoint, unitVector } from "./utils";

export interface LineSegmentParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Dashed line */
  dashed?: boolean;
  /** Optional label at midpoint */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function lineSegment(params: LineSegmentParams): SceneGeometry {
  const { x1, y1, x2, y2, dashed, label, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const uv = unitVector(x1, y1, x2, y2);
  if (!uv) {
    return {
      paths: [],
      labels: [],
      bounds: { x: x1, y: y1, width: 0, height: 0 },
      anchors: {
        start: { x: x1, y: y1 },
        end: { x: x2, y: y2 },
        mid: { x: x1, y: y1 },
      },
    };
  }

  const d = `M ${x1} ${y1} L ${x2} ${y2}`;

  paths.push({
    id: `${id}-line`,
    d,
    roughOptions: {
      ...GEOMETRY_STROKE,
      stroke: strokeColor,
      ...(dashed ? { strokeLineDash: [6, 4] } : {}),
    },
  });

  if (label) {
    const mid = midpoint(x1, y1, x2, y2);
    // Perpendicular offset for label placement
    const px = -uv.uy;
    const py = uv.ux;
    const offset = 14;
    labels.push({
      id: `${id}-label`,
      text: label,
      x: mid.x + px * offset,
      y: mid.y + py * offset,
      anchor: "middle",
      fontSize: 14,
      color: strokeColor,
    });
  }

  const mid = midpoint(x1, y1, x2, y2);
  const minX = Math.min(x1, x2);
  const minY = Math.min(y1, y2);
  const maxX = Math.max(x1, x2);
  const maxY = Math.max(y1, y2);

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
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
      mid: { x: mid.x, y: mid.y },
    },
  };
}

export const lineSegmentDef: ComponentDef<LineSegmentParams> = {
  kind: "line-segment",
  render: lineSegment,
  anchorNames: ["start", "end", "mid"],
  defaultStyle: GEOMETRY_STROKE,
};

registerComponent(lineSegmentDef);
