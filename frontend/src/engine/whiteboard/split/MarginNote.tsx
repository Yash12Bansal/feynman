/**
 * MarginNote — doc 19 §12 live-annotation primitive.
 *
 * A short text note anchored to one side of an element's bounds with a thin
 * lead-line connector. Renders in viewBox space, fades in over ~280ms, and
 * stays visible until the next clear_annotations / show_diagram.
 *
 * Used for tiny inline annotations next to an element — e.g., "= mg" next to
 * a force vector, or "ground frame" next to a parabola. Less heavy than a
 * full design diagram element; more contextual than a free-floating text.
 */

import { useRef, type RefObject } from "react";
import type { ElementMeta } from "../../../types/visuals";
import { useResolvedBounds } from "./SlideAnnotationLayer";

const CONNECTOR_LENGTH = 28;
const NOTE_PADDING = 10;
const NOTE_FONT = 16;

interface MarginNoteProps {
  readonly anchorElementId: string;
  readonly side: "top" | "bottom" | "left" | "right";
  readonly text: string;
  readonly dictionary: Record<string, ElementMeta> | undefined;
  readonly stageRef: RefObject<HTMLElement | null> | undefined;
  readonly overlayRef: RefObject<SVGSVGElement | null>;
}

export function MarginNote({
  anchorElementId,
  side,
  text,
  dictionary,
  stageRef,
  overlayRef,
}: MarginNoteProps) {
  const target = useRef({
    kind: "id" as const,
    value: anchorElementId,
  }).current;
  const bounds = useResolvedBounds(target, stageRef, overlayRef, dictionary);

  if (!bounds || !text.trim()) return null;
  const [bx, by, bw, bh] = bounds;

  const geom = computeNoteGeometry(bx, by, bw, bh, side, text);

  return (
    <g
      className="sb-margin-note"
      data-anchor-element-id={anchorElementId}
      data-side={side}
    >
      <line
        className="sb-margin-note-connector"
        x1={geom.connectorStartX}
        y1={geom.connectorStartY}
        x2={geom.connectorEndX}
        y2={geom.connectorEndY}
      />
      <text
        className="sb-margin-note-text"
        x={geom.textX}
        y={geom.textY}
        textAnchor={geom.textAnchor}
        dominantBaseline={geom.textBaseline}
        fontSize={NOTE_FONT}
      >
        {text.trim()}
      </text>
    </g>
  );
}

interface NoteGeometry {
  readonly connectorStartX: number;
  readonly connectorStartY: number;
  readonly connectorEndX: number;
  readonly connectorEndY: number;
  readonly textX: number;
  readonly textY: number;
  readonly textAnchor: "start" | "middle" | "end";
  readonly textBaseline: "auto" | "central" | "hanging";
}

function computeNoteGeometry(
  bx: number,
  by: number,
  bw: number,
  bh: number,
  side: "top" | "bottom" | "left" | "right",
  text: string,
): NoteGeometry {
  const cx = bx + bw / 2;
  const cy = by + bh / 2;
  const textLen = Math.max(28, text.trim().length * NOTE_FONT * 0.55);

  switch (side) {
    case "top": {
      const connectorStartX = cx;
      const connectorStartY = by;
      const connectorEndX = cx;
      const connectorEndY = by - CONNECTOR_LENGTH;
      return {
        connectorStartX,
        connectorStartY,
        connectorEndX,
        connectorEndY,
        textX: connectorEndX,
        textY: connectorEndY - NOTE_PADDING,
        textAnchor: "middle",
        textBaseline: "auto",
      };
    }
    case "bottom": {
      const connectorStartX = cx;
      const connectorStartY = by + bh;
      const connectorEndX = cx;
      const connectorEndY = by + bh + CONNECTOR_LENGTH;
      return {
        connectorStartX,
        connectorStartY,
        connectorEndX,
        connectorEndY,
        textX: connectorEndX,
        textY: connectorEndY + NOTE_PADDING,
        textAnchor: "middle",
        textBaseline: "hanging",
      };
    }
    case "left": {
      const connectorStartX = bx;
      const connectorStartY = cy;
      const connectorEndX = bx - CONNECTOR_LENGTH;
      const connectorEndY = cy;
      return {
        connectorStartX,
        connectorStartY,
        connectorEndX,
        connectorEndY,
        textX: connectorEndX - NOTE_PADDING,
        textY: connectorEndY,
        textAnchor: "end",
        textBaseline: "central",
      };
    }
    case "right": {
      const connectorStartX = bx + bw;
      const connectorStartY = cy;
      const connectorEndX = bx + bw + CONNECTOR_LENGTH;
      const connectorEndY = cy;
      // Width reserved for the text so future layout can avoid collisions —
      // declared here for completeness; not used by current geometry.
      void textLen;
      return {
        connectorStartX,
        connectorStartY,
        connectorEndX,
        connectorEndY,
        textX: connectorEndX + NOTE_PADDING,
        textY: connectorEndY,
        textAnchor: "start",
        textBaseline: "central",
      };
    }
  }
}
