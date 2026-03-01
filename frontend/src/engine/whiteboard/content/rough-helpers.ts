/**
 * Rough.js utilities for hand-drawn whiteboard rendering.
 *
 * Pure functions — no React, no DOM side-effects.
 */

import type { Options as RoughOptions } from "roughjs/bin/core";
import { COLORS } from "../../theme";

// ── Seed hashing ──────────────────────────────────────────────

/**
 * Deterministic string → positive integer hash for Rough.js `seed`.
 * Same ID always produces the same hand-drawn variation.
 */
export function hashSeed(id: string): number {
  let hash = 5381;
  for (let i = 0; i < id.length; i++) {
    hash = ((hash << 5) + hash + id.charCodeAt(i)) | 0;
  }
  // Ensure positive and non-zero
  return (hash >>> 0) + 1;
}

// ── Style defaults ────────────────────────────────────────────

/** Node shapes: organic, visible hand-drawn wobble. */
export const SHAPE_DEFAULTS: RoughOptions = {
  roughness: 1.5,
  bowing: 1,
  strokeWidth: 2,
  fill: `${COLORS.accentGreen}14`, // 8% opacity
  fillStyle: "hachure",
  fillWeight: 1,
  hachureGap: 6,
};

/** Edges: slightly cleaner than shapes for readability. */
export const EDGE_DEFAULTS: RoughOptions = {
  roughness: 1.2,
  bowing: 0.8,
  strokeWidth: 2,
  stroke: COLORS.accentGreen,
};

/** Arrowheads: crisp enough to see direction. */
export const ARROWHEAD_DEFAULTS: RoughOptions = {
  roughness: 0.6,
  bowing: 0.3,
  strokeWidth: 1.5,
  fill: COLORS.accentGreen,
  fillStyle: "solid",
};

// ── Per-node options ──────────────────────────────────────────

/** Merge per-node color into shape defaults. */
export function nodeRoughOptions(color: string, seed: number): RoughOptions {
  const stroke = color || COLORS.accentGreen;
  const fill = color ? `${color}1F` : SHAPE_DEFAULTS.fill;
  return { ...SHAPE_DEFAULTS, stroke, fill, seed };
}

// ── Arrowhead geometry ────────────────────────────────────────

const ARROWHEAD_SIZE = 10;

/**
 * Compute triangle vertices for an arrowhead at the tip of an edge.
 * Returns vertices for `rc.polygon()`.
 *
 * @param x2 - tip x (edge end)
 * @param y2 - tip y (edge end)
 * @param x1 - tail x (edge start, used for direction)
 * @param y1 - tail y
 */
export function computeArrowheadVertices(
  x2: number,
  y2: number,
  x1: number,
  y1: number,
): [number, number][] {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return [];

  const ux = dx / len;
  const uy = dy / len;
  const px = -uy;
  const py = ux;

  const baseX = x2 - ux * ARROWHEAD_SIZE;
  const baseY = y2 - uy * ARROWHEAD_SIZE;
  const halfWidth = ARROWHEAD_SIZE / 2.5;

  return [
    [x2, y2],
    [baseX + px * halfWidth, baseY + py * halfWidth],
    [baseX - px * halfWidth, baseY - py * halfWidth],
  ];
}
