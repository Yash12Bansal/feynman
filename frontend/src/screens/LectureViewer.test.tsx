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
  // Room connected + agent present → roomReady, so Ask Feynman publishes
  // immediately (the lazy-connect deferral path isn't exercised here).
  useConnectionState: () => "connected",
  useRemoteParticipants: () => [{ identity: "agent" }],
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

  // ── Phase 5: delivery + satisfaction prompt ──────────────────────────

  it("satisfaction_prompt renders the 4-option overlay", async () => {
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
    const { findByTestId, queryByTestId } = render(
      <LectureViewer chapterId="chapter:test" />,
    );
    const button = await findByTestId("ask-feynman-button");
    fireEvent.click(button);

    act(() => {
      dataChannelHandler?.({
        payload: encode({
          type: "satisfaction_prompt",
          options: [
            { key: "crystal_clear", label: "Crystal clear", description: "ok" },
            { key: "counter_doubt", label: "Counter-doubt", description: "ok" },
            { key: "somewhat_cleared", label: "Somewhat", description: "ok" },
            { key: "start_over", label: "Start over", description: "ok" },
          ],
        }),
        topic: "doubt_signal",
      });
    });

    await waitFor(() =>
      expect(queryByTestId("satisfaction-prompt")).toBeTruthy(),
    );
  });

  it("clicking a satisfaction option publishes satisfaction_choice and flips to thinking", async () => {
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
    publishData.mockClear(); // clear the doubt_intent publish

    act(() => {
      dataChannelHandler?.({
        payload: encode({
          type: "satisfaction_prompt",
          options: [
            { key: "crystal_clear", label: "Crystal clear", description: "ok" },
          ],
        }),
        topic: "doubt_signal",
      });
    });
    const choice = await findByTestId("satisfaction-option-crystal_clear");
    fireEvent.click(choice);

    expect(publishData).toHaveBeenCalledTimes(1);
    const [bytes] = publishData.mock.calls[0] as [Uint8Array, unknown];
    const sent = JSON.parse(new TextDecoder().decode(bytes));
    expect(sent.type).toBe("satisfaction_choice");
    expect(sent.option).toBe("crystal_clear");
    expect(button.getAttribute("data-state")).toBe("thinking");
  });

  it("lecture_resume message flips button to idle and dismisses prompt", async () => {
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
    const { findByTestId, queryByTestId } = render(
      <LectureViewer chapterId="chapter:test" />,
    );
    const button = await findByTestId("ask-feynman-button");
    fireEvent.click(button);
    act(() => {
      dataChannelHandler?.({
        payload: encode({
          type: "satisfaction_prompt",
          options: [
            { key: "crystal_clear", label: "Crystal clear", description: "ok" },
          ],
        }),
        topic: "doubt_signal",
      });
    });
    await waitFor(() =>
      expect(queryByTestId("satisfaction-prompt")).toBeTruthy(),
    );

    act(() => {
      dataChannelHandler?.({
        payload: encode({ type: "lecture_resume" }),
        topic: "doubt_signal",
      });
    });
    await waitFor(() => expect(button.getAttribute("data-state")).toBe("idle"));
    expect(queryByTestId("satisfaction-prompt")).toBeNull();
  });

  it("doubt_capture_ready flips button to listening (counter-doubt path)", async () => {
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

    act(() => {
      dataChannelHandler?.({
        payload: encode({ type: "doubt_capture_ready" }),
        topic: "doubt_signal",
      });
    });
    await waitFor(() =>
      expect(button.getAttribute("data-state")).toBe("listening"),
    );
  });

  // ── Hotfix: stuck-state timeouts ────────────────────────────────

  it("listening times out to error after 12s of worker silence", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
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
      const { findByTestId, getByText } = render(
        <LectureViewer chapterId="chapter:test" />,
      );
      const button = await findByTestId("ask-feynman-button");
      fireEvent.click(button);
      expect(button.getAttribute("data-state")).toBe("listening");

      // Advance just past the 12s threshold; no inbound message → error.
      await act(async () => {
        vi.advanceTimersByTime(12_500);
      });
      const errorButton = await findByTestId("ask-feynman-button");
      expect(errorButton.getAttribute("data-state")).toBe("error");
      expect(getByText(/didn't hear anything/i)).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("doubt_captured within the window cancels the listening timeout", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
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
      const { findByTestId } = render(
        <LectureViewer chapterId="chapter:test" />,
      );
      const button = await findByTestId("ask-feynman-button");
      fireEvent.click(button);

      // Worker responds before the 12s timeout fires.
      await act(async () => {
        vi.advanceTimersByTime(2_000);
        dataChannelHandler?.({
          payload: encode({
            type: "doubt_captured",
            text: "why?",
            duration_ms: 1000,
          }),
          topic: "doubt_signal",
        });
      });
      expect(button.getAttribute("data-state")).toBe("thinking");

      // Push past the original 12s deadline; should NOT have flipped to error.
      await act(async () => {
        vi.advanceTimersByTime(15_000);
      });
      expect(button.getAttribute("data-state")).toBe("thinking");
    } finally {
      vi.useRealTimers();
    }
  });

  it("retry from error state resets the button to idle", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
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
      const { findByTestId } = render(
        <LectureViewer chapterId="chapter:test" />,
      );
      fireEvent.click(await findByTestId("ask-feynman-button"));
      await act(async () => {
        vi.advanceTimersByTime(12_500);
      });
      // Re-query — error state renders a <div>, not the original <button>.
      const errored = await findByTestId("ask-feynman-button");
      expect(errored.getAttribute("data-state")).toBe("error");

      fireEvent.click(await findByTestId("ask-feynman-retry"));
      const reset = await findByTestId("ask-feynman-button");
      expect(reset.getAttribute("data-state")).toBe("idle");
    } finally {
      vi.useRealTimers();
    }
  });
});
