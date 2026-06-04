import { describe, it, expect } from "vitest";
import {
  listTemplates,
  buildTemplateSpec,
  getTemplate,
  listTemplateConceptIds,
} from "./registry";
import { sweepSpec } from "../../expr/overflow-sweep";
import type { DesignDiagramElement } from "../../../types/visuals";

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

const COORD_FIELDS = [
  "x",
  "y",
  "x1",
  "y1",
  "x2",
  "y2",
  "cx",
  "cy",
  "r",
  "rx",
  "ry",
  "width",
  "height",
  "startAngle",
  "endAngle",
] as const;

function stringCoords(el: DesignDiagramElement): string[] {
  const rec = el as unknown as Record<string, unknown>;
  return COORD_FIELDS.map((f) => rec[f]).filter(
    (v): v is string => typeof v === "string",
  );
}

const templates = listTemplates();

describe("diagram-template registry", () => {
  it("registers all seven templates (4 first-wave + 3 second-wave)", () => {
    expect(listTemplateConceptIds().sort()).toEqual(
      [
        "dc-circuit-series",
        "lens-ray-diagram",
        "right-triangle-trig",
        "vector-addition-2d",
        "unit-circle-sine",
        "projectile-motion",
        "circuit-parallel",
      ].sort(),
    );
  });

  it("getTemplate / buildTemplateSpec resolve known ids and reject unknown", () => {
    expect(getTemplate("right-triangle-trig")).toBeDefined();
    expect(getTemplate("nope")).toBeUndefined();
    expect(buildTemplateSpec("right-triangle-trig")).not.toBeNull();
    expect(buildTemplateSpec("nope")).toBeNull();
  });

  it.each(templates.map((t) => [t.conceptId, t] as const))(
    "%s builds a non-empty spec with a dictionary",
    (_id, template) => {
      const spec = template.build();
      const els = flatten(spec.elements);
      expect(els.length).toBeGreaterThan(0);
      expect(spec.dictionary).toBeDefined();
      expect(Object.keys(spec.dictionary ?? {}).length).toBeGreaterThan(0);
    },
  );

  it.each(templates.map((t) => [t.conceptId, t] as const))(
    "%s dictionary keys all reference real element ids",
    (_id, template) => {
      const spec = template.build();
      const ids = new Set(
        flatten(spec.elements)
          .map((e) => e.id)
          .filter((x): x is string => !!x),
      );
      for (const key of Object.keys(spec.dictionary ?? {})) {
        expect(ids.has(key)).toBe(true);
      }
    },
  );

  it.each(templates.map((t) => [t.conceptId, t] as const))(
    "%s: every parameter is referenced by at least one expression coord (no hardcoded dependents)",
    (_id, template) => {
      const spec = template.build();
      const params = spec.parameters ?? [];
      if (params.length === 0) return; // static template — nothing to check
      const allCoordStrings = flatten(spec.elements).flatMap(stringCoords);
      for (const p of params) {
        const referenced = allCoordStrings.some((s) => s.includes(p.name));
        expect(
          referenced,
          `param "${p.name}" must drive at least one coord`,
        ).toBe(true);
      }
    },
  );

  it.each(templates.map((t) => [t.conceptId, t] as const))(
    "%s stays within the viewBox across its full parameter range (overflow sweep)",
    (_id, template) => {
      const result = sweepSpec(template.build());
      expect(result.violations).toHaveLength(0);
    },
  );
});
