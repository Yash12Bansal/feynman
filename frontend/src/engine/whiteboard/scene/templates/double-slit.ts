/**
 * Double-slit experiment template.
 *
 * Renders a light source, barrier with two slits, wavefront arcs,
 * detection screen, and interference pattern. Exercises very different
 * SVG primitives (arcs, filled rectangles, thin lines) from the
 * free-body diagram.
 *
 * Layout: 700x400 scene coordinate space. Three sections left-to-right:
 * source → barrier → screen.
 */

import type { SceneGeometry, ScenePath, SceneLabel } from "../scene-types";
import {
  LIGHT_RAY_DEFAULTS,
  WAVEFRONT_DEFAULTS,
  BARRIER_SOLID,
  APPARATUS_STROKE,
} from "../scene-rough-helpers";
import { COLORS } from "../../../theme";
import { computeTightBounds } from "../scene-layout";

export interface DoubleSlitParams {
  /** Show wavefront arcs from each slit (default true) */
  showWaves?: boolean;
  /** Show interference pattern on screen (default true) */
  showPattern?: boolean;
  /** Show rays from source to slits (default true) */
  showRays?: boolean;
  /** Show labels (default true) */
  showLabels?: boolean;
  /** Slit separation — affects fringe spacing (default "narrow") */
  slitSeparation?: "narrow" | "wide";
}

// ── Layout constants ─────────────────────────────────────────

const SOURCE_X = 60;
const SOURCE_Y = 200;
const SOURCE_RADIUS = 6;

const BARRIER_X = 220;
const BARRIER_W = 20;
const BARRIER_TOP = 50;
const BARRIER_BOTTOM = 350;
const CENTER_Y = 200;
const SLIT_HALF_WIDTH = 6;

const NARROW_D = 50;
const WIDE_D = 80;

const SCREEN_X = 580;
const SCREEN_TOP = 50;
const SCREEN_BOTTOM = 350;
const BAND_WIDTH = 25;

const WAVEFRONT_RADII = [40, 80, 120];

const NUM_BRIGHT = 7;
const NUM_DARK = 6;
const TOTAL_BANDS = NUM_BRIGHT + NUM_DARK;

// ── Template ─────────────────────────────────────────────────

export function doubleSlit(params: DoubleSlitParams = {}): SceneGeometry {
  const {
    showWaves = true,
    showPattern = true,
    showRays = true,
    showLabels = true,
    slitSeparation = "narrow",
  } = params;

  const d = slitSeparation === "wide" ? WIDE_D : NARROW_D;
  const slit1Y = CENTER_Y - d / 2;
  const slit2Y = CENTER_Y + d / 2;

  const slit1Top = slit1Y - SLIT_HALF_WIDTH;
  const slit1Bottom = slit1Y + SLIT_HALF_WIDTH;
  const slit2Top = slit2Y - SLIT_HALF_WIDTH;
  const slit2Bottom = slit2Y + SLIT_HALF_WIDTH;

  const barrierRight = BARRIER_X + BARRIER_W;

  const paths: ScenePath[] = [];
  const labels: SceneLabel[] = [];

  // ── Light source (always visible) ──────────────────────────
  // Full circle via two semicircular arcs
  paths.push({
    id: "source",
    d: [
      `M ${SOURCE_X - SOURCE_RADIUS} ${SOURCE_Y}`,
      `A ${SOURCE_RADIUS} ${SOURCE_RADIUS} 0 1 1 ${SOURCE_X + SOURCE_RADIUS} ${SOURCE_Y}`,
      `A ${SOURCE_RADIUS} ${SOURCE_RADIUS} 0 1 1 ${SOURCE_X - SOURCE_RADIUS} ${SOURCE_Y}`,
      "Z",
    ].join(" "),
    roughOptions: {
      ...LIGHT_RAY_DEFAULTS,
      stroke: COLORS.accentBlue,
      fill: COLORS.accentBlue,
      fillStyle: "solid",
      roughness: 0.3,
    },
  });

  // ── Barrier with two slits (always visible) ────────────────
  // Top section
  paths.push({
    id: "barrier-top",
    d: `M ${BARRIER_X} ${BARRIER_TOP} L ${barrierRight} ${BARRIER_TOP} L ${barrierRight} ${slit1Top} L ${BARRIER_X} ${slit1Top} Z`,
    roughOptions: {
      ...BARRIER_SOLID,
      stroke: COLORS.textSecondary,
      fill: COLORS.textSecondary,
    },
  });

  // Middle section (between slits)
  paths.push({
    id: "barrier-middle",
    d: `M ${BARRIER_X} ${slit1Bottom} L ${barrierRight} ${slit1Bottom} L ${barrierRight} ${slit2Top} L ${BARRIER_X} ${slit2Top} Z`,
    roughOptions: {
      ...BARRIER_SOLID,
      stroke: COLORS.textSecondary,
      fill: COLORS.textSecondary,
    },
  });

  // Bottom section
  paths.push({
    id: "barrier-bottom",
    d: `M ${BARRIER_X} ${slit2Bottom} L ${barrierRight} ${slit2Bottom} L ${barrierRight} ${BARRIER_BOTTOM} L ${BARRIER_X} ${BARRIER_BOTTOM} Z`,
    roughOptions: {
      ...BARRIER_SOLID,
      stroke: COLORS.textSecondary,
      fill: COLORS.textSecondary,
    },
  });

  // ── Detection screen (always visible) ──────────────────────
  paths.push({
    id: "screen",
    d: `M ${SCREEN_X} ${SCREEN_TOP} L ${SCREEN_X} ${SCREEN_BOTTOM}`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: COLORS.textSecondary,
      strokeWidth: 2,
    },
  });

  // ── Rays from source to slits ──────────────────────────────
  if (showRays) {
    paths.push({
      id: "slit-ray-1",
      d: `M ${SOURCE_X} ${SOURCE_Y} L ${BARRIER_X} ${slit1Y}`,
      roughOptions: {
        ...LIGHT_RAY_DEFAULTS,
        stroke: COLORS.accentBlue,
      },
    });

    paths.push({
      id: "slit-ray-2",
      d: `M ${SOURCE_X} ${SOURCE_Y} L ${BARRIER_X} ${slit2Y}`,
      roughOptions: {
        ...LIGHT_RAY_DEFAULTS,
        stroke: COLORS.accentBlue,
      },
    });
  }

  // ── Wavefront arcs from each slit ──────────────────────────
  if (showWaves) {
    const waveColor = `${COLORS.accentBlue}99`; // ~60% opacity

    for (const [si, slitY] of [slit1Y, slit2Y].entries()) {
      for (const [ri, r] of WAVEFRONT_RADII.entries()) {
        // Rightward semicircular arc from (barrierRight, slitY-r)
        // to (barrierRight, slitY+r)
        paths.push({
          id: `wavefront-s${si + 1}-${ri}`,
          d: `M ${barrierRight} ${slitY - r} A ${r} ${r} 0 0 1 ${barrierRight} ${slitY + r}`,
          roughOptions: {
            ...WAVEFRONT_DEFAULTS,
            stroke: waveColor,
          },
        });
      }
    }
  }

  // ── Interference pattern on screen ─────────────────────────
  if (showPattern) {
    const screenHeight = SCREEN_BOTTOM - SCREEN_TOP;
    const bandHeight = screenHeight / TOTAL_BANDS;

    let brightIdx = 0;
    let darkIdx = 0;

    for (let i = 0; i < TOTAL_BANDS; i++) {
      const bandTop = SCREEN_TOP + i * bandHeight;
      const bandBottom = SCREEN_TOP + (i + 1) * bandHeight;
      const isBright = i % 2 === 0;

      if (isBright) {
        paths.push({
          id: `bright-band-${brightIdx}`,
          d: `M ${SCREEN_X} ${bandTop} L ${SCREEN_X + BAND_WIDTH} ${bandTop} L ${SCREEN_X + BAND_WIDTH} ${bandBottom} L ${SCREEN_X} ${bandBottom} Z`,
          roughOptions: {
            roughness: 0.6,
            bowing: 0.3,
            strokeWidth: 0.5,
            stroke: COLORS.accentGreen,
            fill: COLORS.accentGreen,
            fillStyle: "hachure",
            fillWeight: 1,
            hachureGap: 4,
          },
        });
        brightIdx++;
      } else {
        paths.push({
          id: `dark-band-${darkIdx}`,
          d: `M ${SCREEN_X} ${bandTop} L ${SCREEN_X + BAND_WIDTH} ${bandTop} L ${SCREEN_X + BAND_WIDTH} ${bandBottom} L ${SCREEN_X} ${bandBottom} Z`,
          roughOptions: {
            roughness: 0.6,
            bowing: 0.3,
            strokeWidth: 0.5,
            stroke: `${COLORS.accentRed}33`,
            fill: `${COLORS.accentRed}33`,
            fillStyle: "solid",
          },
        });
        darkIdx++;
      }
    }
  }

  // ── Labels ─────────────────────────────────────────────────
  if (showLabels) {
    labels.push({
      id: "source-label",
      text: "Light source",
      x: SOURCE_X,
      y: SOURCE_Y - 22,
      anchor: "middle",
      fontSize: 13,
      color: COLORS.textSecondary,
    });

    labels.push({
      id: "slit-sep-label",
      text: "d",
      x: BARRIER_X - 14,
      y: CENTER_Y + 5,
      anchor: "end",
      fontSize: 15,
      color: COLORS.textPrimary,
    });

    labels.push({
      id: "screen-label",
      text: "Screen",
      x: SCREEN_X + BAND_WIDTH + 10,
      y: SCREEN_TOP + 15,
      anchor: "start",
      fontSize: 13,
      color: COLORS.textSecondary,
    });
  }

  return {
    paths,
    labels,
    bounds: computeTightBounds(paths, labels, 30),
    anchors: {
      source: { x: SOURCE_X, y: SOURCE_Y },
      slit1: { x: BARRIER_X, y: slit1Y },
      slit2: { x: BARRIER_X, y: slit2Y },
      screenCenter: { x: SCREEN_X, y: CENTER_Y },
    },
  };
}
