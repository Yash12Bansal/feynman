/**
 * LeftToRightOpticalBench — layout strategy for optics diagrams.
 *
 * Two modes:
 * - Ray optics: lens + object → auto-compute image via thin lens equation + 3 principal rays
 * - Wave optics: source + barrier with slits → auto-generate wavefronts + interference pattern
 *
 * The LLM sends semantic elements (lens kind, focal length, object distance).
 * This strategy does ALL the physics and spatial computation.
 */

// Side-effect imports: ensure optics components are registered
import "../../components/optics";
import "../../components/force-arrow";

import type {
  SemanticSceneElement,
  LayoutContext,
  SceneGeometry,
} from "../types";
import type { ScenePath, SceneLabel } from "../../scene-types";
import { getComponent } from "../../components/registry";
import { computeTightBounds } from "../../scene-layout";
import {
  APPARATUS_STROKE,
  LIGHT_RAY_DEFAULTS,
} from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import { registerStrategy } from "../registry";

// ── Helpers ──────────────────────────────────────────────────

function normalizeKind(kind: string): string {
  return kind.replace(/_/g, "-");
}

function findByKind(
  elements: SemanticSceneElement[],
  kind: string,
): SemanticSceneElement[] {
  return elements.filter((el) => normalizeKind(el.kind) === kind);
}

function getExtra<T>(el: SemanticSceneElement, key: string, fallback: T): T {
  if (el.extras && key in el.extras) return el.extras[key] as T;
  return fallback;
}

// ── Strategy ─────────────────────────────────────────────────

function leftToRightOpticalBench(
  elements: SemanticSceneElement[],
  context: LayoutContext,
): SceneGeometry {
  const allPaths: ScenePath[] = [];
  const allLabels: SceneLabel[] = [];
  const { sceneWidth, sceneHeight } = context;
  const axisY = sceneHeight / 2;

  // Optical axis: dashed horizontal line
  allPaths.push({
    id: "optical-axis",
    d: `M 20 ${axisY} L ${sceneWidth - 20} ${axisY}`,
    roughOptions: {
      ...APPARATUS_STROKE,
      stroke: COLORS.textSecondary,
      strokeWidth: 1,
      roughness: 0.3,
      strokeLineDash: [6, 6],
    },
  });

  // Classify mode
  const lenses = [
    ...findByKind(elements, "convex-lens"),
    ...findByKind(elements, "concave-lens"),
  ];
  const barriers = findByKind(elements, "barrier");
  const hasSlits = barriers.some((b) => getExtra(b, "slit_count", 0) > 0);

  if (lenses.length > 0) {
    renderRayOptics(elements, lenses, context, axisY, allPaths, allLabels);
  } else if (hasSlits || barriers.length > 0) {
    renderWaveOptics(elements, barriers, context, axisY, allPaths, allLabels);
  }

  return {
    paths: allPaths,
    labels: allLabels,
    bounds: computeTightBounds(allPaths, allLabels, 30),
    anchors: {
      axisCenter: { x: sceneWidth / 2, y: axisY },
    },
  };
}

// ── Ray Optics Mode ──────────────────────────────────────────

function renderRayOptics(
  elements: SemanticSceneElement[],
  lenses: SemanticSceneElement[],
  context: LayoutContext,
  axisY: number,
  allPaths: ScenePath[],
  allLabels: SceneLabel[],
): void {
  const { sceneWidth, sceneHeight } = context;
  const lensEl = lenses[0];
  const lensKind = normalizeKind(lensEl.kind);
  const isConvex = lensKind === "convex-lens";

  const f = getExtra(lensEl, "focal_length", 80) as number;
  const lensX = sceneWidth / 2;
  const lensHeight = sceneHeight * 0.6;

  // Draw lens
  const lensComp = getComponent(lensKind);
  if (lensComp) {
    const lensGeom = lensComp.render({
      cx: lensX,
      cy: axisY,
      height: lensHeight,
      label: lensEl.label,
      color: lensEl.color,
      id: lensEl.id,
    });
    allPaths.push(...lensGeom.paths);
    allLabels.push(...lensGeom.labels);
  }

  // Focal point markers
  const focalPoints = [
    { x: lensX - f, label: "F" },
    { x: lensX + f, label: "F'" },
  ];
  for (const fp of focalPoints) {
    allPaths.push({
      id: `focal-${fp.label}`,
      d: `M ${fp.x - 3} ${axisY} A 3 3 0 1 1 ${fp.x + 3} ${axisY} A 3 3 0 1 1 ${fp.x - 3} ${axisY} Z`,
      roughOptions: {
        ...LIGHT_RAY_DEFAULTS,
        stroke: COLORS.accentAmber,
        fill: COLORS.accentAmber,
        fillStyle: "solid",
        roughness: 0.3,
      },
    });
    allLabels.push({
      id: `focal-${fp.label}-label`,
      text: fp.label,
      x: fp.x,
      y: axisY + 18,
      anchor: "middle",
      fontSize: 13,
      color: COLORS.accentAmber,
    });
  }

  // Find object element (force_arrow with extras.object_distance)
  const objectEls = findByKind(elements, "force-arrow").filter(
    (el) => el.extras && "object_distance" in el.extras,
  );

  if (objectEls.length === 0) return;

  const objEl = objectEls[0];
  const do_ = getExtra(objEl, "object_distance", f * 2) as number;
  const objH = getExtra(objEl, "object_height", 50) as number;

  // Thin lens equation: 1/f = 1/do + 1/di → di = (f * do) / (do - f)
  const effectiveF = isConvex ? f : -f;
  const di = (effectiveF * do_) / (do_ - effectiveF);
  const magnification = -di / do_;
  const imgH = Math.abs(magnification) * objH;
  const isVirtual = di < 0;
  const isInverted = magnification < 0;

  const objX = lensX - do_;
  const imgX = lensX + di;

  // Draw object arrow (upright, from axis upward: angle=270 in our system)
  const arrowComp = getComponent("force-arrow");
  if (arrowComp) {
    // Object arrow: upright
    const objGeom = arrowComp.render({
      x: objX,
      y: axisY,
      angle: 270,
      length: objH,
      color: objEl.color ?? COLORS.accentBlue,
      label: objEl.label ?? "Object",
      id: `${objEl.id}-obj`,
    });
    allPaths.push(...objGeom.paths);
    allLabels.push(...objGeom.labels);

    // Image arrow
    const imgAngle = isInverted ? 90 : 270; // 90 = downward (inverted), 270 = upward
    const imgColor = isVirtual ? COLORS.textSecondary : COLORS.accentGreen;
    const imgGeom = arrowComp.render({
      x: Math.abs(di) < 10000 ? imgX : lensX + sceneWidth * 0.4,
      y: axisY,
      angle: imgAngle,
      length: Math.min(imgH, sceneHeight * 0.4),
      color: imgColor,
      label: "Image",
      id: `${objEl.id}-img`,
    });
    allPaths.push(...imgGeom.paths);
    allLabels.push(...imgGeom.labels);

    // If virtual image, make image arrow dashed
    if (isVirtual) {
      for (const p of imgGeom.paths) {
        if (p.roughOptions) {
          p.roughOptions.strokeLineDash = [6, 4];
        }
      }
    }
  }

  // ── 3 Principal Rays ──────────────────────────────────────
  const objTipY = axisY - objH;
  const imgTipY = isInverted ? axisY + imgH : axisY - imgH;
  const clampedImgTipY = Math.max(
    axisY - sceneHeight * 0.4,
    Math.min(axisY + sceneHeight * 0.4, imgTipY),
  );

  const rayComp = getComponent("ray");
  if (!rayComp) return;

  // Ray 1 (blue): Parallel to axis → through far focal point
  // Object tip → lens at same height, then bends toward far focal point
  const ray1Color = COLORS.accentBlue;
  const ray1LensY = objTipY;
  // Segment 1: parallel to axis from object to lens
  allPaths.push(
    ...rayComp.render({
      x1: objX,
      y1: objTipY,
      x2: lensX,
      y2: ray1LensY,
      color: ray1Color,
      id: "ray1-seg1",
    }).paths,
  );
  // Segment 2: from lens toward image (or extended backward for virtual)
  if (!isVirtual) {
    allPaths.push(
      ...rayComp.render({
        x1: lensX,
        y1: ray1LensY,
        x2: imgX,
        y2: clampedImgTipY,
        color: ray1Color,
        id: "ray1-seg2",
      }).paths,
    );
  } else {
    // Solid ray continues forward from lens
    const ray1FwdX = lensX + sceneWidth * 0.35;
    const ray1Slope = (clampedImgTipY - ray1LensY) / (imgX - lensX);
    const ray1FwdY = ray1LensY + ray1Slope * (ray1FwdX - lensX);
    allPaths.push(
      ...rayComp.render({
        x1: lensX,
        y1: ray1LensY,
        x2: ray1FwdX,
        y2: ray1FwdY,
        color: ray1Color,
        id: "ray1-seg2",
      }).paths,
    );
    // Dashed extension backward to virtual image
    allPaths.push(
      ...rayComp.render({
        x1: lensX,
        y1: ray1LensY,
        x2: imgX,
        y2: clampedImgTipY,
        dashed: true,
        showArrow: false,
        color: ray1Color,
        id: "ray1-ext",
      }).paths,
    );
  }

  // Ray 2 (green): Through lens center → straight through
  const ray2Color = COLORS.accentGreen;
  const ray2EndX = isVirtual ? lensX + sceneWidth * 0.35 : imgX;
  const ray2Slope = (axisY - objTipY) / (lensX - objX);
  const ray2EndY = objTipY + ray2Slope * (ray2EndX - objX);
  allPaths.push(
    ...rayComp.render({
      x1: objX,
      y1: objTipY,
      x2: ray2EndX,
      y2: ray2EndY,
      color: ray2Color,
      id: "ray2",
    }).paths,
  );

  // Ray 3 (amber): Through near focal → parallel to axis after lens
  const ray3Color = COLORS.accentAmber;
  const nearFocalX = lensX - f;
  // Line from object tip through near focal point to lens
  const ray3Slope =
    nearFocalX !== objX ? (axisY - objTipY) / (nearFocalX - objX) : 0;
  const ray3LensY = objTipY + ray3Slope * (lensX - objX);

  // Segment 1: object to lens
  allPaths.push(
    ...rayComp.render({
      x1: objX,
      y1: objTipY,
      x2: lensX,
      y2: ray3LensY,
      color: ray3Color,
      id: "ray3-seg1",
    }).paths,
  );

  // Segment 2: parallel to axis after lens
  if (!isVirtual) {
    allPaths.push(
      ...rayComp.render({
        x1: lensX,
        y1: ray3LensY,
        x2: imgX,
        y2: ray3LensY,
        color: ray3Color,
        id: "ray3-seg2",
      }).paths,
    );
  } else {
    const ray3FwdX = lensX + sceneWidth * 0.35;
    allPaths.push(
      ...rayComp.render({
        x1: lensX,
        y1: ray3LensY,
        x2: ray3FwdX,
        y2: ray3LensY,
        color: ray3Color,
        id: "ray3-seg2",
      }).paths,
    );
    // Dashed extension backward
    allPaths.push(
      ...rayComp.render({
        x1: lensX,
        y1: ray3LensY,
        x2: imgX,
        y2: clampedImgTipY,
        dashed: true,
        showArrow: false,
        color: ray3Color,
        id: "ray3-ext",
      }).paths,
    );
  }
}

// ── Wave Optics Mode ─────────────────────────────────────────

function renderWaveOptics(
  elements: SemanticSceneElement[],
  barriers: SemanticSceneElement[],
  context: LayoutContext,
  axisY: number,
  allPaths: ScenePath[],
  allLabels: SceneLabel[],
): void {
  const { sceneWidth, sceneHeight } = context;
  const margin = sceneHeight * 0.1;
  const visibleTop = margin;
  const visibleBottom = sceneHeight - margin;

  // Positions (left-to-right)
  const sourceX = sceneWidth * 0.15;
  const barrierX = sceneWidth * 0.35;
  const screenX = sceneWidth * 0.85;

  // Source
  const sources = findByKind(elements, "point-source");
  const sourceComp = getComponent("point-source");
  if (sources.length > 0 && sourceComp) {
    const srcEl = sources[0];
    const srcGeom = sourceComp.render({
      cx: sourceX,
      cy: axisY,
      label: srcEl.label,
      color: srcEl.color,
      id: srcEl.id,
    });
    allPaths.push(...srcGeom.paths);
    allLabels.push(...srcGeom.labels);
  }

  // Barrier
  const barrierEl = barriers[0];
  const slitCount = getExtra(barrierEl, "slit_count", 2) as number;
  const slitSep = getExtra(barrierEl, "slit_separation", 50) as number;
  const barrierWidth = 20;

  // Compute slit positions centered on axis
  const slitSpecs: { y: number; halfWidth?: number }[] = [];
  if (slitCount === 1) {
    slitSpecs.push({ y: axisY, halfWidth: 6 });
  } else {
    const totalSpan = (slitCount - 1) * slitSep;
    const topSlitY = axisY - totalSpan / 2;
    for (let i = 0; i < slitCount; i++) {
      slitSpecs.push({ y: topSlitY + i * slitSep, halfWidth: 6 });
    }
  }

  const barrierComp = getComponent("barrier");
  if (barrierComp) {
    const barrierGeom = barrierComp.render({
      x: barrierX,
      yTop: visibleTop,
      yBottom: visibleBottom,
      width: barrierWidth,
      slits: slitSpecs,
      color: barrierEl.color,
      id: barrierEl.id,
    });
    allPaths.push(...barrierGeom.paths);
    allLabels.push(...barrierGeom.labels);
  }

  // Screen
  const screens = findByKind(elements, "screen");
  const screenComp = getComponent("screen");
  if (screens.length > 0 && screenComp) {
    const scrEl = screens[0];
    const scrGeom = screenComp.render({
      x: screenX,
      yTop: visibleTop,
      yBottom: visibleBottom,
      label: scrEl.label,
      color: scrEl.color,
      id: scrEl.id,
    });
    allPaths.push(...scrGeom.paths);
    allLabels.push(...scrGeom.labels);
  }

  // Rays from source to slits
  const rayComp = getComponent("ray");
  if (rayComp) {
    for (let i = 0; i < slitSpecs.length; i++) {
      const slitY = slitSpecs[i].y;
      const rayGeom = rayComp.render({
        x1: sourceX,
        y1: axisY,
        x2: barrierX,
        y2: slitY,
        color: COLORS.accentBlue,
        id: `source-to-slit-${i}`,
      });
      allPaths.push(...rayGeom.paths);
    }
  }

  // Wavefront arcs from each slit exit
  const wavefrontComp = getComponent("wavefront-arc");
  const slitExitX = barrierX + barrierWidth;
  const wavefrontRadii = [40, 80, 120];

  if (wavefrontComp) {
    for (let i = 0; i < slitSpecs.length; i++) {
      const slitY = slitSpecs[i].y;
      for (let ri = 0; ri < wavefrontRadii.length; ri++) {
        const r = wavefrontRadii[ri];
        const wfGeom = wavefrontComp.render({
          cx: slitExitX,
          cy: slitY,
          radius: r,
          startAngle: -90,
          endAngle: 90,
          id: `wavefront-s${i}-r${ri}`,
        });
        allPaths.push(...wfGeom.paths);
      }
    }
  }

  // Interference pattern (only for 2 slits + screen present)
  if (slitCount === 2 && screens.length > 0) {
    renderInterferencePattern(screenX, visibleTop, visibleBottom, allPaths);
  }
}

// ── Interference Pattern ─────────────────────────────────────

function renderInterferencePattern(
  screenX: number,
  top: number,
  bottom: number,
  allPaths: ScenePath[],
): void {
  const bandWidth = 25;
  const numBright = 7;
  const numDark = 6;
  const totalBands = numBright + numDark;
  const screenHeight = bottom - top;
  const bandHeight = screenHeight / totalBands;

  let brightIdx = 0;
  let darkIdx = 0;

  for (let i = 0; i < totalBands; i++) {
    const bandTop = top + i * bandHeight;
    const bandBottom = top + (i + 1) * bandHeight;
    const isBright = i % 2 === 0;

    if (isBright) {
      allPaths.push({
        id: `bright-band-${brightIdx}`,
        d: `M ${screenX} ${bandTop} L ${screenX + bandWidth} ${bandTop} L ${screenX + bandWidth} ${bandBottom} L ${screenX} ${bandBottom} Z`,
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
      allPaths.push({
        id: `dark-band-${darkIdx}`,
        d: `M ${screenX} ${bandTop} L ${screenX + bandWidth} ${bandTop} L ${screenX + bandWidth} ${bandBottom} L ${screenX} ${bandBottom} Z`,
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

// ── Self-registration ────────────────────────────────────────

registerStrategy("optics", leftToRightOpticalBench);

export { leftToRightOpticalBench };
