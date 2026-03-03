/**
 * Test tube component — narrow rectangle + semicircular bottom, open top.
 *
 * Pure function: given center + dimensions → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CHEM_GLASSWARE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface TestTubeParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Total height (default 80) */
  height?: number;
  /** Tube width (default 20) */
  width?: number;
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

const DEFAULT_HEIGHT = 80;
const DEFAULT_WIDTH = 20;

export function testTube(params: TestTubeParams): SceneGeometry {
  const {
    cx,
    cy,
    height = DEFAULT_HEIGHT,
    width = DEFAULT_WIDTH,
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
  const r = width / 2; // semicircle radius at bottom

  // Body: two vertical walls + semicircular bottom
  // Left wall from top down, semicircle, right wall up
  const d =
    `M ${cx - r} ${top} ` +
    `L ${cx - r} ${bottom - r} ` +
    `A ${r} ${r} 0 0 0 ${cx + r} ${bottom - r} ` +
    `L ${cx + r} ${top}`;

  paths.push({
    id: `${id}-body`,
    d,
    roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
  });

  // Liquid fill
  if (fill_level > 0) {
    const clampedFill = Math.min(1, Math.max(0, fill_level));
    const fillableH = height - r; // from top to where arc starts
    const liquidTop = bottom - r - fillableH * clampedFill;
    const liqColor = fill_color ?? COLORS.accentBlue;

    // Fill inside tube
    const fillD =
      `M ${cx - r + 1} ${liquidTop} ` +
      `L ${cx - r + 1} ${bottom - r} ` +
      `A ${r - 1} ${r - 1} 0 0 0 ${cx + r - 1} ${bottom - r} ` +
      `L ${cx + r - 1} ${liquidTop} Z`;

    paths.push({
      id: `${id}-liquid`,
      d: fillD,
      roughOptions: {
        stroke: "none",
        fill: `${liqColor}44`,
        fillStyle: "solid",
        strokeWidth: 0,
      },
    });

    // Liquid surface line
    paths.push({
      id: `${id}-surface`,
      d: `M ${cx - r + 1} ${liquidTop} L ${cx + r - 1} ${liquidTop}`,
      roughOptions: {
        ...CHEM_GLASSWARE,
        stroke: liqColor,
        strokeWidth: 1.2,
        roughness: 1.0,
      },
    });
  }

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx + r + 10,
      y: cy,
      anchor: "start",
      fontSize: 12,
      color: strokeColor,
    });
  }

  return {
    paths,
    labels,
    bounds: { x: cx - r, y: top, width, height },
    anchors: {
      center: { x: cx, y: cy },
      top: { x: cx, y: top },
      bottom: { x: cx, y: bottom },
    },
  };
}

export const testTubeDef: ComponentDef<TestTubeParams> = {
  kind: "test-tube",
  render: testTube,
  anchorNames: ["center", "top", "bottom"],
  defaultStyle: CHEM_GLASSWARE,
};

registerComponent(testTubeDef);
