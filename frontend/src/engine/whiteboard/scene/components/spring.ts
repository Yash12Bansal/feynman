/**
 * Spring component — a zigzag path between two endpoints.
 *
 * Pure function: given two points + coil params → SceneGeometry.
 * The zigzag alternates perpendicular to the spring axis.
 */

import type { SceneGeometry, ScenePath } from "../scene-types";
import { SPRING_DEFAULTS } from "../scene-rough-helpers";

export interface SpringParams {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Number of coils (default 8) */
  coils?: number;
  /** Zigzag amplitude perpendicular to axis (default 10) */
  amplitude?: number;
  /** Unique id for paths */
  id: string;
  /** Stroke color override */
  color?: string;
}

export function spring(params: SpringParams): SceneGeometry {
  const { x1, y1, x2, y2, coils = 8, amplitude = 10, id, color } = params;

  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);

  // Degenerate: zero-length spring
  if (len === 0) {
    return {
      paths: [],
      labels: [],
      bounds: { x: x1, y: y1, width: 0, height: 0 },
      anchors: { start: { x: x1, y: y1 }, end: { x: x2, y: y2 } },
    };
  }

  // Unit vectors: along axis and perpendicular
  const ux = dx / len;
  const uy = dy / len;
  const px = -uy;
  const py = ux;

  // Leave straight lead-in segments at each end
  const leadIn = Math.min(len * 0.1, 15);
  const coilLen = len - 2 * leadIn;
  const segLen = coilLen / (coils * 2);

  let d = `M ${x1} ${y1}`;

  // Lead-in
  const startX = x1 + ux * leadIn;
  const startY = y1 + uy * leadIn;
  d += ` L ${startX} ${startY}`;

  // Zigzag coils
  for (let i = 0; i < coils * 2; i++) {
    const t = leadIn + (i + 1) * segLen;
    const baseX = x1 + ux * t;
    const baseY = y1 + uy * t;
    const sign = i % 2 === 0 ? 1 : -1;
    const ptX = baseX + px * amplitude * sign;
    const ptY = baseY + py * amplitude * sign;
    d += ` L ${ptX} ${ptY}`;
  }

  // Lead-out
  d += ` L ${x2} ${y2}`;

  const strokeColor = color ?? SPRING_DEFAULTS.stroke ?? "#f0f0f0";

  const paths: ScenePath[] = [
    {
      id: `${id}-coil`,
      d,
      roughOptions: {
        ...SPRING_DEFAULTS,
        stroke: strokeColor,
      },
    },
  ];

  // Bounds: account for amplitude
  const allX = [x1, x2, x1 + px * amplitude, x1 - px * amplitude];
  const allY = [y1, y2, y1 + py * amplitude, y1 - py * amplitude];
  const minX = Math.min(...allX);
  const minY = Math.min(...allY);
  const maxX = Math.max(...allX);
  const maxY = Math.max(...allY);

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
