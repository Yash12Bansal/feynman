import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeAll, afterEach } from "vitest";
import type { VisualInstruction } from "../../../types/visuals";
import type { BoardTransition, BoardMeta } from "../useBoardStore";

// ── Mock GSAP ────────────────────────────────────────────────

const tlMock = {
  to: vi.fn().mockReturnThis(),
  fromTo: vi.fn().mockReturnThis(),
  kill: vi.fn(),
};

const gsapMock = {
  timeline: vi.fn(() => ({ ...tlMock })),
  set: vi.fn(),
};

vi.mock("gsap", () => ({ default: gsapMock }));

// ── Stub getTotalLength on SVG paths (for snapshot subcomponents) ──

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

// ── ResizeObserver mock ──────────────────────────────────────

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  // jsdom doesn't implement matchMedia — stub with reduced-motion off
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false } as MediaQueryList),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

// ── Lazy imports (after mocks) ───────────────────────────────

async function loadBoardNavigator() {
  const mod = await import("../BoardNavigator");
  return mod.BoardNavigator;
}

// ── Helpers ──────────────────────────────────────────────────

const noopComplete = vi.fn();
const noopGetInstructions = vi.fn().mockReturnValue([]);

function defaultProps(overrides?: {
  activeBoardMeta?: BoardMeta | null;
  pendingTransition?: BoardTransition | null;
  onTransitionComplete?: () => void;
  getBoardInstructions?: (id: string) => VisualInstruction[];
}) {
  return {
    activeBoardMeta: null,
    pendingTransition: null,
    onTransitionComplete: noopComplete,
    getBoardInstructions: noopGetInstructions,
    ...overrides,
  };
}

// ── Tests ────────────────────────────────────────────────────

describe("BoardNavigator", () => {
  it("renders children (active board content) when no transition", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const { getByText } = render(
      <BoardNavigator {...defaultProps()}>
        <div>Board Content</div>
      </BoardNavigator>,
    );
    expect(getByText("Board Content")).toBeTruthy();
  });

  it("wraps children in wb-board-layer", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const { container } = render(
      <BoardNavigator {...defaultProps()}>
        <div>Content</div>
      </BoardNavigator>,
    );
    expect(container.querySelector(".wb-board-layer")).toBeTruthy();
  });

  it("renders board label when activeBoardMeta has label", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const { container } = render(
      <BoardNavigator
        {...defaultProps({
          activeBoardMeta: { id: "board-2", label: "Doubt #1" },
        })}
      >
        <div />
      </BoardNavigator>,
    );
    const label = container.querySelector(".wb-board-label");
    expect(label).toBeTruthy();
    expect(label?.textContent).toBe("Doubt #1");
  });

  it("does not render board label when meta is null", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const { container } = render(
      <BoardNavigator {...defaultProps()}>
        <div />
      </BoardNavigator>,
    );
    expect(container.querySelector(".wb-board-label")).toBeNull();
  });

  it("no peek overlay when no transition", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const { container } = render(
      <BoardNavigator {...defaultProps()}>
        <div />
      </BoardNavigator>,
    );
    expect(container.querySelector(".wb-board-peek")).toBeNull();
  });

  it("creates GSAP timeline for new intent transition", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const transition: BoardTransition = {
      from: "board-1",
      to: "board-2",
      intent: "new",
    };
    render(
      <BoardNavigator {...defaultProps({ pendingTransition: transition })}>
        <div />
      </BoardNavigator>,
    );
    expect(gsapMock.timeline).toHaveBeenCalled();
  });

  it("creates GSAP timeline for revisit intent", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const transition: BoardTransition = {
      from: "board-2",
      to: "board-1",
      intent: "revisit",
    };
    render(
      <BoardNavigator {...defaultProps({ pendingTransition: transition })}>
        <div />
      </BoardNavigator>,
    );
    expect(gsapMock.timeline).toHaveBeenCalled();
  });

  it("prefers-reduced-motion: calls onTransitionComplete immediately for new/revisit", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const matchMediaSpy = vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
    } as MediaQueryList);

    const onComplete = vi.fn();
    const transition: BoardTransition = {
      from: "board-1",
      to: "board-2",
      intent: "new",
    };
    render(
      <BoardNavigator
        {...defaultProps({
          pendingTransition: transition,
          onTransitionComplete: onComplete,
        })}
      >
        <div />
      </BoardNavigator>,
    );
    expect(onComplete).toHaveBeenCalled();
    matchMediaSpy.mockRestore();
  });

  it("board label updates on meta change", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const { container, rerender } = render(
      <BoardNavigator
        {...defaultProps({
          activeBoardMeta: { id: "b1", label: "First" },
        })}
      >
        <div />
      </BoardNavigator>,
    );
    expect(container.querySelector(".wb-board-label")?.textContent).toBe(
      "First",
    );
    rerender(
      <BoardNavigator
        {...defaultProps({
          activeBoardMeta: { id: "b2", label: "Second" },
        })}
      >
        <div />
      </BoardNavigator>,
    );
    expect(container.querySelector(".wb-board-label")?.textContent).toBe(
      "Second",
    );
  });

  it("renders wb-navigator container", async () => {
    const BoardNavigator = await loadBoardNavigator();
    const { container } = render(
      <BoardNavigator {...defaultProps()}>
        <div />
      </BoardNavigator>,
    );
    expect(container.querySelector(".wb-navigator")).toBeTruthy();
  });
});
