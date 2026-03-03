/**
 * Shared math utilities for circuit components.
 *
 * Every circuit component takes two endpoints (x1,y1)→(x2,y2) and draws
 * its symbol along the axis between them. This module extracts the
 * unit-vector rotation math so 11 component files don't duplicate it.
 */

/** Basis vectors + midpoint for an endpoint pair. */
export interface EndpointBasis {
  /** Midpoint x */
  mx: number;
  /** Midpoint y */
  my: number;
  /** Unit vector along axis (x1→x2), x component */
  ux: number;
  /** Unit vector along axis (x1→x2), y component */
  uy: number;
  /** Unit vector perpendicular (left of axis), x component */
  px: number;
  /** Unit vector perpendicular (left of axis), y component */
  py: number;
  /** Total length between endpoints */
  len: number;
}

/**
 * Compute basis vectors for a pair of endpoints.
 * Returns null if the endpoints are coincident (zero length).
 */
export function computeBasis(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): EndpointBasis | null {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);

  if (len === 0) return null;

  const ux = dx / len;
  const uy = dy / len;

  return {
    mx: (x1 + x2) / 2,
    my: (y1 + y2) / 2,
    ux,
    uy,
    px: -uy,
    py: ux,
    len,
  };
}

/**
 * Convert local (along, perp) coordinates to world (x, y)
 * relative to the midpoint of the basis.
 */
export function toWorld(
  basis: EndpointBasis,
  along: number,
  perp: number,
): { x: number; y: number } {
  return {
    x: basis.mx + basis.ux * along + basis.px * perp,
    y: basis.my + basis.uy * along + basis.py * perp,
  };
}
