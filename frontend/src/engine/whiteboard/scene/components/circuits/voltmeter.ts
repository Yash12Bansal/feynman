/**
 * Voltmeter component — circle with "V" label inside.
 *
 * Pure function: given two endpoints → SceneGeometry.
 * Note: In v1 layout, voltmeter is registered but parallel routing
 * (where voltmeters typically appear) is deferred to Phase 8.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { computeBasis, toWorld } from "./utils";

export interface VoltmeterParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Optional label (placed outside; "V" is always inside) */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function voltmeter(params: VoltmeterParams): SceneGeometry {
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

  const radius = Math.min(basis.len * 0.18, 12);
  const cx = basis.mx;
  const cy = basis.my;

  // Lead wires
  const start = toWorld(basis, -basis.len / 2, 0);
  const circleStart = toWorld(basis, -radius, 0);
  const circleEnd = toWorld(basis, radius, 0);
  const end = toWorld(basis, basis.len / 2, 0);

  paths.push({
    id: `${id}-lead-start`,
    d: `M ${start.x} ${start.y} L ${circleStart.x} ${circleStart.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 1.8 },
  });
  paths.push({
    id: `${id}-lead-end`,
    d: `M ${circleEnd.x} ${circleEnd.y} L ${end.x} ${end.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 1.8 },
  });

  // Circle
  paths.push({
    id: `${id}-circle`,
    d: `M ${cx - radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx + radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx - radius} ${cy} Z`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor },
  });

  // "V" label inside the circle
  labels.push({
    id: `${id}-symbol`,
    text: "V",
    x: cx,
    y: cy + 5,
    anchor: "middle",
    fontSize: 13,
    color: strokeColor,
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx,
      y: cy - radius - 10,
      anchor: "middle",
      fontSize: 14,
      color: strokeColor,
    });
  }

  return {
    paths,
    labels,
    bounds: {
      x: cx - radius,
      y: cy - radius,
      width: radius * 2 || 1,
      height: radius * 2 || 1,
    },
    anchors: {
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
      center: { x: cx, y: cy },
    },
  };
}

export const voltmeterDef: ComponentDef<VoltmeterParams> = {
  kind: "voltmeter",
  render: voltmeter,
  anchorNames: ["start", "end", "center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(voltmeterDef);
