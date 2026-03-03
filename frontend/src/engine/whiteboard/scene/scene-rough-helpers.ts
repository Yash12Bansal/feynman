/**
 * Rough.js style defaults for scientific apparatus.
 *
 * Apparatus needs different roughness than graph nodes — cleaner lines,
 * less bowing, since these represent precise physical objects drawn
 * with a teacher's deliberate hand.
 */

import type { Options as RoughOptions } from "roughjs/bin/core";
import { COLORS } from "../../theme";

/** Apparatus outlines: precise but still hand-drawn. */
export const APPARATUS_STROKE: RoughOptions = {
  roughness: 1.2,
  bowing: 0.8,
  strokeWidth: 2.5,
  stroke: COLORS.textPrimary,
  fill: "none",
};

/** Apparatus with fill (blocks, masses). */
export const APPARATUS_FILLED: RoughOptions = {
  roughness: 1.0,
  bowing: 0.5,
  strokeWidth: 2,
  fillStyle: "hachure",
  fillWeight: 1,
  hachureGap: 6,
};

/** Force vectors: colored arrows. */
export const VECTOR_DEFAULTS: RoughOptions = {
  roughness: 0.8,
  bowing: 0.4,
  strokeWidth: 2.5,
  fill: "none",
};

/** Spring coils: moderate wobble. */
export const SPRING_DEFAULTS: RoughOptions = {
  roughness: 1.0,
  bowing: 0.6,
  strokeWidth: 2,
  fill: "none",
};

/** Light rays: thin, clean lines for optics diagrams. */
export const LIGHT_RAY_DEFAULTS: RoughOptions = {
  roughness: 0.6,
  bowing: 0.3,
  strokeWidth: 1.5,
  fill: "none",
};

/** Wavefront arcs: very clean, thin, partially transparent. */
export const WAVEFRONT_DEFAULTS: RoughOptions = {
  roughness: 0.4,
  bowing: 0.2,
  strokeWidth: 1,
  fill: "none",
};

/** Solid-filled barrier/apparatus: minimal roughness for precision equipment. */
export const BARRIER_SOLID: RoughOptions = {
  roughness: 0.6,
  bowing: 0.3,
  strokeWidth: 1.5,
  fillStyle: "solid",
};

/** Circuit schematic symbols: clean, precise strokes. */
export const CIRCUIT_SYMBOL: RoughOptions = {
  roughness: 0.8,
  bowing: 0.4,
  strokeWidth: 2.0,
  fill: "none",
};

/** Circuit wires: thinner, cleaner lines. */
export const CIRCUIT_WIRE: RoughOptions = {
  roughness: 0.6,
  bowing: 0.2,
  strokeWidth: 1.8,
  fill: "none",
};

/** Geometry construction lines: clean, compass-and-straightedge feel. */
export const GEOMETRY_STROKE: RoughOptions = {
  roughness: 0.6,
  bowing: 0.3,
  strokeWidth: 2.0,
  fill: "none",
};

/** Geometry annotations (marks, arcs): thinner/subtler than construction lines. */
export const GEOMETRY_ANNOTATION: RoughOptions = {
  roughness: 0.4,
  bowing: 0.2,
  strokeWidth: 1.5,
  fill: "none",
};
