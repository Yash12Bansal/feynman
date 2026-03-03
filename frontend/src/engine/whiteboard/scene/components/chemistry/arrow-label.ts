/**
 * Arrow label component — horizontal arrow with text label above.
 *
 * Used for reaction arrows in chemical equations (e.g. "→ Spark").
 * Pure function: given center + dimensions → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CHEM_LABEL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface ArrowLabelParams {
  /** Start x */
  x1: number;
  /** Start y */
  y1: number;
  /** End x */
  x2: number;
  /** End y */
  y2: number;
  /** Condition/label text above arrow (e.g. "Spark", "Heat", "Δ") */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const ARROWHEAD_SIZE = 10;

export function arrowLabel(params: ArrowLabelParams): SceneGeometry {
  const { x1, y1, x2, y2, label, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

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
        center: { x: x1, y: y1 },
      },
    };
  }

  const ux = dx / len;
  const uy = dy / len;
  const px = -uy;
  const py = ux;

  // Arrow shaft
  paths.push({
    id: `${id}-shaft`,
    d: `M ${x1} ${y1} L ${x2} ${y2}`,
    roughOptions: { ...CHEM_LABEL, stroke: strokeColor },
  });

  // Arrowhead triangle
  const tipX = x2;
  const tipY = y2;
  const base1X = tipX - ux * ARROWHEAD_SIZE + px * ARROWHEAD_SIZE * 0.4;
  const base1Y = tipY - uy * ARROWHEAD_SIZE + py * ARROWHEAD_SIZE * 0.4;
  const base2X = tipX - ux * ARROWHEAD_SIZE - px * ARROWHEAD_SIZE * 0.4;
  const base2Y = tipY - uy * ARROWHEAD_SIZE - py * ARROWHEAD_SIZE * 0.4;

  paths.push({
    id: `${id}-head`,
    d: `M ${tipX} ${tipY} L ${base1X} ${base1Y} L ${base2X} ${base2Y} Z`,
    roughOptions: {
      ...CHEM_LABEL,
      stroke: strokeColor,
      fill: strokeColor,
      fillStyle: "solid",
    },
  });

  // Label above midpoint
  if (label) {
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    labels.push({
      id: `${id}-label`,
      text: label,
      x: midX + px * 16,
      y: midY + py * 16,
      anchor: "middle",
      fontSize: 13,
      color: strokeColor,
    });
  }

  const allX = [x1, x2, base1X, base2X];
  const allY = [y1, y2, base1Y, base2Y];

  return {
    paths,
    labels,
    bounds: {
      x: Math.min(...allX),
      y: Math.min(...allY) - 20,
      width: Math.max(...allX) - Math.min(...allX) || 1,
      height: Math.max(...allY) - Math.min(...allY) + 20 || 1,
    },
    anchors: {
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
      center: { x: (x1 + x2) / 2, y: (y1 + y2) / 2 },
    },
  };
}

export const arrowLabelDef: ComponentDef<ArrowLabelParams> = {
  kind: "arrow-label",
  render: arrowLabel,
  anchorNames: ["start", "end", "center"],
  defaultStyle: CHEM_LABEL,
};

registerComponent(arrowLabelDef);
