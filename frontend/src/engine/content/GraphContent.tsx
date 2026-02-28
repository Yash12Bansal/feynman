import { useEffect, useMemo, useRef } from "react";
import { Chart, type ChartConfiguration } from "chart.js";
import type {
  ShowGraphInstruction,
  DataSeries,
  FunctionDef,
} from "../../types/visuals";
import { COLORS } from "../theme";
import { evaluateFunction } from "../math-eval";
import "../chart-defaults";

// ── Constants ─────────────────────────────────────────────────

const GRAPH_TYPE_LABELS: Record<string, string> = {
  line: "LINE CHART",
  bar: "BAR CHART",
  scatter: "SCATTER PLOT",
  function: "FUNCTION GRAPH",
};

/** Color palette for multi-series charts. */
const SERIES_COLORS = [
  COLORS.accentPurple,
  COLORS.accentBlue,
  COLORS.accentGreen,
  COLORS.accentAmber,
  "#ff6384",
  "#ff9f40",
];

/** Safety caps. */
const MAX_POINTS_PER_SERIES = 200;
const MAX_SERIES = 8;

// ── Chart config builders ────────────────────────────────────

function pickColor(index: number, explicit?: string): string {
  return explicit || SERIES_COLORS[index % SERIES_COLORS.length];
}

function buildFunctionConfig(
  functions: FunctionDef[],
  instruction: ShowGraphInstruction,
): ChartConfiguration {
  const xMin = instruction.x_axis?.min ?? -10;
  const xMax = instruction.x_axis?.max ?? 10;

  const datasets = functions.slice(0, MAX_SERIES).map((fn, i) => {
    const points = evaluateFunction(fn, xMin, xMax);
    const color = pickColor(i, fn.color);
    return {
      label: fn.label || fn.expression,
      data: points.map((p) => ({ x: p.x, y: p.y })),
      borderColor: color,
      backgroundColor: `${color}33`,
      showLine: true,
      pointRadius: 0,
      pointHitRadius: 8,
      tension: 0,
      fill: false,
    };
  });

  return {
    type: "scatter",
    data: { datasets },
    options: {
      animation:
        instruction.animated !== false
          ? { duration: 800, easing: "easeOutQuart" }
          : false,
      scales: {
        x: {
          type: "linear",
          title: {
            display: !!instruction.x_axis?.label,
            text: instruction.x_axis?.label || "",
          },
          min: instruction.x_axis?.min ?? undefined,
          max: instruction.x_axis?.max ?? undefined,
        },
        y: {
          type: "linear",
          title: {
            display: !!instruction.y_axis?.label,
            text: instruction.y_axis?.label || "",
          },
          min: instruction.y_axis?.min ?? undefined,
          max: instruction.y_axis?.max ?? undefined,
        },
      },
      plugins: {
        legend: { display: functions.length > 1 },
      },
    },
  };
}

function buildSeriesConfig(
  series: DataSeries[],
  instruction: ShowGraphInstruction,
): ChartConfiguration {
  const graphType = instruction.graph_type;
  const capped = series.slice(0, MAX_SERIES);

  // Bar charts with category labels
  const isBar = graphType === "bar";
  const hasLabels = isBar && capped.some((s) => s.points.some((p) => p.label));

  if (isBar && hasLabels) {
    // Category bar chart — labels on x-axis
    const labels =
      capped[0]?.points
        .slice(0, MAX_POINTS_PER_SERIES)
        .map((p) => p.label || String(p.x)) ?? [];

    const datasets = capped.map((s, i) => {
      const color = pickColor(i, s.color);
      return {
        label: s.label || `Series ${i + 1}`,
        data: s.points.slice(0, MAX_POINTS_PER_SERIES).map((p) => p.y),
        backgroundColor: `${color}80`,
        borderColor: color,
        borderWidth: 2,
      };
    });

    return {
      type: "bar",
      data: { labels, datasets },
      options: {
        animation:
          instruction.animated !== false
            ? { duration: 800, easing: "easeOutQuart" }
            : false,
        scales: {
          x: {
            type: "category",
            title: {
              display: !!instruction.x_axis?.label,
              text: instruction.x_axis?.label || "",
            },
          },
          y: {
            type: "linear",
            title: {
              display: !!instruction.y_axis?.label,
              text: instruction.y_axis?.label || "",
            },
            min: instruction.y_axis?.min ?? undefined,
            max: instruction.y_axis?.max ?? undefined,
          },
        },
        plugins: {
          legend: { display: capped.length > 1 },
        },
      },
    };
  }

  // Line / scatter / numeric bar
  const chartType = isBar
    ? "bar"
    : graphType === "scatter"
      ? "scatter"
      : "line";

  const datasets = capped.map((s, i) => {
    const color = pickColor(i, s.color);
    const points = s.points.slice(0, MAX_POINTS_PER_SERIES);

    const base = {
      label: s.label || `Series ${i + 1}`,
      data: points.map((p) => ({ x: p.x, y: p.y })),
      borderColor: color,
      backgroundColor: chartType === "bar" ? `${color}80` : `${color}1A`,
      borderWidth: chartType === "bar" ? 2 : 3,
    };

    if (chartType === "line") {
      return { ...base, fill: true, tension: 0.2, pointRadius: 4 };
    }
    if (chartType === "scatter") {
      return { ...base, pointRadius: 6, pointHoverRadius: 9, showLine: false };
    }
    return base;
  });

  return {
    type: chartType as "line" | "bar" | "scatter",
    data: { datasets },
    options: {
      animation:
        instruction.animated !== false
          ? { duration: 800, easing: "easeOutQuart" }
          : false,
      scales: {
        x: {
          type: "linear",
          title: {
            display: !!instruction.x_axis?.label,
            text: instruction.x_axis?.label || "",
          },
          min: instruction.x_axis?.min ?? undefined,
          max: instruction.x_axis?.max ?? undefined,
        },
        y: {
          type: "linear",
          title: {
            display: !!instruction.y_axis?.label,
            text: instruction.y_axis?.label || "",
          },
          min: instruction.y_axis?.min ?? undefined,
          max: instruction.y_axis?.max ?? undefined,
        },
      },
      plugins: {
        legend: { display: capped.length > 1 },
      },
    },
  };
}

function buildChartConfig(
  instruction: ShowGraphInstruction,
): ChartConfiguration | null {
  const hasFunctions =
    instruction.functions && instruction.functions.length > 0;
  const hasSeries = instruction.series && instruction.series.length > 0;

  if (instruction.graph_type === "function" && hasFunctions) {
    return buildFunctionConfig(instruction.functions!, instruction);
  }
  if (hasSeries) {
    return buildSeriesConfig(instruction.series!, instruction);
  }
  if (hasFunctions) {
    return buildFunctionConfig(instruction.functions!, instruction);
  }
  return null;
}

// ── Component ────────────────────────────────────────────────

export function GraphContent({
  instruction,
}: {
  instruction: ShowGraphInstruction;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  const config = useMemo(() => buildChartConfig(instruction), [instruction]);

  // Create / destroy Chart.js instance
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !config) return;

    // Destroy previous instance if any
    chartRef.current?.destroy();

    chartRef.current = new Chart(canvas, config);

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [config]);

  // Fallback when no data
  if (!config) {
    const badge = GRAPH_TYPE_LABELS[instruction.graph_type] ?? "GRAPH";
    return (
      <div>
        {instruction.title && (
          <h3
            style={{
              margin: 0,
              marginBottom: 12,
              fontSize: 28,
              fontWeight: 700,
              lineHeight: "36px",
              color: COLORS.accentPurple,
            }}
          >
            {instruction.title}
          </h3>
        )}
        <div
          style={{
            height: 200,
            border: `2px dashed ${COLORS.accentPurple}30`,
            borderRadius: 8,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.05em",
              color: "#0a0a14",
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

  return (
    <div>
      {instruction.title && (
        <h3
          style={{
            margin: 0,
            marginBottom: 12,
            fontSize: 28,
            fontWeight: 700,
            lineHeight: "36px",
            color: COLORS.accentPurple,
          }}
        >
          {instruction.title}
        </h3>
      )}
      <div style={{ position: "relative", width: "100%" }}>
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
