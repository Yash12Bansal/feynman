/**
 * Parallel mark component — chevron arrow(s) at segment midpoint.
 *
 * 2 paths per chevron (two short lines forming a V). count controls
 * how many chevrons to draw (1 = single, 2 = double parallel mark).
 * Pure function: given two endpoints + count → SceneGeometry.
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { GEOMETRY_ANNOTATION } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { midpoint, unitVector } from "./utils";

export interface ParallelMarkParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Number of chevrons (default 1) */
  count?: number;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function parallelMark(params: ParallelMarkParams): SceneGeometry {
  const { x1, y1, x2, y2, count = 1, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];

  const uv = unitVector(x1, y1, x2, y2);
  if (!uv) {
    return {
      paths: [],
      labels: [],
      bounds: { x: x1, y: y1, width: 0, height: 0 },
      anchors: {
        mid: { x: x1, y: y1 },
        start: { x: x1, y: y1 },
        end: { x: x2, y: y2 },
      },
    };
  }

  const mid = midpoint(x1, y1, x2, y2);
  // Perpendicular direction
  const px = -uv.uy;
  const py = uv.ux;

  const chevronLen = 6; // half-length of each chevron arm
  const spacing = 5; // space between multiple chevrons
  const effectiveCount = Math.max(1, Math.round(Number(count)));

  // Center the group of chevrons at the midpoint
  const totalSpan = (effectiveCount - 1) * spacing;
  const startOffset = -totalSpan / 2;

  for (let i = 0; i < effectiveCount; i++) {
    const offset = startOffset + i * spacing;
    // Center of this chevron along the segment
    const cx = mid.x + uv.ux * offset;
    const cy = mid.y + uv.uy * offset;

    // Tip of chevron (points in direction of segment)
    const tipX = cx + uv.ux * chevronLen;
    const tipY = cy + uv.uy * chevronLen;

    // Two arms: go back along segment and out perpendicular
    const arm1X = cx - uv.ux * chevronLen + px * chevronLen;
    const arm1Y = cy - uv.uy * chevronLen + py * chevronLen;
    const arm2X = cx - uv.ux * chevronLen - px * chevronLen;
    const arm2Y = cy - uv.uy * chevronLen - py * chevronLen;

    paths.push({
      id: `${id}-chev${i}-a`,
      d: `M ${arm1X} ${arm1Y} L ${tipX} ${tipY}`,
      roughOptions: { ...GEOMETRY_ANNOTATION, stroke: strokeColor },
    });
    paths.push({
      id: `${id}-chev${i}-b`,
      d: `M ${arm2X} ${arm2Y} L ${tipX} ${tipY}`,
      roughOptions: { ...GEOMETRY_ANNOTATION, stroke: strokeColor },
    });
  }

  const allX = [x1, x2];
  const allY = [y1, y2];
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
    anchors: {
      mid: { x: mid.x, y: mid.y },
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
    },
  };
}

export const parallelMarkDef: ComponentDef<ParallelMarkParams> = {
  kind: "parallel-mark",
  render: parallelMark,
  anchorNames: ["mid", "start", "end"],
  defaultStyle: GEOMETRY_ANNOTATION,
};

registerComponent(parallelMarkDef);
