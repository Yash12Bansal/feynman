/**
 * Wire component — straight line between two endpoints.
 *
 * Pure function: given two endpoints → SceneGeometry.
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { CIRCUIT_WIRE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface WireParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function wire(params: WireParams): SceneGeometry {
  const { x1, y1, x2, y2, color, id } = params;

  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);

  if (len === 0) {
    return {
      paths: [],
      labels: [],
      bounds: { x: x1, y: y1, width: 0, height: 0 },
      anchors: { start: { x: x1, y: y1 }, end: { x: x2, y: y2 } },
    };
  }

  const strokeColor = color ?? COLORS.textPrimary;

  const paths: ScenePath[] = [
    {
      id: `${id}-line`,
      d: `M ${x1} ${y1} L ${x2} ${y2}`,
      roughOptions: { ...CIRCUIT_WIRE, stroke: strokeColor },
    },
  ];

  const minX = Math.min(x1, x2);
  const minY = Math.min(y1, y2);
  const maxX = Math.max(x1, x2);
  const maxY = Math.max(y1, y2);

  return {
    paths,
    labels: [],
    bounds: {
      x: minX,
      y: minY,
      width: maxX - minX || 1,
      height: maxY - minY || 1,
    },
    anchors: {
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
    },
  };
}

export const wireDef: ComponentDef<WireParams> = {
  kind: "wire",
  render: wire,
  anchorNames: ["start", "end"],
  defaultStyle: CIRCUIT_WIRE,
};

registerComponent(wireDef);
