/**
 * Battery component — long/short perpendicular lines representing +/− plates.
 *
 * Pure function: given two endpoints → SceneGeometry.
 * The positive plate (long line) is at the start end, negative (short) at end.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { computeBasis, toWorld } from "./utils";

export interface BatteryParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Optional label (e.g. "12V") */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function battery(params: BatteryParams): SceneGeometry {
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

  // Gap between plates
  const gap = Math.min(basis.len * 0.15, 8);
  // Plate sizes
  const longPlate = Math.min(basis.len * 0.4, 20);
  const shortPlate = longPlate * 0.6;

  // Long plate (positive, toward start)
  const lp1 = toWorld(basis, -gap, longPlate);
  const lp2 = toWorld(basis, -gap, -longPlate);
  paths.push({
    id: `${id}-pos`,
    d: `M ${lp1.x} ${lp1.y} L ${lp2.x} ${lp2.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 2.5 },
  });

  // Short plate (negative, toward end)
  const sp1 = toWorld(basis, gap, shortPlate);
  const sp2 = toWorld(basis, gap, -shortPlate);
  paths.push({
    id: `${id}-neg`,
    d: `M ${sp1.x} ${sp1.y} L ${sp2.x} ${sp2.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 2.5 },
  });

  // Lead wires from endpoints to plates
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
    // Label offset perpendicular to axis
    const labelPos = toWorld(basis, 0, longPlate + 14);
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

  const allX = [x1, x2, lp1.x, lp2.x, sp1.x, sp2.x];
  const allY = [y1, y2, lp1.y, lp2.y, sp1.y, sp2.y];
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

export const batteryDef: ComponentDef<BatteryParams> = {
  kind: "battery",
  render: battery,
  anchorNames: ["start", "end", "center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(batteryDef);
