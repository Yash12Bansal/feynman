/**
 * defaultReveal — derive a staged reveal order for a diagram. Consumed by the
 * reveal pipeline ONLY when `presentation_mode === "build_up"`, so it never
 * changes an "overview" diagram.
 *
 * Precedence:
 *   1. Explicit `spec.animations` steps (author-stated order) — see below.
 *   2. Dictionary roles → tiers (the tasteful default, zero LLM tokens).
 *   3. Source order (no dictionary).
 *
 * Order (skip empty tiers):
 *   0. stage      — surfaces / axes / ground / frames / grid
 *   1. objects    — bodies / lenses / circuit components / nodes / shapes
 *   1.5 unknown   — anything whose role doesn't map (after objects)
 *   2. relations  — vectors / forces / rays / arrows
 *   3. captions   — labels / dimensions / angles / equations / titles
 *
 * Fallback when there's no dictionary: source order, one element per group, so
 * an explicitly-opted-in build_up still reveals progressively.
 */

import type {
  DesignDiagramAnimationStep,
  DesignDiagramElement,
  DesignDiagramSpec,
  ElementMeta,
} from "../../../types/visuals";
import { resolveTarget } from "./resolveTarget";

export interface RevealPlan {
  /** Ordered groups of element ids; each group is revealed in one step. */
  order: string[][];
}

const STAGE =
  /(surface|ground|axis|principal_axis|frame|grid|floor|wall|boundary|baseline)/;
const RELATION =
  /(force|vector|velocity|accel|ray|arrow|tension|current|weight|momentum)/;
const CAPTION =
  /(label|dimension|annotation|callout|angle|value|measure|title|caption|equation|text|marker)/;
const OBJECT =
  /(object|body|mass|block|node|shape|lens|mirror|battery|resistor|cell|bulb|component|point|vertex|slit)/;

/** Map a dictionary role to a reveal tier. Unknown/empty → 1.5 (mid). */
function tierForRole(role: string | undefined): number {
  if (!role) return 1.5;
  const r = role.toLowerCase();
  if (STAGE.test(r)) return 0;
  if (CAPTION.test(r)) return 3; // before RELATION so "angle_label" reads as caption
  if (RELATION.test(r)) return 2;
  if (OBJECT.test(r)) return 1;
  return 1.5;
}

function flatten(
  els: readonly DesignDiagramElement[] | undefined,
): DesignDiagramElement[] {
  const out: DesignDiagramElement[] = [];
  for (const el of els ?? []) {
    if (el.type === "svg_group") out.push(...flatten(el.elements));
    else out.push(el);
  }
  return out;
}

/**
 * Resolve one explicit `animations` step to the source-ordered, deduped list of
 * element ids it reveals. `role_targets` resolve via the dictionary (reusing
 * `resolveTarget` so role semantics stay in one place); `element_targets` are
 * taken verbatim. Both are filtered to ids that actually exist in the diagram
 * and ordered by their position in `idOrder` so a step reads top-to-bottom.
 */
function resolveStepTargets(
  step: DesignDiagramAnimationStep,
  dict: Record<string, ElementMeta> | undefined,
  elements: readonly DesignDiagramElement[],
  idOrder: ReadonlyMap<string, number>,
): string[] {
  const out = new Set<string>();
  for (const role of step.role_targets ?? []) {
    for (const id of resolveTarget(
      { kind: "role", value: role },
      dict,
      elements,
    ))
      out.add(id);
  }
  for (const id of step.element_targets ?? []) out.add(id);
  return [...out]
    .filter((id) => idOrder.has(id))
    .sort((a, b) => idOrder.get(a)! - idOrder.get(b)!);
}

export function deriveRevealPlan(spec: DesignDiagramSpec): RevealPlan | null {
  const elements = flatten(spec.elements);
  const ids = elements.map((e) => e.id).filter((id): id is string => !!id);
  if (ids.length === 0) return null;

  // 1. Explicit `animations` steps win — the author has stated the exact reveal
  //    order. Sort by `step` (stable; ties keep authored order), resolve each
  //    step's targets, drop steps that resolve to nothing. Only use this path if
  //    at least one step has real targets; otherwise fall through to heuristics
  //    (so a legacy/no-op `animations` value can't blank the diagram).
  const steps = spec.animations;
  if (steps && steps.length > 0) {
    const idOrder = new Map(ids.map((id, i) => [id, i]));
    const ordered = steps
      .map((s, i) => ({ s, i }))
      .sort((a, b) => (a.s.step ?? 0) - (b.s.step ?? 0) || a.i - b.i);
    const order: string[][] = [];
    for (const { s } of ordered) {
      const group = resolveStepTargets(s, spec.dictionary, elements, idOrder);
      if (group.length > 0) order.push(group);
    }
    if (order.length > 0) return { order };
  }

  const dict = spec.dictionary;
  if (dict && Object.keys(dict).length > 0) {
    // Bucket by tier, preserving source order within each tier.
    const buckets = new Map<number, string[]>();
    for (const el of elements) {
      if (!el.id) continue;
      const tier = tierForRole(dict[el.id]?.role);
      const bucket = buckets.get(tier);
      if (bucket) bucket.push(el.id);
      else buckets.set(tier, [el.id]);
    }
    const order = [...buckets.keys()]
      .sort((a, b) => a - b)
      .map((t) => buckets.get(t)!);
    return { order };
  }

  // No dictionary → reveal one element at a time in source order.
  return { order: ids.map((id) => [id]) };
}
