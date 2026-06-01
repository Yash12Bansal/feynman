/**
 * Pointer — doc 19 §12 live-annotation primitive ("look here").
 *
 * Draws an arrow pointing AT an element from one side. Rebuilt on the hardened
 * bounds core (the original was deleted in 04cec94 because it drew at
 * misresolved positions): it resolves the target's bounds via
 * `useResolvedBounds` — which now measures the live DOM with correct timing and
 * returns `null` (→ render nothing) on any failure — so a bad resolve can never
 * draw a stray arrow.
 *
 * Renders in the annotation overlay's viewBox space, which (post-P0) coincides
 * exactly with the diagram, so the apex lands on the element's edge.
 */

import { useMemo, type RefObject } from "react";
import type { AnnotationTarget, ElementMeta } from "../../../types/visuals";
import { useResolvedBounds } from "./SlideAnnotationLayer";

const SHAFT_LEN = 46; // length of the arrow shaft, viewBox units
const GAP = 9; // gap between the arrowhead apex and the element edge
const HEAD_LEN = 15;
const HEAD_HALF_W = 7;

interface PointerProps {
  readonly elementId: string;
  readonly fromSide: "top" | "bottom" | "left" | "right";
  readonly dictionary: Record<string, ElementMeta> | undefined;
  readonly stageRef: RefObject<HTMLElement | null> | undefined;
  readonly overlayRef: RefObject<SVGSVGElement | null>;
}

interface PointerGeometry {
  readonly shaftX1: number;
  readonly shaftY1: number;
  readonly shaftX2: number;
  readonly shaftY2: number;
  readonly head: string; // path `d` for the filled triangle
  /** Entrance offset (the arrow slides in from its tail) as CSS vars. */
  readonly bounceX: number;
  readonly bounceY: number;
}

export function Pointer({
  elementId,
  fromSide,
  dictionary,
  stageRef,
  overlayRef,
}: PointerProps) {
  const target = useMemo<AnnotationTarget>(
    () => ({ kind: "id", value: elementId }),
    [elementId],
  );
  const bounds = useResolvedBounds(target, stageRef, overlayRef, dictionary);

  if (!bounds) return null;
  const [bx, by, bw, bh] = bounds;
  const geom = computeGeometry(bx, by, bw, bh, fromSide);

  return (
    <g
      className="sb-pointer"
      data-element-id={elementId}
      data-from-side={fromSide}
      style={
        {
          "--pointer-bounce-x": `${geom.bounceX}px`,
          "--pointer-bounce-y": `${geom.bounceY}px`,
        } as React.CSSProperties
      }
    >
      <line
        className="sb-pointer-shaft"
        x1={geom.shaftX1}
        y1={geom.shaftY1}
        x2={geom.shaftX2}
        y2={geom.shaftY2}
      />
      <path className="sb-pointer-head" d={geom.head} />
    </g>
  );
}

function computeGeometry(
  bx: number,
  by: number,
  bw: number,
  bh: number,
  side: "top" | "bottom" | "left" | "right",
): PointerGeometry {
  const cx = bx + bw / 2;
  const cy = by + bh / 2;

  switch (side) {
    case "left": {
      const apexX = bx - GAP;
      const backX = apexX - HEAD_LEN;
      return {
        shaftX1: backX - SHAFT_LEN,
        shaftY1: cy,
        shaftX2: backX,
        shaftY2: cy,
        head: triangle(
          apexX,
          cy,
          backX,
          cy - HEAD_HALF_W,
          backX,
          cy + HEAD_HALF_W,
        ),
        bounceX: -16,
        bounceY: 0,
      };
    }
    case "right": {
      const apexX = bx + bw + GAP;
      const backX = apexX + HEAD_LEN;
      return {
        shaftX1: backX + SHAFT_LEN,
        shaftY1: cy,
        shaftX2: backX,
        shaftY2: cy,
        head: triangle(
          apexX,
          cy,
          backX,
          cy - HEAD_HALF_W,
          backX,
          cy + HEAD_HALF_W,
        ),
        bounceX: 16,
        bounceY: 0,
      };
    }
    case "top": {
      const apexY = by - GAP;
      const backY = apexY - HEAD_LEN;
      return {
        shaftX1: cx,
        shaftY1: backY - SHAFT_LEN,
        shaftX2: cx,
        shaftY2: backY,
        head: triangle(
          cx,
          apexY,
          cx - HEAD_HALF_W,
          backY,
          cx + HEAD_HALF_W,
          backY,
        ),
        bounceX: 0,
        bounceY: -16,
      };
    }
    case "bottom": {
      const apexY = by + bh + GAP;
      const backY = apexY + HEAD_LEN;
      return {
        shaftX1: cx,
        shaftY1: backY + SHAFT_LEN,
        shaftX2: cx,
        shaftY2: backY,
        head: triangle(
          cx,
          apexY,
          cx - HEAD_HALF_W,
          backY,
          cx + HEAD_HALF_W,
          backY,
        ),
        bounceX: 0,
        bounceY: 16,
      };
    }
  }
}

function triangle(
  ax: number,
  ay: number,
  bx: number,
  by: number,
  cx: number,
  cy: number,
): string {
  return `M ${ax.toFixed(2)} ${ay.toFixed(2)} L ${bx.toFixed(2)} ${by.toFixed(
    2,
  )} L ${cx.toFixed(2)} ${cy.toFixed(2)} Z`;
}
