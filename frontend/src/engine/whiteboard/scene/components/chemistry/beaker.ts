/**
 * Beaker component — trapezoid body wider at top, optional pour spout, liquid fill.
 *
 * Pure function: given center + dimensions → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CHEM_GLASSWARE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface BeakerParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Total width at top (default 70) */
  width?: number;
  /** Total height (default 80) */
  height?: number;
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

const DEFAULT_WIDTH = 70;
const DEFAULT_HEIGHT = 80;
const TAPER = 0.8; // bottom is 80% of top width

export function beaker(params: BeakerParams): SceneGeometry {
  const {
    cx,
    cy,
    width = DEFAULT_WIDTH,
    height = DEFAULT_HEIGHT,
    fill_level = 0,
    fill_color,
    label,
    color,
    id,
  } = params;

  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const topW = width;
  const bottomW = width * TAPER;
  const top = cy - height / 2;
  const bottom = cy + height / 2;

  // Trapezoid body (open top)
  const tl = { x: cx - topW / 2, y: top };
  const tr = { x: cx + topW / 2, y: top };
  const br = { x: cx + bottomW / 2, y: bottom };
  const bl = { x: cx - bottomW / 2, y: bottom };

  // Pour spout at top-left: small notch
  const spoutSize = 6;
  const spoutX = tl.x;
  const spoutY = tl.y;

  // Body outline (left wall → bottom → right wall), open top
  paths.push({
    id: `${id}-body`,
    d: `M ${spoutX - spoutSize} ${spoutY - spoutSize} L ${tl.x} ${tl.y} L ${bl.x} ${bl.y} L ${br.x} ${br.y} L ${tr.x} ${tr.y}`,
    roughOptions: { ...CHEM_GLASSWARE, stroke: strokeColor },
  });

  // Liquid fill
  if (fill_level > 0) {
    const clampedFill = Math.min(1, Math.max(0, fill_level));
    const liquidTop = bottom - height * clampedFill;
    // Interpolate width at liquid level
    const t = (liquidTop - top) / height;
    const liquidW = topW + (bottomW - topW) * t;
    const liqColor = fill_color ?? COLORS.accentBlue;

    paths.push({
      id: `${id}-liquid`,
      d:
        `M ${cx - liquidW / 2} ${liquidTop} ` +
        `L ${bl.x} ${bl.y} L ${br.x} ${br.y} ` +
        `L ${cx + liquidW / 2} ${liquidTop} Z`,
      roughOptions: {
        ...CHEM_GLASSWARE,
        stroke: "none",
        fill: `${liqColor}44`,
        fillStyle: "solid",
        strokeWidth: 0,
      },
    });

    // Liquid surface line
    paths.push({
      id: `${id}-surface`,
      d: `M ${cx - liquidW / 2} ${liquidTop} L ${cx + liquidW / 2} ${liquidTop}`,
      roughOptions: {
        ...CHEM_GLASSWARE,
        stroke: liqColor,
        strokeWidth: 1.5,
        roughness: 1.0,
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

  const mouthY = top;

  return {
    paths,
    labels,
    bounds: {
      x: cx - topW / 2 - spoutSize,
      y: top - spoutSize,
      width: topW + spoutSize,
      height: height + spoutSize,
    },
    anchors: {
      center: { x: cx, y: cy },
      top: { x: cx, y: top },
      bottom: { x: cx, y: bottom },
      left: { x: cx - topW / 2, y: cy },
      right: { x: cx + topW / 2, y: cy },
      mouth: { x: cx, y: mouthY },
    },
  };
}

export const beakerDef: ComponentDef<BeakerParams> = {
  kind: "beaker",
  render: beaker,
  anchorNames: ["center", "top", "bottom", "left", "right", "mouth"],
  defaultStyle: CHEM_GLASSWARE,
};

registerComponent(beakerDef);
