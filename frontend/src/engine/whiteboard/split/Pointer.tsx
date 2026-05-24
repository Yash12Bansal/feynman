/**
 * Pointer — doc 19 §12 live-annotation primitive.
 *
 * An arrow pointing at an element from a specified side. Lighter-weight than
 * `<Spotlight>` — it doesn't dim the rest of the diagram. Used when the
 * teacher wants to "tap" or refer to a previously-revealed element without
 * re-spotlighting it.
 *
 * The arrow tail starts off-bounds and bounces into final position on
 * appearance (260ms), then pulses subtly until cleared.
 */

import { useRef, type CSSProperties, type RefObject } from "react";
import type { ElementMeta } from "../../../types/visuals";
import { useResolvedBounds } from "./SlideAnnotationLayer";

const SHAFT_LENGTH = 56;
const HEAD_LENGTH = 14;
const HEAD_WIDTH = 12;
const TIP_GAP = 6; // gap between the head tip and the element bounds
const BOUNCE_OFFSET = 28; // how far the pointer comes from at start

interface PointerProps {
  readonly elementId: string;
  readonly fromSide: "top" | "bottom" | "left" | "right";
  readonly dictionary: Record<string, ElementMeta> | undefined;
  readonly stageRef: RefObject<HTMLElement | null> | undefined;
  readonly overlayRef: RefObject<SVGSVGElement | null>;
}

export function Pointer({
  elementId,
  fromSide,
  dictionary,
  stageRef,
  overlayRef,
}: PointerProps) {
  // Stable ref so the hook returns consistent identities across renders.
  const target = useRef({ kind: "id" as const, value: elementId }).current;
  const bounds = useResolvedBounds(target, stageRef, overlayRef, dictionary);

  if (!bounds) return null;
  const [bx, by, bw, bh] = bounds;

  const geom = computeArrowGeometry(bx, by, bw, bh, fromSide);

  const bounceStyle: CSSProperties = {
    ["--pointer-bounce-x" as string]: `${geom.bounceX}px`,
    ["--pointer-bounce-y" as string]: `${geom.bounceY}px`,
  };

  return (
    <g
      className="sb-pointer"
      data-element-id={elementId}
      data-from-side={fromSide}
      style={bounceStyle}
    >
      <g className="sb-pointer-pulse">
        {/* Shaft */}
        <line
          className="sb-pointer-shaft"
          x1={geom.tailX}
          y1={geom.tailY}
          x2={geom.tipX}
          y2={geom.tipY}
        />
        {/* Arrowhead: filled triangle */}
        <path className="sb-pointer-head" d={geom.headPath} />
      </g>
    </g>
  );
}

interface ArrowGeometry {
  readonly tipX: number;
  readonly tipY: number;
  readonly tailX: number;
  readonly tailY: number;
  readonly headPath: string;
  /** How far in pixels the pointer translates from on mount (bounce-in). */
  readonly bounceX: number;
  readonly bounceY: number;
}

function computeArrowGeometry(
  bx: number,
  by: number,
  bw: number,
  bh: number,
  fromSide: "top" | "bottom" | "left" | "right",
): ArrowGeometry {
  // Anchor: the midpoint of the bounds edge on the requested side.
  // Tail: SHAFT_LENGTH away from the tip along the side's outward normal.
  const cx = bx + bw / 2;
  const cy = by + bh / 2;
  switch (fromSide) {
    case "top": {
      const tipX = cx;
      const tipY = by - TIP_GAP;
      const tailX = tipX;
      const tailY = tipY - SHAFT_LENGTH;
      return {
        tipX,
        tipY,
        tailX,
        tailY,
        headPath: arrowHeadPath(tipX, tipY, 0, -1),
        bounceX: 0,
        bounceY: -BOUNCE_OFFSET,
      };
    }
    case "bottom": {
      const tipX = cx;
      const tipY = by + bh + TIP_GAP;
      const tailX = tipX;
      const tailY = tipY + SHAFT_LENGTH;
      return {
        tipX,
        tipY,
        tailX,
        tailY,
        headPath: arrowHeadPath(tipX, tipY, 0, 1),
        bounceX: 0,
        bounceY: BOUNCE_OFFSET,
      };
    }
    case "left": {
      const tipX = bx - TIP_GAP;
      const tipY = cy;
      const tailX = tipX - SHAFT_LENGTH;
      const tailY = tipY;
      return {
        tipX,
        tipY,
        tailX,
        tailY,
        headPath: arrowHeadPath(tipX, tipY, -1, 0),
        bounceX: -BOUNCE_OFFSET,
        bounceY: 0,
      };
    }
    case "right": {
      const tipX = bx + bw + TIP_GAP;
      const tipY = cy;
      const tailX = tipX + SHAFT_LENGTH;
      const tailY = tipY;
      return {
        tipX,
        tipY,
        tailX,
        tailY,
        headPath: arrowHeadPath(tipX, tipY, 1, 0),
        bounceX: BOUNCE_OFFSET,
        bounceY: 0,
      };
    }
  }
}

/**
 * Builds a triangle arrowhead path. The tip is at (tipX, tipY), pointing in
 * the direction (dx, dy) which is the outward normal — for from_side="left",
 * the arrow points LEFT into the element so dx = -1. We extend the triangle
 * backwards from the tip along (-dx, -dy) to form the base.
 */
function arrowHeadPath(
  tipX: number,
  tipY: number,
  dx: number,
  dy: number,
): string {
  // Base center: HEAD_LENGTH back from tip along the inverse normal (pointing
  // away from the element, into the shaft).
  const baseCx = tipX - dx * HEAD_LENGTH;
  const baseCy = tipY - dy * HEAD_LENGTH;
  // Perpendicular: (-dy, dx) rotated 90°.
  const px = -dy;
  const py = dx;
  const half = HEAD_WIDTH / 2;
  const left = { x: baseCx + px * half, y: baseCy + py * half };
  const right = { x: baseCx - px * half, y: baseCy - py * half };
  return `M ${tipX.toFixed(2)} ${tipY.toFixed(2)} L ${left.x.toFixed(2)} ${left.y.toFixed(2)} L ${right.x.toFixed(2)} ${right.y.toFixed(2)} Z`;
}
