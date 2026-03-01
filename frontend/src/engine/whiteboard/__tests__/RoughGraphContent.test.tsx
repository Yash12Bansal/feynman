import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { ShowGraphInstruction } from "../../../types/visuals";

// ── Mock GSAP ─────────────────────────────────────────────────

vi.mock("gsap", () => {
  const tl = {
    fromTo: vi.fn().mockReturnThis(),
    to: vi.fn().mockReturnThis(),
    kill: vi.fn(),
  };
  return {
    default: {
      timeline: () => tl,
      set: vi.fn(),
    },
  };
});

// ── Mock Rough.js ─────────────────────────────────────────────

function makeSvgGroup(): SVGGElement {
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M0,0 L100,100");
  (path as unknown as Record<string, unknown>).getTotalLength = () => 100;
  g.appendChild(path);
  return g;
}

vi.mock("roughjs", () => {
  const rcMethods = {
    rectangle: vi.fn(() => makeSvgGroup()),
    circle: vi.fn(() => makeSvgGroup()),
    ellipse: vi.fn(() => makeSvgGroup()),
    polygon: vi.fn(() => makeSvgGroup()),
    line: vi.fn(() => makeSvgGroup()),
    linearPath: vi.fn(() => makeSvgGroup()),
  };
  return {
    default: {
      svg: () => rcMethods,
    },
  };
});

// ── Fixtures ──────────────────────────────────────────────────

const lineInstruction: ShowGraphInstruction = {
  type: "show_graph",
  graph_type: "line",
  title: "Temperature Over Time",
  x_axis: { label: "Time (s)" },
  y_axis: { label: "Temp (°C)" },
  series: [
    {
      label: "Sensor A",
      points: [
        { x: 0, y: 20 },
        { x: 1, y: 22 },
        { x: 2, y: 25 },
        { x: 3, y: 23 },
        { x: 4, y: 28 },
      ],
    },
  ],
  animated: false,
};

const barInstruction: ShowGraphInstruction = {
  type: "show_graph",
  graph_type: "bar",
  title: "Test Scores",
  series: [
    {
      label: "Class A",
      points: [
        { x: 1, y: 85, label: "Math" },
        { x: 2, y: 92, label: "Science" },
        { x: 3, y: 78, label: "English" },
      ],
    },
  ],
  animated: false,
};

const scatterInstruction: ShowGraphInstruction = {
  type: "show_graph",
  graph_type: "scatter",
  title: "Height vs Weight",
  series: [
    {
      label: "Students",
      points: [
        { x: 150, y: 50 },
        { x: 160, y: 55 },
        { x: 170, y: 65 },
        { x: 165, y: 60 },
      ],
    },
  ],
  animated: false,
};

const functionInstruction: ShowGraphInstruction = {
  type: "show_graph",
  graph_type: "function",
  title: "Quadratic Function",
  x_axis: { min: -5, max: 5 },
  functions: [{ expression: "x^2", label: "f(x) = x²" }],
  animated: false,
};

const emptyInstruction: ShowGraphInstruction = {
  type: "show_graph",
  graph_type: "bar",
  title: "Empty Chart",
  animated: false,
};

const multiSeriesInstruction: ShowGraphInstruction = {
  type: "show_graph",
  graph_type: "line",
  title: "Multi Series",
  series: [
    {
      label: "Series 1",
      points: [
        { x: 0, y: 10 },
        { x: 1, y: 20 },
      ],
    },
    {
      label: "Series 2",
      points: [
        { x: 0, y: 15 },
        { x: 1, y: 25 },
      ],
    },
  ],
  animated: false,
};

// ── Lazy imports (after mocks) ────────────────────────────────

async function importComponent() {
  const mod = await import("../content/RoughGraphContent");
  return mod.RoughGraphContent;
}

async function importInstructionSwitch() {
  const mod = await import("../InstructionSwitch");
  return mod.InstructionSwitch;
}

async function importChartLayout() {
  return await import("../layout/chart-layout");
}

// ── Line chart ────────────────────────────────────────────────

describe("RoughGraphContent — line chart", () => {
  it("renders SVG with correct viewBox", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={lineInstruction} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    const viewBox = svg!.getAttribute("viewBox");
    expect(viewBox).toBe("0 0 600 400");
  });

  it("renders axis elements", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={lineInstruction} />,
    );
    const axes = container.querySelectorAll("[data-rough-axis]");
    expect(axes.length).toBe(2); // x + y
  });

  it("renders series line", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={lineInstruction} />,
    );
    const series = container.querySelectorAll("[data-rough-series]");
    expect(series.length).toBe(1);
  });

  it("renders tick labels", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={lineInstruction} />,
    );
    const tickLabels = container.querySelectorAll("[data-chart-label]");
    expect(tickLabels.length).toBeGreaterThan(0);
  });

  it("renders axis labels", async () => {
    const RoughGraphContent = await importComponent();
    render(<RoughGraphContent instruction={lineInstruction} />);
    expect(screen.getByText("Time (s)")).toBeTruthy();
    expect(screen.getByText("Temp (°C)")).toBeTruthy();
  });

  it("renders title", async () => {
    const RoughGraphContent = await importComponent();
    render(<RoughGraphContent instruction={lineInstruction} />);
    expect(screen.getByText("Temperature Over Time")).toBeTruthy();
  });

  it("sets role=img and aria-label on SVG", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={lineInstruction} />,
    );
    const svg = container.querySelector("svg");
    expect(svg!.getAttribute("role")).toBe("img");
    expect(svg!.getAttribute("aria-label")).toBeTruthy();
  });
});

// ── Bar chart ─────────────────────────────────────────────────

describe("RoughGraphContent — bar chart", () => {
  it("renders bar elements", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={barInstruction} />,
    );
    const bars = container.querySelectorAll("[data-rough-bar]");
    expect(bars.length).toBe(3);
  });

  it("renders category labels", async () => {
    const RoughGraphContent = await importComponent();
    render(<RoughGraphContent instruction={barInstruction} />);
    expect(screen.getByText("Math")).toBeTruthy();
    expect(screen.getByText("Science")).toBeTruthy();
    expect(screen.getByText("English")).toBeTruthy();
  });

  it("does not render series polylines", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={barInstruction} />,
    );
    const series = container.querySelectorAll("[data-rough-series]");
    expect(series.length).toBe(0);
  });
});

// ── Scatter chart ─────────────────────────────────────────────

describe("RoughGraphContent — scatter chart", () => {
  it("renders point elements", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={scatterInstruction} />,
    );
    const points = container.querySelectorAll("[data-rough-point]");
    expect(points.length).toBe(4);
  });
});

// ── Function chart ────────────────────────────────────────────

describe("RoughGraphContent — function chart", () => {
  it("renders series from evaluated expression", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={functionInstruction} />,
    );
    const series = container.querySelectorAll("[data-rough-series]");
    expect(series.length).toBe(1);
  });

  it("renders title", async () => {
    const RoughGraphContent = await importComponent();
    render(<RoughGraphContent instruction={functionInstruction} />);
    expect(screen.getByText("Quadratic Function")).toBeTruthy();
  });
});

// ── Fallback ──────────────────────────────────────────────────

describe("RoughGraphContent — fallback", () => {
  it("shows badge when no data", async () => {
    const RoughGraphContent = await importComponent();
    render(<RoughGraphContent instruction={emptyInstruction} />);
    expect(screen.getByText("BAR CHART")).toBeTruthy();
  });

  it("does not render SVG when no data", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={emptyInstruction} />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("does not render canvas element", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={emptyInstruction} />,
    );
    expect(container.querySelector("canvas")).toBeNull();
  });
});

// ── Multi-series ──────────────────────────────────────────────

describe("RoughGraphContent — multi-series", () => {
  it("renders multiple series lines", async () => {
    const RoughGraphContent = await importComponent();
    const { container } = render(
      <RoughGraphContent instruction={multiSeriesInstruction} />,
    );
    const series = container.querySelectorAll("[data-rough-series]");
    expect(series.length).toBe(2);
  });
});

// ── InstructionSwitch routing ─────────────────────────────────

describe("Whiteboard InstructionSwitch — show_graph", () => {
  it("routes show_graph to SVG (not canvas)", async () => {
    const InstructionSwitch = await importInstructionSwitch();
    const { container } = render(
      <InstructionSwitch instruction={lineInstruction} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    const canvas = container.querySelector("canvas");
    expect(canvas).toBeNull();
  });

  it("renders data-rough-axis attributes", async () => {
    const InstructionSwitch = await importInstructionSwitch();
    const { container } = render(
      <InstructionSwitch instruction={lineInstruction} />,
    );
    const axes = container.querySelectorAll("[data-rough-axis]");
    expect(axes.length).toBeGreaterThan(0);
  });
});

// ── chart-layout pure functions ───────────────────────────────

describe("chart-layout", () => {
  it("niceAxis produces ticks within range", async () => {
    const { niceAxis } = await importChartLayout();
    const axis = niceAxis(0, 100);
    expect(axis.min).toBeLessThanOrEqual(0);
    expect(axis.max).toBeGreaterThanOrEqual(100);
    expect(axis.ticks.length).toBeGreaterThan(0);
    for (const tick of axis.ticks) {
      expect(tick.value).toBeGreaterThanOrEqual(axis.min);
      expect(tick.value).toBeLessThanOrEqual(axis.max);
    }
  });

  it("niceAxis handles degenerate range (all same value)", async () => {
    const { niceAxis } = await importChartLayout();
    const axis = niceAxis(5, 5);
    expect(axis.min).toBeLessThan(5);
    expect(axis.max).toBeGreaterThan(5);
    expect(axis.ticks.length).toBeGreaterThan(0);
  });

  it("computeChartLayout returns null for no data", async () => {
    const { computeChartLayout } = await importChartLayout();
    const result = computeChartLayout(emptyInstruction);
    expect(result).toBeNull();
  });

  it("computeChartLayout returns layout for line chart", async () => {
    const { computeChartLayout } = await importChartLayout();
    const result = computeChartLayout(lineInstruction);
    expect(result).not.toBeNull();
    expect(result!.chartType).toBe("line");
    expect(result!.viewWidth).toBe(600);
    expect(result!.viewHeight).toBe(400);
  });

  it("computeChartLayout returns layout for bar chart", async () => {
    const { computeChartLayout } = await importChartLayout();
    const result = computeChartLayout(barInstruction);
    expect(result).not.toBeNull();
    expect(result!.chartType).toBe("bar");
  });

  it("computeChartLayout returns layout for function chart", async () => {
    const { computeChartLayout } = await importChartLayout();
    const result = computeChartLayout(functionInstruction);
    expect(result).not.toBeNull();
    expect(result!.chartType).toBe("function");
  });

  it("niceAxis respects negative ranges", async () => {
    const { niceAxis } = await importChartLayout();
    const axis = niceAxis(-50, 50);
    expect(axis.min).toBeLessThanOrEqual(-50);
    expect(axis.max).toBeGreaterThanOrEqual(50);
  });
});
