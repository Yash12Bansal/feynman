/**
 * Safe, memoized math-expression evaluator for diagram coordinates.
 *
 * Diagram specs may give any coordinate as a string expression that references
 * parameter names, e.g. `"450 + 80*cos(theta)"`. This module compiles each
 * unique expression ONCE (memoized by string) via `expr-eval`'s sandboxed
 * Parser and evaluates it against a `{ name: value }` scope.
 *
 * Why expr-eval and not `new Function`/`eval`: the previous diagram renderer
 * built a `new Function(...)` per call — both a code-injection surface and a
 * per-frame perf sink (rebuilt on every render, ~200x per graph curve). This
 * evaluator never constructs functions from strings and caches compiled ASTs,
 * so a parameter change only re-evaluates (no re-parse).
 *
 * Angle convention: trig functions are RADIANS (expr-eval native; matches the
 * graph-curve evaluator in `math-eval.ts`). Degree-typed FIELDS on elements
 * (e.g. `svg_arc.startAngle`) stay in degrees and are converted to radians at
 * their own boundary (see `arcPath` in DesignDiagramContent). So an author who
 * writes `startAngle: "theta"` supplies degrees; one who writes `cos(theta)`
 * inside a coordinate expression supplies radians.
 *
 * Supported functions (expr-eval built-ins, all Math-parity): sin, cos, tan,
 * asin, acos, atan2, sinh, cosh, tanh, sqrt, abs, log (natural log), exp, pow,
 * floor, ceil, min, max; constants PI, E. `^` is exponentiation.
 */

import { Parser } from "expr-eval";

/**
 * One shared parser. `assignment: false` removes the `=` operator so an
 * expression can never mutate scope or smuggle in a statement — coordinate
 * expressions are pure math. Every other operator keeps its (Math-parity)
 * default. This is the sandbox boundary: there is no `eval`/`Function` path,
 * and tokens like `eval`/`function`/`=` fail to parse (→ NaN, never executed).
 */
const parser = new Parser({ operators: { assignment: false } });

export interface Compiled {
  readonly source: string;
  /** Evaluate against a parameter scope. Returns NaN on any failure. */
  evaluate(scope: Record<string, number>): number;
}

const cache = new Map<string, Compiled>();

/**
 * Compile (and memoize) a math expression string. Never throws — a malformed
 * expression compiles to a stub whose `evaluate` returns NaN, so a bad string
 * is parsed at most once and never crashes the render path.
 */
export function compile(expr: string): Compiled {
  const cached = cache.get(expr);
  if (cached) return cached;

  let compiled: Compiled;
  try {
    const parsed = parser.parse(expr);
    compiled = {
      source: expr,
      evaluate(scope) {
        try {
          const result = parsed.evaluate(scope);
          return typeof result === "number" ? result : NaN;
        } catch {
          // Unbound variable, etc. — caller falls back.
          return NaN;
        }
      },
    };
  } catch {
    // Parse failure (malformed expr, disabled `=`, unknown token like `eval`).
    compiled = { source: expr, evaluate: () => NaN };
  }

  cache.set(expr, compiled);
  return compiled;
}

/** Compile (cached) + evaluate in one call, with a non-finite → fallback guard. */
export function evaluateExpr(
  expr: string,
  scope: Record<string, number>,
  fallback = 0,
): number {
  const result = compile(expr).evaluate(scope);
  return Number.isFinite(result) ? result : fallback;
}

/**
 * Resolve a coordinate value (number | expression-string | nullish) to a
 * number. Drop-in replacement for the renderer's old `resolveValue`.
 */
export function resolveCoord(
  val: number | string | undefined | null,
  scope: Record<string, number>,
  fallback = 0,
): number {
  if (val === undefined || val === null) return fallback;
  if (typeof val === "number") return Number.isFinite(val) ? val : fallback;
  return evaluateExpr(val, scope, fallback);
}

/**
 * Interpolate `${expr}` segments inside an SVG `transform` string against a
 * parameter scope. Each `${...}` is evaluated as a coordinate expression (same
 * sandbox + math vocabulary as `resolveCoord`) and replaced with its numeric
 * value; everything outside the braces is left verbatim.
 *
 * This is what lets a moving element TILT / SPIN / SQUASH (not just translate)
 * driven by an animated parameter — e.g.
 *   "translate(${x0 + range*t}, ${ground - 4*peak*t*(1-t)}) rotate(${angle})"
 * As the param `t` tweens, the whole group's transform recomputes per frame.
 *
 * Backward compatible: a transform with no `${` is returned unchanged (so every
 * existing static `transform` string passes straight through). A bad/unbound
 * expression resolves to 0 rather than corrupting the attribute.
 */
const TRANSFORM_TEMPLATE_RE = /\$\{([^}]*)\}/g;

export function resolveTransform(
  transform: string | undefined | null,
  scope: Record<string, number>,
): string | undefined {
  if (typeof transform !== "string" || transform.length === 0) return undefined;
  if (transform.indexOf("${") === -1) return transform;
  return transform.replace(TRANSFORM_TEMPLATE_RE, (_match, expr: string) => {
    const value = evaluateExpr(expr.trim(), scope, 0);
    // Round to keep the attribute compact and stable across frames.
    return String(Math.round(value * 1000) / 1000);
  });
}

/** Test/diagnostic helper — clears the compile cache. */
export function _clearExprCache(): void {
  cache.clear();
}
