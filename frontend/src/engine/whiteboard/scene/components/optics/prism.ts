/**
 * Prism component — an equilateral triangle (apex up by default), rotatable.
 *
 * Pure function: given center + side length + rotation → SceneGeometry.
 * Outline only (no fill) — matches apparatus style.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { APPARATUS_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface PrismParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Side length (default 80) */
  sideLength?: number;
  /** Rotation in degrees (default 0) */
  rotation?: number;
  /** Optional label */
  label?: string;
  /** Stroke color (default textSecondary) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

function rotatePoint(
  px: number,
  py: number,
  cx: number,
  cy: number,
  angleDeg: number,
): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const dx = px - cx;
  const dy = py - cy;
  return {
    x: cx + dx * cos - dy * sin,
    y: cy + dx * sin + dy * cos,
  };
}

export function prism(params: PrismParams): SceneGeometry {
  const { cx, cy, sideLength = 80, rotation = 0, label, color, id } = params;

  const strokeColor = color ?? COLORS.textSecondary;

  // Equilateral triangle: height = sideLength * sqrt(3)/2
  const h = (sideLength * Math.sqrt(3)) / 2;
  // Centroid is at 1/3 from base, 2/3 from apex
  const apexY = cy - (2 / 3) * h;
  const baseY = cy + (1 / 3) * h;
  const halfBase = sideLength / 2;

  // Vertices before rotation (apex up)
  const rawApex = { x: cx, y: apexY };
  const rawBaseLeft = { x: cx - halfBase, y: baseY };
  const rawBaseRight = { x: cx + halfBase, y: baseY };

  // Apply rotation
  const apex = rotatePoint(rawApex.x, rawApex.y, cx, cy, rotation);
  const baseLeft = rotatePoint(rawBaseLeft.x, rawBaseLeft.y, cx, cy, rotation);
  const baseRight = rotatePoint(
    rawBaseRight.x,
    rawBaseRight.y,
    cx,
    cy,
    rotation,
  );

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  paths.push({
    id: `${id}-triangle`,
    d: `M ${apex.x} ${apex.y} L ${baseRight.x} ${baseRight.y} L ${baseLeft.x} ${baseLeft.y} Z`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
      fill: "none",
    },
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx,
      y: cy + 5,
      anchor: "middle",
      fontSize: 14,
      color: strokeColor,
    });
  }

  // Compute face midpoints for anchors
  const leftFace = {
    x: (apex.x + baseLeft.x) / 2,
    y: (apex.y + baseLeft.y) / 2,
  };
  const rightFace = {
    x: (apex.x + baseRight.x) / 2,
    y: (apex.y + baseRight.y) / 2,
  };

  // Bounds
  const allX = [apex.x, baseLeft.x, baseRight.x];
  const allY = [apex.y, baseLeft.y, baseRight.y];
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
      center: { x: cx, y: cy },
      apex,
      baseLeft,
      baseRight,
      leftFace,
      rightFace,
    },
  };
}

export const prismDef: ComponentDef<PrismParams> = {
  kind: "prism",
  render: prism,
  anchorNames: [
    "center",
    "apex",
    "baseLeft",
    "baseRight",
    "leftFace",
    "rightFace",
  ],
  defaultStyle: APPARATUS_STROKE,
};

registerComponent(prismDef);
