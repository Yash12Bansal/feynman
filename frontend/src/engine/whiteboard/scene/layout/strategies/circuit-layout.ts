/**
 * SchematicCircuit — layout strategy for series circuit diagrams.
 *
 * Takes an ordered list of elements and arranges them in a rectangular
 * circuit loop: battery on the left side, other components distributed
 * across top → right → bottom sides.
 *
 * Covers: Ohm's law, series resistance, RC/RL circuits, switch+bulb circuits.
 * Parallel branches and explicit `connections` routing deferred to Phase 8.
 */

// Side-effect imports: ensure circuit components are registered
import "../../components/circuits";

import type {
  SemanticSceneElement,
  LayoutContext,
  SceneGeometry,
} from "../types";
import type { ScenePath, SceneLabel } from "../../scene-types";
import { getComponent } from "../../components/registry";
import { computeTightBounds } from "../../scene-layout";
import { CIRCUIT_WIRE } from "../../scene-rough-helpers";
import { COLORS } from "../../../../theme";
import { registerStrategy } from "../registry";

// ── Helpers ──────────────────────────────────────────────────

function normalizeKind(kind: string): string {
  return kind.replace(/_/g, "-");
}

interface CornerLoop {
  topLeft: { x: number; y: number };
  topRight: { x: number; y: number };
  bottomRight: { x: number; y: number };
  bottomLeft: { x: number; y: number };
}

interface Side {
  start: { x: number; y: number };
  end: { x: number; y: number };
  direction: "horizontal" | "vertical";
}

// ── Strategy ─────────────────────────────────────────────────

function schematicCircuit(
  elements: SemanticSceneElement[],
  context: LayoutContext,
): SceneGeometry {
  const allPaths: ScenePath[] = [];
  const allLabels: SceneLabel[] = [];
  const { sceneWidth, sceneHeight } = context;

  if (elements.length === 0) {
    return {
      paths: [],
      labels: [],
      bounds: { x: 0, y: 0, width: 0, height: 0 },
      anchors: {},
    };
  }

  // Step 1 — Parse elements
  const batteryIdx = elements.findIndex(
    (el) => normalizeKind(el.kind) === "battery",
  );
  const batteryEl = batteryIdx >= 0 ? elements[batteryIdx] : elements[0];
  const groundEls = elements.filter(
    (el) => normalizeKind(el.kind) === "ground",
  );

  // Series elements = everything except battery, ground, voltmeter
  const excludeKinds = new Set(["battery", "ground", "voltmeter"]);
  const seriesEls = elements.filter(
    (el) => el !== batteryEl && !excludeKinds.has(normalizeKind(el.kind)),
  );

  // Step 2 — Define rectangular loop
  const margin = 60;
  const loop: CornerLoop = {
    topLeft: { x: margin, y: margin },
    topRight: { x: sceneWidth - margin, y: margin },
    bottomRight: { x: sceneWidth - margin, y: sceneHeight - margin },
    bottomLeft: { x: margin, y: sceneHeight - margin },
  };

  // Step 3 — Distribute components across 3 sides (top, right, bottom)
  const sides: Side[] = [
    {
      start: loop.topLeft,
      end: loop.topRight,
      direction: "horizontal",
    },
    {
      start: loop.topRight,
      end: loop.bottomRight,
      direction: "vertical",
    },
    {
      start: loop.bottomRight,
      end: loop.bottomLeft,
      direction: "horizontal",
    },
  ];

  const slotLen = 90; // ~70px body + 10px lead each side

  // Greedy fill: assign components to sides
  interface Assignment {
    el: SemanticSceneElement;
    sideIdx: number;
    slotIdx: number;
  }

  const assignments: Assignment[] = [];
  let currentSide = 0;
  const sideCapacities: number[] = sides.map((s) => {
    const dx = s.end.x - s.start.x;
    const dy = s.end.y - s.start.y;
    const sideLen = Math.sqrt(dx * dx + dy * dy);
    return Math.max(1, Math.floor(sideLen / slotLen));
  });
  const sideCounts = [0, 0, 0];

  for (const el of seriesEls) {
    // Find next side with room
    while (
      currentSide < 3 &&
      sideCounts[currentSide] >= sideCapacities[currentSide]
    ) {
      currentSide++;
    }
    if (currentSide >= 3) {
      // Overflow: pack into last side
      currentSide = 2;
    }
    assignments.push({
      el,
      sideIdx: currentSide,
      slotIdx: sideCounts[currentSide],
    });
    sideCounts[currentSide]++;
  }

  // Step 4 — Render components on each side
  const allAnchors: Record<string, { x: number; y: number }> = {};

  // Track last endpoint per side for wiring
  interface SideEndpoints {
    first?: { x: number; y: number };
    last?: { x: number; y: number };
  }
  const sideEndpoints: SideEndpoints[] = [{}, {}, {}];

  for (let sideIdx = 0; sideIdx < 3; sideIdx++) {
    const side = sides[sideIdx];
    const sideAssignments = assignments.filter((a) => a.sideIdx === sideIdx);
    const n = sideAssignments.length;
    if (n === 0) continue;

    const sdx = side.end.x - side.start.x;
    const sdy = side.end.y - side.start.y;
    const sideLen = Math.sqrt(sdx * sdx + sdy * sdy);
    const gap = (sideLen - n * slotLen) / (n + 1);

    for (let i = 0; i < n; i++) {
      const { el } = sideAssignments[i];
      const kind = normalizeKind(el.kind);
      const comp = getComponent(kind);
      if (!comp) continue;

      // Position along side
      const tStart = (gap * (i + 1) + slotLen * i) / sideLen;
      const tEnd = (gap * (i + 1) + slotLen * (i + 1)) / sideLen;

      // For bottom side, components go right→left (reversed direction)
      const effectiveTStart = sideIdx === 2 ? 1 - tStart : tStart;
      const effectiveTEnd = sideIdx === 2 ? 1 - tEnd : tEnd;

      const x1 = side.start.x + sdx * effectiveTStart;
      const y1 = side.start.y + sdy * effectiveTStart;
      const x2 = side.start.x + sdx * effectiveTEnd;
      const y2 = side.start.y + sdy * effectiveTEnd;

      const params: Record<string, unknown> = {
        x1,
        y1,
        x2,
        y2,
        id: el.id,
        label: el.label,
        color: el.color,
      };

      // Pass extras
      if (el.extras) {
        for (const [key, val] of Object.entries(el.extras)) {
          params[key] = val;
        }
      }

      const geom = comp.render(params);
      allPaths.push(...geom.paths);
      allLabels.push(...geom.labels);

      if (geom.anchors) {
        for (const [name, pt] of Object.entries(geom.anchors)) {
          allAnchors[`${el.id}-${name}`] = pt;
        }
      }

      // Track endpoints for wiring
      if (i === 0) {
        sideEndpoints[sideIdx].first = { x: x1, y: y1 };
      }
      if (i === n - 1) {
        sideEndpoints[sideIdx].last = { x: x2, y: y2 };
      }
    }
  }

  // Step 6 — Battery on left side (vertical: bottom→top)
  const batteryComp = getComponent(normalizeKind(batteryEl.kind));
  if (batteryComp) {
    const batteryParams: Record<string, unknown> = {
      x1: loop.bottomLeft.x,
      y1: loop.bottomLeft.y,
      x2: loop.topLeft.x,
      y2: loop.topLeft.y,
      id: batteryEl.id,
      label: batteryEl.label,
      color: batteryEl.color,
    };
    if (batteryEl.extras) {
      for (const [key, val] of Object.entries(batteryEl.extras)) {
        batteryParams[key] = val;
      }
    }
    const bGeom = batteryComp.render(batteryParams);
    allPaths.push(...bGeom.paths);
    allLabels.push(...bGeom.labels);
    if (bGeom.anchors) {
      for (const [name, pt] of Object.entries(bGeom.anchors)) {
        allAnchors[`${batteryEl.id}-${name}`] = pt;
      }
    }
  }

  // Step 5 — Render wires connecting components + corners
  const wireColor = COLORS.textPrimary;

  // Wire from topLeft corner to first component on top side (or topRight if no components)
  const renderWire = (
    ax: number,
    ay: number,
    bx: number,
    by: number,
    wireId: string,
  ) => {
    allPaths.push({
      id: wireId,
      d: `M ${ax} ${ay} L ${bx} ${by}`,
      roughOptions: { ...CIRCUIT_WIRE, stroke: wireColor },
    });
  };

  // Connect battery top (topLeft) → first component on top side
  if (sideEndpoints[0].first) {
    renderWire(
      loop.topLeft.x,
      loop.topLeft.y,
      sideEndpoints[0].first.x,
      sideEndpoints[0].first.y,
      "wire-tl-to-top-first",
    );
  }
  // Last component on top side → topRight corner
  if (sideEndpoints[0].last) {
    renderWire(
      sideEndpoints[0].last.x,
      sideEndpoints[0].last.y,
      loop.topRight.x,
      loop.topRight.y,
      "wire-top-last-to-tr",
    );
  }
  // If no components on top side, wire straight across
  if (!sideEndpoints[0].first) {
    renderWire(
      loop.topLeft.x,
      loop.topLeft.y,
      loop.topRight.x,
      loop.topRight.y,
      "wire-top-side",
    );
  }

  // Connect topRight → right side components → bottomRight
  if (sideEndpoints[1].first) {
    renderWire(
      loop.topRight.x,
      loop.topRight.y,
      sideEndpoints[1].first.x,
      sideEndpoints[1].first.y,
      "wire-tr-to-right-first",
    );
  }
  if (sideEndpoints[1].last) {
    renderWire(
      sideEndpoints[1].last.x,
      sideEndpoints[1].last.y,
      loop.bottomRight.x,
      loop.bottomRight.y,
      "wire-right-last-to-br",
    );
  }
  if (!sideEndpoints[1].first) {
    renderWire(
      loop.topRight.x,
      loop.topRight.y,
      loop.bottomRight.x,
      loop.bottomRight.y,
      "wire-right-side",
    );
  }

  // Connect bottomRight → bottom side components → bottomLeft
  if (sideEndpoints[2].first) {
    renderWire(
      loop.bottomRight.x,
      loop.bottomRight.y,
      sideEndpoints[2].first.x,
      sideEndpoints[2].first.y,
      "wire-br-to-bottom-first",
    );
  }
  if (sideEndpoints[2].last) {
    renderWire(
      sideEndpoints[2].last.x,
      sideEndpoints[2].last.y,
      loop.bottomLeft.x,
      loop.bottomLeft.y,
      "wire-bottom-last-to-bl",
    );
  }
  if (!sideEndpoints[2].first) {
    renderWire(
      loop.bottomRight.x,
      loop.bottomRight.y,
      loop.bottomLeft.x,
      loop.bottomLeft.y,
      "wire-bottom-side",
    );
  }

  // Wire between consecutive components on the same side
  for (let sideIdx = 0; sideIdx < 3; sideIdx++) {
    const sideAssignments = assignments.filter((a) => a.sideIdx === sideIdx);
    if (sideAssignments.length <= 1) continue;

    const side = sides[sideIdx];
    const sdx = side.end.x - side.start.x;
    const sdy = side.end.y - side.start.y;
    const sideLen = Math.sqrt(sdx * sdx + sdy * sdy);
    const n = sideAssignments.length;
    const gap = (sideLen - n * slotLen) / (n + 1);

    for (let i = 0; i < n - 1; i++) {
      const tEnd = (gap * (i + 1) + slotLen * (i + 1)) / sideLen;
      const tNextStart = (gap * (i + 2) + slotLen * (i + 1)) / sideLen;

      const effectiveTEnd = sideIdx === 2 ? 1 - tEnd : tEnd;
      const effectiveTNextStart = sideIdx === 2 ? 1 - tNextStart : tNextStart;

      const endX = side.start.x + sdx * effectiveTEnd;
      const endY = side.start.y + sdy * effectiveTEnd;
      const nextStartX = side.start.x + sdx * effectiveTNextStart;
      const nextStartY = side.start.y + sdy * effectiveTNextStart;

      renderWire(
        endX,
        endY,
        nextStartX,
        nextStartY,
        `wire-s${sideIdx}-${i}-to-${i + 1}`,
      );
    }
  }

  // Step 7 — Ground (if present): branch downward from bottomLeft
  for (let gi = 0; gi < groundEls.length; gi++) {
    const gEl = groundEls[gi];
    const groundComp = getComponent("ground");
    if (!groundComp) continue;

    const gx = loop.bottomLeft.x;
    const gy = loop.bottomLeft.y;

    // Short wire stem downward
    const stemLen = 20;
    renderWire(gx, gy, gx, gy + stemLen, `wire-ground-stem-${gi}`);

    const gGeom = groundComp.render({
      x1: gx,
      y1: gy + stemLen,
      id: gEl.id,
    });
    allPaths.push(...gGeom.paths);
    allLabels.push(...gGeom.labels);
  }

  // Step 8 — Bounds
  return {
    paths: allPaths,
    labels: allLabels,
    bounds: computeTightBounds(allPaths, allLabels, 30),
    anchors: allAnchors,
  };
}

// ── Self-registration ────────────────────────────────────────

registerStrategy("circuit", schematicCircuit);

export { schematicCircuit };
