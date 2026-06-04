/**
 * Parametric diagram templates (Workstream E).
 *
 * Hand-authored, verified `DesignDiagramSpec` factories for the canonical
 * IGCSE figures that recur every term. They are NOT LLM-generated: they load
 * instantly (zero tokens, <1 frame), are correct by construction, and serve
 * the "cache-hit on demo diagrams is non-negotiable" guarantee. Each returns a
 * spec the existing renderer + interactivity/reveal layers consume unchanged.
 */

import type { DesignDiagramSpec } from "../../../types/visuals";

/** Optional numeric overrides applied to a template's parameter defaults. */
export type TemplateParams = Record<string, number>;

export interface DiagramTemplate {
  /** Stable id used for cache-hit lookup (e.g. "right-triangle-trig"). */
  readonly conceptId: string;
  readonly title: string;
  readonly subject: "math" | "physics";
  /** Build a render-ready spec; `params` overrides the default slider values. */
  readonly build: (params?: TemplateParams) => DesignDiagramSpec;
}

// Shared dark-board palette (mirrors design_agent/backend/prompts.py).
export const INK = "#e8e8ee";
export const MUTED = "rgba(232, 232, 238, 0.62)";
export const BLUE = "#7fd4ff";
export const GREEN = "#9effc9";
export const PINK = "#ff7a8a";
export const AMBER = "#ffd27f";
