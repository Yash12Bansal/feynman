/**
 * Concave lens component — a biconcave lens shape () with outward arrowhead tips.
 *
 * Pure function: given center + height + bulge → SceneGeometry.
 * Two cubic bezier arcs curving inward toward center axis.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { APPARATUS_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface ConcaveLensParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Total height of the lens (default 120) */
  height?: number;
  /** Horizontal inward curve distance (default 12) */
  bulge?: number;
  /** Optional label */
  label?: string;
  /** Stroke color (default textPrimary) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const ARROW_SIZE = 6;

export function concaveLens(params: ConcaveLensParams): SceneGeometry {
  const { cx, cy, height = 120, bulge = 12, label, color, id } = params;

  const strokeColor = color ?? COLORS.textPrimary;
  const halfH = height / 2;
  const top = cy - halfH;
  const bottom = cy + halfH;

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Left surface: curves inward to the right (concave)
  paths.push({
    id: `${id}-left`,
    d: [
      `M ${cx} ${top}`,
      `C ${cx + bulge} ${top + halfH * 0.33}, ${cx + bulge} ${bottom - halfH * 0.33}, ${cx} ${bottom}`,
    ].join(" "),
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
      strokeWidth: 2,
    },
  });

  // Right surface: curves inward to the left (concave)
  paths.push({
    id: `${id}-right`,
    d: [
      `M ${cx} ${top}`,
      `C ${cx - bulge} ${top + halfH * 0.33}, ${cx - bulge} ${bottom - halfH * 0.33}, ${cx} ${bottom}`,
    ].join(" "),
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
      strokeWidth: 2,
    },
  });

  // Outward arrowheads at tips (pointing outward = diverging lens symbol)
  // Top arrowhead: two small lines pointing outward
  paths.push({
    id: `${id}-arrow-top`,
    d: `M ${cx - ARROW_SIZE} ${top - ARROW_SIZE} L ${cx} ${top} L ${cx + ARROW_SIZE} ${top - ARROW_SIZE}`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
      strokeWidth: 1.5,
      roughness: 0.4,
    },
  });

  // Bottom arrowhead: two small lines pointing outward
  paths.push({
    id: `${id}-arrow-bottom`,
    d: `M ${cx - ARROW_SIZE} ${bottom + ARROW_SIZE} L ${cx} ${bottom} L ${cx + ARROW_SIZE} ${bottom + ARROW_SIZE}`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
      strokeWidth: 1.5,
      roughness: 0.4,
    },
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx,
      y: top - 10,
      anchor: "middle",
      fontSize: 14,
      color: strokeColor,
    });
  }

  return {
    paths,
    labels,
    bounds: {
      x: cx - bulge,
      y: top - ARROW_SIZE,
      width: bulge * 2,
      height: height + ARROW_SIZE * 2,
    },
    anchors: {
      center: { x: cx, y: cy },
      top: { x: cx, y: top },
      bottom: { x: cx, y: bottom },
    },
  };
}

export const concaveLensDef: ComponentDef<ConcaveLensParams> = {
  kind: "concave-lens",
  render: concaveLens,
  anchorNames: ["center", "top", "bottom"],
  defaultStyle: APPARATUS_STROKE,
};

registerComponent(concaveLensDef);
