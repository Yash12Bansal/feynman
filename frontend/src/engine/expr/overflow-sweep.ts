/**
 * Parameter-overflow sweep — the automated guard for the viewBox-clipping bug.
 *
 * `DesignDiagramContent` sets the SVG `viewBox` to `0 0 width height` with no
 * overflow protection, so any element whose resolved coordinates fall outside
 * `[0,0,width,height]` is silently clipped. For a parameterized spec, a bad
 * expression may stay in-bounds at the default but clip at a slider extreme.
 *
 * `sweepSpec` steps every parameter across its range, resolves each element's
 * bounds at each combination, and reports any coordinate that is non-finite
 * (`reason: "nan"`) or outside the canvas (`reason: "out_of_bounds"`). It is
 * pure (no React, no DOM) so it runs in unit tests and could gate CI.
 *
 * Coordinate resolution mirrors the renderer's per-field fallbacks, so an
 * ABSENT optional field uses the same default the renderer draws (never a
 * false NaN), while a PRESENT-but-broken expression surfaces as NaN.
 *
 * Limitations (documented, not silent): `svg_path` `d` data is a static string
 * and is not swept; `svg_group` children are checked in local coordinates (the
 * group `transform` is not applied); the multi-parameter cartesian product is
 * capped — beyond the cap it falls back to per-axis sweeps plus the corner
 * vectors, which catches monotonic clipping but can miss an interior singular
 * point on a diagonal.
 */

import type {
  DesignDiagramElement,
  DesignDiagramSliderParam,
  DesignDiagramSpec,
} from "../../types/visuals";
import { resolveCoord } from "./evaluate";

export interface SweepViolation {
  paramVector: Record<string, number>;
  elementId: string | undefined;
  elementType: string;
  field: string;
  value: number;
  reason: "nan" | "out_of_bounds";
}

export interface SweepResult {
  ok: boolean;
  violations: SweepViolation[];
  combinationsTested: number;
}

export interface SweepOptions {
  /** Max parameter combinations before falling back to axes + corners. */
  maxCombinations?: number;
  /** Cap on collected violations (keeps output bounded). */
  maxViolations?: number;
}

const DEFAULT_MAX_COMBINATIONS = 2000;
const DEFAULT_MAX_VIOLATIONS = 200;

/** Evenly spaced values across a parameter's range, inclusive of both ends. */
function axisValues(p: DesignDiagramSliderParam): number[] {
  const span = p.max - p.min;
  const rawStep = p.step && p.step > 0 ? p.step : span / 10;
  const n = span === 0 ? 0 : Math.max(1, Math.round(Math.abs(span / rawStep)));
  const values: number[] = [];
  for (let i = 0; i <= n; i++)
    values.push(p.min + (n === 0 ? 0 : (i / n) * span));
  return values;
}

/** Build the list of parameter vectors to test. */
function buildVectors(
  params: readonly DesignDiagramSliderParam[],
  maxCombinations: number,
): Array<Record<string, number>> {
  if (params.length === 0) return [{}];

  const axes = params.map((p) => ({ name: p.name, values: axisValues(p) }));
  const total = axes.reduce((acc, a) => acc * a.values.length, 1);

  if (total <= maxCombinations) {
    let vectors: Array<Record<string, number>> = [{}];
    for (const axis of axes) {
      const next: Array<Record<string, number>> = [];
      for (const vec of vectors)
        for (const v of axis.values) next.push({ ...vec, [axis.name]: v });
      vectors = next;
    }
    return vectors;
  }

  // Fallback: each axis swept at the others' defaults, plus the 2^n corners.
  const defaults: Record<string, number> = {};
  for (const p of params) defaults[p.name] = p.default;

  const vectors: Array<Record<string, number>> = [];
  for (const axis of axes)
    for (const v of axis.values) vectors.push({ ...defaults, [axis.name]: v });

  const cornerCount = Math.min(1 << params.length, 1024);
  for (let mask = 0; mask < cornerCount; mask++) {
    const vec: Record<string, number> = {};
    params.forEach((p, idx) => {
      vec[p.name] = (mask >> idx) & 1 ? p.max : p.min;
    });
    vectors.push(vec);
  }
  return vectors;
}

interface BoundPoint {
  field: string;
  x: number;
  y: number;
}

/**
 * Resolve an element's checkable bound points for a given scope. Absent fields
 * use the renderer's defaults; present-but-broken fields resolve to NaN.
 */
function elementPoints(
  el: DesignDiagramElement,
  scope: Record<string, number>,
): BoundPoint[] {
  // Present → value (NaN if the expression is bad); absent → renderer default.
  const r = (v: number | string | undefined, fallback: number): number =>
    v === undefined || v === null ? fallback : resolveCoord(v, scope, NaN);

  switch (el.type) {
    case "svg_line":
    case "svg_arrow":
      return [
        { field: "p1", x: r(el.x1, 0), y: r(el.y1, 0) },
        { field: "p2", x: r(el.x2, 0), y: r(el.y2, 0) },
      ];
    case "svg_rect": {
      const x = r(el.x, 0);
      const y = r(el.y, 0);
      const w = r(el.width, 100);
      const h = r(el.height, 50);
      return [
        { field: "topLeft", x, y },
        { field: "bottomRight", x: x + w, y: y + h },
      ];
    }
    case "svg_frame": {
      const x = r(el.x, 0);
      const y = r(el.y, 0);
      const w = r(el.width, 300);
      const h = r(el.height, 200);
      return [
        { field: "topLeft", x, y },
        { field: "bottomRight", x: x + w, y: y + h },
      ];
    }
    case "svg_circle": {
      const cx = r(el.cx, 0);
      const cy = r(el.cy, 0);
      const rad = r(el.r, 10);
      return [
        { field: "min", x: cx - rad, y: cy - rad },
        { field: "max", x: cx + rad, y: cy + rad },
      ];
    }
    case "svg_ellipse": {
      const cx = r(el.cx, 0);
      const cy = r(el.cy, 0);
      const rx = r(el.rx, 10);
      const ry = r(el.ry, 5);
      return [
        { field: "min", x: cx - rx, y: cy - ry },
        { field: "max", x: cx + rx, y: cy + ry },
      ];
    }
    case "svg_arc": {
      // Over-approximate the arc by its full circle's bounding box.
      const cx = r(el.cx, 0);
      const cy = r(el.cy, 0);
      const rad = r(el.r, 50);
      return [
        { field: "min", x: cx - rad, y: cy - rad },
        { field: "max", x: cx + rad, y: cy + rad },
      ];
    }
    case "svg_text":
    case "svg_latex":
      return [{ field: "anchor", x: r(el.x, 0), y: r(el.y, 0) }];
    case "graph": {
      const x = r(el.x, 0);
      const y = r(el.y, 0);
      const w = r(el.width, 300);
      const h = r(el.height, 200);
      return [
        { field: "topLeft", x, y },
        { field: "bottomRight", x: x + w, y: y + h },
      ];
    }
    // svg_path (static `d`) and svg_group (recursed by the caller) yield no
    // direct points here.
    default:
      return [];
  }
}

/** Recursively flatten groups so every primitive is checked. */
function flatten(
  elements: readonly DesignDiagramElement[] | undefined,
): DesignDiagramElement[] {
  const out: DesignDiagramElement[] = [];
  for (const el of elements ?? []) {
    if (el.type === "svg_group") {
      out.push(...flatten(el.elements));
    } else {
      out.push(el);
    }
  }
  return out;
}

/**
 * Sweep every parameter combination and report NaN / out-of-bounds coords.
 * `ok === true` means no element ever leaves the canvas across the swept range.
 */
export function sweepSpec(
  spec: DesignDiagramSpec,
  opts: SweepOptions = {},
): SweepResult {
  const maxCombinations = opts.maxCombinations ?? DEFAULT_MAX_COMBINATIONS;
  const maxViolations = opts.maxViolations ?? DEFAULT_MAX_VIOLATIONS;
  const width = spec.width ?? 900;
  const height = spec.height ?? 650;

  const elements = flatten(spec.elements);
  const vectors = buildVectors(spec.parameters ?? [], maxCombinations);
  const violations: SweepViolation[] = [];

  outer: for (const scope of vectors) {
    for (const el of elements) {
      for (const pt of elementPoints(el, scope)) {
        const nan = !Number.isFinite(pt.x) || !Number.isFinite(pt.y);
        const oob =
          !nan && (pt.x < 0 || pt.x > width || pt.y < 0 || pt.y > height);
        if (nan || oob) {
          violations.push({
            paramVector: scope,
            elementId: el.id,
            elementType: el.type,
            field: pt.field,
            value: nan
              ? Number.isFinite(pt.x)
                ? pt.y
                : pt.x
              : pt.x < 0 || pt.x > width
                ? pt.x
                : pt.y,
            reason: nan ? "nan" : "out_of_bounds",
          });
          if (violations.length >= maxViolations) break outer;
        }
      }
    }
  }

  return {
    ok: violations.length === 0,
    violations,
    combinationsTested: vectors.length,
  };
}
