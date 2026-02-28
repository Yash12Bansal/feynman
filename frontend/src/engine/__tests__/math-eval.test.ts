import { describe, it, expect } from "vitest";
import { evaluateFunction } from "../math-eval";
import type { FunctionDef } from "../../types/visuals";

function makeFn(
  overrides: Partial<FunctionDef> & { expression: string },
): FunctionDef {
  return { expression: overrides.expression, ...overrides };
}

describe("evaluateFunction", () => {
  it("evaluates polynomial (x^2)", () => {
    const points = evaluateFunction(makeFn({ expression: "x^2" }), -5, 5);
    expect(points.length).toBeGreaterThan(0);
    // x=0 should yield y=0
    const origin = points.find((p) => Math.abs(p.x) < 0.2);
    expect(origin).toBeDefined();
    expect(origin!.y).toBeCloseTo(origin!.x ** 2, 1);
  });

  it("evaluates trig (sin(x))", () => {
    const points = evaluateFunction(
      makeFn({ expression: "sin(x)" }),
      -Math.PI,
      Math.PI,
    );
    expect(points.length).toBeGreaterThan(0);
    // All y values should be between -1 and 1
    for (const p of points) {
      expect(p.y).toBeGreaterThanOrEqual(-1.001);
      expect(p.y).toBeLessThanOrEqual(1.001);
    }
  });

  it("skips NaN (sqrt(x) for negative x)", () => {
    const points = evaluateFunction(makeFn({ expression: "sqrt(x)" }), -5, 5);
    // Should have points only for x >= 0
    for (const p of points) {
      expect(p.x).toBeGreaterThanOrEqual(-0.001);
      expect(isFinite(p.y)).toBe(true);
    }
    // Should have fewer points than full domain
    const fullPoints = evaluateFunction(makeFn({ expression: "x" }), -5, 5);
    expect(points.length).toBeLessThan(fullPoints.length);
  });

  it("skips Infinity (1/x at x=0)", () => {
    const points = evaluateFunction(makeFn({ expression: "1/x" }), -5, 5);
    // No point should have Infinity or -Infinity
    for (const p of points) {
      expect(isFinite(p.y)).toBe(true);
    }
  });

  it("respects domain_min/domain_max", () => {
    const points = evaluateFunction(
      makeFn({ expression: "x", domain_min: 2, domain_max: 8 }),
    );
    expect(points.length).toBeGreaterThan(0);
    for (const p of points) {
      expect(p.x).toBeGreaterThanOrEqual(2);
      expect(p.x).toBeLessThanOrEqual(8);
    }
  });

  it("returns empty array for invalid expressions", () => {
    const points = evaluateFunction(
      makeFn({ expression: "not a valid expr !!!" }),
    );
    expect(points).toEqual([]);
  });

  it("handles constants (pi, e)", () => {
    const points = evaluateFunction(makeFn({ expression: "x + PI" }), 0, 1);
    expect(points.length).toBeGreaterThan(0);
    // At x=0, y should be approximately pi
    const first = points[0];
    expect(first.y).toBeCloseTo(Math.PI, 1);
  });

  it("generates approximately 101 points (100 intervals)", () => {
    const points = evaluateFunction(makeFn({ expression: "x" }), 0, 10);
    expect(points.length).toBe(101);
  });
});
