/**
 * Junction component — filled dot at a point.
 *
 * Pure function: given a center point → SceneGeometry.
 * Used at T-intersections and parallel branches (Phase 8).
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface JunctionParams {
  /** Center x (or x1 for endpoint-pair compatibility) */
  x1: number;
  /** Center y (or y1 for endpoint-pair compatibility) */
  y1: number;
  /** Ignored (junctions are single-point) */
  x2?: number;
  /** Ignored (junctions are single-point) */
  y2?: number;
  /** Dot radius (default 4) */
  radius?: number;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function junction(params: JunctionParams): SceneGeometry {
  const { x1: cx, y1: cy, radius = 4, color, id } = params;

  const strokeColor = color ?? COLORS.textPrimary;

  const paths: ScenePath[] = [
    {
      id: `${id}-dot`,
      d: `M ${cx - radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx + radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx - radius} ${cy} Z`,
      roughOptions: {
        ...CIRCUIT_SYMBOL,
        stroke: strokeColor,
        fill: strokeColor,
        fillStyle: "solid",
        roughness: 0.3,
      },
    },
  ];

  return {
    paths,
    labels: [],
    bounds: {
      x: cx - radius,
      y: cy - radius,
      width: radius * 2,
      height: radius * 2,
    },
    anchors: {
      center: { x: cx, y: cy },
    },
  };
}

export const junctionDef: ComponentDef<JunctionParams> = {
  kind: "junction",
  render: junction,
  anchorNames: ["center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(junctionDef);
