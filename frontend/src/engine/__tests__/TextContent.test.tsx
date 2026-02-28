import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TextContent } from "../content/TextContent";
import type { ShowTextInstruction } from "../../types/visuals";

describe("TextContent", () => {
  it("renders title and body text", () => {
    const instruction: ShowTextInstruction = {
      type: "show_text",
      title: "Newton's First Law",
      text: "An object at rest stays at rest.",
    };
    render(<TextContent instruction={instruction} />);
    expect(screen.getByText("Newton's First Law")).toBeTruthy();
    expect(screen.getByText("An object at rest stays at rest.")).toBeTruthy();
  });

  it("renders without title", () => {
    const instruction: ShowTextInstruction = {
      type: "show_text",
      text: "Body text only.",
    };
    render(<TextContent instruction={instruction} />);
    expect(screen.getByText("Body text only.")).toBeTruthy();
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("applies definition style accent color", () => {
    const instruction: ShowTextInstruction = {
      type: "show_text",
      title: "Test",
      text: "content",
      style: "definition",
    };
    const { container } = render(<TextContent instruction={instruction} />);
    const heading = container.querySelector("h3");
    expect(heading).toBeTruthy();
    // definition uses accentBlue (#60a5fa)
    expect(heading!.style.color).toBe("rgb(96, 165, 250)");
  });

  it("applies key_point style accent color", () => {
    const instruction: ShowTextInstruction = {
      type: "show_text",
      title: "Important",
      text: "content",
      style: "key_point",
    };
    const { container } = render(<TextContent instruction={instruction} />);
    const heading = container.querySelector("h3");
    // key_point uses accentAmber (#fbbf24)
    expect(heading!.style.color).toBe("rgb(251, 191, 36)");
  });

  it("applies example style accent color", () => {
    const instruction: ShowTextInstruction = {
      type: "show_text",
      title: "Example",
      text: "content",
      style: "example",
    };
    const { container } = render(<TextContent instruction={instruction} />);
    const heading = container.querySelector("h3");
    // example uses accentGreen (#4ade80)
    expect(heading!.style.color).toBe("rgb(74, 222, 128)");
  });
});
