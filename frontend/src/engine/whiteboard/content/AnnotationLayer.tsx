/**
 * SVG overlay layer for freehand annotations.
 *
 * Positioned absolutely covering the full 1920×1080 board surface.
 * pointer-events: none so it doesn't intercept clicks.
 * Renders one <AnnotationOverlay> per annotation instruction.
 */

import type { RefObject } from "react";
import type { AnnotateInstruction } from "../../../types/visuals";
import { BOARD_WIDTH, BOARD_HEIGHT } from "../types";
import { AnnotationOverlay } from "./AnnotationOverlay";

export interface AnnotationLayerProps {
  annotations: AnnotateInstruction[];
  boardRef: RefObject<HTMLDivElement | null>;
  scale: number;
}

export function AnnotationLayer({
  annotations,
  boardRef,
  scale,
}: AnnotationLayerProps) {
  if (annotations.length === 0) return null;

  return (
    <svg
      className="wb-annotation-layer"
      width={BOARD_WIDTH}
      height={BOARD_HEIGHT}
      viewBox={`0 0 ${BOARD_WIDTH} ${BOARD_HEIGHT}`}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        pointerEvents: "none",
        zIndex: 10,
      }}
    >
      {annotations.map((instr, idx) => (
        <AnnotationOverlay
          key={`ann-${instr.element_id ?? instr.action}-${idx}`}
          instruction={instr}
          boardRef={boardRef}
          scale={scale}
        />
      ))}
    </svg>
  );
}
