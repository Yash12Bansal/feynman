/**
 * Tubing component — quadratic bezier curve between two endpoints.
 *
 * Used to connect apparatus components (like a rubber tube from flask to beaker).
 * Two-endpoint pattern (like wire/spring).
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { CHEM_GLASSWARE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface TubingParams {
  /** Start x */
  x1: number;
  /** Start y */
  y1: number;
  /** End x */
  x2: number;
  /** End y */
  y2: number;
  /** Sag/droop amount in pixels (default 30, positive = downward) */
  sag?: number;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const DEFAULT_SAG = 30;

export function tubing(params: TubingParams): SceneGeometry {
  const { x1, y1, x2, y2, sag = DEFAULT_SAG, color, id } = params;
  const strokeColor = color ?? COLORS.textSecondary;

  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);

  if (len === 0) {
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

  // Midpoint + perpendicular offset for sag
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  // Perpendicular direction (pointing "down" relative to the line)
  const px = -dy / len;
  const py = dx / len;

  // Control point for quadratic bezier
  const cpX = midX + px * sag;
  const cpY = midY + py * sag;

  const paths: ScenePath[] = [
    {
      id: `${id}-tube`,
      d: `M ${x1} ${y1} Q ${cpX} ${cpY} ${x2} ${y2}`,
      roughOptions: {
        ...CHEM_GLASSWARE,
        stroke: strokeColor,
        strokeWidth: 3,
        roughness: 0.6,
      },
    },
  ];

  const allX = [x1, x2, cpX];
  const allY = [y1, y2, cpY];
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
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
      mid: { x: cpX, y: cpY },
    },
  };
}

export const tubingDef: ComponentDef<TubingParams> = {
  kind: "tubing",
  render: tubing,
  anchorNames: ["start", "end", "mid"],
  defaultStyle: CHEM_GLASSWARE,
};

registerComponent(tubingDef);
