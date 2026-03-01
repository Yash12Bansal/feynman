/**
 * Pure chart layout engine — no React, no DOM, no Rough.js.
 *
 * Computes axis ticks, data positions, and pixel mapping functions
 * for SVG chart rendering. Mirrors `engine/layout/diagram-layout.ts`.
 */

import type {
  ShowGraphInstruction,
  DataSeries,
  FunctionDef,
} from "../../../types/visuals";
import { evaluateFunction, type EvalPoint } from "../../math-eval";

// ── Constants ─────────────────────────────────────────────────

const VIEW_WIDTH = 600;
const VIEW_HEIGHT = 400;

const MARGIN = {
  left: 64,
  right: 20,
  top: 16,
  topWithTitle: 36,
  bottom: 48,
} as const;

const MAX_POINTS_PER_SERIES = 200;
const MAX_SERIES = 8;

// ── Types ─────────────────────────────────────────────────────

export interface TickMark {
  value: number;
  px: number;
  label: string;
}

export interface AxisLayout {
  min: number;
  max: number;
  ticks: TickMark[];
}

interface PlotArea {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface BaseLayout {
  viewWidth: number;
  viewHeight: number;
  plot: PlotArea;
  xAxis: AxisLayout;
  yAxis: AxisLayout;
  xLabel: string;
  yLabel: string;
  zeroLineY: number | null;
  rotateXLabels: boolean;
  showLegend: boolean;
  seriesLabels: string[];
  seriesColors: string[];
}

export interface BarPosition {
  x: number;
  y: number;
  width: number;
  height: number;
  seriesIdx: number;
  barIdx: number;
}

export interface PointPosition {
  px: number;
  py: number;
  seriesIdx: number;
  pointIdx: number;
}

export interface LineChartLayout extends BaseLayout {
  chartType: "line";
  seriesPoints: PointPosition[][];
}

export interface BarChartLayout extends BaseLayout {
  chartType: "bar";
  bars: BarPosition[];
  categoryLabels: string[];
}

export interface ScatterChartLayout extends BaseLayout {
  chartType: "scatter";
  seriesPoints: PointPosition[][];
}

export interface FunctionChartLayout extends BaseLayout {
  chartType: "function";
  seriesPoints: PointPosition[][];
  evaluatedSeries: EvalPoint[][];
}

export type ChartLayout =
  | LineChartLayout
  | BarChartLayout
  | ScatterChartLayout
  | FunctionChartLayout;

// ── Series colors ─────────────────────────────────────────────

const SERIES_COLORS = [
  "#a78bfa", // accentPurple
  "#60a5fa", // accentBlue
  "#4ade80", // accentGreen
  "#fbbf24", // accentAmber
  "#ff6384",
  "#ff9f40",
];

function pickColor(index: number, explicit?: string): string {
  return explicit || SERIES_COLORS[index % SERIES_COLORS.length];
}

// ── Nice axis algorithm ───────────────────────────────────────

const NICE_STEPS = [1, 2, 5, 10];

/**
 * Compute "nice" axis ticks that bracket the data range.
 * Inspired by Wilkinson's extended algorithm — simplified for teaching charts.
 */
export function niceAxis(
  dataMin: number,
  dataMax: number,
  targetTicks = 6,
): AxisLayout {
  // Degenerate: all same value
  if (dataMin === dataMax) {
    dataMin = dataMin - 1;
    dataMax = dataMax + 1;
  }

  // Ensure min < max
  if (dataMin > dataMax) {
    [dataMin, dataMax] = [dataMax, dataMin];
  }

  const range = dataMax - dataMin;
  const roughStep = range / Math.max(targetTicks - 1, 1);
  const mag = Math.pow(10, Math.floor(Math.log10(roughStep)));

  let bestStep = mag;
  for (const ns of NICE_STEPS) {
    const candidate = ns * mag;
    if (candidate >= roughStep) {
      bestStep = candidate;
      break;
    }
  }

  const niceMin = Math.floor(dataMin / bestStep) * bestStep;
  const niceMax = Math.ceil(dataMax / bestStep) * bestStep;

  const ticks: TickMark[] = [];
  // Round to avoid floating point artifacts
  const precision = Math.max(0, -Math.floor(Math.log10(bestStep)) + 1);
  for (let v = niceMin; v <= niceMax + bestStep * 0.01; v += bestStep) {
    const rounded = parseFloat(v.toFixed(precision));
    ticks.push({ value: rounded, px: 0, label: formatTick(rounded) });
  }

  return { min: niceMin, max: niceMax, ticks };
}

function formatTick(value: number): string {
  if (Math.abs(value) >= 1e6) return value.toExponential(1);
  if (Number.isInteger(value)) return String(value);
  // Trim trailing zeros
  return parseFloat(value.toPrecision(4)).toString();
}

// ── Pixel mapping ─────────────────────────────────────────────

function makeToPixelX(plot: PlotArea, min: number, max: number) {
  const range = max - min || 1;
  return (v: number) => plot.x + ((v - min) / range) * plot.width;
}

function makeToPixelY(plot: PlotArea, min: number, max: number) {
  const range = max - min || 1;
  // Y is flipped: top = max, bottom = min
  return (v: number) => plot.y + (1 - (v - min) / range) * plot.height;
}

function applyPixelToTicks(
  ticks: TickMark[],
  toPixel: (v: number) => number,
): void {
  for (const t of ticks) {
    t.px = toPixel(t.value);
  }
}

// ── Compute plot area ─────────────────────────────────────────

function computePlot(hasTitle: boolean): PlotArea {
  const top = hasTitle ? MARGIN.topWithTitle : MARGIN.top;
  return {
    x: MARGIN.left,
    y: top,
    width: VIEW_WIDTH - MARGIN.left - MARGIN.right,
    height: VIEW_HEIGHT - top - MARGIN.bottom,
  };
}

// ── Per-chart-type builders ───────────────────────────────────

function buildBarLayout(
  series: DataSeries[],
  instruction: ShowGraphInstruction,
): BarChartLayout | null {
  const capped = series.slice(0, MAX_SERIES);
  if (capped.length === 0) return null;

  const firstSeries = capped[0];
  const points = firstSeries.points.slice(0, MAX_POINTS_PER_SERIES);
  if (points.length === 0) return null;

  const hasLabels = points.some((p) => p.label);
  const hasTitle = !!instruction.title;
  const plot = computePlot(hasTitle);

  // Category labels
  const categoryLabels = points.map((p) => p.label || String(p.x));
  const rotateXLabels = categoryLabels.some((l) => l.length > 6);

  // Y-axis from data
  let yMin = 0;
  let yMax = 0;
  for (const s of capped) {
    for (const p of s.points.slice(0, MAX_POINTS_PER_SERIES)) {
      if (p.y < yMin) yMin = p.y;
      if (p.y > yMax) yMax = p.y;
    }
  }

  // Apply overrides
  if (instruction.y_axis?.min !== undefined) yMin = instruction.y_axis.min;
  if (instruction.y_axis?.max !== undefined) yMax = instruction.y_axis.max;

  // Always include 0 for bar charts
  if (yMin > 0) yMin = 0;
  if (yMax < 0) yMax = 0;

  const yAxis = niceAxis(yMin, yMax);
  const toPixelY = makeToPixelY(plot, yAxis.min, yAxis.max);
  applyPixelToTicks(yAxis.ticks, toPixelY);

  // X positions — evenly spaced categories
  const numCategories = points.length;
  const categoryWidth = plot.width / numCategories;
  const numSeries = capped.length;
  const groupWidth = categoryWidth * 0.7;
  const barWidth = groupWidth / numSeries;
  const groupOffset = (categoryWidth - groupWidth) / 2;

  const xTicks: TickMark[] = categoryLabels.map((label, i) => ({
    value: i,
    px: plot.x + i * categoryWidth + categoryWidth / 2,
    label,
  }));

  const xAxis: AxisLayout = {
    min: 0,
    max: numCategories,
    ticks: xTicks,
  };

  // Build bar positions
  const zeroY = toPixelY(0);
  const bars: BarPosition[] = [];

  for (let si = 0; si < numSeries; si++) {
    const seriesPoints = capped[si].points.slice(0, MAX_POINTS_PER_SERIES);
    for (let bi = 0; bi < seriesPoints.length; bi++) {
      const p = seriesPoints[bi];
      const barX = plot.x + bi * categoryWidth + groupOffset + si * barWidth;
      const barTop = toPixelY(p.y);

      bars.push({
        x: barX,
        y: Math.min(barTop, zeroY),
        width: barWidth,
        height: Math.abs(barTop - zeroY),
        seriesIdx: si,
        barIdx: bi,
      });
    }
  }

  // Zero line position
  const zeroLineY = yAxis.min < 0 && yAxis.max > 0 ? toPixelY(0) : null;

  // Series metadata
  const seriesLabels = capped.map((s, i) => s.label || `Series ${i + 1}`);
  const seriesColors = capped.map((s, i) => pickColor(i, s.color));

  if (hasLabels) {
    return {
      chartType: "bar",
      viewWidth: VIEW_WIDTH,
      viewHeight: VIEW_HEIGHT,
      plot,
      xAxis,
      yAxis,
      xLabel: instruction.x_axis?.label || "",
      yLabel: instruction.y_axis?.label || "",
      zeroLineY,
      rotateXLabels,
      showLegend: numSeries > 1,
      seriesLabels,
      seriesColors,
      bars,
      categoryLabels,
    };
  }

  // Numeric bar chart — positions from x values
  const allX = capped.flatMap((s) =>
    s.points.slice(0, MAX_POINTS_PER_SERIES).map((p) => p.x),
  );
  const xMin = instruction.x_axis?.min ?? Math.min(...allX);
  const xMax = instruction.x_axis?.max ?? Math.max(...allX);
  const numericXAxis = niceAxis(xMin, xMax);
  const toPixelX = makeToPixelX(plot, numericXAxis.min, numericXAxis.max);
  applyPixelToTicks(numericXAxis.ticks, toPixelX);

  // Recompute bars with numeric x positions
  const avgSpacing =
    allX.length > 1
      ? (Math.max(...allX) - Math.min(...allX)) / (allX.length - 1)
      : 1;
  const numericBarWidth = Math.max(
    4,
    Math.min(
      categoryWidth * 0.6,
      (avgSpacing / (numericXAxis.max - numericXAxis.min)) * plot.width * 0.6,
    ),
  );

  const numericBars: BarPosition[] = [];
  for (let si = 0; si < numSeries; si++) {
    const sp = capped[si].points.slice(0, MAX_POINTS_PER_SERIES);
    const seriesBarWidth = numericBarWidth / numSeries;
    for (let bi = 0; bi < sp.length; bi++) {
      const p = sp[bi];
      const cx = toPixelX(p.x);
      const barX = cx - numericBarWidth / 2 + si * seriesBarWidth;
      const barTop = toPixelY(p.y);

      numericBars.push({
        x: barX,
        y: Math.min(barTop, zeroY),
        width: seriesBarWidth,
        height: Math.abs(barTop - zeroY),
        seriesIdx: si,
        barIdx: bi,
      });
    }
  }

  return {
    chartType: "bar",
    viewWidth: VIEW_WIDTH,
    viewHeight: VIEW_HEIGHT,
    plot,
    xAxis: numericXAxis,
    yAxis,
    xLabel: instruction.x_axis?.label || "",
    yLabel: instruction.y_axis?.label || "",
    zeroLineY,
    rotateXLabels: false,
    showLegend: numSeries > 1,
    seriesLabels,
    seriesColors,
    bars: numericBars,
    categoryLabels: numericXAxis.ticks.map((t) => t.label),
  };
}

function buildLineLayout(
  series: DataSeries[],
  instruction: ShowGraphInstruction,
): LineChartLayout | null {
  const capped = series.slice(0, MAX_SERIES);
  if (capped.length === 0) return null;

  const allPoints = capped.flatMap((s) =>
    s.points.slice(0, MAX_POINTS_PER_SERIES),
  );
  if (allPoints.length === 0) return null;

  const hasTitle = !!instruction.title;
  const plot = computePlot(hasTitle);

  // Compute data ranges
  let xMin = Math.min(...allPoints.map((p) => p.x));
  let xMax = Math.max(...allPoints.map((p) => p.x));
  let yMin = Math.min(...allPoints.map((p) => p.y));
  let yMax = Math.max(...allPoints.map((p) => p.y));

  // Apply overrides (ignore zero-width)
  if (
    instruction.x_axis?.min !== undefined &&
    instruction.x_axis?.max !== undefined &&
    instruction.x_axis.min < instruction.x_axis.max
  ) {
    xMin = instruction.x_axis.min;
    xMax = instruction.x_axis.max;
  } else {
    if (instruction.x_axis?.min !== undefined) xMin = instruction.x_axis.min;
    if (instruction.x_axis?.max !== undefined) xMax = instruction.x_axis.max;
  }
  if (
    instruction.y_axis?.min !== undefined &&
    instruction.y_axis?.max !== undefined &&
    instruction.y_axis.min < instruction.y_axis.max
  ) {
    yMin = instruction.y_axis.min;
    yMax = instruction.y_axis.max;
  } else {
    if (instruction.y_axis?.min !== undefined) yMin = instruction.y_axis.min;
    if (instruction.y_axis?.max !== undefined) yMax = instruction.y_axis.max;
  }

  const xAxis = niceAxis(xMin, xMax);
  const yAxis = niceAxis(yMin, yMax);

  const toPixelX = makeToPixelX(plot, xAxis.min, xAxis.max);
  const toPixelY = makeToPixelY(plot, yAxis.min, yAxis.max);

  applyPixelToTicks(xAxis.ticks, toPixelX);
  applyPixelToTicks(yAxis.ticks, toPixelY);

  const seriesPoints: PointPosition[][] = capped.map((s, si) =>
    s.points.slice(0, MAX_POINTS_PER_SERIES).map((p, pi) => ({
      px: toPixelX(p.x),
      py: toPixelY(p.y),
      seriesIdx: si,
      pointIdx: pi,
    })),
  );

  const zeroLineY = yAxis.min < 0 && yAxis.max > 0 ? toPixelY(0) : null;
  const rotateXLabels = xAxis.ticks.some((t) => t.label.length > 6);

  return {
    chartType: "line",
    viewWidth: VIEW_WIDTH,
    viewHeight: VIEW_HEIGHT,
    plot,
    xAxis,
    yAxis,
    xLabel: instruction.x_axis?.label || "",
    yLabel: instruction.y_axis?.label || "",
    zeroLineY,
    rotateXLabels,
    showLegend: capped.length > 1,
    seriesLabels: capped.map((s, i) => s.label || `Series ${i + 1}`),
    seriesColors: capped.map((s, i) => pickColor(i, s.color)),
    seriesPoints,
  };
}

function buildScatterLayout(
  series: DataSeries[],
  instruction: ShowGraphInstruction,
): ScatterChartLayout | null {
  const lineLayout = buildLineLayout(series, instruction);
  if (!lineLayout) return null;

  return {
    ...lineLayout,
    chartType: "scatter",
  };
}

function buildFunctionLayout(
  functions: FunctionDef[],
  instruction: ShowGraphInstruction,
): FunctionChartLayout | null {
  const capped = functions.slice(0, MAX_SERIES);
  if (capped.length === 0) return null;

  const xMin = instruction.x_axis?.min ?? -10;
  const xMax = instruction.x_axis?.max ?? 10;

  // Evaluate all functions
  const evaluatedSeries: EvalPoint[][] = capped.map((fn) =>
    evaluateFunction(fn, xMin, xMax),
  );

  // If all functions return empty points, bail
  if (evaluatedSeries.every((pts) => pts.length === 0)) return null;

  const allPoints = evaluatedSeries.flat();
  const hasTitle = !!instruction.title;
  const plot = computePlot(hasTitle);

  let dataYMin = Math.min(...allPoints.map((p) => p.y));
  let dataYMax = Math.max(...allPoints.map((p) => p.y));

  if (instruction.y_axis?.min !== undefined) dataYMin = instruction.y_axis.min;
  if (instruction.y_axis?.max !== undefined) dataYMax = instruction.y_axis.max;

  const xAxis = niceAxis(xMin, xMax);
  const yAxis = niceAxis(dataYMin, dataYMax);

  const toPixelX = makeToPixelX(plot, xAxis.min, xAxis.max);
  const toPixelY = makeToPixelY(plot, yAxis.min, yAxis.max);

  applyPixelToTicks(xAxis.ticks, toPixelX);
  applyPixelToTicks(yAxis.ticks, toPixelY);

  const seriesPoints: PointPosition[][] = evaluatedSeries.map((pts, si) =>
    pts.map((p, pi) => ({
      px: toPixelX(p.x),
      py: toPixelY(p.y),
      seriesIdx: si,
      pointIdx: pi,
    })),
  );

  const zeroLineY = yAxis.min < 0 && yAxis.max > 0 ? toPixelY(0) : null;

  return {
    chartType: "function",
    viewWidth: VIEW_WIDTH,
    viewHeight: VIEW_HEIGHT,
    plot,
    xAxis,
    yAxis,
    xLabel: instruction.x_axis?.label || "",
    yLabel: instruction.y_axis?.label || "",
    zeroLineY,
    rotateXLabels: false,
    showLegend: capped.length > 1,
    seriesLabels: capped.map((fn) => fn.label || fn.expression),
    seriesColors: capped.map((fn, i) => pickColor(i, fn.color)),
    seriesPoints,
    evaluatedSeries,
  };
}

// ── Public API ────────────────────────────────────────────────

/**
 * Compute chart layout from a ShowGraphInstruction.
 * Returns null when there is no renderable data (triggers fallback).
 */
export function computeChartLayout(
  instruction: ShowGraphInstruction,
): ChartLayout | null {
  const hasFunctions =
    instruction.functions && instruction.functions.length > 0;
  const hasSeries = instruction.series && instruction.series.length > 0;

  switch (instruction.graph_type) {
    case "function":
      if (hasFunctions)
        return buildFunctionLayout(instruction.functions!, instruction);
      return null;

    case "bar":
      if (hasSeries) return buildBarLayout(instruction.series!, instruction);
      return null;

    case "scatter":
      if (hasSeries)
        return buildScatterLayout(instruction.series!, instruction);
      return null;

    case "line":
    default:
      if (hasSeries) return buildLineLayout(instruction.series!, instruction);
      if (hasFunctions)
        return buildFunctionLayout(instruction.functions!, instruction);
      return null;
  }
}
