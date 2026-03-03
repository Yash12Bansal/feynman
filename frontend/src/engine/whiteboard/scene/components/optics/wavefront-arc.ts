/**
 * Wavefront arc component — a semicircular arc representing a wavefront.
 *
 * Pure function: given center, radius, angle range → SceneGeometry.
 * Uses SVG arc command for the curved wavefront.
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { WAVEFRONT_DEFAULTS } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface WavefrontArcParams {
  /** Arc center x */
  cx: number;
  /** Arc center y */
  cy: number;
  /** Arc radius */
  radius: number;
  /** Start angle in degrees (default -90, i.e. top) */
  startAngle?: number;
  /** End angle in degrees (default 90, i.e. bottom) */
  endAngle?: number;
  /** Stroke color (default accentBlue+99 for transparency) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function wavefrontArc(params: WavefrontArcParams): SceneGeometry {
  const { cx, cy, radius, startAngle = -90, endAngle = 90, color, id } = params;

  const strokeColor = color ?? `${COLORS.accentBlue}99`;

  const startRad = (startAngle * Math.PI) / 180;
  const endRad = (endAngle * Math.PI) / 180;

  const x1 = cx + radius * Math.cos(startRad);
  const y1 = cy + radius * Math.sin(startRad);
  const x2 = cx + radius * Math.cos(endRad);
  const y2 = cy + radius * Math.sin(endRad);

  // Determine if the arc spans more than 180 degrees
  const angleDiff = (endAngle - startAngle + 360) % 360 || 360;
  const largeArc = angleDiff > 180 ? 1 : 0;

  const paths: ScenePath[] = [
    {
      id: `${id}-arc`,
      d: `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`,
      roughOptions: {
        ...WAVEFRONT_DEFAULTS,
        stroke: strokeColor,
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
      arcTop: { x: x1, y: y1 },
      arcBottom: { x: x2, y: y2 },
    },
  };
}

export const wavefrontArcDef: ComponentDef<WavefrontArcParams> = {
  kind: "wavefront-arc",
  render: wavefrontArc,
  anchorNames: ["center", "arcTop", "arcBottom"],
  defaultStyle: WAVEFRONT_DEFAULTS,
};

registerComponent(wavefrontArcDef);
