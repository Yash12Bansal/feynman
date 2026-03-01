import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { DrawDiagramInstruction } from "../../../types/visuals";

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
  // jsdom doesn't implement getTotalLength — stub it
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
  };
  return {
    default: {
      svg: () => rcMethods,
    },
  };
});

// ── Fixtures ──────────────────────────────────────────────────

const structuredInstruction: DrawDiagramInstruction = {
  type: "draw_diagram",
  diagram_type: "force_diagram",
  title: "Free Body Diagram",
  description: "Forces acting on a block.",
  nodes: [
    { id: "block", label: "Block (m)", shape: "rectangle", color: "#60a5fa" },
    { id: "weight", label: "mg", shape: "circle", color: "#ef4444" },
    { id: "normal", label: "N", shape: "circle", color: "#4ade80" },
  ],
  edges: [
    { from_id: "block", to_id: "weight", label: "gravity", directed: true },
    {
      from_id: "block",
      to_id: "normal",
      label: "perpendicular",
      directed: true,
    },
  ],
  progressive: true,
};

const undirectedInstruction: DrawDiagramInstruction = {
  type: "draw_diagram",
  nodes: [
    { id: "a", label: "A" },
    { id: "b", label: "B" },
  ],
  edges: [{ from_id: "a", to_id: "b", directed: false }],
};

const descriptionOnlyInstruction: DrawDiagramInstruction = {
  type: "draw_diagram",
  description: "A block on an inclined plane.",
};

// ── Lazy imports (after mocks) ────────────────────────────────

async function importComponent() {
  const mod = await import("../content/RoughDiagramContent");
  return mod.RoughDiagramContent;
}

async function importInstructionSwitch() {
  const mod = await import("../InstructionSwitch");
  return mod.InstructionSwitch;
}

async function importHelpers() {
  return await import("../content/rough-helpers");
}

// ── RoughDiagramContent — structured ──────────────────────────

describe("RoughDiagramContent — structured", () => {
  it("renders SVG with correct viewBox", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={structuredInstruction} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    const viewBox = svg!.getAttribute("viewBox");
    expect(viewBox).toBeTruthy();
    const parts = viewBox!.split(" ").map(Number);
    expect(parts).toHaveLength(4);
    expect(parts[2]).toBeGreaterThan(0);
    expect(parts[3]).toBeGreaterThan(0);
  });

  it("renders data-rough-node groups for each node", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={structuredInstruction} />,
    );
    const nodeEls = container.querySelectorAll("[data-rough-node]");
    expect(nodeEls).toHaveLength(3);
  });

  it("renders data-rough-edge groups for each edge", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={structuredInstruction} />,
    );
    const edgeEls = container.querySelectorAll("[data-rough-edge]");
    expect(edgeEls).toHaveLength(2);
  });

  it("renders arrowhead groups for directed edges", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={structuredInstruction} />,
    );
    const arrowheads = container.querySelectorAll("[data-rough-arrowhead]");
    expect(arrowheads).toHaveLength(2);
  });

  it("omits arrowheads for undirected edges", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={undirectedInstruction} />,
    );
    const arrowheads = container.querySelectorAll("[data-rough-arrowhead]");
    expect(arrowheads).toHaveLength(0);
  });

  it("renders clean text labels for nodes", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={structuredInstruction} />,
    );
    const labelEls = container.querySelectorAll("[data-node-label]");
    expect(labelEls).toHaveLength(3);
  });

  it("renders edge labels", async () => {
    const RoughDiagramContent = await importComponent();
    render(<RoughDiagramContent instruction={structuredInstruction} />);
    expect(screen.getByText("gravity")).toBeTruthy();
    expect(screen.getByText("perpendicular")).toBeTruthy();
  });

  it("renders title + description", async () => {
    const RoughDiagramContent = await importComponent();
    render(<RoughDiagramContent instruction={structuredInstruction} />);
    expect(screen.getByText("Free Body Diagram")).toBeTruthy();
    expect(screen.getByText("Forces acting on a block.")).toBeTruthy();
  });

  it("sets role=img and aria-label on SVG", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={structuredInstruction} />,
    );
    const svg = container.querySelector("svg");
    expect(svg!.getAttribute("role")).toBe("img");
    expect(svg!.getAttribute("aria-label")).toBeTruthy();
  });
});

// ── RoughDiagramContent — fallback ────────────────────────────

describe("RoughDiagramContent — fallback", () => {
  it("renders badge + description when no nodes", async () => {
    const RoughDiagramContent = await importComponent();
    render(<RoughDiagramContent instruction={descriptionOnlyInstruction} />);
    expect(screen.getByText("DIAGRAM")).toBeTruthy();
    expect(screen.getByText("A block on an inclined plane.")).toBeTruthy();
  });

  it("does not render SVG when no nodes", async () => {
    const RoughDiagramContent = await importComponent();
    const { container } = render(
      <RoughDiagramContent instruction={descriptionOnlyInstruction} />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("shows correct badge for diagram type", async () => {
    const RoughDiagramContent = await importComponent();
    const instruction: DrawDiagramInstruction = {
      type: "draw_diagram",
      diagram_type: "flowchart",
      description: "A process flow.",
    };
    render(<RoughDiagramContent instruction={instruction} />);
    expect(screen.getByText("FLOWCHART")).toBeTruthy();
  });
});

// ── Whiteboard InstructionSwitch ──────────────────────────────

describe("Whiteboard InstructionSwitch", () => {
  it("routes draw_diagram to RoughDiagramContent", async () => {
    const InstructionSwitch = await importInstructionSwitch();
    const { container } = render(
      <InstructionSwitch instruction={structuredInstruction} />,
    );
    // Rough renderer uses data-rough-node, clean one uses data-node
    const roughNodes = container.querySelectorAll("[data-rough-node]");
    expect(roughNodes.length).toBeGreaterThan(0);
    const cleanNodes = container.querySelectorAll("[data-node]");
    expect(cleanNodes).toHaveLength(0);
  });

  it("routes show_text to TextContent", async () => {
    const InstructionSwitch = await importInstructionSwitch();
    render(
      <InstructionSwitch
        instruction={{ type: "show_text", text: "Hello world" }}
      />,
    );
    expect(screen.getByText("Hello world")).toBeTruthy();
  });

  it("returns null for unknown type", async () => {
    const InstructionSwitch = await importInstructionSwitch();
    const { container } = render(
      <InstructionSwitch instruction={{ type: "clear" as never } as never} />,
    );
    expect(container.innerHTML).toBe("");
  });
});

// ── rough-helpers ─────────────────────────────────────────────

describe("rough-helpers", () => {
  it("hashSeed returns deterministic positive integer", async () => {
    const { hashSeed } = await importHelpers();
    const a = hashSeed("block");
    const b = hashSeed("block");
    expect(a).toBe(b);
    expect(a).toBeGreaterThan(0);
    expect(Number.isInteger(a)).toBe(true);
  });

  it("hashSeed returns different values for different IDs", async () => {
    const { hashSeed } = await importHelpers();
    expect(hashSeed("block")).not.toBe(hashSeed("weight"));
  });

  it("hashSeed never returns 0", async () => {
    const { hashSeed } = await importHelpers();
    // Test with empty string edge case
    expect(hashSeed("")).toBeGreaterThan(0);
    expect(hashSeed("0")).toBeGreaterThan(0);
    expect(hashSeed("a")).toBeGreaterThan(0);
  });

  it("computeArrowheadVertices returns 3 vertices for valid edge", async () => {
    const { computeArrowheadVertices } = await importHelpers();
    const vertices = computeArrowheadVertices(100, 100, 0, 0);
    expect(vertices).toHaveLength(3);
    // Each vertex is a [number, number] tuple
    for (const v of vertices) {
      expect(v).toHaveLength(2);
      expect(typeof v[0]).toBe("number");
      expect(typeof v[1]).toBe("number");
    }
  });

  it("computeArrowheadVertices returns empty for zero-length edge", async () => {
    const { computeArrowheadVertices } = await importHelpers();
    const vertices = computeArrowheadVertices(50, 50, 50, 50);
    expect(vertices).toHaveLength(0);
  });
});
