// TODO(DEADCODE): tests dead engine/whiteboard modules (Group 1/2); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
import { it } from "vitest";
it.skip("dead code (TODO(DEADCODE)) — file slated for deletion", () => {});
// import { render, screen } from "@testing-library/react";
// import { describe, it, expect, vi, beforeEach } from "vitest";
// import type { ShowGraphInstruction } from "../../types/visuals";

// // vi.hoisted makes these available during mock hoisting
// const { mockDestroy, mockChart } = vi.hoisted(() => {
//   const mockDestroy = vi.fn();
//   const mockChart = vi.fn().mockImplementation(() => ({
//     destroy: mockDestroy,
//   }));
//   return { mockDestroy, mockChart };
// });

// // Mock Chart.js — jsdom has no canvas rendering context
// vi.mock("chart.js", () => ({
//   Chart: mockChart,
//   LineController: {},
//   BarController: {},
//   ScatterController: {},
//   LineElement: {},
//   BarElement: {},
//   PointElement: {},
//   LinearScale: {},
//   CategoryScale: {},
//   Title: {},
//   Tooltip: {},
//   Legend: {},
//   Filler: {},
// }));

// // Mock chart-defaults (side-effect module)
// vi.mock("../chart-defaults", () => ({}));

// // Import after mocks are set up
// import { GraphContent } from "../content/GraphContent";

// beforeEach(() => {
//   mockChart.mockClear();
//   mockDestroy.mockClear();
// });

// describe("GraphContent", () => {
//   it("renders canvas when series data provided", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "line",
//       series: [
//         {
//           label: "Temperature",
//           points: [
//             { x: 0, y: 20 },
//             { x: 1, y: 22 },
//           ],
//         },
//       ],
//     };
//     const { container } = render(<GraphContent instruction={instruction} />);
//     const canvas = container.querySelector("canvas");
//     expect(canvas).toBeTruthy();
//   });

//   it("renders canvas when functions data provided", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "function",
//       functions: [{ expression: "x^2" }],
//     };
//     const { container } = render(<GraphContent instruction={instruction} />);
//     const canvas = container.querySelector("canvas");
//     expect(canvas).toBeTruthy();
//   });

//   it("renders title", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "line",
//       title: "Temperature Over Time",
//       series: [{ label: "Temp", points: [{ x: 0, y: 20 }] }],
//     };
//     render(<GraphContent instruction={instruction} />);
//     expect(screen.getByText("Temperature Over Time")).toBeTruthy();
//   });

//   it("falls back to badge when no data", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "bar",
//     };
//     render(<GraphContent instruction={instruction} />);
//     expect(screen.getByText("BAR CHART")).toBeTruthy();
//   });

//   it("creates Chart instance on mount with correct type", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "scatter",
//       series: [
//         {
//           points: [
//             { x: 1, y: 2 },
//             { x: 3, y: 4 },
//           ],
//         },
//       ],
//     };
//     render(<GraphContent instruction={instruction} />);
//     expect(mockChart).toHaveBeenCalledTimes(1);
//     const [, config] = mockChart.mock.calls[0];
//     expect(config.type).toBe("scatter");
//   });

//   it("destroys Chart instance on unmount", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "line",
//       series: [{ points: [{ x: 0, y: 0 }] }],
//     };
//     const { unmount } = render(<GraphContent instruction={instruction} />);
//     unmount();
//     expect(mockDestroy).toHaveBeenCalled();
//   });

//   it("uses category scale for bar charts with labels", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "bar",
//       series: [
//         {
//           label: "Scores",
//           points: [
//             { x: 1, y: 85, label: "Math" },
//             { x: 2, y: 92, label: "Science" },
//           ],
//         },
//       ],
//     };
//     render(<GraphContent instruction={instruction} />);
//     expect(mockChart).toHaveBeenCalledTimes(1);
//     const [, config] = mockChart.mock.calls[0];
//     expect(config.type).toBe("bar");
//     expect(config.data.labels).toEqual(["Math", "Science"]);
//   });

//   it("hides legend for single series", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "line",
//       series: [{ points: [{ x: 0, y: 0 }] }],
//     };
//     render(<GraphContent instruction={instruction} />);
//     const [, config] = mockChart.mock.calls[0];
//     expect(config.options.plugins.legend.display).toBe(false);
//   });

//   it("shows legend for multi-series", () => {
//     const instruction: ShowGraphInstruction = {
//       type: "show_graph",
//       graph_type: "line",
//       series: [
//         { label: "A", points: [{ x: 0, y: 0 }] },
//         { label: "B", points: [{ x: 1, y: 1 }] },
//       ],
//     };
//     render(<GraphContent instruction={instruction} />);
//     const [, config] = mockChart.mock.calls[0];
//     expect(config.options.plugins.legend.display).toBe(true);
//   });
// });
