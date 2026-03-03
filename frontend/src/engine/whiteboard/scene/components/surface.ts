/**
 * Surface component — a horizontal line with diagonal hatch marks below.
 *
 * Pure function: given endpoints + hatch params → SceneGeometry.
 * Matches the manual surface style in free-body.ts (APPARATUS_STROKE + textSecondary).
 */

import type { SceneGeometry, ScenePath } from "../scene-types";
import { APPARATUS_STROKE } from "../scene-rough-helpers";
import { COLORS } from "../../../theme";
import type { ComponentDef } from "./types";
import { registerComponent } from "./registry";

export interface SurfaceParams {
  /** Left endpoint x */
  x1: number;
  /** Surface y position */
  y: number;
  /** Right endpoint x */
  x2: number;
  /** Show hatch marks below surface (default true) */
  showHatch?: boolean;
  /** Spacing between hatch marks in px (default 20) */
  hatchSpacing?: number;
  /** Length of hatch marks in px (default 12) */
  hatchLength?: number;
  /** Stroke color (default textSecondary) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const DEFAULT_HATCH_SPACING = 20;
const DEFAULT_HATCH_LENGTH = 12;

export function surface(params: SurfaceParams): SceneGeometry {
  const {
    x1,
    y,
    x2,
    showHatch = true,
    hatchSpacing = DEFAULT_HATCH_SPACING,
    hatchLength = DEFAULT_HATCH_LENGTH,
    color,
    id,
  } = params;

  const strokeColor = color ?? COLORS.textSecondary;
  const left = Math.min(x1, x2);
  const right = Math.max(x1, x2);

  const paths: ScenePath[] = [];

  // Main surface line
  paths.push({
    id: `${id}-line`,
    d: `M ${left} ${y} L ${right} ${y}`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
      strokeWidth: 1.5,
    },
  });

  // Hatch marks: diagonal lines below the surface
  if (showHatch && hatchSpacing > 0) {
    // Start offset from left edge so hatches aren't right at the boundary
    const startX = left + hatchSpacing;
    for (let hx = startX; hx < right; hx += hatchSpacing) {
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

  const midX = (left + right) / 2;
  const boundsBottom = showHatch ? y + hatchLength : y;

  return {
    paths,
    labels: [],
    bounds: {
      x: left,
      y,
      width: right - left,
      height: boundsBottom - y || 1,
    },
    anchors: {
      left: { x: left, y },
      right: { x: right, y },
      center: { x: midX, y },
    },
  };
}

/** Registry definition for the surface component. */
export const surfaceDef: ComponentDef<SurfaceParams> = {
  kind: "surface",
  render: surface,
  anchorNames: ["left", "right", "center"],
  defaultStyle: APPARATUS_STROKE,
};

registerComponent(surfaceDef);
