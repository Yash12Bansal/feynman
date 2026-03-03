/**
 * Barrier component — a solid wall with optional slits (gaps).
 *
 * Pure function: given position + slit positions → SceneGeometry.
 * Renders filled rectangles with gaps at each slit location.
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { BARRIER_SOLID } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface SlitSpec {
  /** Slit center y position */
  y: number;
  /** Half-width of the slit opening (default 6) */
  halfWidth?: number;
}

export interface BarrierParams {
  /** Left edge x */
  x: number;
  /** Top y */
  yTop: number;
  /** Bottom y */
  yBottom: number;
  /** Barrier width (default 20) */
  width?: number;
  /** Slit definitions */
  slits?: SlitSpec[];
  /** Fill/stroke color (default textSecondary) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function barrier(params: BarrierParams): SceneGeometry {
  const { x, yTop, yBottom, width = 20, slits = [], color, id } = params;

  const strokeColor = color ?? COLORS.textSecondary;
  const right = x + width;

  const paths: ScenePath[] = [];
  const anchors: Record<string, { x: number; y: number }> = {};

  // Sort slits by y position
  const sorted = [...slits].sort((a, b) => a.y - b.y);

  // Build solid sections between slits
  const edges: number[] = [yTop];
  for (const slit of sorted) {
    const hw = slit.halfWidth ?? 6;
    edges.push(slit.y - hw);
    edges.push(slit.y + hw);
  }
  edges.push(yBottom);

  // Each pair of edges forms a filled rectangle
  for (let i = 0; i < edges.length; i += 2) {
    const sectionTop = edges[i];
    const sectionBottom = edges[i + 1];
    if (sectionBottom <= sectionTop) continue;

    paths.push({
      id: `${id}-section-${i}`,
      d: `M ${x} ${sectionTop} L ${right} ${sectionTop} L ${right} ${sectionBottom} L ${x} ${sectionBottom} Z`,
      roughOptions: {
        ...BARRIER_SOLID,
        stroke: strokeColor,
        fill: strokeColor,
      },
    });
  }

  // Anchors
  const midY = (yTop + yBottom) / 2;
  anchors.top = { x: x + width / 2, y: yTop };
  anchors.bottom = { x: x + width / 2, y: yBottom };
  anchors.center = { x: x + width / 2, y: midY };

  // Slit anchors (at the exit side of each slit)
  for (let i = 0; i < sorted.length; i++) {
    anchors[`slit-${i}`] = { x: right, y: sorted[i].y };
  }

  return {
    paths,
    labels: [],
    bounds: { x, y: yTop, width, height: yBottom - yTop },
    anchors,
  };
}

export const barrierDef: ComponentDef<BarrierParams> = {
  kind: "barrier",
  render: barrier,
  anchorNames: ["top", "bottom", "center"],
  defaultStyle: BARRIER_SOLID,
};

registerComponent(barrierDef);
