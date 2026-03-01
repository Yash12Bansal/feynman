/**
 * Hand-drawn chart renderer using Rough.js.
 *
 * Two-layer SVG architecture (mirrors RoughDiagramContent):
 * 1. Rough layer (imperative) — Rough.js gridlines, axes, data shapes
 * 2. Label layer (declarative React) — tick labels, axis labels, legend
 *
 * Replaces Chart.js Canvas for the whiteboard surface only.
 * Clean card-list renderer keeps Chart.js unchanged.
 */

import { useEffect, useMemo, useRef } from "react";
import gsap from "gsap";
import rough from "roughjs";
import type { ShowGraphInstruction } from "../../../types/visuals";
import { COLORS } from "../../theme";
import { computeChartLayout, type ChartLayout } from "../layout/chart-layout";
import {
  hashSeed,
  seriesRoughOptions,
  AXIS_DEFAULTS,
  GRID_DEFAULTS,
} from "./rough-helpers";
import { ALIVE_FILTER_ID } from "../AliveFilter";

// ── Constants ─────────────────────────────────────────────────

const GRAPH_TYPE_LABELS: Record<string, string> = {
  line: "LINE CHART",
  bar: "BAR CHART",
  scatter: "SCATTER PLOT",
  function: "FUNCTION GRAPH",
};

const LABEL_FONT = "Inter, system-ui, sans-serif";

// ── Structured rough chart ────────────────────────────────────

function StructuredRoughGraph({
  instruction,
  layout,
}: {
  instruction: ShowGraphInstruction;
  layout: ChartLayout;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const roughLayerRef = useRef<SVGGElement>(null);
  const labelLayerRef = useRef<SVGGElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  const animated = instruction.animated !== false;

  // ── Layer 1: Rough.js drawing ─────────────────────────────
  useEffect(() => {
    const svg = svgRef.current;
    const roughLayer = roughLayerRef.current;
    if (!svg || !roughLayer) return;

    // Clear previous
    while (roughLayer.firstChild) {
      roughLayer.removeChild(roughLayer.firstChild);
    }

    const rc = rough.svg(svg);
    const { plot, yAxis } = layout;

    // 1. Horizontal gridlines at each y-tick
    for (let i = 0; i < yAxis.ticks.length; i++) {
      const tick = yAxis.ticks[i];
      const gridLine = rc.line(
        plot.x,
        tick.px,
        plot.x + plot.width,
        tick.px,
        GRID_DEFAULTS,
      );
      gridLine.setAttribute("data-rough-gridline", `y-${i}`);
      roughLayer.appendChild(gridLine);
    }

    // 2. Y-axis line
    const yAxisLine = rc.line(
      plot.x,
      plot.y,
      plot.x,
      plot.y + plot.height,
      AXIS_DEFAULTS,
    );
    yAxisLine.setAttribute("data-rough-axis", "y");
    roughLayer.appendChild(yAxisLine);

    // 3. X-axis line at y=0 or bottom
    const xAxisY =
      layout.zeroLineY !== null ? layout.zeroLineY : plot.y + plot.height;
    const xAxisLine = rc.line(
      plot.x,
      xAxisY,
      plot.x + plot.width,
      xAxisY,
      AXIS_DEFAULTS,
    );
    xAxisLine.setAttribute("data-rough-axis", "x");
    roughLayer.appendChild(xAxisLine);

    // 4. Data shapes — dispatch by chart type
    if (layout.chartType === "line" || layout.chartType === "function") {
      for (let si = 0; si < layout.seriesPoints.length; si++) {
        const pts = layout.seriesPoints[si];
        if (pts.length < 2) continue;

        const coords: [number, number][] = pts.map((p) => [p.px, p.py]);
        const color = layout.seriesColors[si];
        const opts = seriesRoughOptions(
          color,
          hashSeed(`series-${si}`),
          "line",
        );
        const path = rc.linearPath(coords, opts);
        path.setAttribute("data-rough-series", String(si));
        roughLayer.appendChild(path);
      }
    } else if (layout.chartType === "bar") {
      for (const bar of layout.bars) {
        const color = layout.seriesColors[bar.seriesIdx];
        const opts = seriesRoughOptions(
          color,
          hashSeed(`bar-${bar.seriesIdx}-${bar.barIdx}`),
          "bar",
        );
        const rect = rc.rectangle(bar.x, bar.y, bar.width, bar.height, opts);
        rect.setAttribute("data-rough-bar", `${bar.seriesIdx}-${bar.barIdx}`);
        roughLayer.appendChild(rect);
      }
    } else if (layout.chartType === "scatter") {
      for (let si = 0; si < layout.seriesPoints.length; si++) {
        const pts = layout.seriesPoints[si];
        const color = layout.seriesColors[si];
        for (let pi = 0; pi < pts.length; pi++) {
          const p = pts[pi];
          const opts = seriesRoughOptions(
            color,
            hashSeed(`point-${si}-${pi}`),
            "scatter",
          );
          const dot = rc.circle(p.px, p.py, 10, opts);
          dot.setAttribute("data-rough-point", `${si}-${pi}`);
          roughLayer.appendChild(dot);
        }
      }
    }
  }, [layout]);

  // ── Layer 2: GSAP animation ───────────────────────────────
  useEffect(() => {
    const svg = svgRef.current;
    const labelLayer = labelLayerRef.current;
    if (!svg || !labelLayer || !animated) return;

    timelineRef.current?.kill();

    const tl = gsap.timeline();
    timelineRef.current = tl;

    // Gather elements
    const axisEls = svg.querySelectorAll<SVGElement>("[data-rough-axis]");
    const gridEls = svg.querySelectorAll<SVGElement>("[data-rough-gridline]");
    const labelEls =
      labelLayer.querySelectorAll<SVGElement>("[data-chart-label]");

    // Phase 1: Axes draw in via strokeDashoffset
    const axisPaths: SVGPathElement[] = [];
    axisEls.forEach((el) => {
      const path = el.querySelector<SVGPathElement>("path");
      if (path) axisPaths.push(path);
    });

    axisPaths.forEach((path) => {
      const length = path.getTotalLength();
      gsap.set(path, {
        strokeDasharray: length,
        strokeDashoffset: length,
      });
    });
    if (axisPaths.length > 0) {
      tl.to(axisPaths, {
        strokeDashoffset: 0,
        duration: 0.3,
        stagger: 0.1,
        ease: "power2.out",
      });
    }

    // Phase 2: Data appears
    if (layout.chartType === "line" || layout.chartType === "function") {
      const seriesEls = svg.querySelectorAll<SVGElement>("[data-rough-series]");
      const seriesPaths: SVGPathElement[] = [];
      seriesEls.forEach((el) => {
        const path = el.querySelector<SVGPathElement>("path");
        if (path) seriesPaths.push(path);
      });

      seriesPaths.forEach((path) => {
        const length = path.getTotalLength();
        gsap.set(path, {
          strokeDasharray: length,
          strokeDashoffset: length,
        });
      });
      if (seriesPaths.length > 0) {
        tl.to(seriesPaths, {
          strokeDashoffset: 0,
          duration: 0.5,
          stagger: 0.1,
          ease: "power2.out",
        });
      }
    } else if (layout.chartType === "bar") {
      const barEls = svg.querySelectorAll<SVGElement>("[data-rough-bar]");
      if (barEls.length > 0) {
        gsap.set(barEls, {
          scaleY: 0,
          transformOrigin: "bottom center",
        });
        tl.to(barEls, {
          scaleY: 1,
          duration: 0.3,
          stagger: 0.06,
          ease: "power2.out",
        });
      }
    } else if (layout.chartType === "scatter") {
      const pointEls = svg.querySelectorAll<SVGElement>("[data-rough-point]");
      if (pointEls.length > 0) {
        gsap.set(pointEls, { scale: 0, transformOrigin: "center" });
        tl.to(pointEls, {
          scale: 1,
          duration: 0.3,
          stagger: 0.04,
          ease: "back.out(1.4)",
        });
      }
    }

    // Phase 3: Labels + gridlines fade in
    const fadeTargets = [...Array.from(gridEls), ...Array.from(labelEls)];
    if (fadeTargets.length > 0) {
      gsap.set(fadeTargets, { opacity: 0 });
      tl.to(fadeTargets, {
        opacity: 1,
        duration: 0.3,
        stagger: 0.02,
        ease: "power2.out",
      });
    }

    return () => {
      tl.kill();
    };
  }, [layout, animated]);

  const description = instruction.title || `${instruction.graph_type} chart`;

  return (
    <div>
      {instruction.title && (
        <div
          style={{
            fontSize: 20,
            fontStyle: "italic",
            lineHeight: "28px",
            color: COLORS.accentPurple,
            marginBottom: 12,
          }}
        >
          {instruction.title}
        </div>
      )}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${layout.viewWidth} ${layout.viewHeight}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={description}
        style={{ display: "block" }}
      >
        {/* Layer 1: Rough.js shapes (imperative) — alive filter for organic wobble */}
        <g ref={roughLayerRef} style={{ filter: `url(#${ALIVE_FILTER_ID})` }} />

        {/* Layer 2: Clean labels (declarative) */}
        <g ref={labelLayerRef}>
          {/* Y-axis tick labels */}
          {layout.yAxis.ticks.map((tick, i) => (
            <text
              key={`y-tick-${i}`}
              data-chart-label="y-tick"
              x={layout.plot.x - 8}
              y={tick.px + 4}
              textAnchor="end"
              fill={COLORS.textSecondary}
              fontSize={11}
              fontFamily={LABEL_FONT}
            >
              {tick.label}
            </text>
          ))}

          {/* X-axis tick labels */}
          {layout.xAxis.ticks.map((tick, i) => (
            <text
              key={`x-tick-${i}`}
              data-chart-label="x-tick"
              x={tick.px}
              y={layout.plot.y + layout.plot.height + 18}
              textAnchor={layout.rotateXLabels ? "end" : "middle"}
              fill={COLORS.textSecondary}
              fontSize={11}
              fontFamily={LABEL_FONT}
              transform={
                layout.rotateXLabels
                  ? `rotate(-30, ${tick.px}, ${layout.plot.y + layout.plot.height + 18})`
                  : undefined
              }
            >
              {tick.label}
            </text>
          ))}

          {/* X-axis label */}
          {layout.xLabel && (
            <text
              data-chart-label="x-axis-label"
              x={layout.plot.x + layout.plot.width / 2}
              y={layout.viewHeight - 4}
              textAnchor="middle"
              fill={COLORS.textSecondary}
              fontSize={13}
              fontFamily={LABEL_FONT}
              fontWeight={500}
            >
              {layout.xLabel}
            </text>
          )}

          {/* Y-axis label */}
          {layout.yLabel && (
            <text
              data-chart-label="y-axis-label"
              x={14}
              y={layout.plot.y + layout.plot.height / 2}
              textAnchor="middle"
              fill={COLORS.textSecondary}
              fontSize={13}
              fontFamily={LABEL_FONT}
              fontWeight={500}
              transform={`rotate(-90, 14, ${layout.plot.y + layout.plot.height / 2})`}
            >
              {layout.yLabel}
            </text>
          )}

          {/* Legend */}
          {layout.showLegend &&
            layout.seriesLabels.map((label, i) => {
              const legendX = layout.plot.x + i * 120;
              const legendY = layout.viewHeight - 4;
              return (
                <g key={`legend-${i}`} data-chart-label="legend">
                  <rect
                    x={legendX}
                    y={legendY - 8}
                    width={12}
                    height={12}
                    rx={2}
                    fill={layout.seriesColors[i]}
                    opacity={0.8}
                  />
                  <text
                    x={legendX + 16}
                    y={legendY + 2}
                    fill={COLORS.textSecondary}
                    fontSize={11}
                    fontFamily={LABEL_FONT}
                  >
                    {label}
                  </text>
                </g>
              );
            })}
        </g>
      </svg>
    </div>
  );
}

// ── Fallback (no data) ────────────────────────────────────────

function FallbackGraph({ instruction }: { instruction: ShowGraphInstruction }) {
  const badge = GRAPH_TYPE_LABELS[instruction.graph_type] ?? "GRAPH";

  return (
    <div>
      {instruction.title && (
        <div
          style={{
            fontSize: 20,
            fontStyle: "italic",
            lineHeight: "28px",
            color: COLORS.accentPurple,
            marginBottom: 12,
          }}
        >
          {instruction.title}
        </div>
      )}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.05em",
            color: COLORS.diagramBg,
            background: `${COLORS.accentPurple}99`,
            padding: "3px 8px",
            borderRadius: 4,
          }}
        >
          {badge}
        </span>
      </div>
    </div>
  );
}

// ── Public component ──────────────────────────────────────────

export function RoughGraphContent({
  instruction,
}: {
  instruction: ShowGraphInstruction;
}) {
  const layout = useMemo(() => computeChartLayout(instruction), [instruction]);

  if (layout) {
    return <StructuredRoughGraph instruction={instruction} layout={layout} />;
  }

  return <FallbackGraph instruction={instruction} />;
}
