/**
 * CenterBodyRadialForces — layout strategy for free-body diagrams.
 *
 * Algorithm:
 * 1. Find body (first "box" element) → center of scene
 * 2. Find surface → position below body bottom edge
 * 3. Find forces (kind "force_arrow" or "force-arrow") → map direction to angle
 * 4. Find spring → add wall at left edge, spring from wall to body
 * 5. Merge all geometries → computeTightBounds
 *
 * Uses getComponent() from the component registry — components must be
 * imported/registered before this strategy runs.
 */

// Side-effect imports: ensure components are registered before getComponent() calls
import "../../components/box";
import "../../components/surface";
import "../../components/force-arrow";
import "../../components/spring";

import type {
  SemanticSceneElement,
  LayoutContext,
  SceneGeometry,
} from "../types";
import type { ScenePath, SceneLabel } from "../../scene-types";
import { DIRECTION_ANGLES, type ForceDirection } from "../types";
import { getComponent } from "../../components/registry";
import { computeTightBounds } from "../../scene-layout";
import { APPARATUS_STROKE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import { registerStrategy } from "../registry";

// ── Constants ────────────────────────────────────────────────

const DEFAULT_ARROW_LENGTH = 100;
const BLOCK_DEFAULT_WIDTH = 80;
const BLOCK_DEFAULT_HEIGHT = 60;

// ── Helpers ──────────────────────────────────────────────────

/** Normalize kind: LLM produces "force_arrow", registry key is "force-arrow". */
function normalizeKind(kind: string): string {
  return kind.replace(/_/g, "-");
}

/** Find elements by normalized kind. */
function findByKind(
  elements: SemanticSceneElement[],
  kind: string,
): SemanticSceneElement[] {
  return elements.filter((el) => normalizeKind(el.kind) === kind);
}

/** Resolve direction string to angle in degrees. */
function directionToAngle(dir: string): number | null {
  // Normalize underscore → hyphen for direction too
  const normalized = dir.replace(/_/g, "-") as ForceDirection;
  return DIRECTION_ANGLES[normalized] ?? null;
}

// ── Strategy ─────────────────────────────────────────────────

function centerBodyRadialForces(
  elements: SemanticSceneElement[],
  context: LayoutContext,
): SceneGeometry {
  const allPaths: ScenePath[] = [];
  const allLabels: SceneLabel[] = [];

  const { sceneWidth, sceneHeight } = context;
  const bodyCx = sceneWidth / 2;
  const bodyCy = sceneHeight / 2;

  // ── 1. Body (box) ──────────────────────────────────────────
  const boxes = findByKind(elements, "box");
  if (boxes.length === 0) {
    return {
      paths: [],
      labels: [],
      bounds: { x: 0, y: 0, width: 0, height: 0 },
    };
  }

  const bodyEl = boxes[0];
  const boxComp = getComponent("box");
  if (boxComp) {
    const boxGeom = boxComp.render({
      cx: bodyCx,
      cy: bodyCy,
      width: BLOCK_DEFAULT_WIDTH,
      height: BLOCK_DEFAULT_HEIGHT,
      label: bodyEl.label,
      color: bodyEl.color,
      id: bodyEl.id,
    });
    allPaths.push(...boxGeom.paths);
    allLabels.push(...boxGeom.labels);
  }

  // ── 2. Surface ─────────────────────────────────────────────
  const surfaces = findByKind(elements, "surface");
  if (surfaces.length > 0) {
    const surfEl = surfaces[0];
    const surfComp = getComponent("surface");
    if (surfComp) {
      const surfaceY = bodyCy + BLOCK_DEFAULT_HEIGHT / 2;
      const surfGeom = surfComp.render({
        x1: 60,
        y: surfaceY,
        x2: sceneWidth - 60,
        color: surfEl.color,
        id: surfEl.id,
      });
      allPaths.push(...surfGeom.paths);
      allLabels.push(...surfGeom.labels);
    }
  }

  // ── 3. Force arrows ────────────────────────────────────────
  const forces = findByKind(elements, "force-arrow");
  for (const force of forces) {
    // Only forces attached to the body
    if (force.from !== bodyEl.id) continue;

    let angle: number;
    if (force.angle != null) {
      angle = force.angle;
    } else if (force.direction) {
      const resolved = directionToAngle(force.direction);
      if (resolved == null) continue;
      angle = resolved;
    } else {
      continue; // No direction info — skip
    }

    const length = DEFAULT_ARROW_LENGTH * (force.magnitude ?? 1);
    const color = force.color ?? COLORS.textPrimary;

    const arrowComp = getComponent("force-arrow");
    if (arrowComp) {
      const arrowGeom = arrowComp.render({
        x: bodyCx,
        y: bodyCy,
        angle,
        length,
        color,
        label: force.label,
        id: force.id,
      });
      allPaths.push(...arrowGeom.paths);
      allLabels.push(...arrowGeom.labels);
    }
  }

  // ── 4. Spring ──────────────────────────────────────────────
  const springs = findByKind(elements, "spring");
  if (springs.length > 0) {
    const springEl = springs[0];
    const wallX = 40;
    const wallTop = bodyCy - BLOCK_DEFAULT_HEIGHT;
    const wallBottom = bodyCy + BLOCK_DEFAULT_HEIGHT;

    // Wall line
    allPaths.push({
      id: "wall",
      d: `M ${wallX} ${wallTop} L ${wallX} ${wallBottom}`,
      roughOptions: {
        ...APPARATUS_STROKE,
        stroke: COLORS.textSecondary,
      },
    });

    // Wall hatch marks
    for (let hy = wallTop; hy < wallBottom; hy += 15) {
      allPaths.push({
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

    // Spring from wall to body left edge
    const springComp = getComponent("spring");
    if (springComp) {
      const bodyLeftX = bodyCx - BLOCK_DEFAULT_WIDTH / 2;
      const springGeom = springComp.render({
        x1: wallX,
        y1: bodyCy,
        x2: bodyLeftX,
        y2: bodyCy,
        coils: 8,
        amplitude: 10,
        id: springEl.id,
        color: springEl.color ?? COLORS.textPrimary,
      });
      allPaths.push(...springGeom.paths);
      allLabels.push(...springGeom.labels);
    }
  }

  return {
    paths: allPaths,
    labels: allLabels,
    bounds: computeTightBounds(allPaths, allLabels, 30),
    anchors: {
      blockCenter: { x: bodyCx, y: bodyCy },
    },
  };
}

// ── Self-registration ────────────────────────────────────────

registerStrategy("free_body", centerBodyRadialForces);

export { centerBodyRadialForces };
