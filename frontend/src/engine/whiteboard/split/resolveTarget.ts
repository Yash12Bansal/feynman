/**
 * resolveTarget — DOM-free mapping from an `AnnotationTarget` to element ids,
 * using only the spec's `dictionary` + `elements`. Shared by:
 *  - the staged-reveal pipeline (runs in a hook, no DOM scope) to turn a
 *    focus/reveal target into the set of element ids to reveal;
 *  - the annotation layer's `role` resolution (which then queries the live DOM
 *    by the returned ids — see `SlideAnnotationLayer`).
 *
 * `id` returns the id verbatim; `role` returns every element sharing that
 * dictionary role; `color`/`near_text` scan the spec elements; `data_attr` has
 * no dictionary/element mapping and returns [] (the DOM layer handles it).
 */

import type {
  AnnotationTarget,
  DesignDiagramElement,
  ElementMeta,
} from "../../../types/visuals";

/** Parse the brief's string target form ("role:vector", "id:foo"). */
export function parseTargetString(s: string): AnnotationTarget {
  const idx = s.indexOf(":");
  if (idx === -1) return { kind: "id", value: s };
  const kind = s.slice(0, idx);
  const value = s.slice(idx + 1);
  if (
    kind === "role" ||
    kind === "color" ||
    kind === "near_text" ||
    kind === "id"
  ) {
    return { kind, value };
  }
  // Unknown prefix (e.g. a CSS-ish "fill:#fff") — treat the whole thing as id.
  return { kind: "id", value: s };
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

export function resolveTarget(
  target: AnnotationTarget,
  dictionary: Record<string, ElementMeta> | undefined,
  elements: readonly DesignDiagramElement[] | undefined,
): string[] {
  switch (target.kind) {
    case "id":
      return [target.value];

    case "role": {
      if (!dictionary) return [];
      return Object.entries(dictionary)
        .filter(([, meta]) => meta?.role === target.value)
        .map(([id]) => id);
    }

    case "color": {
      const ids: string[] = [];
      for (const el of flatten(elements)) {
        if (!el.id) continue;
        const anyEl = el as { stroke?: string; fill?: string };
        if (anyEl.stroke === target.value || anyEl.fill === target.value) {
          ids.push(el.id);
        }
      }
      return ids;
    }

    case "near_text": {
      const ids: string[] = [];
      for (const el of flatten(elements)) {
        if (!el.id) continue;
        const text =
          el.type === "svg_text"
            ? el.text
            : el.type === "svg_latex"
              ? el.expression
              : undefined;
        if (text && text.includes(target.value)) ids.push(el.id);
      }
      return ids;
    }

    case "data_attr":
    default:
      return [];
  }
}

/**
 * Given a focused element id, return all ids sharing its dictionary role (the
 * "role group"). Falls back to `[elementId]` when there's no dictionary entry.
 * This is what build_up reveal uses: focusing one element reveals its group.
 */
export function roleGroupForElement(
  elementId: string,
  dictionary: Record<string, ElementMeta> | undefined,
): string[] {
  const role = dictionary?.[elementId]?.role;
  if (!role) return [elementId];
  const group = resolveTarget(
    { kind: "role", value: role },
    dictionary,
    undefined,
  );
  return group.length > 0 ? group : [elementId];
}
