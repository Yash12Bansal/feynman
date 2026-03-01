/**
 * Pure math functions for annotation path generation.
 *
 * Zero DOM, zero React. All annotation shapes are sampled analytically
 * and converted to Perfect Freehand input points with pressure curves.
 *
 * Three annotation types:
 * - Circle: ellipse around a target element
 * - Underline: line beneath a target element
 * - Arrow: quadratic bezier between two elements with arrowhead
 */

import { getStroke } from "perfect-freehand";
import { hashSeed } from "./rough-helpers";

// ── Types ─────────────────────────────────────────────────────

export interface InputPoint {
  x: number;
  y: number;
  pressure: number;
}

export interface ArrowheadVertices {
  tip: [number, number];
  left: [number, number];
  right: [number, number];
}

// ── Pressure curves ───────────────────────────────────────────

/**
 * Pressure ramps up quickly, holds, then tapers off — mimics a
 * confident pen stroke that lifts gently at the end.
 */
function pressureCurve(t: number): number {
  if (t < 0.1) return 0.3 + t * 4; // ramp up
  if (t > 0.85) return Math.max(0, 0.7 * (1 - (t - 0.85) / 0.15)); // taper
  return 0.7; // hold
}

// ── Wobble ────────────────────────────────────────────────────

/**
 * Deterministic per-point wobble. Small perpendicular displacement
 * gives organic feel without randomness.
 */
function wobble(seed: number, i: number, scale: number = 2): number {
  const x = (seed * 0.1 + i * 7.31) % 1;
  return Math.sin(x * Math.PI * 2) * scale;
}

// ── Ellipse sampling ──────────────────────────────────────────

/**
 * Sample points along an ellipse path with pressure curve.
 * @param cx - center x
 * @param cy - center y
 * @param rx - radius x (half-width)
 * @param ry - radius y (half-height)
 * @param n - number of sample points
 * @param seed - deterministic wobble seed
 */
export function sampleEllipse(
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  n: number = 72,
  seed: number = 1,
): InputPoint[] {
  const points: InputPoint[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const angle = t * Math.PI * 2;
    const w = wobble(seed, i, 1.5);
    points.push({
      x: cx + (rx + w) * Math.cos(angle),
      y: cy + (ry + w) * Math.sin(angle),
      pressure: pressureCurve(t),
    });
  }
  return points;
}

/**
 * SVG arc path for an ellipse centerline — used as mask animation path.
 */
export function ellipseCenterline(
  cx: number,
  cy: number,
  rx: number,
  ry: number,
): string {
  // Two-arc technique for a full ellipse
  return [
    `M ${cx - rx} ${cy}`,
    `A ${rx} ${ry} 0 1 1 ${cx + rx} ${cy}`,
    `A ${rx} ${ry} 0 1 1 ${cx - rx} ${cy}`,
  ].join(" ");
}

// ── Line sampling ─────────────────────────────────────────────

/**
 * Sample points along a straight line with pressure curve.
 */
export function sampleLine(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  n: number = 32,
  seed: number = 1,
): InputPoint[] {
  const points: InputPoint[] = [];
  // Perpendicular direction for wobble
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const px = len > 0 ? -dy / len : 0;
  const py = len > 0 ? dx / len : 0;

  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const w = wobble(seed, i, 1.5);
    points.push({
      x: x1 + dx * t + px * w,
      y: y1 + dy * t + py * w,
      pressure: pressureCurve(t),
    });
  }
  return points;
}

/**
 * SVG line path string for mask animation.
 */
export function lineCenterline(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): string {
  return `M ${x1} ${y1} L ${x2} ${y2}`;
}

// ── Quadratic Bezier sampling ─────────────────────────────────

/**
 * Sample points along a quadratic bezier with pressure curve.
 * Uses de Casteljau evaluation.
 */
export function sampleQuadBezier(
  p0: [number, number],
  p1: [number, number], // control point
  p2: [number, number],
  n: number = 48,
  seed: number = 1,
): InputPoint[] {
  const points: InputPoint[] = [];

  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const mt = 1 - t;
    // de Casteljau
    const x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0];
    const y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1];
    // Tangent for perpendicular wobble
    const tx = 2 * mt * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0]);
    const ty = 2 * mt * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1]);
    const tlen = Math.sqrt(tx * tx + ty * ty);
    const px = tlen > 0 ? -ty / tlen : 0;
    const py = tlen > 0 ? tx / tlen : 0;
    const w = wobble(seed, i, 1.5);

    points.push({
      x: x + px * w,
      y: y + py * w,
      pressure: pressureCurve(t),
    });
  }
  return points;
}

/**
 * SVG quadratic bezier path string for mask animation.
 */
export function bezierCenterline(
  p0: [number, number],
  cp: [number, number],
  p2: [number, number],
): string {
  return `M ${p0[0]} ${p0[1]} Q ${cp[0]} ${cp[1]} ${p2[0]} ${p2[1]}`;
}

// ── Arrowhead ─────────────────────────────────────────────────

/**
 * Compute triangle vertices for an arrowhead at a given endpoint.
 * @param endpoint - [x, y] where the arrow tip is
 * @param angle - direction the arrow points (radians)
 * @param size - size of the arrowhead
 */
export function computeArrowhead(
  endpoint: [number, number],
  angle: number,
  size: number = 14,
): ArrowheadVertices {
  const spread = Math.PI / 7; // ~25 degrees
  return {
    tip: endpoint,
    left: [
      endpoint[0] - size * Math.cos(angle - spread),
      endpoint[1] - size * Math.sin(angle - spread),
    ],
    right: [
      endpoint[0] - size * Math.cos(angle + spread),
      endpoint[1] - size * Math.sin(angle + spread),
    ],
  };
}

// ── Path length estimation ────────────────────────────────────

/**
 * Analytical path length estimation. No DOM calls.
 *
 * - Ellipse: Ramanujan approximation
 * - Line: Pythagorean distance
 * - Bezier: chord approximation (p0→cp→p2 path length)
 */
export function estimatePathLength(
  type: "ellipse" | "line" | "bezier",
  params: {
    rx?: number;
    ry?: number;
    x1?: number;
    y1?: number;
    x2?: number;
    y2?: number;
    p0?: [number, number];
    cp?: [number, number];
    p2?: [number, number];
  },
): number {
  switch (type) {
    case "ellipse": {
      const { rx = 0, ry = 0 } = params;
      // Ramanujan's approximation
      const h = ((rx - ry) * (rx - ry)) / ((rx + ry) * (rx + ry));
      return Math.PI * (rx + ry) * (1 + (3 * h) / (10 + Math.sqrt(4 - 3 * h)));
    }
    case "line": {
      const { x1 = 0, y1 = 0, x2 = 0, y2 = 0 } = params;
      const dx = x2 - x1;
      const dy = y2 - y1;
      return Math.sqrt(dx * dx + dy * dy);
    }
    case "bezier": {
      const { p0 = [0, 0], cp = [0, 0], p2 = [0, 0] } = params;
      // Chord approximation: sum of two segments
      const d1 = Math.sqrt((cp[0] - p0[0]) ** 2 + (cp[1] - p0[1]) ** 2);
      const d2 = Math.sqrt((p2[0] - cp[0]) ** 2 + (p2[1] - cp[1]) ** 2);
      return d1 + d2;
    }
  }
}

// ── Perfect Freehand → SVG path ───────────────────────────────

/**
 * Convert Perfect Freehand outline points to an SVG path `d` attribute.
 */
export function outlineToSvgPath(outline: number[][]): string {
  if (outline.length < 2) return "";

  const [first, ...rest] = outline;
  let d = `M ${first[0].toFixed(2)} ${first[1].toFixed(2)}`;

  for (const [x, y] of rest) {
    d += ` L ${x.toFixed(2)} ${y.toFixed(2)}`;
  }

  d += " Z";
  return d;
}

/**
 * Convert input points to a filled SVG path using Perfect Freehand.
 */
export function inputPointsToPath(
  points: InputPoint[],
  options?: { size?: number; smoothing?: number },
): string {
  const { size = 3.5, smoothing = 0.5 } = options ?? {};
  const outline = getStroke(
    points.map((p) => [p.x, p.y, p.pressure]),
    {
      size,
      thinning: 0.5,
      smoothing,
      streamline: 0.5,
      simulatePressure: false,
    },
  );
  return outlineToSvgPath(outline);
}

/**
 * Helper to compute annotation seed from an element ID.
 */
export function annotationSeed(id: string): number {
  return hashSeed(`ann-${id}`);
}
