/**
 * Circle shape component — circle with optional fill.
 *
 * Pure function: given center and radius → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { GEOMETRY_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface CircleShapeParams {
  /** Center x */
  x1: number;
  /** Center y */
  y1: number;
  /** Radius (default 60) */
  radius?: number;
  /** Hachure fill */
  filled?: boolean;
  /** Optional label */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function circleShape(params: CircleShapeParams): SceneGeometry {
  const { x1, y1, radius = 60, filled, label, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Two-arc circle
  const d =
    `M ${x1 - radius} ${y1} ` +
    `A ${radius} ${radius} 0 1 1 ${x1 + radius} ${y1} ` +
    `A ${radius} ${radius} 0 1 1 ${x1 - radius} ${y1} Z`;

  paths.push({
    id: `${id}-circle`,
    d,
    roughOptions: {
      ...GEOMETRY_STROKE,
      stroke: strokeColor,
      ...(filled
        ? {
            fill: strokeColor,
            fillStyle: "hachure",
            fillWeight: 1,
            hachureGap: 6,
          }
        : { fill: "none" }),
    },
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: x1,
      y: y1 - radius - 10,
      anchor: "middle",
      fontSize: 14,
      color: strokeColor,
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
    anchors: {
      center: { x: x1, y: y1 },
      top: { x: x1, y: y1 - radius },
      bottom: { x: x1, y: y1 + radius },
      left: { x: x1 - radius, y: y1 },
      right: { x: x1 + radius, y: y1 },
    },
  };
}

export const circleShapeDef: ComponentDef<CircleShapeParams> = {
  kind: "circle-shape",
  render: circleShape,
  anchorNames: ["center", "top", "bottom", "left", "right"],
  defaultStyle: GEOMETRY_STROKE,
};

registerComponent(circleShapeDef);
