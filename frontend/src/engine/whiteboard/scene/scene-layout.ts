/**
 * Layout utilities for scene geometry.
 *
 * computeTightBounds scans all paths and labels to compute the actual
 * bounding box of the scene content, replacing hardcoded canvas sizes
 * with tight-fitting bounds + padding.
 *
 * Pure utility — no React, no DOM.
 */

import type { ScenePath, SceneLabel } from "./scene-types";

/**
 * Extract x,y coordinate pairs from an SVG path data string.
 *
 * Handles M (moveto), L (lineto), and A (arc) commands.
 * For arcs, extracts the endpoint coordinates (last two numbers in
 * the 7-parameter arc command). Arc intermediate extents are approximate —
 * the padding in computeTightBounds compensates.
 */
export function extractPathCoords(d: string): { x: number; y: number }[] {
  const coords: { x: number; y: number }[] = [];
  const segments = d.match(/[MLHVCSQTAZ][^MLHVCSQTAZ]*/gi) ?? [];
  const NUM_RE = /-?[\d.]+(?:e[+-]?\d+)?/g;

  for (const seg of segments) {
    const cmd = seg[0].toUpperCase();
    const nums = [...seg.slice(1).matchAll(NUM_RE)].map((m) => Number(m[0]));

    switch (cmd) {
      case "M":
      case "L":
        for (let i = 0; i + 1 < nums.length; i += 2) {
          coords.push({ x: nums[i], y: nums[i + 1] });
        }
        break;
      case "A":
        // Arc: rx ry x-rotation large-arc-flag sweep-flag x y
        for (let i = 0; i + 6 < nums.length; i += 7) {
          coords.push({ x: nums[i + 5], y: nums[i + 6] });
        }
        break;
      case "C":
        // Cubic bezier: x1 y1 x2 y2 x y
        for (let i = 0; i + 5 < nums.length; i += 6) {
          coords.push({ x: nums[i], y: nums[i + 1] });
          coords.push({ x: nums[i + 2], y: nums[i + 3] });
          coords.push({ x: nums[i + 4], y: nums[i + 5] });
        }
        break;
      case "Q":
        // Quadratic bezier: x1 y1 x y
        for (let i = 0; i + 3 < nums.length; i += 4) {
          coords.push({ x: nums[i], y: nums[i + 1] });
          coords.push({ x: nums[i + 2], y: nums[i + 3] });
        }
        break;
      // Z, H, V, S, T: no full x,y pairs we need for bounding
    }
  }

  return coords;
}

/**
 * Compute tight bounding box around all paths and labels.
 *
 * Templates use fixed scene coordinates for layout, but the returned
 * bounds are tight to the actual content — no wasted dead space in
 * the SVG viewBox.
 */
export function computeTightBounds(
  paths: ScenePath[],
  labels: SceneLabel[],
  padding = 30,
): { x: number; y: number; width: number; height: number } {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  const expand = (x: number, y: number) => {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  };

  // Extract coordinates from all path data strings
  for (const path of paths) {
    const coords = extractPathCoords(path.d);
    for (const c of coords) {
      expand(c.x, c.y);
    }
  }

  // Include labels with approximate text extent
  for (const label of labels) {
    const fontSize = label.fontSize ?? 14;
    const charWidth = fontSize * 0.6;
    const textWidth = label.text.length * charWidth;

    let leftX: number;
    switch (label.anchor ?? "middle") {
      case "start":
        leftX = label.x;
        break;
      case "middle":
        leftX = label.x - textWidth / 2;
        break;
      case "end":
        leftX = label.x - textWidth;
        break;
    }

    // Text extends upward from baseline by ~fontSize, downward slightly
    expand(leftX, label.y - fontSize);
    expand(leftX + textWidth, label.y);
  }

  // Empty scene: return zero bounds
  if (minX === Infinity) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }

  return {
    x: minX - padding,
    y: minY - padding,
    width: maxX - minX + 2 * padding,
    height: maxY - minY + 2 * padding,
  };
}
