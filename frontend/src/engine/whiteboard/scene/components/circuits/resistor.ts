/**
 * Resistor component — American-style zigzag (4 peaks) between two endpoints.
 *
 * Pure function: given two endpoints → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { computeBasis, toWorld } from "./utils";

export interface ResistorParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Optional label (e.g. "100Ω") */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function resistor(params: ResistorParams): SceneGeometry {
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

  // Zigzag body occupies middle 60% of the span
  const bodyHalf = basis.len * 0.3;
  const peaks = 4;
  const amplitude = Math.min(basis.len * 0.12, 12);
  const segLen = (bodyHalf * 2) / (peaks * 2);

  // Build zigzag path
  const start = toWorld(basis, -basis.len / 2, 0);
  const bodyStart = toWorld(basis, -bodyHalf, 0);
  let d = `M ${start.x} ${start.y} L ${bodyStart.x} ${bodyStart.y}`;

  for (let i = 0; i < peaks * 2; i++) {
    const along = -bodyHalf + (i + 1) * segLen;
    const sign = i % 2 === 0 ? 1 : -1;
    const pt = toWorld(basis, along, amplitude * sign);
    d += ` L ${pt.x} ${pt.y}`;
  }

  const bodyEnd = toWorld(basis, bodyHalf, 0);
  const end = toWorld(basis, basis.len / 2, 0);
  d += ` L ${bodyEnd.x} ${bodyEnd.y} L ${end.x} ${end.y}`;

  paths.push({
    id: `${id}-zigzag`,
    d,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor },
  });

  if (label) {
    const labelPos = toWorld(basis, 0, amplitude + 14);
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

  const allX = [x1, x2];
  const allY = [y1, y2];
  for (let i = 0; i < peaks * 2; i++) {
    const along = -bodyHalf + (i + 1) * segLen;
    const sign = i % 2 === 0 ? 1 : -1;
    const pt = toWorld(basis, along, amplitude * sign);
    allX.push(pt.x);
    allY.push(pt.y);
  }
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

export const resistorDef: ComponentDef<ResistorParams> = {
  kind: "resistor",
  render: resistor,
  anchorNames: ["start", "end", "center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(resistorDef);
