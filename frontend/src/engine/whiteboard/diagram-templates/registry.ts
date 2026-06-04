/**
 * Diagram-template registry (Workstream E). The single instant-canonical
 * lookup: a `conceptId` → render-ready `DesignDiagramSpec`, zero LLM calls.
 *
 * Sits in front of the reuse (precomputed chapter diagram) and generate (live
 * LLM) tiers as tier-0 — the fastest, always-correct path. This is the source
 * of truth for the available concept ids; the backend planner mirrors it.
 */

import type { DesignDiagramSpec } from "../../../types/visuals";
import type { DiagramTemplate, TemplateParams } from "./types";
import { rightTriangleTrig } from "./right-triangle-trig";
import { vectorAddition2d } from "./vector-addition-2d";
import { lensRayDiagram } from "./lens-ray-diagram";
import { dcCircuitSeries } from "./dc-circuit-series";
import { unitCircleSine } from "./unit-circle-sine";
import { projectileMotion } from "./projectile-motion";
import { dcCircuitParallel } from "./circuit-parallel";

const ALL: readonly DiagramTemplate[] = [
  rightTriangleTrig,
  vectorAddition2d,
  lensRayDiagram,
  dcCircuitSeries,
  // 2nd wave (Phase 2).
  unitCircleSine,
  projectileMotion,
  dcCircuitParallel,
];

const TEMPLATES = new Map<string, DiagramTemplate>(
  ALL.map((t) => [t.conceptId, t]),
);

export function getTemplate(conceptId: string): DiagramTemplate | undefined {
  return TEMPLATES.get(conceptId);
}

/** Build a render-ready spec for a concept id, or null if unknown. */
export function buildTemplateSpec(
  conceptId: string,
  params?: TemplateParams,
): DesignDiagramSpec | null {
  const t = TEMPLATES.get(conceptId);
  return t ? t.build(params) : null;
}

export function listTemplates(): readonly DiagramTemplate[] {
  return ALL;
}

export function listTemplateConceptIds(): string[] {
  return ALL.map((t) => t.conceptId);
}
