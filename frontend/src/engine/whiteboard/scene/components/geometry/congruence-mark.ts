/**
 * Congruence mark component — tick(s) perpendicular to segment at midpoint.
 *
 * 1 path per tick. count controls how many ticks (1 = single, 2 = double, etc.).
 * Pure function: given two endpoints + count → SceneGeometry.
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { GEOMETRY_ANNOTATION } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { midpoint, unitVector } from "./utils";

export interface CongruenceMarkParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Number of ticks (default 1) */
  count?: number;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function congruenceMark(params: CongruenceMarkParams): SceneGeometry {
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

  const tickHalf = 6; // half-length of each tick
  const spacing = 4; // space between multiple ticks along the segment
  const effectiveCount = Math.max(1, Math.round(Number(count)));

  // Center the group of ticks at the midpoint
  const totalSpan = (effectiveCount - 1) * spacing;
  const startOffset = -totalSpan / 2;

  for (let i = 0; i < effectiveCount; i++) {
    const offset = startOffset + i * spacing;
    // Center of this tick along the segment
    const cx = mid.x + uv.ux * offset;
    const cy = mid.y + uv.uy * offset;

    // Tick endpoints: perpendicular to segment
    const t1x = cx + px * tickHalf;
    const t1y = cy + py * tickHalf;
    const t2x = cx - px * tickHalf;
    const t2y = cy - py * tickHalf;

    paths.push({
      id: `${id}-tick${i}`,
      d: `M ${t1x} ${t1y} L ${t2x} ${t2y}`,
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

export const congruenceMarkDef: ComponentDef<CongruenceMarkParams> = {
  kind: "congruence-mark",
  render: congruenceMark,
  anchorNames: ["mid", "start", "end"],
  defaultStyle: GEOMETRY_ANNOTATION,
};

registerComponent(congruenceMarkDef);
