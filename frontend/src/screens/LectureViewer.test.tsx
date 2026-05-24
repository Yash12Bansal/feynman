/**
 * Tests for the immersive LectureViewer.
 *
 * Focus: chapter-loading state machine + SplitBoard wiring + Ask Feynman
 * data-channel handshake. The playback engine itself is tested in
 * useExtractionPlayback.test.tsx — here we only verify the viewer mounts,
 * fetches, and routes the right children.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, waitFor } from "@testing-library/react";

vi.mock("../engine/whiteboard/split/SplitBoard", () => ({
  SplitBoard: ({ mode }: { mode?: string }) => (
    <div data-testid="split-board" data-mode={mode}>
      split-board
    </div>
  ),
}));

// LiveKit hooks: provide a fake room + capture the data-channel handler so
// tests can simulate worker → client doubt_captured messages.
const publishData = vi.fn(() => Promise.resolve());
let dataChannelHandler:
  | ((msg: { payload: Uint8Array; topic?: string }) => void)
  | null = null;

vi.mock("@livekit/components-react", () => ({
  useRoomContext: () => ({ localParticipant: { publishData } }),
  useDataChannel: (
    _topic: string,
    handler: (msg: { payload: Uint8Array; topic?: string }) => void,
  ) => {
    dataChannelHandler = handler;
    return { isSubscribed: true };
  },
}));

const { LectureViewer } = await import("./LectureViewer");

afterEach(() => {
  vi.restoreAllMocks();
  publishData.mockClear();
  dataChannelHandler = null;
});

function encode(obj: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(obj));
}

describe("LectureViewer", () => {
  it("shows a preparing status while the chapter is loading", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {}), // never resolves
    );
    const { getByText } = render(<LectureViewer chapterId="chapter:test" />);
    expect(getByText(/Preparing lecture/i)).toBeTruthy();
    fetchSpy.mockRestore();
  });

  it("surfaces a fetch error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("not found", { status: 404 }),
    );
    const { findByText } = render(<LectureViewer chapterId="chapter:test" />);
    await findByText(/Failed to load lecture/i);
  });

  it("renders SplitBoard in split mode once the chapter loads", async () => {
    const payload = {
      chapter_id: "chapter:test",
      title: "Test",
      chapter_index: 1,
      events: [],
      diagrams: {},
      topics: {},
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId } = render(<LectureViewer chapterId="chapter:test" />);
    const board = await waitFor(() => findByTestId("split-board"));
    expect(board.getAttribute("data-mode")).toBe("split");
  });

  it("tapping Ask Feynman publishes a doubt_intent and flips to listening", async () => {
    const payload = {
      chapter_id: "chapter:test",
      title: "Test",
      chapter_index: 1,
      events: [],
      diagrams: {},
      topics: {},
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId } = render(<LectureViewer chapterId="chapter:test" />);
    const button = await findByTestId("ask-feynman-button");
    fireEvent.click(button);

    expect(publishData).toHaveBeenCalledTimes(1);
    const [bytes, opts] = publishData.mock.calls[0] as [
      Uint8Array,
      { reliable: boolean; topic: string },
    ];
    const intent = JSON.parse(new TextDecoder().decode(bytes));
    expect(intent.type).toBe("doubt_intent");
    expect(intent.chapter_id).toBe("chapter:test");
    expect(opts.topic).toBe("doubt_signal");
    expect(opts.reliable).toBe(true);

    expect(button.getAttribute("data-state")).toBe("listening");
  });

  it("doubt_captured message flips the button to thinking", async () => {
    const payload = {
      chapter_id: "chapter:test",
      title: "Test",
      chapter_index: 1,
      events: [],
      diagrams: {},
      topics: {},
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId } = render(<LectureViewer chapterId="chapter:test" />);
    const button = await findByTestId("ask-feynman-button");
    fireEvent.click(button);
    expect(button.getAttribute("data-state")).toBe("listening");

    act(() => {
      dataChannelHandler?.({
        payload: encode({
          type: "doubt_captured",
          text: "why",
          duration_ms: 1200,
        }),
        topic: "doubt_signal",
      });
    });
    await waitFor(() =>
      expect(button.getAttribute("data-state")).toBe("thinking"),
    );
  });

  it("doubt_capture_failed message resets the button to idle", async () => {
    const payload = {
      chapter_id: "chapter:test",
      title: "Test",
      chapter_index: 1,
      events: [],
      diagrams: {},
      topics: {},
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId } = render(<LectureViewer chapterId="chapter:test" />);
    const button = await findByTestId("ask-feynman-button");
    fireEvent.click(button);
    expect(button.getAttribute("data-state")).toBe("listening");

    act(() => {
      dataChannelHandler?.({
        payload: encode({
          type: "doubt_capture_failed",
          reason: "no_transcript",
        }),
        topic: "doubt_signal",
      });
    });
    await waitFor(() => expect(button.getAttribute("data-state")).toBe("idle"));
  });
});
