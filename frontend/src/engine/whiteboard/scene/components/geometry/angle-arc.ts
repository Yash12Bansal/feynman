/**
 * Angle arc component — arc between two rays emanating from a vertex.
 *
 * Always draws the shorter arc (< 180°). Label at the bisector.
 * Pure function: given vertex + two ray points → SceneGeometry.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { GEOMETRY_ANNOTATION } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";
import { normalizeAngle } from "./utils";

export interface AngleArcParams {
  /** Vertex */
  x1: number;
  y1: number;
  /** Point on ray 1 */
  x2: number;
  y2: number;
  /** Point on ray 2 */
  x3: number;
  y3: number;
  /** Arc radius from vertex (default 20) */
  radius?: number;
  /** Optional angle label (e.g. "60°") */
  label?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

export function angleArc(params: AngleArcParams): SceneGeometry {
  const { x1, y1, x2, y2, x3, y3, radius = 20, label, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Angles from vertex to each ray point
  const angle1 = normalizeAngle(Math.atan2(y2 - y1, x2 - x1));
  const angle2 = normalizeAngle(Math.atan2(y3 - y1, x3 - x1));

  // Always draw the shorter arc
  let startAngle = angle1;
  let endAngle = angle2;
  let diff = normalizeAngle(endAngle - startAngle);

  if (diff > Math.PI) {
    // Swap to get the shorter arc
    startAngle = angle2;
    endAngle = angle1;
    diff = normalizeAngle(endAngle - startAngle);
  }

  // Arc start and end points
  const arcStartX = x1 + radius * Math.cos(startAngle);
  const arcStartY = y1 + radius * Math.sin(startAngle);
  const arcEndX = x1 + radius * Math.cos(endAngle);
  const arcEndY = y1 + radius * Math.sin(endAngle);

  // SVG arc: large-arc-flag = 0 (always short arc), sweep = 1 (clockwise)
  const largeArc = 0;
  const sweep = 1;
  const d =
    `M ${arcStartX} ${arcStartY} ` +
    `A ${radius} ${radius} 0 ${largeArc} ${sweep} ${arcEndX} ${arcEndY}`;

  paths.push({
    id: `${id}-arc`,
    d,
    roughOptions: { ...GEOMETRY_ANNOTATION, stroke: strokeColor },
  });

  // Label at bisector
  if (label) {
    const bisector = startAngle + diff / 2;
    const labelDist = radius + 12;
    labels.push({
      id: `${id}-label`,
      text: label,
      x: x1 + labelDist * Math.cos(bisector),
      y: y1 + labelDist * Math.sin(bisector),
      anchor: "middle",
      fontSize: 12,
      color: strokeColor,
    });
  }

  const allX = [arcStartX, arcEndX];
  const allY = [arcStartY, arcEndY];
  const minX = Math.min(...allX);
  const minY = Math.min(...allY);
  const maxX = Math.max(...allX);
  const maxY = Math.max(...allY);

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
      vertex: { x: x1, y: y1 },
      arcStart: { x: arcStartX, y: arcStartY },
      arcEnd: { x: arcEndX, y: arcEndY },
    },
  };
}

export const angleArcDef: ComponentDef<AngleArcParams> = {
  kind: "angle-arc",
  render: angleArc,
  anchorNames: ["vertex", "arcStart", "arcEnd"],
  defaultStyle: GEOMETRY_ANNOTATION,
};

registerComponent(angleArcDef);
