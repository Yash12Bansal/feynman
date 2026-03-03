/**
 * Force arrow component — a vector arrow with shaft, triangular head, and label.
 *
 * Pure function: given origin, direction, magnitude → SceneGeometry.
 * No React, no DOM. Returns SVG path data for rough.path().
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../scene-types";
import { VECTOR_DEFAULTS } from "../scene-rough-helpers";

export interface ForceArrowParams {
  /** Arrow origin x */
  x: number;
  /** Arrow origin y */
  y: number;
  /** Direction in degrees (0 = right, 90 = down) */
  angle: number;
  /** Arrow length in scene units */
  length: number;
  /** Stroke color */
  color?: string;
  /** Label text (e.g. "W", "N", "f") */
  label?: string;
  /** Unique id prefix for paths */
  id: string;
}

const ARROWHEAD_LENGTH = 14;
const ARROWHEAD_HALF_WIDTH = 6;

export function forceArrow(params: ForceArrowParams): SceneGeometry {
  const { x, y, angle, length, color, label, id } = params;

  const rad = (angle * Math.PI) / 180;
  const dx = Math.cos(rad);
  const dy = Math.sin(rad);

  // Perpendicular for arrowhead width
  const px = -dy;
  const py = dx;

  const tipX = x + dx * length;
  const tipY = y + dy * length;

  // Shaft ends at the arrowhead base
  const shaftEndX = x + dx * (length - ARROWHEAD_LENGTH);
  const shaftEndY = y + dy * (length - ARROWHEAD_LENGTH);

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  const strokeColor = color ?? VECTOR_DEFAULTS.stroke ?? "#f0f0f0";

  // Zero-length arrow: no paths
  if (length <= 0) {
    return {
      paths: [],
      labels: [],
      bounds: { x, y, width: 0, height: 0 },
      anchors: { tail: { x, y }, tip: { x, y } },
    };
  }

  // Shaft path
  const shaftD =
    length > ARROWHEAD_LENGTH
      ? `M ${x} ${y} L ${shaftEndX} ${shaftEndY}`
      : `M ${x} ${y} L ${tipX} ${tipY}`;

  paths.push({
    id: `${id}-shaft`,
    d: shaftD,
    roughOptions: {
      ...VECTOR_DEFAULTS,
      stroke: strokeColor,
    },
  });

  // Arrowhead (filled triangle) — only if arrow is long enough
  if (length > ARROWHEAD_LENGTH) {
    const baseX = shaftEndX;
    const baseY = shaftEndY;
    const leftX = baseX + px * ARROWHEAD_HALF_WIDTH;
    const leftY = baseY + py * ARROWHEAD_HALF_WIDTH;
    const rightX = baseX - px * ARROWHEAD_HALF_WIDTH;
    const rightY = baseY - py * ARROWHEAD_HALF_WIDTH;

    const headD = `M ${tipX} ${tipY} L ${leftX} ${leftY} L ${rightX} ${rightY} Z`;
    paths.push({
      id: `${id}-head`,
      d: headD,
      roughOptions: {
        ...VECTOR_DEFAULTS,
        stroke: strokeColor,
        fill: strokeColor,
        fillStyle: "solid",
        roughness: 0.5,
      },
    });
  }

  // Label at midpoint, offset perpendicular to the arrow axis
  if (label) {
    const midX = x + dx * (length / 2);
    const midY = y + dy * (length / 2);
    const labelOffsetDist = 18;
    labels.push({
      id: `${id}-label`,
      text: label,
      x: midX + px * labelOffsetDist,
      y: midY + py * labelOffsetDist,
      anchor: "middle",
      color: strokeColor,
    });
  }

  // Compute bounds
  const allX = [x, tipX];
  const allY = [y, tipY];
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
      tail: { x, y },
      tip: { x: tipX, y: tipY },
    },
  };
}
