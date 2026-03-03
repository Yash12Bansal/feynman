/**
 * Chemistry layout strategy — reaction equations and apparatus setups.
 *
 * Two auto-detected modes:
 * - REACTION: molecules + arrow_labels → left-to-right reaction equation
 * - APPARATUS: any glassware/burner/etc → lab bench spatial layout
 *
 * The LLM sends semantic elements. This strategy does all spatial computation.
 */

// Side-effect imports: ensure chemistry components are registered
import "../../components/chemistry";

import type {
  SemanticSceneElement,
  LayoutContext,
  SceneGeometry,
} from "../types";
import type { ScenePath, SceneLabel } from "../../scene-types";
import { getComponent } from "../../components/registry";
import { computeTightBounds } from "../../scene-layout";
import { CHEM_LABEL } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import { registerStrategy } from "../registry";

// ── Helpers ──────────────────────────────────────────────────

function normalizeKind(kind: string): string {
  return kind.replace(/_/g, "-");
}

const APPARATUS_KINDS = new Set([
  "beaker",
  "flask",
  "test-tube",
  "bunsen-burner",
  "thermometer",
  "tubing",
]);

/** Default anchor names for apparatus components when `from` is just an element ID. */
const DEFAULT_CONNECTION_ANCHOR: Record<string, string> = {
  beaker: "mouth",
  flask: "neck",
  "test-tube": "top",
  "bunsen-burner": "top",
};

function isApparatus(kind: string): boolean {
  return APPARATUS_KINDS.has(normalizeKind(kind));
}

function getExtra<T>(el: SemanticSceneElement, key: string, fallback: T): T {
  if (el.extras && key in el.extras) return el.extras[key] as T;
  return fallback;
}

// ── Mode detection ───────────────────────────────────────────

type ChemMode = "reaction" | "apparatus" | "empty";

function detectMode(elements: SemanticSceneElement[]): ChemMode {
  if (elements.length === 0) return "empty";

  const hasMolecules = elements.some(
    (el) => normalizeKind(el.kind) === "molecule",
  );
  const hasArrows = elements.some(
    (el) => normalizeKind(el.kind) === "arrow-label",
  );
  const hasApparatus = elements.some((el) => isApparatus(el.kind));

  // If apparatus components are present → apparatus mode
  if (hasApparatus) return "apparatus";
  // Molecules + arrows without apparatus → reaction mode
  if (hasMolecules || hasArrows) return "reaction";

  return "empty";
}

// ── Strategy ─────────────────────────────────────────────────

function chemistryLayout(
  elements: SemanticSceneElement[],
  context: LayoutContext,
): SceneGeometry {
  const mode = detectMode(elements);

  switch (mode) {
    case "reaction":
      return renderReactionMode(elements, context);
    case "apparatus":
      return renderApparatusMode(elements, context);
    case "empty":
    default:
      return {
        paths: [],
        labels: [],
        bounds: { x: 0, y: 0, width: 0, height: 0 },
        anchors: {},
      };
  }
}

// ── Reaction Mode ────────────────────────────────────────────

function renderReactionMode(
  elements: SemanticSceneElement[],
  context: LayoutContext,
): SceneGeometry {
  const allPaths: ScenePath[] = [];
  const allLabels: SceneLabel[] = [];
  const allAnchors: Record<string, { x: number; y: number }> = {};
  const { sceneWidth, sceneHeight } = context;
  const centerY = sceneHeight / 2;

  // Partition: elements before first arrow_label = reactants, after = products
  const firstArrowIdx = elements.findIndex(
    (el) => normalizeKind(el.kind) === "arrow-label",
  );

  let reactantEls: SemanticSceneElement[];
  let arrowEls: SemanticSceneElement[];
  let productEls: SemanticSceneElement[];

  if (firstArrowIdx === -1) {
    // No arrow — treat all as reactants
    reactantEls = elements.filter(
      (el) => normalizeKind(el.kind) === "molecule",
    );
    arrowEls = [];
    productEls = [];
  } else {
    reactantEls = elements
      .slice(0, firstArrowIdx)
      .filter((el) => normalizeKind(el.kind) === "molecule");
    arrowEls = elements.filter(
      (el) => normalizeKind(el.kind) === "arrow-label",
    );
    productEls = elements
      .slice(firstArrowIdx + 1)
      .filter((el) => normalizeKind(el.kind) === "molecule");
  }

  // Layout zones: reactants (left 35%) → arrow (center 30%) → products (right 35%)
  const reactantZone = { left: sceneWidth * 0.05, right: sceneWidth * 0.38 };
  const arrowZone = { left: sceneWidth * 0.38, right: sceneWidth * 0.62 };
  const productZone = { left: sceneWidth * 0.62, right: sceneWidth * 0.95 };

  // Render molecules in a zone with "+" signs between them
  const renderMoleculeGroup = (
    mols: SemanticSceneElement[],
    zone: { left: number; right: number },
  ) => {
    const zoneW = zone.right - zone.left;
    const count = mols.length;
    if (count === 0) return;

    // Slot width includes space for "+" signs between molecules
    const totalSlots = count + (count - 1); // molecules + plus signs
    const slotW = zoneW / totalSlots;

    for (let i = 0; i < count; i++) {
      const el = mols[i];
      const slotIdx = i * 2; // skip plus sign slots
      const cx = zone.left + (slotIdx + 0.5) * slotW;

      const comp = getComponent("molecule");
      if (!comp) continue;

      const geom = comp.render({
        cx,
        cy: centerY,
        label: el.label ?? "",
        coefficient: getExtra(el, "coefficient", undefined),
        state: getExtra(el, "state", undefined),
        color: el.color,
        id: el.id,
      });
      allPaths.push(...geom.paths);
      allLabels.push(...geom.labels);
      if (geom.anchors) {
        for (const [name, pt] of Object.entries(geom.anchors)) {
          allAnchors[`${el.id}-${name}`] = pt;
        }
      }

      // "+" label between molecules (not after last)
      if (i < count - 1) {
        const plusX = zone.left + (slotIdx + 1.5) * slotW;
        allLabels.push({
          id: `plus-${el.id}`,
          text: "+",
          x: plusX,
          y: centerY + 5,
          anchor: "middle",
          fontSize: 18,
          color: COLORS.textSecondary,
        });
      }
    }
  };

  renderMoleculeGroup(reactantEls, reactantZone);
  renderMoleculeGroup(productEls, productZone);

  // Render arrow(s) in center zone
  const arrowComp = getComponent("arrow-label");
  if (arrowComp && arrowEls.length > 0) {
    const arrowEl = arrowEls[0];
    const arrowGeom = arrowComp.render({
      x1: arrowZone.left + 10,
      y1: centerY,
      x2: arrowZone.right - 10,
      y2: centerY,
      label: arrowEl.label,
      color: arrowEl.color,
      id: arrowEl.id,
    });
    allPaths.push(...arrowGeom.paths);
    allLabels.push(...arrowGeom.labels);
    if (arrowGeom.anchors) {
      for (const [name, pt] of Object.entries(arrowGeom.anchors)) {
        allAnchors[`${arrowEl.id}-${name}`] = pt;
      }
    }
  } else if (
    firstArrowIdx === -1 &&
    reactantEls.length > 0 &&
    productEls.length === 0
  ) {
    // No arrow at all — that's fine, just molecules
  }

  return {
    paths: allPaths,
    labels: allLabels,
    bounds: computeTightBounds(allPaths, allLabels, 30),
    anchors: allAnchors,
  };
}

// ── Apparatus Mode ───────────────────────────────────────────

function renderApparatusMode(
  elements: SemanticSceneElement[],
  context: LayoutContext,
): SceneGeometry {
  const allPaths: ScenePath[] = [];
  const allLabels: SceneLabel[] = [];
  const allAnchors: Record<string, { x: number; y: number }> = {};
  const { sceneWidth, sceneHeight } = context;

  // Horizontal bench line at 70% height
  const benchY = sceneHeight * 0.7;
  allPaths.push({
    id: "bench-line",
    d: `M ${sceneWidth * 0.05} ${benchY} L ${sceneWidth * 0.95} ${benchY}`,
    roughOptions: {
      ...CHEM_LABEL,
      stroke: COLORS.textSecondary,
      strokeWidth: 2,
      roughness: 0.8,
    },
  });

  // Separate element types
  const tubingEls = elements.filter(
    (el) => normalizeKind(el.kind) === "tubing",
  );
  const thermometerEls = elements.filter(
    (el) => normalizeKind(el.kind) === "thermometer",
  );
  const burnerEls = elements.filter(
    (el) => normalizeKind(el.kind) === "bunsen-burner",
  );
  const mainApparatus = elements.filter(
    (el) =>
      normalizeKind(el.kind) !== "tubing" &&
      normalizeKind(el.kind) !== "thermometer" &&
      normalizeKind(el.kind) !== "bunsen-burner" &&
      isApparatus(el.kind),
  );

  // Distribute main apparatus left-to-right along bench
  const margin = sceneWidth * 0.1;
  const availableW = sceneWidth * 0.8;
  const count = mainApparatus.length;

  // Also count burners for positioning
  const totalSlots = count + burnerEls.length;
  const slotW = totalSlots > 0 ? availableW / totalSlots : availableW;

  // Track which burner is adjacent to which apparatus for positioning
  const burnerParent = new Map<string, string>();
  for (const bEl of burnerEls) {
    // Burner is positioned below the next apparatus in element order
    const bIdx = elements.indexOf(bEl);
    // Find adjacent apparatus
    for (let i = bIdx - 1; i >= 0; i--) {
      if (
        isApparatus(elements[i].kind) &&
        normalizeKind(elements[i].kind) !== "bunsen-burner"
      ) {
        burnerParent.set(bEl.id, elements[i].id);
        break;
      }
    }
    if (!burnerParent.has(bEl.id)) {
      // Look forward
      for (let i = bIdx + 1; i < elements.length; i++) {
        if (
          isApparatus(elements[i].kind) &&
          normalizeKind(elements[i].kind) !== "bunsen-burner"
        ) {
          burnerParent.set(bEl.id, elements[i].id);
          break;
        }
      }
    }
  }

  // Render main apparatus
  const positionMap = new Map<string, { cx: number; cy: number }>();

  for (let i = 0; i < count; i++) {
    const el = mainApparatus[i];
    const kind = normalizeKind(el.kind);
    const comp = getComponent(kind);
    if (!comp) continue;

    const cx = margin + (i + 0.5) * slotW;
    const cy = benchY - 50; // above bench

    positionMap.set(el.id, { cx, cy });

    const renderParams: Record<string, unknown> = {
      cx,
      cy,
      id: el.id,
      label: el.label,
      color: el.color,
    };

    // Pass extras
    if (el.extras) {
      for (const [key, val] of Object.entries(el.extras)) {
        renderParams[key] = val;
      }
    }

    const geom = comp.render(renderParams);
    allPaths.push(...geom.paths);
    allLabels.push(...geom.labels);
    if (geom.anchors) {
      for (const [name, pt] of Object.entries(geom.anchors)) {
        allAnchors[`${el.id}-${name}`] = pt;
      }
    }
  }

  // Render burners below their parent apparatus
  for (const bEl of burnerEls) {
    const parentId = burnerParent.get(bEl.id);
    const parentPos = parentId ? positionMap.get(parentId) : undefined;
    const comp = getComponent("bunsen-burner");
    if (!comp) continue;

    const cx = parentPos ? parentPos.cx : margin + count * slotW + slotW / 2;
    const cy = benchY + 35; // below bench

    positionMap.set(bEl.id, { cx, cy });

    const renderParams: Record<string, unknown> = {
      cx,
      cy,
      id: bEl.id,
      label: bEl.label,
      color: bEl.color,
    };

    if (bEl.extras) {
      for (const [key, val] of Object.entries(bEl.extras)) {
        renderParams[key] = val;
      }
    }

    const geom = comp.render(renderParams);
    allPaths.push(...geom.paths);
    allLabels.push(...geom.labels);
    if (geom.anchors) {
      for (const [name, pt] of Object.entries(geom.anchors)) {
        allAnchors[`${bEl.id}-${name}`] = pt;
      }
    }
  }

  // Render thermometers inside referenced vessel
  for (const tEl of thermometerEls) {
    const comp = getComponent("thermometer");
    if (!comp) continue;

    const fromId = tEl.from ?? undefined;
    const parentPos = fromId ? positionMap.get(fromId) : undefined;

    const cx = parentPos ? parentPos.cx + 12 : margin + (count + 0.5) * slotW;
    const cy = parentPos ? parentPos.cy - 10 : benchY - 60;

    positionMap.set(tEl.id, { cx, cy });

    const renderParams: Record<string, unknown> = {
      cx,
      cy,
      id: tEl.id,
      label: tEl.label,
      color: tEl.color,
    };

    if (tEl.extras) {
      for (const [key, val] of Object.entries(tEl.extras)) {
        renderParams[key] = val;
      }
    }

    const geom = comp.render(renderParams);
    allPaths.push(...geom.paths);
    allLabels.push(...geom.labels);
    if (geom.anchors) {
      for (const [name, pt] of Object.entries(geom.anchors)) {
        allAnchors[`${tEl.id}-${name}`] = pt;
      }
    }
  }

  // Render tubing: resolve from/to against anchor map
  for (const tEl of tubingEls) {
    const comp = getComponent("tubing");
    if (!comp) continue;

    const fromRef = tEl.from ?? "";
    const toRef = tEl.to ?? "";

    const resolveAnchor = (ref: string): { x: number; y: number } | null => {
      if (!ref) return null;

      // Check if ref is "element.anchor" format
      if (ref.includes(".")) {
        const key = ref.replace(".", "-");
        return allAnchors[key] ?? null;
      }

      // Plain element ID → use default connection anchor
      const elemKind = elements.find((e) => e.id === ref);
      if (!elemKind) return null;
      const kind = normalizeKind(elemKind.kind);
      const defaultAnchor = DEFAULT_CONNECTION_ANCHOR[kind] ?? "top";
      return allAnchors[`${ref}-${defaultAnchor}`] ?? null;
    };

    const startPt = resolveAnchor(fromRef);
    const endPt = resolveAnchor(toRef);

    if (startPt && endPt) {
      const renderParams: Record<string, unknown> = {
        x1: startPt.x,
        y1: startPt.y,
        x2: endPt.x,
        y2: endPt.y,
        id: tEl.id,
        color: tEl.color,
      };

      if (tEl.extras) {
        for (const [key, val] of Object.entries(tEl.extras)) {
          renderParams[key] = val;
        }
      }

      const geom = comp.render(renderParams);
      allPaths.push(...geom.paths);
      allLabels.push(...geom.labels);
      if (geom.anchors) {
        for (const [name, pt] of Object.entries(geom.anchors)) {
          allAnchors[`${tEl.id}-${name}`] = pt;
        }
      }
    }
  }

  // Also handle explicit connections array from semantic spec
  // connections: [["rbf.outlet", "collector.mouth"]] auto-generate tubing
  // This is resolved at a higher level, but if tubing elements are present they handle it

  return {
    paths: allPaths,
    labels: allLabels,
    bounds: computeTightBounds(allPaths, allLabels, 30),
    anchors: allAnchors,
  };
}

// ── Self-registration ────────────────────────────────────────

registerStrategy("chemistry", chemistryLayout);

export { chemistryLayout };
