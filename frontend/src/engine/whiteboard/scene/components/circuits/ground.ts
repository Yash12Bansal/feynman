/**
 * Ground component — 3 descending horizontal lines + vertical stem.
 *
 * Pure function: given a top point → SceneGeometry.
 * The stem connects to the circuit from the top anchor.
 */

import type { SceneGeometry, ScenePath } from "../../scene-types";
import { CIRCUIT_SYMBOL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface GroundParams {
  /** Top connection point x (or x1 for endpoint compatibility) */
  x1: number;
  /** Top connection point y (or y1 for endpoint compatibility) */
  y1: number;
  /** Ignored */
  x2?: number;
  /** Ignored */
  y2?: number;
  /** Total height of ground symbol below stem (default 20) */
  height?: number;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function ground(params: GroundParams): SceneGeometry {
  const { x1: cx, y1: top, height = 20, color, id } = params;

  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];

  const stemLen = 10;
  const stemBottom = top + stemLen;

  // Vertical stem
  paths.push({
    id: `${id}-stem`,
    d: `M ${cx} ${top} L ${cx} ${stemBottom}`,
    roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 1.8 },
  });

  // Three horizontal lines, each shorter and lower
  const lineWidths = [height, height * 0.65, height * 0.3];
  const lineGap = height / 4;

  for (let i = 0; i < 3; i++) {
    const y = stemBottom + i * lineGap;
    const halfW = lineWidths[i] / 2;
    paths.push({
      id: `${id}-line${i}`,
      d: `M ${cx - halfW} ${y} L ${cx + halfW} ${y}`,
      roughOptions: { ...CIRCUIT_SYMBOL, stroke: strokeColor, strokeWidth: 2 },
    });
  }

  const totalH = stemLen + 2 * lineGap;
  const halfW = height / 2;

  return {
    paths,
    labels: [],
    bounds: { x: cx - halfW, y: top, width: height || 1, height: totalH || 1 },
    anchors: {
      top: { x: cx, y: top },
      center: { x: cx, y: top + totalH / 2 },
    },
  };
}

export const groundDef: ComponentDef<GroundParams> = {
  kind: "ground",
  render: ground,
  anchorNames: ["top", "center"],
  defaultStyle: CIRCUIT_SYMBOL,
};

registerComponent(groundDef);
