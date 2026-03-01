import { createRef } from "react";
import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import type { AnnotateInstruction } from "../../../types/visuals";
import { AnnotationOverlay } from "../content/AnnotationOverlay";
import { AnnotationLayer } from "../content/AnnotationLayer";
import { ElementRegistryContext } from "../../elements";
import type { ElementRegistry } from "../../elements";

// ── Mock GSAP ─────────────────────────────────────────────────

const mockTl = {
  to: vi.fn().mockReturnThis(),
  fromTo: vi.fn().mockReturnThis(),
  kill: vi.fn(),
};

vi.mock("gsap", () => ({
  default: {
    timeline: () => mockTl,
    set: vi.fn(),
  },
}));

// ── Mock registry ─────────────────────────────────────────────

function createMockRegistry(
  entries: Record<
    string,
    { left: number; top: number; width: number; height: number }
  > = {},
): ElementRegistry {
  return {
    register: vi.fn(),
    unregister: vi.fn(),
    get: (id: string) => {
      const rect = entries[id];
      if (!rect) return undefined;
      const el = document.createElement("div");
      vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        right: rect.left + rect.width,
        bottom: rect.top + rect.height,
        x: rect.left,
        y: rect.top,
        toJSON: () => ({}),
      });
      return {
        id,
        ref: el as unknown as HTMLDivElement,
        instruction: { type: "show_text", text: "mock" } as never,
      };
    },
  };
}

function createMockBoardRef() {
  const el = document.createElement("div");
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    width: 1920,
    height: 1080,
    right: 1920,
    bottom: 1080,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  const ref = createRef<HTMLDivElement>();
  // Mutate ref to set current (React's createRef returns { current: null })
  (ref as { current: HTMLDivElement }).current = el;
  return ref;
}

// ── ResizeObserver mock ───────────────────────────────────────

beforeAll(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

beforeEach(() => {
  vi.clearAllMocks();
});

// ── AnnotationOverlay ─────────────────────────────────────────

describe("AnnotationOverlay", () => {
  it("renders null when target not found", () => {
    const registry = createMockRegistry({});
    const boardRef = createMockBoardRef();
    const instruction: AnnotateInstruction = {
      type: "annotate",
      action: "circle",
      target_id: "nonexistent",
    };

    const { container } = render(
      <ElementRegistryContext.Provider value={registry}>
        <svg>
          <AnnotationOverlay
            instruction={instruction}
            boardRef={boardRef}
            scale={1}
          />
        </svg>
      </ElementRegistryContext.Provider>,
    );

    // The g element exists but has no filled path (no d attribute set)
    const fillPath = container.querySelector("[data-fill]");
    expect(fillPath?.getAttribute("d")).toBeNull();
  });

  it("renders SVG path when circle target found", async () => {
    const registry = createMockRegistry({
      "eq-1": { left: 100, top: 200, width: 300, height: 80 },
    });
    const boardRef = createMockBoardRef();
    const instruction: AnnotateInstruction = {
      type: "annotate",
      action: "circle",
      target_id: "eq-1",
    };

    render(
      <ElementRegistryContext.Provider value={registry}>
        <svg>
          <AnnotationOverlay
            instruction={instruction}
            boardRef={boardRef}
            scale={1}
          />
        </svg>
      </ElementRegistryContext.Provider>,
    );

    // Wait for rAF
    await new Promise((r) => setTimeout(r, 50));

    // GSAP timeline should have been called for animation
    expect(mockTl.to).toHaveBeenCalled();
  });

  it("renders arrow between two elements", () => {
    const registry = createMockRegistry({
      "eq-1": { left: 100, top: 100, width: 200, height: 60 },
      "eq-2": { left: 500, top: 300, width: 200, height: 60 },
    });
    const boardRef = createMockBoardRef();
    const instruction: AnnotateInstruction = {
      type: "annotate",
      action: "arrow",
      from_id: "eq-1",
      to_id: "eq-2",
    };

    const { container } = render(
      <ElementRegistryContext.Provider value={registry}>
        <svg>
          <AnnotationOverlay
            instruction={instruction}
            boardRef={boardRef}
            scale={1}
          />
        </svg>
      </ElementRegistryContext.Provider>,
    );

    // Arrow annotation should have arrowhead path element
    const arrowPath = container.querySelector("[data-arrow]");
    expect(arrowPath).toBeTruthy();
  });

  it("uses default red color when no color specified", () => {
    const registry = createMockRegistry({
      "eq-1": { left: 100, top: 200, width: 300, height: 80 },
    });
    const boardRef = createMockBoardRef();
    const instruction: AnnotateInstruction = {
      type: "annotate",
      action: "circle",
      target_id: "eq-1",
    };

    const { container } = render(
      <ElementRegistryContext.Provider value={registry}>
        <svg>
          <AnnotationOverlay
            instruction={instruction}
            boardRef={boardRef}
            scale={1}
          />
        </svg>
      </ElementRegistryContext.Provider>,
    );

    const fillPath = container.querySelector("[data-fill]");
    // Default red fill
    expect(fillPath?.getAttribute("fill")).toBe("#ef4444");
  });

  it("uses custom color when specified", () => {
    const registry = createMockRegistry({
      "eq-1": { left: 100, top: 200, width: 300, height: 80 },
    });
    const boardRef = createMockBoardRef();
    const instruction: AnnotateInstruction = {
      type: "annotate",
      action: "underline",
      target_id: "eq-1",
      color: "#00ff00",
    };

    const { container } = render(
      <ElementRegistryContext.Provider value={registry}>
        <svg>
          <AnnotationOverlay
            instruction={instruction}
            boardRef={boardRef}
            scale={1}
          />
        </svg>
      </ElementRegistryContext.Provider>,
    );

    const fillPath = container.querySelector("[data-fill]");
    expect(fillPath?.getAttribute("fill")).toBe("#00ff00");
  });
});

// ── AnnotationLayer ───────────────────────────────────────────

describe("AnnotationLayer", () => {
  it("renders nothing when annotations array is empty", () => {
    const registry = createMockRegistry({});
    const boardRef = createRef<HTMLDivElement>();
    const { container } = render(
      <ElementRegistryContext.Provider value={registry}>
        <AnnotationLayer annotations={[]} boardRef={boardRef} scale={1} />
      </ElementRegistryContext.Provider>,
    );
    expect(container.querySelector(".wb-annotation-layer")).toBeNull();
  });

  it("renders SVG layer with correct dimensions", () => {
    const registry = createMockRegistry({
      "eq-1": { left: 100, top: 200, width: 300, height: 80 },
    });
    const boardRef = createMockBoardRef();
    const annotations: AnnotateInstruction[] = [
      { type: "annotate", action: "circle", target_id: "eq-1" },
    ];

    const { container } = render(
      <ElementRegistryContext.Provider value={registry}>
        <AnnotationLayer
          annotations={annotations}
          boardRef={boardRef}
          scale={1}
        />
      </ElementRegistryContext.Provider>,
    );

    const svg = container.querySelector(".wb-annotation-layer");
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute("width")).toBe("1920");
    expect(svg?.getAttribute("height")).toBe("1080");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 1920 1080");
  });

  it("has pointer-events none", () => {
    const registry = createMockRegistry({
      "eq-1": { left: 100, top: 200, width: 300, height: 80 },
    });
    const boardRef = createMockBoardRef();
    const annotations: AnnotateInstruction[] = [
      { type: "annotate", action: "circle", target_id: "eq-1" },
    ];

    const { container } = render(
      <ElementRegistryContext.Provider value={registry}>
        <AnnotationLayer
          annotations={annotations}
          boardRef={boardRef}
          scale={1}
        />
      </ElementRegistryContext.Provider>,
    );

    const svg = container.querySelector(".wb-annotation-layer") as SVGElement;
    expect(svg.style.pointerEvents).toBe("none");
  });
});
