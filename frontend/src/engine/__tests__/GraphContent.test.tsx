import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { GraphContent } from "../content/GraphContent";
import type { ShowGraphInstruction } from "../../types/visuals";

describe("GraphContent", () => {
  it("renders placeholder with type badge", () => {
    const instruction: ShowGraphInstruction = {
      type: "show_graph",
      graph_type: "function",
      title: "Height vs Time",
    };
    render(<GraphContent instruction={instruction} />);
    expect(screen.getByText("FUNCTION GRAPH")).toBeTruthy();
  });

  it("renders title", () => {
    const instruction: ShowGraphInstruction = {
      type: "show_graph",
      graph_type: "line",
      title: "Temperature Over Time",
    };
    render(<GraphContent instruction={instruction} />);
    expect(screen.getByText("Temperature Over Time")).toBeTruthy();
    expect(screen.getByText("LINE CHART")).toBeTruthy();
  });

  it("shows axis labels", () => {
    const instruction: ShowGraphInstruction = {
      type: "show_graph",
      graph_type: "scatter",
      x_axis: { label: "Time (s)" },
      y_axis: { label: "Height (m)" },
    };
    render(<GraphContent instruction={instruction} />);
    expect(screen.getByText("Time (s)")).toBeTruthy();
    expect(screen.getByText("Height (m)")).toBeTruthy();
  });

  it("renders without title", () => {
    const instruction: ShowGraphInstruction = {
      type: "show_graph",
      graph_type: "bar",
    };
    render(<GraphContent instruction={instruction} />);
    expect(screen.getByText("BAR CHART")).toBeTruthy();
  });
});
