import { render } from "@testing-library/react";
import { describe, it, expect, beforeAll, vi } from "vitest";
import { WhiteboardScene } from "../WhiteboardScene";
import { BoardElement } from "../BoardElement";
import { BoardLayoutContext } from "../board-layout-context";
import {
  ElementRegistryContext,
  useCreateElementRegistry,
} from "../../elements";
import { allZones, computeBoardLayout } from "../zone-layout";
import type { VisualInstruction } from "../../../types/visuals";

// ── Mock GSAP (needed for HandwrittenTextContent) ───────────

vi.mock("gsap", () => {
  const tween = { kill: vi.fn() };
  const tl = {
    to: vi.fn().mockReturnThis(),
    fromTo: vi.fn().mockReturnThis(),
    kill: vi.fn(),
  };
  return {
    default: {
      timeline: () => tl,
      set: vi.fn(),
      to: vi.fn().mockReturnValue(tween),
      fromTo: vi.fn().mockReturnValue(tween),
    },
  };
});

// ── Stub getTotalLength on SVG paths (jsdom lacks it) ───────

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

// ── ResizeObserver mock ─────────────────────────────────────

class MockResizeObserver {
  callback: ResizeObserverCallback;

  constructor(cb: ResizeObserverCallback) {
    this.callback = cb;
  }

  observe(target: Element) {
    // Fire immediately with the target's dimensions
    this.callback(
      [
        {
          target,
          contentRect: { width: 1920, height: 1080 } as DOMRectReadOnly,
          borderBoxSize: [],
          contentBoxSize: [],
          devicePixelContentBoxSize: [],
        },
      ],
      this,
    );
  }

  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
});

// ── Board rendering ─────────────────────────────────────────

describe("WhiteboardScene — board rendering", () => {
  it("renders the board surface", () => {
    const { container } = render(<WhiteboardScene instructions={[]} />);
    expect(container.querySelector(".wb-board-surface")).toBeTruthy();
  });

  it("board div has 1920x1080 dimensions", () => {
    const { container } = render(<WhiteboardScene instructions={[]} />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board).toBeTruthy();
    expect(board.style.width).toBe("1920px");
    expect(board.style.height).toBe("1080px");
  });

  it("viewport has wb-viewport class for overflow clipping", () => {
    const { container } = render(<WhiteboardScene instructions={[]} />);
    const viewport = container.querySelector(".wb-viewport") as HTMLDivElement;
    expect(viewport).toBeTruthy();
    expect(viewport.classList.contains("wb-viewport")).toBe(true);
  });

  it("injects theme CSS variables on the board", () => {
    const { container } = render(<WhiteboardScene instructions={[]} />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board.style.getPropertyValue("--color-background")).toBeTruthy();
    expect(board.style.getPropertyValue("--color-text-primary")).toBeTruthy();
  });
});

// ── Scaling ─────────────────────────────────────────────────

describe("WhiteboardScene — scaling", () => {
  it("applies transform with scale and translation", () => {
    const { container } = render(<WhiteboardScene instructions={[]} />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board.style.transform).toContain("scale(");
    expect(board.style.transform).toContain("translate(");
  });

  it("at exact 1920x1080, scale is 1 and offsets are 0", () => {
    const { container } = render(<WhiteboardScene instructions={[]} />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board.style.transform).toContain("scale(1)");
    expect(board.style.transform).toContain("translate(0px, 0px)");
  });
});

// ── BoardElement ────────────────────────────────────────────

function BoardElementWrapper({ children }: { children: React.ReactNode }) {
  const layout = computeBoardLayout();
  const registry = useCreateElementRegistry();
  return (
    <BoardLayoutContext.Provider value={layout}>
      <ElementRegistryContext.Provider value={registry}>
        {children}
      </ElementRegistryContext.Provider>
    </BoardLayoutContext.Provider>
  );
}

describe("BoardElement", () => {
  const bounds = { x: 100, y: 200, width: 400, height: 300 };

  it("renders children", () => {
    const { getByText } = render(
      <BoardElementWrapper>
        <BoardElement id="el-1" bounds={bounds}>
          <span>Hello</span>
        </BoardElement>
      </BoardElementWrapper>,
    );
    expect(getByText("Hello")).toBeTruthy();
  });

  it("sets inline position from bounds", () => {
    const { container } = render(
      <BoardElementWrapper>
        <BoardElement id="el-1" bounds={bounds} />
      </BoardElementWrapper>,
    );
    const el = container.querySelector(
      '[data-element-id="el-1"]',
    ) as HTMLDivElement;
    expect(el).toBeTruthy();
    expect(el.style.left).toBe("100px");
    expect(el.style.top).toBe("200px");
    expect(el.style.width).toBe("400px");
    expect(el.style.height).toBe("300px");
  });

  it("sets data-element-id and data-type attributes", () => {
    const { container } = render(
      <BoardElementWrapper>
        <BoardElement id="eq-1" bounds={bounds} dataType="show_equation" />
      </BoardElementWrapper>,
    );
    const el = container.querySelector('[data-element-id="eq-1"]');
    expect(el).toBeTruthy();
    expect(el?.getAttribute("data-type")).toBe("show_equation");
  });

  it("multiple elements positioned independently", () => {
    const bounds1 = { x: 0, y: 0, width: 100, height: 50 };
    const bounds2 = { x: 500, y: 300, width: 200, height: 100 };

    const { container } = render(
      <BoardElementWrapper>
        <BoardElement id="a" bounds={bounds1} />
        <BoardElement id="b" bounds={bounds2} />
      </BoardElementWrapper>,
    );

    const a = container.querySelector(
      '[data-element-id="a"]',
    ) as HTMLDivElement;
    const b = container.querySelector(
      '[data-element-id="b"]',
    ) as HTMLDivElement;
    expect(a.style.left).toBe("0px");
    expect(a.style.top).toBe("0px");
    expect(b.style.left).toBe("500px");
    expect(b.style.top).toBe("300px");
  });
});

// ── Zone debug ──────────────────────────────────────────────

describe("WhiteboardScene — zone debug", () => {
  it("does not render zone overlay when debugZones is false", () => {
    const { container } = render(<WhiteboardScene instructions={[]} />);
    expect(container.querySelector(".wb-zone-debug")).toBeNull();
  });

  it("renders all 9 zone outlines when debugZones is true", () => {
    const { container } = render(
      <WhiteboardScene instructions={[]} debugZones />,
    );
    const zoneOutlines = container.querySelectorAll(".wb-zone-debug");
    expect(zoneOutlines.length).toBe(9);
  });

  it("renders zone name labels", () => {
    const { container } = render(
      <WhiteboardScene instructions={[]} debugZones />,
    );
    const labels = container.querySelectorAll(".wb-zone-debug-label");
    expect(labels.length).toBe(9);

    const labelTexts = Array.from(labels).map((l) => l.textContent);
    for (const zone of allZones()) {
      expect(labelTexts).toContain(zone);
    }
  });

  it("renders inner bound indicators", () => {
    const { container } = render(
      <WhiteboardScene instructions={[]} debugZones />,
    );
    const innerBounds = container.querySelectorAll(".wb-zone-debug-inner");
    expect(innerBounds.length).toBe(9);
  });
});

// ── Context providers ───────────────────────────────────────

describe("WhiteboardScene — context", () => {
  it("provides BoardLayoutContext (verified via instruction rendering)", () => {
    // If the layout wasn't provided, zone positioning would fail.
    // A text instruction without zone defaults to center-center,
    // and the zone container is positioned using layout data.
    const instructions: VisualInstruction[] = [
      { type: "show_text", text: "probe" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    const zone = container.querySelector('.wb-zone[data-zone="center-center"]');
    expect(zone).toBeTruthy();
    // Zone is positioned using layout inner bounds
    const style = (zone as HTMLDivElement).style;
    expect(parseFloat(style.left)).toBeGreaterThan(0);
    expect(parseFloat(style.top)).toBeGreaterThan(0);
    expect(parseFloat(style.width)).toBeGreaterThan(0);
    expect(parseFloat(style.height)).toBeGreaterThan(0);
  });

  it("provides ElementRegistryContext (verified via WhiteboardCard)", () => {
    // WhiteboardCard calls useElementRegistry — if context wasn't provided,
    // it would throw. A successful render proves context is available.
    const instructions: VisualInstruction[] = [
      { type: "show_text", text: "probe", element_id: "ctx-test" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    expect(
      container.querySelector('[data-element-id="ctx-test"]'),
    ).toBeTruthy();
  });
});

// ── Instruction routing ─────────────────────────────────────

describe("WhiteboardScene — instruction routing", () => {
  it("renders instruction in specified zone", () => {
    const instructions: VisualInstruction[] = [
      { type: "show_text", text: "Newton", zone: "top-left" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    const zone = container.querySelector('.wb-zone[data-zone="top-left"]');
    expect(zone).toBeTruthy();
    expect(zone?.querySelector(".wb-card")).toBeTruthy();
  });

  it("defaults to center-center when zone is undefined", () => {
    const instructions: VisualInstruction[] = [
      { type: "show_text", text: "no zone" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    const zone = container.querySelector('.wb-zone[data-zone="center-center"]');
    expect(zone).toBeTruthy();
    expect(zone?.querySelector(".wb-card")).toBeTruthy();
    // No other zones should be rendered
    expect(container.querySelectorAll(".wb-zone").length).toBe(1);
  });

  it("renders instructions in separate zone containers", () => {
    const instructions: VisualInstruction[] = [
      { type: "show_text", text: "top", zone: "top-left" },
      { type: "show_equation", latex: "x=1", zone: "bottom-right" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    expect(
      container.querySelector('.wb-zone[data-zone="top-left"]'),
    ).toBeTruthy();
    expect(
      container.querySelector('.wb-zone[data-zone="bottom-right"]'),
    ).toBeTruthy();
    expect(container.querySelectorAll(".wb-zone").length).toBe(2);
  });

  it("stacks multiple instructions in same zone", () => {
    const instructions: VisualInstruction[] = [
      { type: "show_text", text: "first", zone: "top-center" },
      { type: "show_text", text: "second", zone: "top-center" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    const zones = container.querySelectorAll(".wb-zone");
    expect(zones.length).toBe(1);
    const cards = zones[0].querySelectorAll(".wb-card");
    expect(cards.length).toBe(2);
  });

  it("separates highlights from zone content", () => {
    const instructions: VisualInstruction[] = [
      {
        type: "show_text",
        text: "target",
        element_id: "t1",
        zone: "top-left",
      },
      { type: "highlight", target_id: "t1", style: "glow" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    // Only one zone rendered (for the text), highlight is not in a zone
    const zones = container.querySelectorAll(".wb-zone");
    expect(zones.length).toBe(1);
    expect(zones[0].querySelectorAll(".wb-card").length).toBe(1);
  });

  it("skips clear instructions from zone rendering", () => {
    const instructions: VisualInstruction[] = [
      { type: "clear" },
      { type: "show_text", text: "after clear", zone: "center-center" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    // Only one zone with one card (clear is filtered out)
    const zones = container.querySelectorAll(".wb-zone");
    expect(zones.length).toBe(1);
    expect(zones[0].querySelectorAll(".wb-card").length).toBe(1);
  });

  it("separates annotate instructions from zone content", () => {
    const instructions: VisualInstruction[] = [
      {
        type: "show_text",
        text: "target",
        element_id: "t1",
        zone: "top-left",
      },
      { type: "annotate", action: "circle", target_id: "t1" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    // Only one zone rendered (for the text), annotate is not in a zone
    const zones = container.querySelectorAll(".wb-zone");
    expect(zones.length).toBe(1);
    expect(zones[0].querySelectorAll(".wb-card").length).toBe(1);
  });

  it("renders AnnotationLayer inside board surface", () => {
    const instructions: VisualInstruction[] = [
      {
        type: "show_text",
        text: "target",
        element_id: "t1",
        zone: "top-left",
      },
      { type: "annotate", action: "circle", target_id: "t1" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    const surface = container.querySelector(".wb-board-surface");
    const annotationLayer = surface?.querySelector(".wb-annotation-layer");
    expect(annotationLayer).toBeTruthy();
  });

  it("sets data-type attribute on whiteboard cards", () => {
    const instructions: VisualInstruction[] = [
      { type: "show_equation", latex: "E=mc^2", zone: "top-right" },
    ];
    const { container } = render(
      <WhiteboardScene instructions={instructions} />,
    );
    const card = container.querySelector(".wb-card");
    expect(card?.getAttribute("data-type")).toBe("show_equation");
  });
});
