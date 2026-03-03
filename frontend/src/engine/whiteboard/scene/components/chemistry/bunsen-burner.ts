/**
 * Bunsen burner component — wide base + narrow chimney + flame.
 *
 * Pure function: given center + dimensions → SceneGeometry.
 * Flame uses two nested bezier teardrops (outer amber, inner blue).
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CHEM_GLASSWARE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface BunsenBurnerParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Total height (default 60) */
  height?: number;
  /** Base width (default 40) */
  width?: number;
  /** Show flame (default true) */
  flame?: boolean;
  /** Optional label */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const DEFAULT_HEIGHT = 60;
const DEFAULT_WIDTH = 40;

export function bunsenBurner(params: BunsenBurnerParams): SceneGeometry {
  const {
    cx,
    cy,
    height = DEFAULT_HEIGHT,
    width = DEFAULT_WIDTH,
    flame = true,
    label,
    color,
    id,
  } = params;

  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const bottom = cy + height / 2;
  const top = cy - height / 2;
  const chimneyW = width * 0.3;
  const chimneyH = height * 0.55;
  const baseH = height * 0.25;

  // Wide rectangular base
  const baseTop = bottom - baseH;
  paths.push({
    id: `${id}-base`,
    d:
      `M ${cx - width / 2} ${baseTop} ` +
      `L ${cx - width / 2} ${bottom} ` +
      `L ${cx + width / 2} ${bottom} ` +
      `L ${cx + width / 2} ${baseTop} Z`,
    roughOptions: {
      ...CHEM_GLASSWARE,
      stroke: strokeColor,
      fill: `${strokeColor}15`,
      fillStyle: "solid",
    },
  });

  // Narrow chimney tube
  const chimneyTop = baseTop - chimneyH;
  paths.push({
    id: `${id}-chimney`,
    d:
      `M ${cx - chimneyW / 2} ${baseTop} ` +
      `L ${cx - chimneyW / 2} ${chimneyTop} ` +
      `M ${cx + chimneyW / 2} ${baseTop} ` +
      `L ${cx + chimneyW / 2} ${chimneyTop}`,
    roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
  });

  // Flame
  if (flame) {
    const flameBottom = chimneyTop;
    const flameH = height * 0.4;
    const outerW = chimneyW * 1.2;
    const innerW = chimneyW * 0.6;

    // Outer flame (amber teardrop)
    paths.push({
      id: `${id}-flame-outer`,
      d:
        `M ${cx} ${flameBottom} ` +
        `C ${cx - outerW} ${flameBottom - flameH * 0.4} ` +
        `${cx - outerW * 0.3} ${flameBottom - flameH * 0.9} ` +
        `${cx} ${flameBottom - flameH} ` +
        `C ${cx + outerW * 0.3} ${flameBottom - flameH * 0.9} ` +
        `${cx + outerW} ${flameBottom - flameH * 0.4} ` +
        `${cx} ${flameBottom}`,
      roughOptions: {
        roughness: 1.2,
        bowing: 0.6,
        strokeWidth: 1.5,
        stroke: COLORS.accentAmber,
        fill: `${COLORS.accentAmber}33`,
        fillStyle: "solid",
      },
    });

    // Inner flame (blue teardrop)
    const innerH = flameH * 0.6;
    paths.push({
      id: `${id}-flame-inner`,
      d:
        `M ${cx} ${flameBottom} ` +
        `C ${cx - innerW} ${flameBottom - innerH * 0.4} ` +
        `${cx - innerW * 0.3} ${flameBottom - innerH * 0.9} ` +
        `${cx} ${flameBottom - innerH} ` +
        `C ${cx + innerW * 0.3} ${flameBottom - innerH * 0.9} ` +
        `${cx + innerW} ${flameBottom - innerH * 0.4} ` +
        `${cx} ${flameBottom}`,
      roughOptions: {
        roughness: 1.0,
        bowing: 0.5,
        strokeWidth: 1,
        stroke: COLORS.accentBlue,
        fill: `${COLORS.accentBlue}44`,
        fillStyle: "solid",
      },
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

  const flameExtent = flame ? height * 0.4 : 0;

  return {
    paths,
    labels,
    bounds: {
      x: cx - width / 2,
      y: top - flameExtent,
      width,
      height: height + flameExtent,
    },
    anchors: {
      center: { x: cx, y: cy },
      top: { x: cx, y: chimneyTop - (flame ? height * 0.4 : 0) },
      bottom: { x: cx, y: bottom },
    },
  };
}

export const bunsenBurnerDef: ComponentDef<BunsenBurnerParams> = {
  kind: "bunsen-burner",
  render: bunsenBurner,
  anchorNames: ["center", "top", "bottom"],
  defaultStyle: CHEM_GLASSWARE,
};

registerComponent(bunsenBurnerDef);
