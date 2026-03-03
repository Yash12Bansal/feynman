/**
 * Box component — a rectangular block with hachure fill and optional label.
 *
 * Pure function: given center + dimensions → SceneGeometry.
 * Matches the manual block style in free-body.ts (APPARATUS_FILLED + accentBlue).
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../scene-types";
import { APPARATUS_FILLED } from "../scene-rough-helpers";
import { COLORS } from "../../../theme";
import type { ComponentDef } from "./types";
import { registerComponent } from "./registry";

export interface BoxParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Box width (default 80) */
  width?: number;
  /** Box height (default 60) */
  height?: number;
  /** Optional text label at center */
  label?: string;
  /** Stroke/label color (default accentBlue) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const DEFAULT_WIDTH = 80;
const DEFAULT_HEIGHT = 60;

export function box(params: BoxParams): SceneGeometry {
  const {
    cx,
    cy,
    width = DEFAULT_WIDTH,
    height = DEFAULT_HEIGHT,
    label,
    color,
    id,
  } = params;

  const strokeColor = color ?? COLORS.accentBlue;

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Rectangle corners
  const left = cx - width / 2;
  const top = cy - height / 2;
  const right = cx + width / 2;
  const bottom = cy + height / 2;

  paths.push({
    id: `${id}-rect`,
    d: `M ${left} ${top} L ${right} ${top} L ${right} ${bottom} L ${left} ${bottom} Z`,
    roughOptions: {
      ...APPARATUS_FILLED,
      stroke: strokeColor,
      fill: `${strokeColor}22`,
    },
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: cx,
      y: cy + 5,
      anchor: "middle",
      fontSize: 16,
      color: strokeColor,
    });
  }

  return {
    paths,
    labels,
    bounds: { x: left, y: top, width, height },
    anchors: {
      center: { x: cx, y: cy },
      top: { x: cx, y: top },
      bottom: { x: cx, y: bottom },
      left: { x: left, y: cy },
      right: { x: right, y: cy },
      topLeft: { x: left, y: top },
      topRight: { x: right, y: top },
      bottomLeft: { x: left, y: bottom },
      bottomRight: { x: right, y: bottom },
    },
  };
}

/** Registry definition for the box component. */
export const boxDef: ComponentDef<BoxParams> = {
  kind: "box",
  render: box,
  anchorNames: [
    "center",
    "top",
    "bottom",
    "left",
    "right",
    "topLeft",
    "topRight",
    "bottomLeft",
    "bottomRight",
  ],
  defaultStyle: APPARATUS_FILLED,
};

registerComponent(boxDef);
