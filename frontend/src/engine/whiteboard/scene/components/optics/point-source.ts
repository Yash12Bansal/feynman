/**
 * Point source component — a filled circle representing a light emitter.
 *
 * Pure function: given center + radius → SceneGeometry.
 * Two semicircular arcs form the circle (same pattern as double-slit template).
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { LIGHT_RAY_DEFAULTS } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface PointSourceParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Circle radius (default 6) */
  radius?: number;
  /** Optional text label */
  label?: string;
  /** Fill/stroke color (default accentBlue) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function pointSource(params: PointSourceParams): SceneGeometry {
  const { cx, cy, radius = 6, label, color, id } = params;
  const strokeColor = color ?? COLORS.accentBlue;

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Full circle via two semicircular arcs
  paths.push({
    id: `${id}-circle`,
    d: [
      `M ${cx - radius} ${cy}`,
      `A ${radius} ${radius} 0 1 1 ${cx + radius} ${cy}`,
      `A ${radius} ${radius} 0 1 1 ${cx - radius} ${cy}`,
      "Z",
    ].join(" "),
    roughOptions: {
      ...LIGHT_RAY_DEFAULTS,
      stroke: strokeColor,
      fill: strokeColor,
      fillStyle: "solid",
      roughness: 0.3,
    },
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx,
      y: cy - radius - 12,
      anchor: "middle",
      fontSize: 13,
      color: COLORS.textSecondary,
    });
  }

  return {
    paths,
    labels,
    bounds: {
      x: cx - radius,
      y: cy - radius,
      width: radius * 2,
      height: radius * 2,
    },
    anchors: {
      center: { x: cx, y: cy },
      right: { x: cx + radius, y: cy },
      left: { x: cx - radius, y: cy },
      top: { x: cx, y: cy - radius },
      bottom: { x: cx, y: cy + radius },
    },
  };
}

export const pointSourceDef: ComponentDef<PointSourceParams> = {
  kind: "point-source",
  render: pointSource,
  anchorNames: ["center", "right", "left", "top", "bottom"],
  defaultStyle: LIGHT_RAY_DEFAULTS,
};

registerComponent(pointSourceDef);
