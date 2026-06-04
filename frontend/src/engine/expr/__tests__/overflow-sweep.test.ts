import { describe, it, expect } from "vitest";
import { sweepSpec } from "../overflow-sweep";
import type { DesignDiagramSpec } from "../../../types/visuals";

describe("sweepSpec — clean specs", () => {
  it("passes a parameterized spec that stays in bounds across its range", () => {
    const spec: DesignDiagramSpec = {
      width: 900,
      height: 650,
      parameters: [{ name: "theta", min: 0, max: 90, default: 45, step: 5 }],
      elements: [
        { type: "svg_line", id: "base", x1: 200, y1: 500, x2: 600, y2: 500 },
        // Vertical leg scales with sin(theta) but capped well inside the canvas.
        {
          type: "svg_line",
          id: "leg",
          x1: 600,
          y1: 500,
          x2: 600,
          y2: "500 - 200*sin(theta * PI / 180)",
        },
      ],
    };
    const result = sweepSpec(spec);
    expect(result.ok).toBe(true);
    expect(result.violations).toHaveLength(0);
  });

  it("treats a param-less spec as a single combination", () => {
    const spec: DesignDiagramSpec = {
      width: 900,
      height: 650,
      elements: [{ type: "svg_circle", id: "c", cx: 100, cy: 100, r: 30 }],
    };
    const result = sweepSpec(spec);
    expect(result.ok).toBe(true);
    expect(result.combinationsTested).toBe(1);
  });
});

describe("sweepSpec — catches the clipping bug", () => {
  it("flags an element that leaves the canvas at a slider extreme", () => {
    const spec: DesignDiagramSpec = {
      width: 900,
      height: 650,
      parameters: [{ name: "a", min: 0, max: 10, default: 0, step: 1 }],
      // At a=10, cx = 1000 > width 900.
      elements: [{ type: "svg_circle", id: "c", cx: "a * 100", cy: 100, r: 5 }],
    };
    const result = sweepSpec(spec);
    expect(result.ok).toBe(false);
    expect(result.violations.some((v) => v.reason === "out_of_bounds")).toBe(
      true,
    );
  });

  it("flags a non-finite (divide-by-zero) coordinate", () => {
    const spec: DesignDiagramSpec = {
      width: 900,
      height: 650,
      parameters: [{ name: "a", min: 0, max: 10, default: 0, step: 1 }],
      // At a=5, 10/(a-5) → Infinity → non-finite.
      elements: [
        { type: "svg_circle", id: "c", cx: "10 / (a - 5)", cy: 100, r: 5 },
      ],
    };
    const result = sweepSpec(spec);
    expect(result.ok).toBe(false);
    expect(result.violations.some((v) => v.reason === "nan")).toBe(true);
  });
});

describe("sweepSpec — combination budget", () => {
  it("falls back to per-axis + corner vectors past maxCombinations", () => {
    const spec: DesignDiagramSpec = {
      width: 900,
      height: 650,
      // 2 params × 11 values each = 121 full combinations.
      parameters: [
        { name: "a", min: 0, max: 10, default: 5, step: 1 },
        { name: "b", min: 0, max: 10, default: 5, step: 1 },
      ],
      elements: [{ type: "svg_circle", id: "c", cx: 450, cy: 325, r: 5 }],
    };
    const result = sweepSpec(spec, { maxCombinations: 10 });
    // Fallback: 2 axes × 11 values (22) + 2^2 corners (4) = 26, not 121.
    expect(result.combinationsTested).toBe(26);
    expect(result.ok).toBe(true);
  });
});

describe("sweepSpec — fixtures glob", () => {
  // Any parameterized spec dropped in ./fixtures/*.json is auto-swept here.
  const modules = import.meta.glob("./fixtures/*.json", { eager: true });
  const fixtures = Object.entries(modules).map(([path, mod]) => [
    path,
    (mod as { default: DesignDiagramSpec }).default,
  ]) as Array<[string, DesignDiagramSpec]>;

  it("has at least one fixture", () => {
    expect(fixtures.length).toBeGreaterThan(0);
  });

  it.each(fixtures)("fixture %s stays within the viewBox", (_path, spec) => {
    const result = sweepSpec(spec);
    expect(result.violations).toHaveLength(0);
  });
});
