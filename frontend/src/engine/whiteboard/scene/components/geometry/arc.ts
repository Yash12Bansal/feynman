/**
 * Arc component — partial circle (e.g. for semicircles, arcs in constructions).
 *
 * Pure function: given center, radius, start/end angles → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { GEOMETRY_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface ArcParams {
  /** Center x */
  x1: number;
  /** Center y */
  y1: number;
  /** Radius (default 50) */
  radius?: number;
  /** Start angle in degrees (default 0) */
  startAngle?: number;
  /** End angle in degrees (default 180) */
  endAngle?: number;
  /** Optional label */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function arc(params: ArcParams): SceneGeometry {
  const {
    x1,
    y1,
    radius = 50,
    startAngle = 0,
    endAngle = 180,
    label,
    color,
    id,
  } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const startRad = (startAngle * Math.PI) / 180;
  const endRad = (endAngle * Math.PI) / 180;

  const arcStartX = x1 + radius * Math.cos(startRad);
  const arcStartY = y1 + radius * Math.sin(startRad);
  const arcEndX = x1 + radius * Math.cos(endRad);
  const arcEndY = y1 + radius * Math.sin(endRad);

  // Determine if the arc spans more than 180°
  let angleDiff = endAngle - startAngle;
  // Normalize to positive
  while (angleDiff < 0) angleDiff += 360;
  while (angleDiff >= 360) angleDiff -= 360;
  const largeArc = angleDiff > 180 ? 1 : 0;
  const sweep = 1;

  const d =
    `M ${arcStartX} ${arcStartY} ` +
    `A ${radius} ${radius} 0 ${largeArc} ${sweep} ${arcEndX} ${arcEndY}`;

  paths.push({
    id: `${id}-arc`,
    d,
    roughOptions: { ...GEOMETRY_STROKE, stroke: strokeColor },
  });

  if (label) {
    const midAngleRad = (startRad + endRad) / 2;
    const labelDist = radius + 14;
    labels.push({
      id: `${id}-label`,
      text: label,
      x: x1 + labelDist * Math.cos(midAngleRad),
      y: y1 + labelDist * Math.sin(midAngleRad),
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
      arcStart: { x: arcStartX, y: arcStartY },
      arcEnd: { x: arcEndX, y: arcEndY },
    },
  };
}

export const arcDef: ComponentDef<ArcParams> = {
  kind: "arc",
  render: arc,
  anchorNames: ["center", "arcStart", "arcEnd"],
  defaultStyle: GEOMETRY_STROKE,
};

registerComponent(arcDef);
