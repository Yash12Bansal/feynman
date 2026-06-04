import { describe, it, expect } from "vitest";
import { deriveRevealPlan } from "../defaultReveal";
import type {
  DesignDiagramAnimationStep,
  DesignDiagramElement,
  DesignDiagramSpec,
  ElementMeta,
} from "../../../../types/visuals";

function el(id: string): DesignDiagramElement {
  return { type: "svg_circle", id, cx: 0, cy: 0, r: 1 };
}

describe("deriveRevealPlan — dictionary tiers", () => {
  it("orders stage → objects → relations → captions", () => {
    const spec: DesignDiagramSpec = {
      // Intentionally out of tier order in the source to prove sorting.
      elements: [el("lbl"), el("vec"), el("ball"), el("ground")],
      dictionary: {
        lbl: { role: "label", semantic: "", position: "top" },
        vec: { role: "velocity", semantic: "", position: "center" },
        ball: { role: "object", semantic: "", position: "center" },
        ground: { role: "surface", semantic: "", position: "bottom" },
      } as Record<string, ElementMeta>,
    };
    const plan = deriveRevealPlan(spec);
    expect(plan?.order).toEqual([["ground"], ["ball"], ["vec"], ["lbl"]]);
  });

  it("groups same-tier elements together, preserving source order", () => {
    const spec: DesignDiagramSpec = {
      elements: [el("f1"), el("f2"), el("base")],
      dictionary: {
        f1: { role: "applied_force", semantic: "", position: "center" },
        f2: { role: "normal_force", semantic: "", position: "center" },
        base: { role: "ground", semantic: "", position: "bottom" },
      } as Record<string, ElementMeta>,
    };
    const plan = deriveRevealPlan(spec);
    // stage (base) first, then both forces in one relations group, source order.
    expect(plan?.order).toEqual([["base"], ["f1", "f2"]]);
  });

  it("places unknown roles in the middle tier (after objects, before relations)", () => {
    const spec: DesignDiagramSpec = {
      elements: [el("obj"), el("mystery"), el("vec")],
      dictionary: {
        obj: { role: "block", semantic: "", position: "center" },
        mystery: { role: "doohickey", semantic: "", position: "center" },
        vec: { role: "force", semantic: "", position: "center" },
      } as Record<string, ElementMeta>,
    };
    const plan = deriveRevealPlan(spec);
    expect(plan?.order).toEqual([["obj"], ["mystery"], ["vec"]]);
  });
});

describe("deriveRevealPlan — explicit animations override", () => {
  const spec = (
    animations: DesignDiagramSpec["animations"],
  ): DesignDiagramSpec => ({
    elements: [el("ground"), el("ball"), el("vec"), el("lbl")],
    dictionary: {
      ground: { role: "surface", semantic: "", position: "bottom" },
      ball: { role: "object", semantic: "", position: "center" },
      vec: { role: "velocity", semantic: "", position: "center" },
      lbl: { role: "label", semantic: "", position: "top" },
    } as Record<string, ElementMeta>,
    animations,
  });

  it("uses author steps verbatim, resolving role_targets via the dictionary", () => {
    // Deliberately a different grouping than the dictionary-tier heuristic.
    const plan = deriveRevealPlan(
      spec([
        { step: 1, role_targets: ["object"] },
        { step: 2, role_targets: ["surface", "velocity"] },
        { step: 3, element_targets: ["lbl"] },
      ]),
    );
    expect(plan?.order).toEqual([["ball"], ["ground", "vec"], ["lbl"]]);
  });

  it("sorts by `step` ordinal, not array position", () => {
    const plan = deriveRevealPlan(
      spec([
        { step: 3, element_targets: ["lbl"] },
        { step: 1, element_targets: ["ground"] },
        { step: 2, element_targets: ["ball"] },
      ]),
    );
    expect(plan?.order).toEqual([["ground"], ["ball"], ["lbl"]]);
  });

  it("dedupes and source-orders ids within a step (role + explicit overlap)", () => {
    const plan = deriveRevealPlan(
      // vec named twice (role 'velocity' + explicit id), ball after it in the
      // step but earlier in source order → comes first, no duplicate.
      spec([
        {
          step: 1,
          role_targets: ["velocity"],
          element_targets: ["vec", "ball"],
        },
      ]),
    );
    expect(plan?.order).toEqual([["ball", "vec"]]);
  });

  it("filters phantom ids and unknown roles, keeping only real elements", () => {
    const plan = deriveRevealPlan(
      spec([
        {
          step: 1,
          role_targets: ["nonexistent_role"],
          element_targets: ["ghost"],
        },
        { step: 2, role_targets: ["object"] },
      ]),
    );
    // Step 1 resolves to nothing (dropped); step 2 reveals the ball.
    expect(plan?.order).toEqual([["ball"]]);
  });

  it("falls through to the dictionary heuristic when every step is a no-op", () => {
    // Legacy/garbage animations (e.g. {duration, loop}) must not blank the board.
    const plan = deriveRevealPlan(
      spec([{ duration_ms: 2000 } as DesignDiagramAnimationStep, {}]),
    );
    // Dictionary tiers, unchanged: stage → object → relation → caption.
    expect(plan?.order).toEqual([["ground"], ["ball"], ["vec"], ["lbl"]]);
  });
});

describe("deriveRevealPlan — fallbacks", () => {
  it("with no dictionary, reveals one element at a time in source order", () => {
    const spec: DesignDiagramSpec = {
      elements: [el("a"), el("b"), el("c")],
    };
    expect(deriveRevealPlan(spec)?.order).toEqual([["a"], ["b"], ["c"]]);
  });

  it("returns null when there are no elements with ids", () => {
    expect(deriveRevealPlan({ elements: [] })).toBeNull();
    expect(
      deriveRevealPlan({
        elements: [{ type: "svg_circle", cx: 0, cy: 0, r: 1 }],
      }),
    ).toBeNull();
  });
});
