import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { EquationContent } from "../content/EquationContent";
import type { ShowEquationInstruction } from "../../types/visuals";

describe("EquationContent", () => {
  it("renders label and latex as monospace text", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "F = ma",
      label: "Newton's Second Law",
    };
    render(<EquationContent instruction={instruction} />);
    expect(screen.getByText("Newton's Second Law")).toBeTruthy();
    expect(screen.getByText("F = ma")).toBeTruthy();
  });

  it("renders without label", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "E = mc^2",
    };
    render(<EquationContent instruction={instruction} />);
    expect(screen.getByText("E = mc^2")).toBeTruthy();
  });

  it("centers the equation text", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "a^2 + b^2 = c^2",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    const eqDiv = container.querySelector(
      "[data-katex-target]",
    ) as HTMLElement | null;
    expect(eqDiv).toBeTruthy();
    expect(eqDiv!.style.textAlign).toBe("center");
  });
});
