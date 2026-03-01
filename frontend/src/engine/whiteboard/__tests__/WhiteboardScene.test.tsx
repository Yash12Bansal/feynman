import { render } from "@testing-library/react";
import { describe, it, expect, beforeAll, vi } from "vitest";
import { WhiteboardScene } from "../WhiteboardScene";
import { BoardElement } from "../BoardElement";
import { useBoardLayout } from "../board-layout-context";
import { useElementRegistry } from "../../elements";
import { BOARD_WIDTH, BOARD_HEIGHT } from "../types";
import { allZones } from "../zone-layout";

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
    const { container } = render(<WhiteboardScene />);
    expect(container.querySelector(".wb-board-surface")).toBeTruthy();
  });

  it("board div has 1920x1080 dimensions", () => {
    const { container } = render(<WhiteboardScene />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board).toBeTruthy();
    expect(board.style.width).toBe("1920px");
    expect(board.style.height).toBe("1080px");
  });

  it("viewport has wb-viewport class for overflow clipping", () => {
    const { container } = render(<WhiteboardScene />);
    const viewport = container.querySelector(".wb-viewport") as HTMLDivElement;
    expect(viewport).toBeTruthy();
    // overflow: hidden is applied via CSS class — verify the class is present
    expect(viewport.classList.contains("wb-viewport")).toBe(true);
  });

  it("injects theme CSS variables on the board", () => {
    const { container } = render(<WhiteboardScene />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board.style.getPropertyValue("--color-background")).toBeTruthy();
    expect(board.style.getPropertyValue("--color-text-primary")).toBeTruthy();
  });
});

// ── Scaling ─────────────────────────────────────────────────

describe("WhiteboardScene — scaling", () => {
  it("applies transform with scale and translation", () => {
    const { container } = render(<WhiteboardScene />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board.style.transform).toContain("scale(");
    expect(board.style.transform).toContain("translate(");
  });

  it("at exact 1920x1080, scale is 1 and offsets are 0", () => {
    // Our MockResizeObserver reports 1920x1080
    const { container } = render(<WhiteboardScene />);
    const board = container.querySelector(".wb-board") as HTMLDivElement;
    expect(board.style.transform).toContain("scale(1)");
    expect(board.style.transform).toContain("translate(0px, 0px)");
  });
});

// ── BoardElement ────────────────────────────────────────────

describe("BoardElement", () => {
  const bounds = { x: 100, y: 200, width: 400, height: 300 };

  it("renders children", () => {
    const { getByText } = render(
      <WhiteboardScene>
        <BoardElement id="el-1" bounds={bounds}>
          <span>Hello</span>
        </BoardElement>
      </WhiteboardScene>,
    );
    expect(getByText("Hello")).toBeTruthy();
  });

  it("sets inline position from bounds", () => {
    const { container } = render(
      <WhiteboardScene>
        <BoardElement id="el-1" bounds={bounds} />
      </WhiteboardScene>,
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
      <WhiteboardScene>
        <BoardElement id="eq-1" bounds={bounds} dataType="show_equation" />
      </WhiteboardScene>,
    );
    const el = container.querySelector('[data-element-id="eq-1"]');
    expect(el).toBeTruthy();
    expect(el?.getAttribute("data-type")).toBe("show_equation");
  });

  it("multiple elements positioned independently", () => {
    const bounds1 = { x: 0, y: 0, width: 100, height: 50 };
    const bounds2 = { x: 500, y: 300, width: 200, height: 100 };

    const { container } = render(
      <WhiteboardScene>
        <BoardElement id="a" bounds={bounds1} />
        <BoardElement id="b" bounds={bounds2} />
      </WhiteboardScene>,
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
    const { container } = render(<WhiteboardScene />);
    expect(container.querySelector(".wb-zone-debug")).toBeNull();
  });

  it("renders all 9 zone outlines when debugZones is true", () => {
    const { container } = render(<WhiteboardScene debugZones />);
    const zoneOutlines = container.querySelectorAll(".wb-zone-debug");
    expect(zoneOutlines.length).toBe(9);
  });

  it("renders zone name labels", () => {
    const { container } = render(<WhiteboardScene debugZones />);
    const labels = container.querySelectorAll(".wb-zone-debug-label");
    expect(labels.length).toBe(9);

    const labelTexts = Array.from(labels).map((l) => l.textContent);
    for (const zone of allZones()) {
      expect(labelTexts).toContain(zone);
    }
  });

  it("renders inner bound indicators", () => {
    const { container } = render(<WhiteboardScene debugZones />);
    const innerBounds = container.querySelectorAll(".wb-zone-debug-inner");
    expect(innerBounds.length).toBe(9);
  });
});

// ── Context providers ───────────────────────────────────────

describe("WhiteboardScene — context", () => {
  it("provides BoardLayoutContext to children", () => {
    function LayoutConsumer() {
      const layout = useBoardLayout();
      return (
        <div
          data-testid="layout-probe"
          data-width={layout.width}
          data-height={layout.height}
          data-has-center={layout.zones["center-center"] ? "yes" : "no"}
        />
      );
    }

    const { getByTestId } = render(
      <WhiteboardScene>
        <LayoutConsumer />
      </WhiteboardScene>,
    );

    const probe = getByTestId("layout-probe");
    expect(probe.getAttribute("data-width")).toBe(String(BOARD_WIDTH));
    expect(probe.getAttribute("data-height")).toBe(String(BOARD_HEIGHT));
    expect(probe.getAttribute("data-has-center")).toBe("yes");
  });

  it("provides ElementRegistryContext to children", () => {
    function RegistryConsumer() {
      const registry = useElementRegistry();
      return (
        <div
          data-testid="registry-probe"
          data-available={registry ? "yes" : "no"}
        />
      );
    }

    const { getByTestId } = render(
      <WhiteboardScene>
        <RegistryConsumer />
      </WhiteboardScene>,
    );

    expect(getByTestId("registry-probe").getAttribute("data-available")).toBe(
      "yes",
    );
  });
});
