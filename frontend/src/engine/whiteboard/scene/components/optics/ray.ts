/**
 * Light ray component — a line with optional arrowhead and dashed variant.
 *
 * Pure function: given two endpoints → SceneGeometry.
 * Smaller arrowhead than force-arrow (head length 10, half-width 4).
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { LIGHT_RAY_DEFAULTS } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface RayParams {
  /** Start x */
  x1: number;
  /** Start y */
  y1: number;
  /** End x */
  x2: number;
  /** End y */
  y2: number;
  /** Dashed line (default false) */
  dashed?: boolean;
  /** Show arrowhead at end (default true) */
  showArrow?: boolean;
  /** Stroke color (default accentBlue) */
  color?: string;
  /** Optional label at midpoint */
  label?: string;
  /** Unique id prefix */
  id: string;
}

const HEAD_LENGTH = 10;
const HEAD_HALF_WIDTH = 4;

export function ray(params: RayParams): SceneGeometry {
  const {
    x1,
    y1,
    x2,
    y2,
    dashed = false,
    showArrow = true,
    color,
    label,
    id,
  } = params;

  const strokeColor = color ?? COLORS.accentBlue;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  if (len === 0) {
    return {
      paths: [],
      labels: [],
      bounds: { x: x1, y: y1, width: 0, height: 0 },
      anchors: {
        start: { x: x1, y: y1 },
        end: { x: x2, y: y2 },
        mid: { x: x1, y: y1 },
      },
    };
  }

  const ux = dx / len;
  const uy = dy / len;
  const px = -uy;
  const py = ux;

  const dashOpts = dashed ? { strokeLineDash: [8, 6] } : {};

  // Shaft (ends at arrowhead base if arrow shown)
  const shaftEndX =
    showArrow && len > HEAD_LENGTH ? x1 + ux * (len - HEAD_LENGTH) : x2;
  const shaftEndY =
    showArrow && len > HEAD_LENGTH ? y1 + uy * (len - HEAD_LENGTH) : y2;

  paths.push({
    id: `${id}-shaft`,
    d: `M ${x1} ${y1} L ${shaftEndX} ${shaftEndY}`,
    roughOptions: {
      ...LIGHT_RAY_DEFAULTS,
      stroke: strokeColor,
      ...dashOpts,
    },
  });

  // Arrowhead
  if (showArrow && len > HEAD_LENGTH) {
    const baseX = shaftEndX;
    const baseY = shaftEndY;
    const leftX = baseX + px * HEAD_HALF_WIDTH;
    const leftY = baseY + py * HEAD_HALF_WIDTH;
    const rightX = baseX - px * HEAD_HALF_WIDTH;
    const rightY = baseY - py * HEAD_HALF_WIDTH;

    paths.push({
      id: `${id}-head`,
      d: `M ${x2} ${y2} L ${leftX} ${leftY} L ${rightX} ${rightY} Z`,
      roughOptions: {
        ...LIGHT_RAY_DEFAULTS,
        stroke: strokeColor,
        fill: strokeColor,
        fillStyle: "solid",
        roughness: 0.3,
      },
    });
  }

  if (label) {
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    labels.push({
      id: `${id}-label`,
      text: label,
      x: midX + px * 14,
      y: midY + py * 14,
      anchor: "middle",
      fontSize: 12,
      color: strokeColor,
    });
  }

  const minX = Math.min(x1, x2);
  const minY = Math.min(y1, y2);
  const maxX = Math.max(x1, x2);
  const maxY = Math.max(y1, y2);

  return {
    paths,
    labels,
    bounds: {
      x: minX,
      y: minY,
      width: maxX - minX || 1,
      height: maxY - minY || 1,
    },
    anchors: {
      start: { x: x1, y: y1 },
      end: { x: x2, y: y2 },
      mid: { x: (x1 + x2) / 2, y: (y1 + y2) / 2 },
    },
  };
}

export const rayDef: ComponentDef<RayParams> = {
  kind: "ray",
  render: ray,
  anchorNames: ["start", "end", "mid"],
  defaultStyle: LIGHT_RAY_DEFAULTS,
};

registerComponent(rayDef);
