/**
 * Point component — filled dot with optional label.
 *
 * Pure function: given a position → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { GEOMETRY_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface PointParams {
  x1: number;
  y1: number;
  /** Dot radius (default 5) */
  radius?: number;
  /** Optional label */
  label?: string;
  /** Stroke/fill color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function point(params: PointParams): SceneGeometry {
  const { x1, y1, radius = 5, label, color, id } = params;
  const fillColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Two-arc circle (full circle = two semicircular arcs)
  const d =
    `M ${x1 - radius} ${y1} ` +
    `A ${radius} ${radius} 0 1 1 ${x1 + radius} ${y1} ` +
    `A ${radius} ${radius} 0 1 1 ${x1 - radius} ${y1} Z`;

  paths.push({
    id: `${id}-dot`,
    d,
    roughOptions: {
      ...GEOMETRY_STROKE,
      stroke: fillColor,
      fill: fillColor,
      fillStyle: "solid",
    },
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: x1,
      y: y1 - radius - 8,
      anchor: "middle",
      fontSize: 14,
      color: fillColor,
    });
  }

  return {
    paths,
    labels,
    bounds: {
      x: x1 - radius,
      y: y1 - radius,
      width: radius * 2,
      height: radius * 2,
    },
    anchors: { center: { x: x1, y: y1 } },
  };
}

export const pointDef: ComponentDef<PointParams> = {
  kind: "point",
  render: point,
  anchorNames: ["center"],
  defaultStyle: GEOMETRY_STROKE,
};

registerComponent(pointDef);
