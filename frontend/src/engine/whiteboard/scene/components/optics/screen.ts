/**
 * Detection screen component — a vertical line for optics experiments.
 *
 * Pure function: given x position + vertical extent → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { APPARATUS_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface ScreenParams {
  /** X position */
  x: number;
  /** Top y */
  yTop: number;
  /** Bottom y */
  yBottom: number;
  /** Optional label */
  label?: string;
  /** Stroke color (default textSecondary) */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function screen(params: ScreenParams): SceneGeometry {
  const { x, yTop, yBottom, label, color, id } = params;
  const strokeColor = color ?? COLORS.textSecondary;

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  paths.push({
    id: `${id}-line`,
    d: `M ${x} ${yTop} L ${x} ${yBottom}`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: strokeColor,
      strokeWidth: 2,
    },
  });

  if (label) {
    labels.push({
      id: `${id}-label`,
      text: label,
      x: x + 12,
      y: yTop + 15,
      anchor: "start",
      fontSize: 13,
      color: COLORS.textSecondary,
    });
  }

  const midY = (yTop + yBottom) / 2;

  return {
    paths,
    labels,
    bounds: { x, y: yTop, width: 1, height: yBottom - yTop },
    anchors: {
      top: { x, y: yTop },
      bottom: { x, y: yBottom },
      center: { x, y: midY },
    },
  };
}

export const screenDef: ComponentDef<ScreenParams> = {
  kind: "screen",
  render: screen,
  anchorNames: ["top", "bottom", "center"],
  defaultStyle: APPARATUS_STROKE,
};

registerComponent(screenDef);
