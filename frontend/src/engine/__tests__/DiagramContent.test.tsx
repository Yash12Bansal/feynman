import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DiagramContent } from "../content/DiagramContent";
import type { DrawDiagramInstruction } from "../../types/visuals";

describe("DiagramContent", () => {
  it("renders placeholder with type badge", () => {
    const instruction: DrawDiagramInstruction = {
      type: "draw_diagram",
      diagram_type: "force_diagram",
      title: "Free Body Diagram",
      description: "Forces acting on a block.",
    };
    render(<DiagramContent instruction={instruction} />);
    expect(screen.getByText("FORCE DIAGRAM")).toBeTruthy();
  });

  it("renders description text", () => {
    const instruction: DrawDiagramInstruction = {
      type: "draw_diagram",
      description: "A block on an inclined plane.",
    };
    render(<DiagramContent instruction={instruction} />);
    expect(screen.getByText("A block on an inclined plane.")).toBeTruthy();
  });

  it("falls back to DIAGRAM badge for free_form", () => {
    const instruction: DrawDiagramInstruction = {
      type: "draw_diagram",
      diagram_type: "free_form",
      title: "Custom",
    };
    render(<DiagramContent instruction={instruction} />);
    expect(screen.getByText("DIAGRAM")).toBeTruthy();
  });

  it("renders SVG placeholder icon", () => {
    const instruction: DrawDiagramInstruction = {
      type: "draw_diagram",
      title: "Test",
    };
    const { container } = render(<DiagramContent instruction={instruction} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });
});
