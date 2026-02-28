import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepEquationContent } from "../content/StepEquationContent";
import type { StepEquationInstruction } from "../../types/visuals";

// Mock GSAP — jsdom doesn't support real animations
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

const threeStepInstruction: StepEquationInstruction = {
  type: "step_equation",
  title: "Solving for x",
  steps: [
    { latex: "2x + 4 = 10" },
    {
      latex: "2x = 6",
      annotation: "Subtract 4 from both sides",
      highlight_terms: ["term-result"],
    },
    {
      latex: "x = 3",
      annotation: "Divide both sides by 2",
    },
  ],
};

describe("StepEquationContent", () => {
  it("renders all steps with KaTeX", () => {
    const { container } = render(
      <StepEquationContent instruction={threeStepInstruction} />,
    );
    const katexEls = container.querySelectorAll(".katex");
    expect(katexEls.length).toBe(3);
  });

  it("renders title when provided", () => {
    render(<StepEquationContent instruction={threeStepInstruction} />);
    expect(screen.getByText("Solving for x")).toBeTruthy();
  });

  it("renders without title", () => {
    const instruction: StepEquationInstruction = {
      type: "step_equation",
      steps: [{ latex: "x = 1" }],
    };
    const { container } = render(
      <StepEquationContent instruction={instruction} />,
    );
    expect(container.querySelector(".katex")).toBeTruthy();
    expect(screen.queryByText("Solving for x")).toBeNull();
  });

  it("renders annotations for non-first steps", () => {
    render(<StepEquationContent instruction={threeStepInstruction} />);
    expect(
      screen.getByText((content) =>
        content.includes("Subtract 4 from both sides"),
      ),
    ).toBeTruthy();
    expect(
      screen.getByText((content) => content.includes("Divide both sides by 2")),
    ).toBeTruthy();
  });

  it("suppresses annotation on first step", () => {
    const instruction: StepEquationInstruction = {
      type: "step_equation",
      steps: [
        { latex: "2x + 4 = 10", annotation: "Original equation" },
        { latex: "2x = 6", annotation: "Subtract 4" },
      ],
    };
    const { container } = render(
      <StepEquationContent instruction={instruction} />,
    );
    const annotations = container.querySelectorAll("[data-step-annotation]");
    // Only the second step should have an annotation rendered
    expect(annotations.length).toBe(1);
  });

  it("sets data-step attributes on step wrappers", () => {
    const { container } = render(
      <StepEquationContent instruction={threeStepInstruction} />,
    );
    const steps = container.querySelectorAll("[data-step]");
    expect(steps.length).toBe(3);
    expect(steps[0].getAttribute("data-step")).toBe("0");
    expect(steps[1].getAttribute("data-step")).toBe("1");
    expect(steps[2].getAttribute("data-step")).toBe("2");
  });

  it("renders display-mode KaTeX (katex-display class)", () => {
    const { container } = render(
      <StepEquationContent instruction={threeStepInstruction} />,
    );
    expect(container.querySelector(".katex-display")).toBeTruthy();
  });
});
