/**
 * Inductor component — 4 semicircular humps along the axis.
 *
 * Pure function: given two endpoints → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { computeBasis, toWorld } from "./utils";

export interface InductorParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Optional label (e.g. "10mH") */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function inductor(params: InductorParams): SceneGeometry {
  const { x1, y1, x2, y2, label, color, id } = params;
  const basis = computeBasis(x1, y1, x2, y2);

  if (!basis) {
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

  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const humps = 4;
  const bodyHalf = basis.len * 0.3;
  const humpWidth = (bodyHalf * 2) / humps;
  const amplitude = Math.min(basis.len * 0.12, 12);

  // Build path: lead-in → 4 semicircular arcs → lead-out
  const start = toWorld(basis, -basis.len / 2, 0);
  const bodyStart = toWorld(basis, -bodyHalf, 0);
  let d = `M ${start.x} ${start.y} L ${bodyStart.x} ${bodyStart.y}`;

  for (let i = 0; i < humps; i++) {
    const arcStart = -bodyHalf + i * humpWidth;
    const arcEnd = arcStart + humpWidth;
    const cp1 = toWorld(basis, arcStart + humpWidth * 0.1, -amplitude);
    const cp2 = toWorld(basis, arcEnd - humpWidth * 0.1, -amplitude);
    const endPt = toWorld(basis, arcEnd, 0);
    d += ` C ${cp1.x} ${cp1.y}, ${cp2.x} ${cp2.y}, ${endPt.x} ${endPt.y}`;
  }

  const end = toWorld(basis, basis.len / 2, 0);
  d += ` L ${end.x} ${end.y}`;

  paths.push({
    id: `${id}-coil`,
    d,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor },
  });

  if (label) {
    const labelPos = toWorld(basis, 0, -amplitude - 14);
    labels.push({
      id: `${id}-label`,
      text: label,
      x: labelPos.x,
      y: labelPos.y,
      anchor: "middle",
      fontSize: 14,
      color: strokeColor,
    });
  }

  // Bounds: include hump amplitude
  const corners = [
    toWorld(basis, -bodyHalf, -amplitude),
    toWorld(basis, bodyHalf, -amplitude),
    { x: x1, y: y1 },
    { x: x2, y: y2 },
  ];
  const allX = corners.map((c) => c.x);
  const allY = corners.map((c) => c.y);
  const minX = Math.min(...allX);
  const minY = Math.min(...allY);
  const maxX = Math.max(...allX);
  const maxY = Math.max(...allY);

  return {
    paths,
    labels,
    bounds: {
      x: minX,
      y: minY,
      width: maxX - minX || 1,
      height: maxY - minY || 1,
    },
    anchors: {
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
      center: { x: basis.mx, y: basis.my },
    },
  };
}

export const inductorDef: ComponentDef<InductorParams> = {
  kind: "inductor",
  render: inductor,
  anchorNames: ["start", "end", "center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(inductorDef);
