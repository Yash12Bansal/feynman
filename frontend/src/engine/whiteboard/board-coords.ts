/**
 * Board-space coordinate utilities.
 *
 * Converts viewport-space DOMRect measurements to board-space coordinates,
 * accounting for the CSS scale transform applied to the board surface.
 *
 * Shared by AnnotationOverlay (freehand annotations) and BoundsReporter
 * (element bounds feedback to backend).
 */

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Convert a viewport-space DOMRect to board-space coordinates.
 *
 * The board surface is rendered at `scale` via CSS transform. Element
 * getBoundingClientRect() returns viewport pixels — we need to undo
 * the scale and offset relative to the board origin.
 */
export function viewportToBoard(
  elRect: DOMRect,
  boardRect: DOMRect,
  scale: number,
): Rect {
  return {
    x: (elRect.left - boardRect.left) / scale,
    y: (elRect.top - boardRect.top) / scale,
    width: elRect.width / scale,
    height: elRect.height / scale,
  };
}
