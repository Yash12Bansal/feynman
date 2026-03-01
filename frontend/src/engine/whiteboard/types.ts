/**
 * Living Whiteboard — type definitions and constants.
 *
 * All coordinates are in logical board space (1920x1080).
 * No rendering, no React — pure data shapes.
 */

// ── Board constants ──────────────────────────────────────────

export const BOARD_WIDTH = 1920;
export const BOARD_HEIGHT = 1080;

// ── Zone identifiers ─────────────────────────────────────────

export type BoardZone =
  | "top-left"
  | "top-center"
  | "top-right"
  | "center-left"
  | "center-center"
  | "center-right"
  | "bottom-left"
  | "bottom-center"
  | "bottom-right";

// ── Geometry ─────────────────────────────────────────────────

/** Axis-aligned rectangle in logical board coordinates. */
export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A zone's spatial bounds — outer cell and usable inner area. */
export interface ZoneBounds {
  zone: BoardZone;
  /** Full zone cell including padding. */
  outer: Rect;
  /** Usable area after padding is applied. */
  inner: Rect;
}

/** Precomputed layout for the entire board. */
export interface BoardLayout {
  width: number;
  height: number;
  zones: Record<BoardZone, ZoneBounds>;
}

/** An element that has been placed on the board. */
export interface PlacedElement {
  id: string;
  zone: BoardZone;
  bounds: Rect;
}

/** Result of computing where a new element should go. */
export interface PlacementResult {
  bounds: Rect;
  /** Whether the element fits vertically within the zone. */
  fits: boolean;
}

/** Summary of remaining space in a zone. */
export interface FreeSpace {
  zone: BoardZone;
  totalArea: number;
  usedArea: number;
  remainingHeight: number;
  nextY: number;
}
