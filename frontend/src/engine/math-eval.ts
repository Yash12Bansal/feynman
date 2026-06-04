/**
 * Function-plotting helper for Chart.js.
 *
 * Converts FunctionDef expressions (e.g., "x^2", "sin(x)", "1/x") into
 * arrays of {x, y} data points. Expression parsing/evaluation is delegated to
 * the shared, memoized evaluator in `./expr/evaluate` so the diagram renderer
 * and the graph plotter use one sandboxed expr-eval core (no `new Function`).
 */

import { compile } from "./expr/evaluate";
import type { FunctionDef } from "../types/visuals";

/** Maximum absolute y value before we discard a point (prevents canvas blow-up). */
const Y_CLAMP = 1e6;

/** Default number of sample points across the domain. */
const SAMPLE_COUNT = 100;

export interface EvalPoint {
  x: number;
  y: number;
}

/**
 * Evaluate a mathematical function across its domain, returning plottable points.
 *
 * - Skips NaN / Infinity points (natural gaps for `1/x` at 0, `sqrt(x)` for x<0)
 * - Clamps extreme y values to prevent canvas blow-up
 * - Returns empty array for invalid expressions
 */
export function evaluateFunction(
  fn: FunctionDef,
  defaultMin = -10,
  defaultMax = 10,
): EvalPoint[] {
  // Invalid expressions compile to a NaN-returning stub, so every sample is
  // skipped below and we return [] — matching the old parse-failure behavior.
  const compiled = compile(fn.expression);

  const xMin = fn.domain_min ?? defaultMin;
  const xMax = fn.domain_max ?? defaultMax;
  const step = (xMax - xMin) / SAMPLE_COUNT;

  const points: EvalPoint[] = [];

  for (let i = 0; i <= SAMPLE_COUNT; i++) {
    const x = xMin + i * step;
    const y = compiled.evaluate({ x });
    if (!Number.isFinite(y)) continue;
    if (Math.abs(y) > Y_CLAMP) continue;
    points.push({ x, y });
  }

  return points;
}
