/**
 * ConstructionSequence — layout strategy for geometry diagrams.
 *
 * Unlike position-based layout strategies (FBD, optics, circuits), geometry
 * uses a dependency-resolution pattern: elements reference each other by ID
 * (a triangle references 3 points, an altitude references a vertex and a side).
 *
 * Algorithm:
 *   Pass 1: Build point map from "point" elements with explicit coords
 *   Pass 2: Auto-place unplaced points (triangle inference, circle center, spread)
 *   Pass 3: Render each element in array order, resolving coordinate refs
 */

// Side-effect imports: ensure geometry components are registered
import "../../components/geometry";

import type {
  SemanticSceneElement,
  LayoutContext,
  SceneGeometry,
} from "../types";
import type { ScenePath, SceneLabel } from "../../scene-types";
import { getComponent } from "../../components/registry";
import { computeTightBounds } from "../../scene-layout";
import { registerStrategy } from "../registry";

// ── Helpers ──────────────────────────────────────────────────

function normalizeKind(kind: string): string {
  return kind.replace(/_/g, "-");
}

type PointMap = Map<string, { x: number; y: number }>;
type AnchorMap = Record<string, { x: number; y: number }>;

/**
 * Resolve a point reference to coordinates.
 *
 * Checks pointMap first (for point elements), then allAnchors
 * (for anchors from already-rendered elements, e.g. "tri-BC_mid").
 */
function resolvePoint(
  ref: string | undefined,
  pointMap: PointMap,
  allAnchors: AnchorMap,
): { x: number; y: number } | null {
  if (!ref) return null;
  const fromPoints = pointMap.get(ref);
  if (fromPoints) return fromPoints;
  const fromAnchors = allAnchors[ref];
  if (fromAnchors) return fromAnchors;
  return null;
}

function extraStr(
  extras: Record<string, string | number | boolean> | undefined,
  key: string,
): string | undefined {
  const val = extras?.[key];
  return val != null ? String(val) : undefined;
}

function extraNum(
  extras: Record<string, string | number | boolean> | undefined,
  key: string,
): number | undefined {
  const val = extras?.[key];
  return val != null ? Number(val) : undefined;
}

// ── Strategy ─────────────────────────────────────────────────

function constructionSequence(
  elements: SemanticSceneElement[],
  context: LayoutContext,
): SceneGeometry {
  const allPaths: ScenePath[] = [];
  const allLabels: SceneLabel[] = [];
  const allAnchors: AnchorMap = {};
  const { sceneWidth, sceneHeight } = context;

  if (elements.length === 0) {
    return {
      paths: [],
      labels: [],
      bounds: { x: 0, y: 0, width: 0, height: 0 },
      anchors: {},
    };
  }

  // ── Pass 1: Build point map ──────────────────────────────

  const pointMap: PointMap = new Map();
  const unplacedPoints: string[] = [];

  for (const el of elements) {
    if (normalizeKind(el.kind) !== "point") continue;

    const ex = extraNum(el.extras, "x");
    const ey = extraNum(el.extras, "y");

    if (ex != null && ey != null) {
      pointMap.set(el.id, { x: ex, y: ey });
    } else {
      unplacedPoints.push(el.id);
    }
  }

  // ── Pass 2: Auto-place unplaced points ───────────────────

  const cx = sceneWidth / 2;
  const cy = sceneHeight / 2;

  if (unplacedPoints.length > 0) {
    // Check if a triangle references 3 unplaced points
    const triangleEl = elements.find((el) => {
      if (normalizeKind(el.kind) !== "triangle") return false;
      const v1 = extraStr(el.extras, "v1");
      const v2 = extraStr(el.extras, "v2");
      const v3 = extraStr(el.extras, "v3");
      return (
        v1 &&
        v2 &&
        v3 &&
        unplacedPoints.includes(v1) &&
        unplacedPoints.includes(v2) &&
        unplacedPoints.includes(v3)
      );
    });

    if (triangleEl) {
      const v1 = extraStr(triangleEl.extras, "v1")!;
      const v2 = extraStr(triangleEl.extras, "v2")!;
      const v3 = extraStr(triangleEl.extras, "v3")!;

      // Scalene triangle centered in scene
      pointMap.set(v1, { x: cx, y: cy - 100 });
      pointMap.set(v2, { x: cx - 90, y: cy + 60 });
      pointMap.set(v3, { x: cx + 110, y: cy + 65 });

      // Remove from unplaced
      const placed = new Set([v1, v2, v3]);
      const remaining = unplacedPoints.filter((p) => !placed.has(p));
      unplacedPoints.length = 0;
      unplacedPoints.push(...remaining);
    }

    // Check if a circle references an unplaced center point
    for (const el of elements) {
      if (normalizeKind(el.kind) !== "circle-shape") continue;
      const centerRef = extraStr(el.extras, "center") ?? el.from;
      if (centerRef && unplacedPoints.includes(centerRef)) {
        pointMap.set(centerRef, { x: cx, y: cy });
        const idx = unplacedPoints.indexOf(centerRef);
        if (idx >= 0) unplacedPoints.splice(idx, 1);
      }
    }

    // Spread remaining unplaced points across the scene
    for (let i = 0; i < unplacedPoints.length; i++) {
      const t = (i + 1) / (unplacedPoints.length + 1);
      pointMap.set(unplacedPoints[i], {
        x: sceneWidth * 0.15 + t * sceneWidth * 0.7,
        y: cy,
      });
    }
  }

  // ── Pass 3: Render each element ──────────────────────────

  for (const el of elements) {
    const kind = normalizeKind(el.kind);
    const comp = getComponent(kind);
    if (!comp) continue;

    const params: Record<string, unknown> = {
      id: el.id,
      label: el.label,
      color: el.color,
    };

    switch (kind) {
      case "point": {
        const pt = pointMap.get(el.id);
        if (!pt) continue;
        params.x1 = pt.x;
        params.y1 = pt.y;
        if (el.extras?.radius != null) params.radius = Number(el.extras.radius);
        break;
      }

      case "line-segment": {
        const fromPt = resolvePoint(el.from, pointMap, allAnchors);
        const toPt = resolvePoint(el.to, pointMap, allAnchors);
        if (!fromPt || !toPt) continue;
        params.x1 = fromPt.x;
        params.y1 = fromPt.y;
        params.x2 = toPt.x;
        params.y2 = toPt.y;
        if (el.extras?.dashed != null)
          params.dashed = Boolean(el.extras.dashed);
        break;
      }

      case "triangle": {
        const v1Ref = extraStr(el.extras, "v1");
        const v2Ref = extraStr(el.extras, "v2");
        const v3Ref = extraStr(el.extras, "v3");
        const p1 = resolvePoint(v1Ref, pointMap, allAnchors);
        const p2 = resolvePoint(v2Ref, pointMap, allAnchors);
        const p3 = resolvePoint(v3Ref, pointMap, allAnchors);
        if (!p1 || !p2 || !p3) continue;
        params.x1 = p1.x;
        params.y1 = p1.y;
        params.x2 = p2.x;
        params.y2 = p2.y;
        params.x3 = p3.x;
        params.y3 = p3.y;
        break;
      }

      case "circle-shape": {
        const centerRef = extraStr(el.extras, "center") ?? el.from;
        const centerPt = resolvePoint(centerRef, pointMap, allAnchors);
        if (!centerPt) continue;
        params.x1 = centerPt.x;
        params.y1 = centerPt.y;
        if (el.extras?.radius != null) params.radius = Number(el.extras.radius);
        if (el.extras?.filled != null)
          params.filled = Boolean(el.extras.filled);
        break;
      }

      case "angle-arc": {
        const vertexRef = extraStr(el.extras, "vertex");
        const ray1Ref = extraStr(el.extras, "ray1");
        const ray2Ref = extraStr(el.extras, "ray2");
        const vertex = resolvePoint(vertexRef, pointMap, allAnchors);
        const ray1Pt = resolvePoint(ray1Ref, pointMap, allAnchors);
        const ray2Pt = resolvePoint(ray2Ref, pointMap, allAnchors);
        if (!vertex || !ray1Pt || !ray2Pt) continue;
        params.x1 = vertex.x;
        params.y1 = vertex.y;
        params.x2 = ray1Pt.x;
        params.y2 = ray1Pt.y;
        params.x3 = ray2Pt.x;
        params.y3 = ray2Pt.y;
        if (el.extras?.radius != null) params.radius = Number(el.extras.radius);
        break;
      }

      case "right-angle-mark": {
        const vertexRef = extraStr(el.extras, "vertex");
        const ray1Ref = extraStr(el.extras, "ray1");
        const ray2Ref = extraStr(el.extras, "ray2");
        const vertex = resolvePoint(vertexRef, pointMap, allAnchors);
        const ray1Pt = resolvePoint(ray1Ref, pointMap, allAnchors);
        const ray2Pt = resolvePoint(ray2Ref, pointMap, allAnchors);
        if (!vertex || !ray1Pt || !ray2Pt) continue;
        params.x1 = vertex.x;
        params.y1 = vertex.y;
        params.x2 = ray1Pt.x;
        params.y2 = ray1Pt.y;
        params.x3 = ray2Pt.x;
        params.y3 = ray2Pt.y;
        if (el.extras?.size != null) params.size = Number(el.extras.size);
        break;
      }

      case "parallel-mark": {
        const fromPt = resolvePoint(el.from, pointMap, allAnchors);
        const toPt = resolvePoint(el.to, pointMap, allAnchors);
        if (!fromPt || !toPt) continue;
        params.x1 = fromPt.x;
        params.y1 = fromPt.y;
        params.x2 = toPt.x;
        params.y2 = toPt.y;
        if (el.extras?.count != null) params.count = Number(el.extras.count);
        break;
      }

      case "congruence-mark": {
        const fromPt = resolvePoint(el.from, pointMap, allAnchors);
        const toPt = resolvePoint(el.to, pointMap, allAnchors);
        if (!fromPt || !toPt) continue;
        params.x1 = fromPt.x;
        params.y1 = fromPt.y;
        params.x2 = toPt.x;
        params.y2 = toPt.y;
        if (el.extras?.count != null) params.count = Number(el.extras.count);
        break;
      }

      case "arc": {
        const centerRef = extraStr(el.extras, "center") ?? el.from;
        const centerPt = resolvePoint(centerRef, pointMap, allAnchors);
        if (!centerPt) continue;
        params.x1 = centerPt.x;
        params.y1 = centerPt.y;
        if (el.extras?.radius != null) params.radius = Number(el.extras.radius);
        if (el.extras?.startAngle != null)
          params.startAngle = Number(el.extras.startAngle);
        if (el.extras?.endAngle != null)
          params.endAngle = Number(el.extras.endAngle);
        break;
      }

      default:
        continue;
    }

    const geom = comp.render(params);
    allPaths.push(...geom.paths);
    allLabels.push(...geom.labels);

    // Namespace anchors as "${el.id}-${anchorName}"
    if (geom.anchors) {
      for (const [name, pt] of Object.entries(geom.anchors)) {
        allAnchors[`${el.id}-${name}`] = pt;
      }
    }
  }

  return {
    paths: allPaths,
    labels: allLabels,
    bounds: computeTightBounds(allPaths, allLabels, 30),
    anchors: allAnchors,
  };
}

// ── Self-registration ────────────────────────────────────────

registerStrategy("geometry", constructionSequence);

export { constructionSequence };
