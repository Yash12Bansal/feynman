/**
 * Switch component — pivot dot + angled arm.
 *
 * Pure function: given two endpoints → SceneGeometry.
 * When closed, arm connects start to end. When open, arm lifts at an angle.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { computeBasis, toWorld } from "./utils";

export interface SwitchParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Whether the switch is closed (default false = open) */
  closed?: boolean;
  /** Optional label */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function switchComponent(params: SwitchParams): SceneGeometry {
  const { x1, y1, x2, y2, closed = false, label, color, id } = params;
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

  const bodyHalf = basis.len * 0.25;
  const dotRadius = 3;

  // Lead wires
  const start = toWorld(basis, -basis.len / 2, 0);
  const pivotPt = toWorld(basis, -bodyHalf, 0);
  const contactPt = toWorld(basis, bodyHalf, 0);
  const end = toWorld(basis, basis.len / 2, 0);

  paths.push({
    id: `${id}-lead-start`,
    d: `M ${start.x} ${start.y} L ${pivotPt.x} ${pivotPt.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 1.8 },
  });
  paths.push({
    id: `${id}-lead-end`,
    d: `M ${contactPt.x} ${contactPt.y} L ${end.x} ${end.y}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 1.8 },
  });

  // Pivot dot (filled circle at start contact)
  paths.push({
    id: `${id}-pivot`,
    d: `M ${pivotPt.x - dotRadius} ${pivotPt.y} A ${dotRadius} ${dotRadius} 0 1 1 ${pivotPt.x + dotRadius} ${pivotPt.y} A ${dotRadius} ${dotRadius} 0 1 1 ${pivotPt.x - dotRadius} ${pivotPt.y} Z`,
    roughOptions: {
      ...CIRCUIT_SYMBOL,
      stroke: strokeColor,
      fill: strokeColor,
      fillStyle: "solid",
      roughness: 0.3,
    },
  });

  // Contact dot at end
  paths.push({
    id: `${id}-contact`,
    d: `M ${contactPt.x - dotRadius} ${contactPt.y} A ${dotRadius} ${dotRadius} 0 1 1 ${contactPt.x + dotRadius} ${contactPt.y} A ${dotRadius} ${dotRadius} 0 1 1 ${contactPt.x - dotRadius} ${contactPt.y} Z`,
    roughOptions: {
      ...CIRCUIT_SYMBOL,
      stroke: strokeColor,
      fill: strokeColor,
      fillStyle: "solid",
      roughness: 0.3,
    },
  });

  // Arm: from pivot to contact (closed) or lifted (open)
  if (closed) {
    paths.push({
      id: `${id}-arm`,
      d: `M ${pivotPt.x} ${pivotPt.y} L ${contactPt.x} ${contactPt.y}`,
      roughOptions: {
        ...CIRCUIT_SYMBOL,
        stroke: strokeColor,
        strokeWidth: 2.5,
      },
    });
  } else {
    // Open: arm lifts ~30° from the axis
    const armLen = bodyHalf * 2;
    const liftPerp = -armLen * Math.sin(Math.PI / 6); // 30° lift
    const liftAlong = armLen * Math.cos(Math.PI / 6);
    const armTip = toWorld(basis, -bodyHalf + liftAlong, liftPerp);
    paths.push({
      id: `${id}-arm`,
      d: `M ${pivotPt.x} ${pivotPt.y} L ${armTip.x} ${armTip.y}`,
      roughOptions: {
        ...CIRCUIT_SYMBOL,
        stroke: strokeColor,
        strokeWidth: 2.5,
      },
    });
  }

  if (label) {
    const labelPos = toWorld(basis, 0, -18);
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

  const allX = [x1, x2, pivotPt.x, contactPt.x];
  const allY = [y1, y2, pivotPt.y, contactPt.y];
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

export const switchComponentDef: ComponentDef<SwitchParams> = {
  kind: "switch",
  render: switchComponent,
  anchorNames: ["start", "end", "center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(switchComponentDef);
