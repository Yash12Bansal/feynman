/**
 * Capacitor component — two perpendicular parallel lines with a gap.
 *
 * Pure function: given two endpoints → SceneGeometry.
 * Supports electrolytic mode (curved negative plate).
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { computeBasis, toWorld } from "./utils";

export interface CapacitorParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Electrolytic capacitor (curved negative plate) */
  electrolytic?: boolean;
  /** Optional label (e.g. "10µF") */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function capacitor(params: CapacitorParams): SceneGeometry {
  const { x1, y1, x2, y2, electrolytic = false, label, color, id } = params;
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

  const gap = Math.min(basis.len * 0.12, 8);
  const plateHeight = Math.min(basis.len * 0.35, 18);

  // First plate (toward start) — always straight
  const p1a = toWorld(basis, -gap, plateHeight);
  const p1b = toWorld(basis, -gap, -plateHeight);
  paths.push({
    id: `${id}-plate1`,
    d: `M ${p1a.x} ${p1a.y} L ${p1b.x} ${p1b.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 2.5 },
  });

  // Second plate (toward end)
  if (electrolytic) {
    // Curved plate for electrolytic
    const p2a = toWorld(basis, gap, plateHeight);
    const p2b = toWorld(basis, gap, -plateHeight);
    const cpA = toWorld(basis, gap + plateHeight * 0.4, plateHeight * 0.5);
    const cpB = toWorld(basis, gap + plateHeight * 0.4, -plateHeight * 0.5);
    paths.push({
      id: `${id}-plate2`,
      d: `M ${p2a.x} ${p2a.y} C ${cpA.x} ${cpA.y}, ${cpB.x} ${cpB.y}, ${p2b.x} ${p2b.y}`,
      roughOptions: {
        ...CIRCUIT_SYMBOL,
        stroke: strokeColor,
        strokeWidth: 2.5,
      },
    });
  } else {
    const p2a = toWorld(basis, gap, plateHeight);
    const p2b = toWorld(basis, gap, -plateHeight);
    paths.push({
      id: `${id}-plate2`,
      d: `M ${p2a.x} ${p2a.y} L ${p2b.x} ${p2b.y}`,
      roughOptions: {
        ...CIRCUIT_SYMBOL,
        stroke: strokeColor,
        strokeWidth: 2.5,
      },
    });
  }

  // Lead wires
  const leadStart = toWorld(basis, -basis.len / 2, 0);
  const plateStart = toWorld(basis, -gap, 0);
  const plateEnd = toWorld(basis, gap, 0);
  const leadEnd = toWorld(basis, basis.len / 2, 0);

  paths.push({
    id: `${id}-lead-start`,
    d: `M ${leadStart.x} ${leadStart.y} L ${plateStart.x} ${plateStart.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 1.8 },
  });
  paths.push({
    id: `${id}-lead-end`,
    d: `M ${plateEnd.x} ${plateEnd.y} L ${leadEnd.x} ${leadEnd.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 1.8 },
  });

  if (label) {
    const labelPos = toWorld(basis, 0, plateHeight + 14);
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

  const allX = [x1, x2, p1a.x, p1b.x];
  const allY = [y1, y2, p1a.y, p1b.y];
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

export const capacitorDef: ComponentDef<CapacitorParams> = {
  kind: "capacitor",
  render: capacitor,
  anchorNames: ["start", "end", "center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(capacitorDef);
