/**
 * Tests for the Phase 2 sentence-boundary queue in useVisualChannel.
 *
 * The queue defers `sync_mode === "after_next_sentence"` instructions until
 * the agent's TTS-aligned transcription emits a `.!?` character. Non-deferred
 * instructions pass straight through to the existing apply path.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// ── Mocks ─────────────────────────────────────────────────────

interface FakeRoom {
  listeners: Map<string, Set<(...args: unknown[]) => void>>;
  on(event: string, cb: (...args: unknown[]) => void): void;
  off(event: string, cb: (...args: unknown[]) => void): void;
  emit(event: string, ...args: unknown[]): void;
}

function makeFakeRoom(): FakeRoom {
  const listeners = new Map<string, Set<(...args: unknown[]) => void>>();
  return {
    listeners,
    on(event, cb) {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event)!.add(cb);
    },
    off(event, cb) {
      listeners.get(event)?.delete(cb);
    },
    emit(event, ...args) {
      for (const cb of listeners.get(event) ?? []) cb(...args);
    },
  };
}

let fakeRoom: FakeRoom;
let dataChannelHandler:
  | ((msg: { payload: Uint8Array; topic?: string }) => void)
  | null = null;

vi.mock("@livekit/components-react", () => ({
  useRoomContext: () => fakeRoom,
  useDataChannel: (
    _topic: string,
    handler: (msg: { payload: Uint8Array; topic?: string }) => void,
  ) => {
    dataChannelHandler = handler;
    return { isSubscribed: true };
  },
}));

vi.mock("livekit-client", () => ({
  RoomEvent: { TranscriptionReceived: "transcriptionReceived" },
}));

// useBoardStore is the state surface; spy on its mutator methods.
const mockSwitchBoard = vi.fn();
const mockAddInstruction = vi.fn();
const mockClearBoard = vi.fn();
const mockScrollTo = vi.fn();
const mockClearTransition = vi.fn();
const mockGetBoardInstructions = vi.fn(() => []);
const mockGetBoardMeta = vi.fn(() => null);

vi.mock("../engine/whiteboard/useBoardStore", () => ({
  useBoardStore: () => ({
    switchBoard: mockSwitchBoard,
    addInstruction: mockAddInstruction,
    clearBoard: mockClearBoard,
    scrollTo: mockScrollTo,
    activeInstructions: [],
    activeBoardId: "board-1",
    activeBoardMeta: null,
    pendingTransition: null,
    cameraState: { x: 0, y: 0, zoom: 1 },
    pendingSlide: {},
    clearTransition: mockClearTransition,
    getBoardInstructions: mockGetBoardInstructions,
    getBoardMeta: mockGetBoardMeta,
  }),
}));

// ── Import after mocks ────────────────────────────────────────

const { useVisualChannel } = await import("./useVisualChannel");

// ── Helpers ───────────────────────────────────────────────────

function encode(obj: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(obj));
}

function send(obj: unknown) {
  if (!dataChannelHandler) throw new Error("data-channel handler not bound");
  dataChannelHandler({ payload: encode(obj), topic: "visuals" });
}

function emitTranscription(
  segments: Array<{ id: string; text: string; final?: boolean }>,
  isLocal = false,
) {
  fakeRoom.emit(
    "transcriptionReceived",
    segments.map((s) => ({
      id: s.id,
      text: s.text,
      startTime: 0,
      endTime: 0,
      final: s.final ?? false,
      language: "",
    })),
    { isLocal },
  );
}

// ── Tests ─────────────────────────────────────────────────────

describe("useVisualChannel — Phase 2 sentence-boundary queue", () => {
  beforeEach(() => {
    fakeRoom = makeFakeRoom();
    dataChannelHandler = null;
    mockSwitchBoard.mockClear();
    mockAddInstruction.mockClear();
    mockClearBoard.mockClear();
    mockScrollTo.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("applies non-deferred instructions immediately", () => {
    renderHook(() => useVisualChannel());
    act(() => {
      send({
        type: "show_text",
        text: "hello",
        sync_mode: "on_playout",
      });
    });
    expect(mockAddInstruction).toHaveBeenCalledOnce();
  });

  it("defers after_next_sentence until a `.!?` is seen", () => {
    renderHook(() => useVisualChannel());
    act(() => {
      send({
        type: "highlight_pulse",
        target_element_id: "side_AB",
        sync_mode: "after_next_sentence",
      });
    });
    // Queued, not applied yet.
    expect(mockAddInstruction).not.toHaveBeenCalled();

    // Transcription updates without sentence-final punctuation: still queued.
    act(() => {
      emitTranscription([{ id: "seg-1", text: "Look at the" }]);
    });
    expect(mockAddInstruction).not.toHaveBeenCalled();

    // First `.` arrives: drain.
    act(() => {
      emitTranscription([{ id: "seg-1", text: "Look at the triangle." }]);
    });
    expect(mockAddInstruction).toHaveBeenCalledOnce();
  });

  it("drains all pending instructions on a single boundary", () => {
    renderHook(() => useVisualChannel());
    act(() => {
      send({
        type: "highlight_pulse",
        target_element_id: "side_AB",
        sync_mode: "after_next_sentence",
      });
      send({
        type: "pin_label",
        target_element_id: "side_BC",
        text: "wall",
        sync_mode: "after_next_sentence",
      });
    });
    expect(mockAddInstruction).not.toHaveBeenCalled();

    act(() => {
      emitTranscription([{ id: "seg-1", text: "First sentence." }]);
    });
    expect(mockAddInstruction).toHaveBeenCalledTimes(2);
  });

  it("falls back to apply after 2s if no boundary is seen", () => {
    renderHook(() => useVisualChannel());
    act(() => {
      send({
        type: "highlight_pulse",
        target_element_id: "side_AB",
        sync_mode: "after_next_sentence",
      });
    });
    expect(mockAddInstruction).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(mockAddInstruction).toHaveBeenCalledOnce();
  });

  it("ignores local-participant transcription (user STT)", () => {
    renderHook(() => useVisualChannel());
    act(() => {
      send({
        type: "highlight_pulse",
        target_element_id: "side_AB",
        sync_mode: "after_next_sentence",
      });
    });

    // User STT — local participant. Has a `.` but must not trigger drain.
    act(() => {
      emitTranscription(
        [{ id: "user-seg-1", text: "What is that." }],
        /* isLocal */ true,
      );
    });
    expect(mockAddInstruction).not.toHaveBeenCalled();

    // Agent transcription should still drain.
    act(() => {
      emitTranscription(
        [{ id: "agent-seg-1", text: "Look here." }],
        /* isLocal */ false,
      );
    });
    expect(mockAddInstruction).toHaveBeenCalledOnce();
  });

  it("only reacts to NEW `.!?` chars in an incremental segment", () => {
    renderHook(() => useVisualChannel());

    // Drain on the first `.` so the segment is "primed."
    act(() => {
      send({
        type: "highlight_pulse",
        target_element_id: "side_AB",
        sync_mode: "after_next_sentence",
      });
      emitTranscription([{ id: "seg-1", text: "Look at this." }]);
    });
    expect(mockAddInstruction).toHaveBeenCalledOnce();

    // Queue another instruction. A re-emission of the SAME text must not
    // re-trigger drain — the `.` is not new in the delta.
    mockAddInstruction.mockClear();
    act(() => {
      send({
        type: "highlight_pulse",
        target_element_id: "side_BC",
        sync_mode: "after_next_sentence",
      });
      // Same segment, same text — no new delta.
      emitTranscription([{ id: "seg-1", text: "Look at this." }]);
    });
    expect(mockAddInstruction).not.toHaveBeenCalled();

    // Now text grows past a new `.`: drain.
    act(() => {
      emitTranscription([{ id: "seg-1", text: "Look at this. And here." }]);
    });
    expect(mockAddInstruction).toHaveBeenCalledOnce();
  });
});
