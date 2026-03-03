/**
 * Free-body diagram template.
 *
 * Composes a block with force arrows (weight, normal, friction, applied)
 * and an optional spring. This is the first scene template — proving
 * the component → template → renderer pipeline.
 *
 * Layout: 500x400 scene coordinate space. Block centered.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../scene-types";
import { APPARATUS_FILLED, APPARATUS_STROKE } from "../scene-rough-helpers";
import { COLORS } from "../../../theme";
import { forceArrow } from "../components/force-arrow";
import { spring } from "../components/spring";
import { computeTightBounds } from "../scene-layout";

export interface FreeBodyParams {
  /** Downward weight arrow (default true) */
  showWeight?: boolean;
  /** Upward normal force arrow (default true) */
  showNormal?: boolean;
  /** Horizontal friction arrow (default false) */
  showFriction?: boolean;
  /** Horizontal applied force arrow, opposite friction (default false) */
  showApplied?: boolean;
  /** Spring attached to left of block (default false) */
  showSpring?: boolean;
  /** Direction friction acts (default "left") */
  frictionDirection?: "left" | "right";
}

// Scene dimensions
const SCENE_W = 500;
const SCENE_H = 400;

// Block dimensions and position
const BLOCK_W = 80;
const BLOCK_H = 60;
const BLOCK_CX = SCENE_W / 2;
const BLOCK_CY = SCENE_H / 2;

// Force arrow lengths
const ARROW_LEN = 100;

export function freeBodyDiagram(params: FreeBodyParams = {}): SceneGeometry {
  const {
    showWeight = true,
    showNormal = true,
    showFriction = false,
    showApplied = false,
    showSpring = false,
    frictionDirection = "left",
  } = params;

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // ── Surface line (ground) ────────────────────────────────────
  const surfaceY = BLOCK_CY + BLOCK_H / 2;
  paths.push({
    id: "surface",
    d: `M 60 ${surfaceY} L ${SCENE_W - 60} ${surfaceY}`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: COLORS.textSecondary,
      strokeWidth: 1.5,
    },
  });

  // Hatch marks below surface
  const hatchSpacing = 20;
  const hatchLen = 12;
  for (let hx = 80; hx < SCENE_W - 60; hx += hatchSpacing) {
    paths.push({
      id: `hatch-${hx}`,
      d: `M ${hx} ${surfaceY} L ${hx - 8} ${surfaceY + hatchLen}`,
      roughOptions: {
        ...APPARATUS_STROKE,
        stroke: COLORS.textSecondary,
        strokeWidth: 1,
        roughness: 0.5,
      },
    });
  }

  // ── Block ────────────────────────────────────────────────────
  const bx = BLOCK_CX - BLOCK_W / 2;
  const by = BLOCK_CY - BLOCK_H / 2;
  paths.push({
    id: "block",
    d: `M ${bx} ${by} L ${bx + BLOCK_W} ${by} L ${bx + BLOCK_W} ${by + BLOCK_H} L ${bx} ${by + BLOCK_H} Z`,
    roughOptions: {
      ...APPARATUS_FILLED,
      stroke: COLORS.accentBlue,
      fill: `${COLORS.accentBlue}22`,
    },
  });

  labels.push({
    id: "block-label",
    text: "m",
    x: BLOCK_CX,
    y: BLOCK_CY + 5,
    anchor: "middle",
    fontSize: 16,
    color: COLORS.accentBlue,
  });

  // ── Weight (downward) ────────────────────────────────────────
  if (showWeight) {
    const w = forceArrow({
      x: BLOCK_CX,
      y: BLOCK_CY,
      angle: 90, // down
      length: ARROW_LEN,
      color: COLORS.accentRed,
      label: "W",
      id: "weight",
    });
    paths.push(...w.paths);
    labels.push(...w.labels);
  }

  // ── Normal (upward) ──────────────────────────────────────────
  if (showNormal) {
    const n = forceArrow({
      x: BLOCK_CX,
      y: BLOCK_CY,
      angle: 270, // up
      length: ARROW_LEN,
      color: COLORS.accentGreen,
      label: "N",
      id: "normal",
    });
    paths.push(...n.paths);
    labels.push(...n.labels);
  }

  // ── Friction (horizontal) ────────────────────────────────────
  if (showFriction) {
    const fAngle = frictionDirection === "left" ? 180 : 0;
    const f = forceArrow({
      x: BLOCK_CX,
      y: BLOCK_CY,
      angle: fAngle,
      length: ARROW_LEN * 0.7,
      color: COLORS.accentAmber,
      label: "f",
      id: "friction",
    });
    paths.push(...f.paths);
    labels.push(...f.labels);
  }

  // ── Applied force (opposite to friction) ─────────────────────
  if (showApplied) {
    const aAngle = frictionDirection === "left" ? 0 : 180;
    const a = forceArrow({
      x: BLOCK_CX,
      y: BLOCK_CY,
      angle: aAngle,
      length: ARROW_LEN,
      color: COLORS.accentPurple,
      label: "F",
      id: "applied",
    });
    paths.push(...a.paths);
    labels.push(...a.labels);
  }

  // ── Spring (left side, attached to wall) ─────────────────────
  if (showSpring) {
    const wallX = 40;
    const wallTop = BLOCK_CY - BLOCK_H;
    const wallBottom = BLOCK_CY + BLOCK_H;

    // Wall line
    paths.push({
      id: "wall",
      d: `M ${wallX} ${wallTop} L ${wallX} ${wallBottom}`,
      roughOptions: {
        ...APPARATUS_STROKE,
        stroke: COLORS.textSecondary,
      },
    });

    // Wall hatch marks
    for (let hy = wallTop; hy < wallBottom; hy += 15) {
      paths.push({
        id: `wall-hatch-${hy}`,
        d: `M ${wallX} ${hy} L ${wallX - 10} ${hy + 10}`,
        roughOptions: {
          ...APPARATUS_STROKE,
          stroke: COLORS.textSecondary,
          strokeWidth: 1,
          roughness: 0.5,
        },
      });
    }

    // Spring from wall to block
    const s = spring({
      x1: wallX,
      y1: BLOCK_CY,
      x2: bx,
      y2: BLOCK_CY,
      coils: 8,
      amplitude: 10,
      id: "spring",
      color: COLORS.textPrimary,
    });
    paths.push(...s.paths);
    labels.push(...s.labels);
  }

  return {
    paths,
    labels,
    bounds: computeTightBounds(paths, labels, 30),
    anchors: {
      blockCenter: { x: BLOCK_CX, y: BLOCK_CY },
    },
  };
}
