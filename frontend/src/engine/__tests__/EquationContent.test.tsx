import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { EquationContent } from "../content/EquationContent";
import type { ShowEquationInstruction } from "../../types/visuals";

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

describe("EquationContent", () => {
  it("renders LaTeX via KaTeX", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "E = mc^2",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    const katexEl = container.querySelector(".katex");
    expect(katexEl).toBeTruthy();
  });

  it("renders label when provided", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "F = ma",
      label: "Newton's Second Law",
    };
    render(<EquationContent instruction={instruction} />);
    expect(screen.getByText("Newton's Second Law")).toBeTruthy();
  });

  it("renders without label", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "a^2 + b^2 = c^2",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    // Should have KaTeX output but no label div
    expect(container.querySelector(".katex")).toBeTruthy();
    // No label text — only the katex-rendered equation should exist
    expect(screen.queryByText("Newton's Second Law")).toBeNull();
  });

  it("falls back to monospace for malformed LaTeX", () => {
    // Use throwOnError: false in KaTeX — it renders error spans instead of throwing.
    // Test that it still produces output (KaTeX error class or the raw text).
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "\\invalid{",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    const target = container.querySelector("[data-katex-target]");
    expect(target).toBeTruthy();
    // KaTeX with throwOnError: false renders error spans with class katex-error
    // or falls back to text content — either way, the container has content
    expect(target!.textContent).toBeTruthy();
  });

  it("sets data-animation attribute on the katex target", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "x^2 + y^2 = r^2",
      animation: "write_on",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    const target = container.querySelector("[data-katex-target]");
    expect(target?.getAttribute("data-animation")).toBe("write_on");
  });

  it("defaults data-animation to fade_in when not specified", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "y = mx + b",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    const target = container.querySelector("[data-katex-target]");
    expect(target?.getAttribute("data-animation")).toBe("fade_in");
  });

  it("renders display-mode KaTeX (katex-display class)", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "\\frac{a}{b}",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    expect(container.querySelector(".katex-display")).toBeTruthy();
  });

  it("centers the equation", () => {
    const instruction: ShowEquationInstruction = {
      type: "show_equation",
      latex: "1 + 1 = 2",
    };
    const { container } = render(<EquationContent instruction={instruction} />);
    const target = container.querySelector(
      "[data-katex-target]",
    ) as HTMLElement | null;
    expect(target).toBeTruthy();
    expect(target!.style.textAlign).toBe("center");
  });
});
