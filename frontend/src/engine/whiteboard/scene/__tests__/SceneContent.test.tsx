import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { DrawSceneInstruction } from "../../../../types/visuals";

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
    path: vi.fn(() => makeSvgGroup()),
  };
  return {
    default: {
      svg: () => rcMethods,
    },
  };
});

// ── Stub getTotalLength globally ──────────────────────────────

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

const templateInstruction: DrawSceneInstruction = {
  type: "draw_scene",
  title: "Free Body Diagram",
  description: "Forces acting on a block on a surface",
  template: {
    template_id: "free_body",
    params: { showWeight: true, showNormal: true, showFriction: true },
  },
  progressive: true,
};

const fallbackInstruction: DrawSceneInstruction = {
  type: "draw_scene",
  description: "A double-slit experiment showing interference.",
};

const unknownTemplateInstruction: DrawSceneInstruction = {
  type: "draw_scene",
  template: {
    template_id: "unknown_template",
  },
};

// ── Lazy imports (after mocks) ────────────────────────────────

async function importComponent() {
  const mod = await import("../SceneContent");
  return mod.SceneContent;
}

// ── SceneContent — template rendering ─────────────────────────

describe("SceneContent — template", () => {
  it("renders SVG with correct viewBox", async () => {
    const SceneContent = await importComponent();
    const { container } = render(
      <SceneContent instruction={templateInstruction} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    const viewBox = svg!.getAttribute("viewBox");
    // Tight bounds from computeTightBounds — no longer a fixed 500x400 canvas
    const parts = viewBox!.split(" ").map(Number);
    expect(parts).toHaveLength(4);
    expect(parts[2]).toBeGreaterThan(200); // width
    expect(parts[3]).toBeGreaterThan(150); // height
  });

  it("renders data-scene-path groups for paths", async () => {
    const SceneContent = await importComponent();
    const { container } = render(
      <SceneContent instruction={templateInstruction} />,
    );
    const pathEls = container.querySelectorAll("[data-scene-path]");
    expect(pathEls.length).toBeGreaterThan(0);
  });

  it("renders data-scene-label groups for labels", async () => {
    const SceneContent = await importComponent();
    const { container } = render(
      <SceneContent instruction={templateInstruction} />,
    );
    const labelEls = container.querySelectorAll("[data-scene-label]");
    expect(labelEls.length).toBeGreaterThan(0);
  });

  it("renders title text", async () => {
    const SceneContent = await importComponent();
    render(<SceneContent instruction={templateInstruction} />);
    expect(screen.getByText("Free Body Diagram")).toBeTruthy();
  });

  it("renders description text", async () => {
    const SceneContent = await importComponent();
    render(<SceneContent instruction={templateInstruction} />);
    expect(
      screen.getByText("Forces acting on a block on a surface"),
    ).toBeTruthy();
  });

  it("sets role=img and aria-label on SVG", async () => {
    const SceneContent = await importComponent();
    const { container } = render(
      <SceneContent instruction={templateInstruction} />,
    );
    const svg = container.querySelector("svg");
    expect(svg!.getAttribute("role")).toBe("img");
    expect(svg!.getAttribute("aria-label")).toBeTruthy();
  });

  it("calls rough.path() for each scene path", async () => {
    const roughModule = await import("roughjs");
    const rc = roughModule.default.svg(null as unknown as SVGSVGElement);
    vi.mocked(rc.path).mockClear();

    const SceneContent = await importComponent();
    render(<SceneContent instruction={templateInstruction} />);

    expect(rc.path).toHaveBeenCalled();
  });
});

// ── SceneContent — fallback ───────────────────────────────────

describe("SceneContent — fallback", () => {
  it("renders SCENE badge when no template", async () => {
    const SceneContent = await importComponent();
    render(<SceneContent instruction={fallbackInstruction} />);
    expect(screen.getByText("SCENE")).toBeTruthy();
  });

  it("renders description when no template", async () => {
    const SceneContent = await importComponent();
    render(<SceneContent instruction={fallbackInstruction} />);
    expect(
      screen.getByText("A double-slit experiment showing interference."),
    ).toBeTruthy();
  });

  it("does not render SVG when no template", async () => {
    const SceneContent = await importComponent();
    const { container } = render(
      <SceneContent instruction={fallbackInstruction} />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("falls back when template_id is unknown", async () => {
    const SceneContent = await importComponent();
    render(<SceneContent instruction={unknownTemplateInstruction} />);
    expect(screen.getByText("SCENE")).toBeTruthy();
  });
});
