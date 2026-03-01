import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import React from "react";
import type { VisualInstruction } from "../../../types/visuals";

// ── Mocks ────────────────────────────────────────────────────

const mockPublishData = vi.fn().mockResolvedValue(undefined);

// Mock useRoomContext — must be before import
vi.mock("@livekit/components-react", () => ({
  useRoomContext: () => ({
    localParticipant: {
      publishData: mockPublishData,
    },
  }),
}));

// Mock element registry entries
const mockEntries =
  vi.fn<() => IterableIterator<[string, { ref: HTMLDivElement }]>>();
vi.mock("../../elements", () => ({
  useElementRegistry: () => ({
    entries: mockEntries,
    get: vi.fn(),
    register: vi.fn(),
    unregister: vi.fn(),
  }),
  ElementRegistryContext: React.createContext(null),
}));

// ── Import after mocks ───────────────────────────────────────

const { BoundsReporter } = await import("../BoundsReporter");

// ── Helpers ──────────────────────────────────────────────────

function makeBoardRef(): React.RefObject<HTMLDivElement> {
  const div = document.createElement("div");
  // Mock getBoundingClientRect for the board surface
  div.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      width: 1920,
      height: 1080,
      left: 0,
      top: 0,
      right: 1920,
      bottom: 1080,
      toJSON: () => ({}),
    }) as DOMRect;
  return { current: div };
}

function makeElementDiv(
  x: number,
  y: number,
  width: number,
  height: number,
): HTMLDivElement {
  const div = document.createElement("div");
  div.getBoundingClientRect = () =>
    ({
      x,
      y,
      width,
      height,
      left: x,
      top: y,
      right: x + width,
      bottom: y + height,
      toJSON: () => ({}),
    }) as DOMRect;
  return div;
}

const textInstruction: VisualInstruction = {
  type: "show_text",
  element_id: "text-1",
  text: "Hello",
};

// ── requestAnimationFrame helper ──────────────────────────────

function flushRAF(): Promise<void> {
  // BoundsReporter waits 2 rAF frames. We need to trigger them.
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        resolve();
      });
    });
  });
}

// ── Tests ────────────────────────────────────────────────────

describe("BoundsReporter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("collects bounds after instruction change", async () => {
    const div1 = makeElementDiv(100, 200, 300, 50);
    mockEntries.mockReturnValue(
      new Map<string, { ref: HTMLDivElement }>([
        ["text-1", { ref: div1 }],
      ]).entries() as IterableIterator<[string, { ref: HTMLDivElement }]>,
    );

    render(
      <BoundsReporter
        boardSurfaceRef={makeBoardRef()}
        scale={1}
        activeBoardId="board-1"
        activeInstructions={[textInstruction]}
      />,
    );

    await flushRAF();

    expect(mockPublishData).toHaveBeenCalled();
    const call = mockPublishData.mock.calls[0];
    const payload = JSON.parse(new TextDecoder().decode(call[0]));
    expect(payload.type).toBe("bounds_report");
    expect(payload.board_id).toBe("board-1");
    expect(payload.elements).toHaveLength(1);
    expect(payload.elements[0].element_id).toBe("text-1");
    expect(payload.elements[0].x).toBe(100);
  });

  it("batches multiple elements in single report", async () => {
    const div1 = makeElementDiv(100, 200, 300, 50);
    const div2 = makeElementDiv(500, 400, 200, 80);
    mockEntries.mockReturnValue(
      new Map<string, { ref: HTMLDivElement }>([
        ["text-1", { ref: div1 }],
        ["eq-1", { ref: div2 }],
      ]).entries() as IterableIterator<[string, { ref: HTMLDivElement }]>,
    );

    render(
      <BoundsReporter
        boardSurfaceRef={makeBoardRef()}
        scale={1}
        activeBoardId="board-1"
        activeInstructions={[textInstruction]}
      />,
    );

    await flushRAF();

    expect(mockPublishData).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(
      new TextDecoder().decode(mockPublishData.mock.calls[0][0]),
    );
    expect(payload.elements).toHaveLength(2);
  });

  it("skips zero-dimension elements", async () => {
    const div1 = makeElementDiv(100, 200, 300, 50);
    const zeroDiv = makeElementDiv(0, 0, 0, 0);
    mockEntries.mockReturnValue(
      new Map<string, { ref: HTMLDivElement }>([
        ["text-1", { ref: div1 }],
        ["hidden", { ref: zeroDiv }],
      ]).entries() as IterableIterator<[string, { ref: HTMLDivElement }]>,
    );

    render(
      <BoundsReporter
        boardSurfaceRef={makeBoardRef()}
        scale={1}
        activeBoardId="board-1"
        activeInstructions={[textInstruction]}
      />,
    );

    await flushRAF();

    const payload = JSON.parse(
      new TextDecoder().decode(mockPublishData.mock.calls[0][0]),
    );
    expect(payload.elements).toHaveLength(1);
    expect(payload.elements[0].element_id).toBe("text-1");
  });

  it("stamps correct board_id", async () => {
    const div1 = makeElementDiv(100, 200, 300, 50);
    mockEntries.mockReturnValue(
      new Map<string, { ref: HTMLDivElement }>([
        ["text-1", { ref: div1 }],
      ]).entries() as IterableIterator<[string, { ref: HTMLDivElement }]>,
    );

    render(
      <BoundsReporter
        boardSurfaceRef={makeBoardRef()}
        scale={1}
        activeBoardId="board-42"
        activeInstructions={[textInstruction]}
      />,
    );

    await flushRAF();

    const payload = JSON.parse(
      new TextDecoder().decode(mockPublishData.mock.calls[0][0]),
    );
    expect(payload.board_id).toBe("board-42");
  });

  it("publishes with lossy data channel options", async () => {
    const div1 = makeElementDiv(100, 200, 300, 50);
    mockEntries.mockReturnValue(
      new Map<string, { ref: HTMLDivElement }>([
        ["text-1", { ref: div1 }],
      ]).entries() as IterableIterator<[string, { ref: HTMLDivElement }]>,
    );

    render(
      <BoundsReporter
        boardSurfaceRef={makeBoardRef()}
        scale={1}
        activeBoardId="board-1"
        activeInstructions={[textInstruction]}
      />,
    );

    await flushRAF();

    const options = mockPublishData.mock.calls[0][1];
    expect(options.topic).toBe("bounds");
    expect(options.reliable).toBe(false);
  });

  it("returns null (headless)", () => {
    mockEntries.mockReturnValue(
      new Map<string, { ref: HTMLDivElement }>().entries() as IterableIterator<
        [string, { ref: HTMLDivElement }]
      >,
    );

    const { container } = render(
      <BoundsReporter
        boardSurfaceRef={makeBoardRef()}
        scale={1}
        activeBoardId="board-1"
        activeInstructions={[]}
      />,
    );

    expect(container.innerHTML).toBe("");
  });
});
