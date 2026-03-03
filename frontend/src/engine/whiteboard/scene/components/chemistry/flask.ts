/**
 * Flask component — conical (Erlenmeyer) or round-bottom flask with narrow neck.
 *
 * Pure function: given center + dimensions → SceneGeometry.
 * extras.variant: "erlenmeyer" (default) or "round_bottom"
 * extras.side_arm: boolean — adds a side arm tube for distillation
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CHEM_GLASSWARE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface FlaskParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Total height (default 90) */
  height?: number;
  /** Body width (default 70) */
  width?: number;
  /** "erlenmeyer" or "round_bottom" */
  variant?: string;
  /** Add a side arm tube */
  side_arm?: boolean;
  /** Liquid fill level 0-1 */
  fill_level?: number;
  /** Liquid fill color */
  fill_color?: string;
  /** Optional label */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const DEFAULT_HEIGHT = 90;
const DEFAULT_WIDTH = 70;
const NECK_WIDTH_RATIO = 0.22;
const NECK_HEIGHT_RATIO = 0.3;

export function flask(params: FlaskParams): SceneGeometry {
  const {
    cx,
    cy,
    height = DEFAULT_HEIGHT,
    width = DEFAULT_WIDTH,
    variant = "erlenmeyer",
    side_arm = false,
    fill_level = 0,
    fill_color,
    label,
    color,
    id,
  } = params;

  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const top = cy - height / 2;
  const bottom = cy + height / 2;
  const neckH = height * NECK_HEIGHT_RATIO;
  const neckW = width * NECK_WIDTH_RATIO;
  const bodyTop = top + neckH;
  const neckTop = top;

  if (variant === "round_bottom") {
    // Round bottom flask: sphere body + narrow neck
    const bodyRadius = width / 2;
    const bodyCenterY = bottom - bodyRadius;

    // Neck: narrow tube from sphere top to flask top
    paths.push({
      id: `${id}-neck`,
      d:
        `M ${cx - neckW / 2} ${neckTop} L ${cx - neckW / 2} ${bodyCenterY - bodyRadius * 0.6} ` +
        `M ${cx + neckW / 2} ${neckTop} L ${cx + neckW / 2} ${bodyCenterY - bodyRadius * 0.6}`,
      roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
    });

    // Sphere body
    paths.push({
      id: `${id}-body`,
      d:
        `M ${cx - neckW / 2} ${bodyCenterY - bodyRadius * 0.6} ` +
        `Q ${cx - bodyRadius} ${bodyCenterY - bodyRadius * 0.3} ${cx - bodyRadius} ${bodyCenterY} ` +
        `A ${bodyRadius} ${bodyRadius} 0 0 0 ${cx + bodyRadius} ${bodyCenterY} ` +
        `Q ${cx + bodyRadius} ${bodyCenterY - bodyRadius * 0.3} ${cx + neckW / 2} ${bodyCenterY - bodyRadius * 0.6}`,
      roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
    });
  } else {
    // Erlenmeyer: triangular body + narrow neck
    // Neck walls
    paths.push({
      id: `${id}-neck`,
      d:
        `M ${cx - neckW / 2} ${neckTop} L ${cx - neckW / 2} ${bodyTop} ` +
        `M ${cx + neckW / 2} ${neckTop} L ${cx + neckW / 2} ${bodyTop}`,
      roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
    });

    // Conical body: neck base → wide bottom
    paths.push({
      id: `${id}-body`,
      d:
        `M ${cx - neckW / 2} ${bodyTop} L ${cx - width / 2} ${bottom} ` +
        `L ${cx + width / 2} ${bottom} L ${cx + neckW / 2} ${bodyTop}`,
      roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
    });
  }

  // Liquid fill
  if (fill_level > 0) {
    const clampedFill = Math.min(1, Math.max(0, fill_level));
    const fillableH = bottom - bodyTop;
    const liquidTop = bottom - fillableH * clampedFill;
    const liqColor = fill_color ?? COLORS.accentBlue;

    if (variant === "round_bottom") {
      // Simplified fill for round bottom
      const bodyRadius = width / 2;
      const bodyCenterY = bottom - bodyRadius;
      const fillY = Math.max(liquidTop, bodyCenterY - bodyRadius);
      paths.push({
        id: `${id}-liquid`,
        d:
          `M ${cx - bodyRadius * 0.8} ${fillY} ` +
          `A ${bodyRadius} ${bodyRadius} 0 0 0 ${cx + bodyRadius * 0.8} ${fillY} Z`,
        roughOptions: {
          stroke: "none",
          fill: `${liqColor}44`,
          fillStyle: "solid",
          strokeWidth: 0,
        },
      });
    } else {
      // Erlenmeyer fill — width interpolated
      const t = (liquidTop - bodyTop) / fillableH;
      const liquidW = neckW + (width - neckW) * (1 - t);
      paths.push({
        id: `${id}-liquid`,
        d:
          `M ${cx - liquidW / 2} ${liquidTop} ` +
          `L ${cx - width / 2} ${bottom} L ${cx + width / 2} ${bottom} ` +
          `L ${cx + liquidW / 2} ${liquidTop} Z`,
        roughOptions: {
          stroke: "none",
          fill: `${liqColor}44`,
          fillStyle: "solid",
          strokeWidth: 0,
        },
      });
    }
  }

  // Side arm for distillation
  const outletX = cx + width / 2 + 20;
  const outletY = bodyTop + (bottom - bodyTop) * 0.2;

  if (side_arm) {
    const armStartX = cx + neckW / 2;
    const armStartY = bodyTop - neckH * 0.3;
    paths.push({
      id: `${id}-arm`,
      d: `M ${armStartX} ${armStartY} L ${outletX} ${outletY}`,
      roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
    });
  }

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx,
      y: bottom + 16,
      anchor: "middle",
      fontSize: 13,
      color: strokeColor,
    });
  }

  return {
    paths,
    labels,
    bounds: {
      x: cx - width / 2 - (side_arm ? 20 : 0),
      y: top,
      width: width + (side_arm ? 40 : 0),
      height,
    },
    anchors: {
      center: { x: cx, y: cy },
      top: { x: cx, y: top },
      bottom: { x: cx, y: bottom },
      neck: { x: cx, y: neckTop },
      outlet: side_arm
        ? { x: outletX, y: outletY }
        : { x: cx + neckW / 2, y: bodyTop },
    },
  };
}

export const flaskDef: ComponentDef<FlaskParams> = {
  kind: "flask",
  render: flask,
  anchorNames: ["center", "top", "bottom", "neck", "outlet"],
  defaultStyle: CHEM_GLASSWARE,
};

registerComponent(flaskDef);
