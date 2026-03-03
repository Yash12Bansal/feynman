/**
 * Inclined plane component — a right triangle with optional angle arc and hatch marks.
 *
 * Pure function: given position + angle + dimensions → SceneGeometry.
 * The triangle sits with its base on the bottom, hypotenuse as the slope.
 * Height = baseWidth * tan(angle).
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../scene-types";
import { APPARATUS_STROKE } from "../scene-rough-helpers";
import { COLORS } from "../../../theme";
import type { ComponentDef } from "./types";
import { registerComponent } from "./registry";

export interface InclinedPlaneParams {
  /** Left corner x of the base */
  x: number;
  /** Bottom y (base sits on this line) */
  y: number;
  /** Base width (default 200) */
  baseWidth?: number;
  /** Incline angle in degrees (default 30) */
  angle?: number;
  /** Show angle arc at bottom-left corner (default true) */
  showAngle?: boolean;
  /** Label for the angle (e.g. "θ", "30°") */
  angleLabel?: string;
  /** Show hatch marks below the base (default false) */
  showHatch?: boolean;
  /** Stroke color (default textSecondary) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const DEFAULT_BASE_WIDTH = 200;
const DEFAULT_ANGLE = 30;
const ANGLE_ARC_RADIUS = 30;

export function inclinedPlane(params: InclinedPlaneParams): SceneGeometry {
  const {
    x,
    y,
    baseWidth = DEFAULT_BASE_WIDTH,
    angle = DEFAULT_ANGLE,
    showAngle = true,
    angleLabel,
    showHatch = false,
    color,
    id,
  } = params;

  const strokeColor = color ?? COLORS.textSecondary;
  const rad = (angle * Math.PI) / 180;
  const height = baseWidth * Math.tan(rad);

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Three vertices of the right triangle
  // baseLeft = bottom-left corner (right angle at bottom-right)
  const baseLeft = { x, y };
  const baseRight = { x: x + baseWidth, y };
  const peak = { x: x + baseWidth, y: y - height };

  // Triangle outline (closed path)
  paths.push({
    id: `${id}-outline`,
    d: `M ${baseLeft.x} ${baseLeft.y} L ${baseRight.x} ${baseRight.y} L ${peak.x} ${peak.y} Z`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
    },
  });

  // Angle arc at bottom-left corner
  if (showAngle) {
    // Arc from base to slope at bottom-left
    const arcR = Math.min(ANGLE_ARC_RADIUS, baseWidth * 0.3);
    const arcEndX = x + arcR * Math.cos(-rad);
    const arcEndY = y + arcR * Math.sin(-rad);

    // SVG arc: from (x + arcR, y) curving up to (arcEndX, arcEndY)
    // Large arc = 0, sweep = 0 (counter-clockwise in SVG's y-down system)
    paths.push({
      id: `${id}-angle-arc`,
      d: `M ${x + arcR} ${y} A ${arcR} ${arcR} 0 0 0 ${arcEndX} ${arcEndY}`,
      roughOptions: {
        ...APPARATUS_STROKE,
        stroke: strokeColor,
        strokeWidth: 1.5,
        roughness: 0.5,
      },
      layer: "clean",
    });

    if (angleLabel) {
      // Position label just outside the arc
      const labelR = arcR + 14;
      const labelAngle = rad / 2; // halfway between base and slope
      labels.push({
        id: `${id}-angle-label`,
        text: angleLabel,
        x: x + labelR * Math.cos(-labelAngle),
        y: y + labelR * Math.sin(-labelAngle),
        anchor: "middle",
        fontSize: 14,
        color: strokeColor,
      });
    }
  }

  // Hatch marks below the base
  if (showHatch) {
    const hatchSpacing = 20;
    const hatchLength = 12;
    const startX = x + hatchSpacing;
    for (let hx = startX; hx < x + baseWidth; hx += hatchSpacing) {
      paths.push({
        id: `${id}-hatch-${Math.round(hx)}`,
        d: `M ${hx} ${y} L ${hx - 8} ${y + hatchLength}`,
        roughOptions: {
          ...APPARATUS_STROKE,
          stroke: strokeColor,
          strokeWidth: 1,
          roughness: 0.5,
        },
      });
    }
  }

  // Slope midpoint
  const slopeCenter = {
    x: (baseLeft.x + peak.x) / 2,
    y: (baseLeft.y + peak.y) / 2,
  };

  const baseCenter = {
    x: (baseLeft.x + baseRight.x) / 2,
    y,
  };

  const hatchExtent = showHatch ? 12 : 0;

  return {
    paths,
    labels,
    bounds: {
      x,
      y: y - height,
      width: baseWidth,
      height: height + hatchExtent,
    },
    anchors: {
      baseLeft: { x: baseLeft.x, y: baseLeft.y },
      baseRight: { x: baseRight.x, y: baseRight.y },
      peak: { x: peak.x, y: peak.y },
      slopeCenter,
      baseCenter,
    },
  };
}

/** Registry definition for the inclined plane component. */
export const inclinedPlaneDef: ComponentDef<InclinedPlaneParams> = {
  kind: "inclined-plane",
  render: inclinedPlane,
  anchorNames: ["baseLeft", "baseRight", "peak", "slopeCenter", "baseCenter"],
  defaultStyle: APPARATUS_STROKE,
};

registerComponent(inclinedPlaneDef);
