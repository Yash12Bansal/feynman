/**
 * Shared math utilities for geometry construction components.
 *
 * Pure functions for Euclidean geometry — distances, midpoints,
 * unit vectors, angles, and circle coordinate math.
 */

/** Euclidean distance between two points. */
export function distance(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  return Math.sqrt(dx * dx + dy * dy);
}

/** Midpoint of two points. */
export function midpoint(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): { x: number; y: number } {
  return { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
}

/**
 * Unit vector from (x1,y1) to (x2,y2).
 * Returns null if the points are coincident.
 */
export function unitVector(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): { ux: number; uy: number } | null {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return null;
  return { ux: dx / len, uy: dy / len };
}

/** Normalize an angle in radians to [0, 2*PI). */
export function normalizeAngle(rad: number): number {
  const TWO_PI = 2 * Math.PI;
  let r = rad % TWO_PI;
  if (r < 0) r += TWO_PI;
  return r;
}

/** Point at a given angle (degrees) on a circle. */
export function pointOnCircle(
  cx: number,
  cy: number,
  r: number,
  angleDeg: number,
): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}
