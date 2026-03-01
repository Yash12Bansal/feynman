import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { ShowTextInstruction } from "../../../types/visuals";

// ── Mock GSAP ─────────────────────────────────────────────────

vi.mock("gsap", () => {
  const tl = {
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

// ── Stub getTotalLength on SVG paths ──────────────────────────

const origCreateElementNS = document.createElementNS.bind(document);
vi.spyOn(document, "createElementNS").mockImplementation(
  (ns: string | null, tag: string) => {
    const el = origCreateElementNS(ns!, tag);
    if (tag === "path") {
      (el as unknown as Record<string, unknown>).getTotalLength = () => 50;
    }
    return el;
  },
);

// ── Fixtures ──────────────────────────────────────────────────

const basicInstruction: ShowTextInstruction = {
  type: "show_text",
  text: "Hello World",
};

const titleAndBodyInstruction: ShowTextInstruction = {
  type: "show_text",
  text: "This is the body text.",
  title: "Key Concept",
};

const keyPointInstruction: ShowTextInstruction = {
  type: "show_text",
  text: "Important point",
  title: "Remember",
  style: "key_point",
};

const exampleInstruction: ShowTextInstruction = {
  type: "show_text",
  text: "Consider this example",
  style: "example",
};

const titleOnlyInstruction: ShowTextInstruction = {
  type: "show_text",
  text: "",
  title: "Just a title",
};

// ── Lazy imports (after mocks) ────────────────────────────────

async function importComponent() {
  const mod = await import("../content/HandwrittenTextContent");
  return mod.HandwrittenTextContent;
}

async function importInstructionSwitch() {
  const mod = await import("../InstructionSwitch");
  return mod.InstructionSwitch;
}

// ── Rendering ─────────────────────────────────────────────────

describe("HandwrittenTextContent — rendering", () => {
  it("renders SVG elements with data-hw-char paths", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={basicInstruction} />,
    );
    const paths = container.querySelectorAll("[data-hw-char]");
    expect(paths.length).toBeGreaterThan(0);
  });

  it("renders body section paths with data-hw-section=body", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={basicInstruction} />,
    );
    const bodyPaths = container.querySelectorAll('[data-hw-section="body"]');
    expect(bodyPaths.length).toBeGreaterThan(0);
  });

  it("renders both title and body sections", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={titleAndBodyInstruction} />,
    );
    const titlePaths = container.querySelectorAll('[data-hw-section="title"]');
    const bodyPaths = container.querySelectorAll('[data-hw-section="body"]');
    expect(titlePaths.length).toBeGreaterThan(0);
    expect(bodyPaths.length).toBeGreaterThan(0);
  });

  it("uses accent color for title stroke", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={titleAndBodyInstruction} />,
    );
    const titlePath = container.querySelector('[data-hw-section="title"]');
    expect(titlePath).toBeTruthy();
    // Default style → accentBlue
    expect(titlePath!.getAttribute("stroke")).toBe("#60a5fa");
  });

  it("uses textPrimary for body stroke", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={basicInstruction} />,
    );
    const bodyPath = container.querySelector('[data-hw-section="body"]');
    expect(bodyPath).toBeTruthy();
    expect(bodyPath!.getAttribute("stroke")).toBe("#f0f0f0");
  });
});

// ── Style variants ────────────────────────────────────────────

describe("HandwrittenTextContent — style accents", () => {
  it("key_point style uses amber accent for title", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={keyPointInstruction} />,
    );
    const titlePath = container.querySelector('[data-hw-section="title"]');
    expect(titlePath!.getAttribute("stroke")).toBe("#fbbf24");
  });

  it("example style uses green accent for title", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent
        instruction={{ ...exampleInstruction, title: "Example" }}
      />,
    );
    const titlePath = container.querySelector('[data-hw-section="title"]');
    expect(titlePath!.getAttribute("stroke")).toBe("#4ade80");
  });
});

// ── Title-only / body-only ────────────────────────────────────

describe("HandwrittenTextContent — edge cases", () => {
  it("handles missing title gracefully", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={basicInstruction} />,
    );
    const titlePaths = container.querySelectorAll('[data-hw-section="title"]');
    expect(titlePaths).toHaveLength(0);
  });

  it("handles empty body text with title", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={titleOnlyInstruction} />,
    );
    const titlePaths = container.querySelectorAll('[data-hw-section="title"]');
    const bodyPaths = container.querySelectorAll('[data-hw-section="body"]');
    expect(titlePaths.length).toBeGreaterThan(0);
    expect(bodyPaths).toHaveLength(0);
  });

  it("handles single character body", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={{ type: "show_text", text: "A" }} />,
    );
    const paths = container.querySelectorAll('[data-hw-section="body"]');
    expect(paths).toHaveLength(1);
    expect(paths[0].getAttribute("data-hw-char")).toBe("A");
  });
});

// ── Accessibility ─────────────────────────────────────────────

describe("HandwrittenTextContent — accessibility", () => {
  it("sets role=img on SVG elements", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={titleAndBodyInstruction} />,
    );
    const svgs = container.querySelectorAll('svg[role="img"]');
    expect(svgs.length).toBeGreaterThan(0);
  });

  it("sets aria-label with text content on SVGs", async () => {
    const HandwrittenTextContent = await importComponent();
    const { container } = render(
      <HandwrittenTextContent instruction={titleAndBodyInstruction} />,
    );
    const svgs = container.querySelectorAll("svg[aria-label]");
    expect(svgs.length).toBeGreaterThan(0);
    // Title SVG should have the title text as aria-label
    const labels = Array.from(svgs).map((s) => s.getAttribute("aria-label"));
    expect(labels).toContain("Key Concept");
    expect(labels).toContain("This is the body text.");
  });
});

// ── InstructionSwitch routing ─────────────────────────────────

describe("Whiteboard InstructionSwitch — show_text routing", () => {
  it("routes show_text to HandwrittenTextContent (has data-hw-char)", async () => {
    const InstructionSwitch = await importInstructionSwitch();
    const { container } = render(
      <InstructionSwitch instruction={basicInstruction} />,
    );
    const hwPaths = container.querySelectorAll("[data-hw-char]");
    expect(hwPaths.length).toBeGreaterThan(0);
    // Should NOT have plain HTML text (old TextContent renders <p> with text)
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs).toHaveLength(0);
  });

  it("routes show_text with title correctly", async () => {
    const InstructionSwitch = await importInstructionSwitch();
    const { container } = render(
      <InstructionSwitch instruction={titleAndBodyInstruction} />,
    );
    const titlePaths = container.querySelectorAll('[data-hw-section="title"]');
    expect(titlePaths.length).toBeGreaterThan(0);
  });
});
