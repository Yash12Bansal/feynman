/**
 * Molecule component — rounded rectangle badge with chemical formula text.
 *
 * Pure function: given center + label → SceneGeometry.
 * Renders optional stoichiometric coefficient prefix and state subscript.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../../scene-types";
import { CHEM_LABEL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import type { ComponentDef } from "../types";
import { registerComponent } from "../registry";

export interface MoleculeParams {
  /** Center x */
  cx: number;
  /** Center y */
  cy: number;
  /** Chemical formula (e.g. "H₂O") */
  label?: string;
  /** Stoichiometric coefficient (e.g. 2 for "2H₂O") */
  coefficient?: number;
  /** State of matter: "s", "l", "g", "aq" */
  state?: string;
  /** Stroke color override */
  color?: string;
  /** Unique id prefix */
  id: string;
}

const BADGE_PADDING_X = 16;
const BADGE_PADDING_Y = 10;
const FONT_SIZE = 16;
const CORNER_RADIUS = 8;

export function molecule(params: MoleculeParams): SceneGeometry {
  const { cx, cy, label = "", coefficient, state, color, id } = params;
  const strokeColor = color ?? COLORS.textPrimary;
  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // Build display text
  let displayText = "";
  if (coefficient && coefficient > 1) {
    displayText += `${coefficient}`;
  }
  displayText += label;
  if (state) {
    displayText += `(${state})`;
  }

  // Compute badge dimensions based on text
  const charWidth = FONT_SIZE * 0.6;
  const textWidth = displayText.length * charWidth;
  const badgeW = Math.max(textWidth + BADGE_PADDING_X * 2, 50);
  const badgeH = FONT_SIZE + BADGE_PADDING_Y * 2;

  const left = cx - badgeW / 2;
  const top = cy - badgeH / 2;
  const right = cx + badgeW / 2;
  const bottom = cy + badgeH / 2;
  const r = Math.min(CORNER_RADIUS, badgeW / 4, badgeH / 4);

  // Rounded rectangle path
  const d =
    `M ${left + r} ${top} ` +
    `L ${right - r} ${top} ` +
    `Q ${right} ${top} ${right} ${top + r} ` +
    `L ${right} ${bottom - r} ` +
    `Q ${right} ${bottom} ${right - r} ${bottom} ` +
    `L ${left + r} ${bottom} ` +
    `Q ${left} ${bottom} ${left} ${bottom - r} ` +
    `L ${left} ${top + r} ` +
    `Q ${left} ${top} ${left + r} ${top} Z`;

  paths.push({
    id: `${id}-badge`,
    d,
    roughOptions: {
      ...CHEM_LABEL,
      stroke: strokeColor,
      fill: `${strokeColor}15`,
      fillStyle: "solid",
    },
  });

  if (displayText) {
    labels.push({
      id: `${id}-formula`,
      text: displayText,
      x: cx,
      y: cy + 5,
      anchor: "middle",
      fontSize: FONT_SIZE,
      color: strokeColor,
    });
  }

  return {
    paths,
    labels,
    bounds: { x: left, y: top, width: badgeW, height: badgeH },
    anchors: {
      center: { x: cx, y: cy },
      left: { x: left, y: cy },
      right: { x: right, y: cy },
      top: { x: cx, y: top },
      bottom: { x: cx, y: bottom },
    },
  };
}

export const moleculeDef: ComponentDef<MoleculeParams> = {
  kind: "molecule",
  render: molecule,
  anchorNames: ["center", "left", "right", "top", "bottom"],
  defaultStyle: CHEM_LABEL,
};

registerComponent(moleculeDef);
