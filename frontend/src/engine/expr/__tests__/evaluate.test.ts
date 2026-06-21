import { describe, it, expect, beforeEach } from "vitest";
import {
  compile,
  evaluateExpr,
  resolveCoord,
  resolveTransform,
  _clearExprCache,
} from "../evaluate";

beforeEach(() => {
  _clearExprCache();
});

describe("evaluate — Math parity", () => {
  // Every documented function must match its Math.* counterpart so the swap
  // from the old `new Function` evaluator is behavior-preserving.
  const cases: Array<[string, Record<string, number>, number]> = [
    ["sin(0)", {}, 0],
    ["cos(0)", {}, 1],
    ["tan(0)", {}, 0],
    ["sqrt(16)", {}, 4],
    ["abs(-3)", {}, 3],
    // log is NATURAL log (Math.log), NOT base-10 — log(E) === 1 pins this.
    ["log(E)", {}, 1],
    ["exp(0)", {}, 1],
    ["exp(1)", {}, Math.E],
    ["pow(2, 10)", {}, 1024],
    ["floor(2.7)", {}, 2],
    ["ceil(2.1)", {}, 3],
    ["min(3, 5)", {}, 3],
    ["max(3, 5)", {}, 5],
    ["atan2(1, 1)", {}, Math.PI / 4],
    ["asin(1)", {}, Math.PI / 2],
    ["acos(1)", {}, 0],
    ["sinh(0)", {}, 0],
    ["cosh(0)", {}, 1],
    ["tanh(0)", {}, 0],
    ["PI", {}, Math.PI],
    ["E", {}, Math.E],
  ];

  it.each(cases)("evaluates %s", (expr, scope, expected) => {
    expect(compile(expr).evaluate(scope)).toBeCloseTo(expected, 10);
  });

  it("treats trig as radians (sin(PI/2) ≈ 1)", () => {
    expect(compile("sin(PI/2)").evaluate({})).toBeCloseTo(1, 10);
  });

  it("treats ^ as exponentiation, not bitwise XOR", () => {
    // The old `new Function` evaluator interpreted `^` as JS XOR (2^10 === 8);
    // expr-eval treats it as power. This is an intentional correctness fix.
    expect(compile("2^10").evaluate({})).toBe(1024);
  });

  it("evaluates parameterized expressions", () => {
    expect(compile("450 + 80*cos(theta)").evaluate({ theta: 0 })).toBeCloseTo(
      530,
      10,
    );
    expect(
      compile("450 + 80*cos(theta)").evaluate({ theta: Math.PI }),
    ).toBeCloseTo(370, 10);
  });
});

describe("compile — memoization", () => {
  it("returns the same compiled object for the same string", () => {
    const a = compile("a + b");
    const b = compile("a + b");
    expect(a).toBe(b);
  });

  it("caches parse failures (no re-parse, no throw)", () => {
    const a = compile("not valid !!!");
    const b = compile("not valid !!!");
    expect(a).toBe(b);
    expect(a.evaluate({})).toBeNaN();
  });
});

describe("evaluate — failure handling", () => {
  it("returns NaN for an unbound variable", () => {
    expect(compile("missing + 1").evaluate({})).toBeNaN();
  });

  it("returns NaN for a malformed expression", () => {
    expect(compile("3 + * 4").evaluate({})).toBeNaN();
  });
});

describe("evaluate — sandbox (no eval / Function / assignment)", () => {
  // None of these should execute anything; they must parse-fail → NaN.
  const dangerous = [
    "x = 5", // assignment disabled
    "eval('1+1')",
    "(function(){ return 1 })()",
    "globalThis",
    "this",
    "window",
    "constructor",
  ];

  it.each(dangerous)("does not execute %s (returns NaN)", (expr) => {
    expect(compile(expr).evaluate({ x: 1 })).toBeNaN();
  });
});

describe("resolveCoord", () => {
  it("passes through finite numbers unchanged", () => {
    expect(resolveCoord(42, {})).toBe(42);
    expect(resolveCoord(0, {})).toBe(0);
  });

  it("returns the fallback for nullish", () => {
    expect(resolveCoord(undefined, {})).toBe(0);
    expect(resolveCoord(null, {}, 7)).toBe(7);
  });

  it("evaluates string expressions", () => {
    expect(resolveCoord("3 + 4", {})).toBe(7);
    expect(resolveCoord("2 * a", { a: 5 })).toBe(10);
  });

  it("returns the fallback when an expression fails or is non-finite", () => {
    expect(resolveCoord("1/0", {}, -1)).toBe(-1); // Infinity → fallback
    expect(resolveCoord("missing", {}, -1)).toBe(-1);
  });
});

describe("evaluateExpr", () => {
  it("returns the fallback for non-finite results", () => {
    expect(evaluateExpr("1/0", {}, 99)).toBe(99);
    expect(evaluateExpr("sqrt(-1)", {}, 99)).toBe(99); // NaN → fallback
  });
});

describe("resolveTransform — param-driven motion", () => {
  it("returns a plain (no-${}) transform unchanged", () => {
    expect(resolveTransform("translate(10, 20) rotate(5)", {})).toBe(
      "translate(10, 20) rotate(5)",
    );
  });

  it("returns undefined for empty/nullish input (so the attr is omitted)", () => {
    expect(resolveTransform(undefined, {})).toBeUndefined();
    expect(resolveTransform(null, {})).toBeUndefined();
    expect(resolveTransform("", {})).toBeUndefined();
  });

  it("interpolates ${expr} segments against the param scope", () => {
    // A ball arcing: x is linear in t, y is a parabola in t.
    const out = resolveTransform(
      "translate(${x0 + range*t}, ${ground - 4*peak*t*(1-t)})",
      { x0: 70, range: 340, ground: 215, peak: 150, t: 0.5 },
    );
    expect(out).toBe("translate(240, 65)");
  });

  it("spins via rotate() driven by the progress param", () => {
    expect(resolveTransform("rotate(${t*1440} 15 6)", { t: 0.25 })).toBe(
      "rotate(360 15 6)",
    );
  });

  it("resolves a bad/unbound ${expr} to 0 rather than corrupting the attr", () => {
    expect(resolveTransform("translate(${nope}, 5)", {})).toBe(
      "translate(0, 5)",
    );
  });
});
