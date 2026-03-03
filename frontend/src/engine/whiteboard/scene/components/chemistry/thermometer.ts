/**
 * Thermometer component — thin vertical stem + filled circle bulb + reading bar.
 *
 * Pure function: given center + dimensions → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CHEM_GLASSWARE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface ThermometerParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Total height (default 70) */
  height?: number;
  /** Mercury reading level 0-1 (default 0.5) */
  reading?: number;
  /** Optional label (e.g. temperature reading) */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const DEFAULT_HEIGHT = 70;
const STEM_WIDTH = 6;
const BULB_RADIUS = 7;

export function thermometer(params: ThermometerParams): SceneGeometry {
  const {
    cx,
    cy,
    height = DEFAULT_HEIGHT,
    reading = 0.5,
    label,
    color,
    id,
  } = params;

  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const top = cy - height / 2;
  const bottom = cy + height / 2;
  const stemBottom = bottom - BULB_RADIUS * 2;

  // Outer stem (thin rectangle)
  paths.push({
    id: `${id}-stem`,
    d:
      `M ${cx - STEM_WIDTH / 2} ${top} ` +
      `L ${cx - STEM_WIDTH / 2} ${stemBottom} ` +
      `M ${cx + STEM_WIDTH / 2} ${top} ` +
      `L ${cx + STEM_WIDTH / 2} ${stemBottom}`,
    roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor, strokeWidth: 1.5 },
  });

  // Cap at top
  paths.push({
    id: `${id}-cap`,
    d: `M ${cx - STEM_WIDTH / 2} ${top} L ${cx + STEM_WIDTH / 2} ${top}`,
    roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor, strokeWidth: 1.5 },
  });

  // Bulb at bottom (circle)
  const bulbCenterY = bottom - BULB_RADIUS;
  paths.push({
    id: `${id}-bulb`,
    d:
      `M ${cx - BULB_RADIUS} ${bulbCenterY} ` +
      `A ${BULB_RADIUS} ${BULB_RADIUS} 0 1 0 ${cx + BULB_RADIUS} ${bulbCenterY} ` +
      `A ${BULB_RADIUS} ${BULB_RADIUS} 0 1 0 ${cx - BULB_RADIUS} ${bulbCenterY} Z`,
    roughOptions: {
      ...CHEM_GLASSWARE,
      stroke: strokeColor,
      fill: COLORS.accentRed,
      fillStyle: "solid",
      strokeWidth: 1.5,
    },
  });

  // Mercury/reading bar inside stem
  const clampedReading = Math.min(1, Math.max(0, reading));
  const stemH = stemBottom - top;
  const mercuryTop = stemBottom - stemH * clampedReading;
  const barW = STEM_WIDTH * 0.5;

  paths.push({
    id: `${id}-mercury`,
    d:
      `M ${cx - barW / 2} ${mercuryTop} ` +
      `L ${cx - barW / 2} ${stemBottom} ` +
      `L ${cx + barW / 2} ${stemBottom} ` +
      `L ${cx + barW / 2} ${mercuryTop} Z`,
    roughOptions: {
      stroke: "none",
      fill: COLORS.accentRed,
      fillStyle: "solid",
      strokeWidth: 0,
      roughness: 0.3,
    },
  });

  // Tick marks
  const tickCount = 5;
  for (let i = 0; i <= tickCount; i++) {
    const ty = top + (stemH * i) / tickCount;
    const tickLen = i % tickCount === 0 ? 4 : 3;
    paths.push({
      id: `${id}-tick-${i}`,
      d: `M ${cx + STEM_WIDTH / 2} ${ty} L ${cx + STEM_WIDTH / 2 + tickLen} ${ty}`,
      roughOptions: {
        ...CHEM_GLASSWARE,
        stroke: strokeColor,
        strokeWidth: 1,
        roughness: 0.3,
      },
    });
  }

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx + STEM_WIDTH / 2 + 14,
      y: cy,
      anchor: "start",
      fontSize: 12,
      color: strokeColor,
    });
  }

  return {
    paths,
    labels,
    bounds: {
      x: cx - BULB_RADIUS,
      y: top,
      width: BULB_RADIUS * 2,
      height,
    },
    anchors: {
      center: { x: cx, y: cy },
      top: { x: cx, y: top },
      bottom: { x: cx, y: bottom },
      bulb: { x: cx, y: bulbCenterY },
    },
  };
}

export const thermometerDef: ComponentDef<ThermometerParams> = {
  kind: "thermometer",
  render: thermometer,
  anchorNames: ["center", "top", "bottom", "bulb"],
  defaultStyle: CHEM_GLASSWARE,
};

registerComponent(thermometerDef);
