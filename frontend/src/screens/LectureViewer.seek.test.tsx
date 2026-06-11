/**
 * Regression tests for the ← / → "seek ±10s" lecture hotkeys.
 *
 * The bug this pins: the arrow-key handler used to compute its seek target from
 * `currentMsRef.current` INSIDE the async IIFE — i.e. *after* `pause()` +
 * `await waitForIdle()` had unwound playback. By then the base had drifted
 * (collapsed toward the current event's start), so "→ +10s" landed back in the
 * same audio event (looked like nothing happened) and "← −10s" under-shot.
 *
 * Fix: snapshot the absolute target synchronously at the keypress, BEFORE
 * pause(). These tests mock `useExtractionPlayback` so we can drive the base
 * value and the post-pause drift directly, and prove the seek target is taken
 * at keypress time. The playback engine itself is covered by
 * useExtractionPlayback.test.tsx; here we isolate the viewer's key→seek wiring.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, waitFor } from "@testing-library/react";

vi.mock("../engine/whiteboard/split/SplitBoard", () => ({
  SplitBoard: () => <div data-testid="split-board">split-board</div>,
}));

// The in-lecture feedback wizard is orthogonal to seeking, and near the end of
// a lecture it auto-opens — pulling in <AuthProvider>, which this isolated
// render doesn't supply. Stub it so the seek tests stay focused and quiet.
vi.mock("../feedback/InLectureFeedback", () => ({
  InLectureFeedback: () => null,
}));

// LiveKit: room connected + agent present, mirroring LectureViewer.test.tsx so
// the viewer mounts without a real provider. None of it matters to the seek path.
vi.mock("@livekit/components-react", () => ({
  useRoomContext: () => ({
    localParticipant: { publishData: vi.fn(() => Promise.resolve()) },
  }),
  useConnectionState: () => "connected",
  useRemoteParticipants: () => [{ identity: "agent" }],
  useDataChannel: () => ({ isSubscribed: true }),
}));

// Controllable playback hook. `state` is mutated by tests to drive the base
// position / play status; the spies record what the handler did. `waitForIdle`
// parks until the test calls `flushIdle()`, so we can mutate `state` mid-flight
// (the exact window the old code read its base in) before the IIFE resumes.
const h = vi.hoisted(() => {
  const resolvers: Array<() => void> = [];
  return {
    state: { currentLectureMs: 0, status: "playing", chapterDurationMs: 600_000 },
    seekToTimeMs: vi.fn(),
    pause: vi.fn(),
    play: vi.fn(() => Promise.resolve()),
    waitForIdle: vi.fn(
      () => new Promise<void>((res) => resolvers.push(res)),
    ),
    flushIdle: () => resolvers.splice(0).forEach((r) => r()),
  };
});

vi.mock("../hooks/useExtractionPlayback", () => ({
  useExtractionPlayback: () => ({
    status: h.state.status,
    slide: null,
    notebook: null,
    setAudioElement: vi.fn(),
    cursor: 0,
    currentTopicId: null,
    currentSnapshot: null,
    currentNarrationText: "",
    chapterDurationMs: h.state.chapterDurationMs,
    currentLectureMs: h.state.currentLectureMs,
    topicJumps: [],
    pause: h.pause,
    play: h.play,
    seekToEvent: vi.fn(),
    seekToTimeMs: h.seekToTimeMs,
    waitForIdle: h.waitForIdle,
    beginDoubtBoard: vi.fn(),
    beginDoubtBoardFromCurrent: vi.fn(),
    addDoubtDiagram: vi.fn(),
    applyDoubtBoardEvents: vi.fn(),
    clearDoubtAnnotations: vi.fn(),
  }),
}));

const { LectureViewer } = await import("./LectureViewer");

const CHAPTER = {
  chapter_id: "chapter:test",
  title: "Test",
  chapter_index: 1,
  events: [],
  diagrams: {},
  topics: {},
};

beforeEach(() => {
  h.state.currentLectureMs = 0;
  h.state.status = "playing";
  h.state.chapterDurationMs = 600_000;
  h.seekToTimeMs.mockClear();
  h.pause.mockClear();
  h.play.mockClear();
  h.waitForIdle.mockClear();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(CHAPTER), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Mount, wait until the chapter has loaded (so playback hotkeys are armed). */
async function mountLoaded() {
  const utils = render(<LectureViewer chapterId="chapter:test" />);
  await waitFor(() => expect(utils.queryByTestId("split-board")).toBeTruthy());
  return utils;
}

function pressArrow(key: "ArrowLeft" | "ArrowRight") {
  act(() => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  });
}

/** Let the seek IIFE run to completion: unblock waitForIdle, flush microtasks. */
async function settleSeek() {
  await act(async () => {
    h.flushIdle();
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("LectureViewer seek hotkeys", () => {
  it("seeks from the position at the keypress — not a base that drifts after pause()", async () => {
    h.state.currentLectureMs = 60_000;
    const { rerender } = await mountLoaded();

    pressArrow("ArrowRight");
    // The seek pauses first (it was playing), then parks on waitForIdle.
    expect(h.pause).toHaveBeenCalledTimes(1);
    expect(h.seekToTimeMs).not.toHaveBeenCalled();

    // Simulate the base drifting AFTER pause() — this is precisely the window
    // the old code read its base in. The fix must ignore this new value.
    h.state.currentLectureMs = 0;
    act(() => rerender(<LectureViewer chapterId="chapter:test" />));

    await settleSeek();

    // 60_000 + 10_000 captured at keypress — NOT 0 + 10_000 from the drift.
    expect(h.seekToTimeMs).toHaveBeenCalledWith(70_000);
    expect(h.play).toHaveBeenCalledTimes(1); // resumed, since it was playing
  });

  it("← seeks −10s and clamps at 0", async () => {
    h.state.currentLectureMs = 5_000;
    await mountLoaded();

    pressArrow("ArrowLeft");
    await settleSeek();

    expect(h.seekToTimeMs).toHaveBeenCalledWith(0); // 5_000 − 10_000, clamped
  });

  it("→ clamps at the chapter duration", async () => {
    h.state.currentLectureMs = 595_000;
    h.state.chapterDurationMs = 600_000;
    await mountLoaded();

    pressArrow("ArrowRight");
    await settleSeek();

    expect(h.seekToTimeMs).toHaveBeenCalledWith(600_000); // not 605_000
  });

  it("while paused, ← seeks without pausing again or auto-resuming", async () => {
    h.state.currentLectureMs = 30_000;
    h.state.status = "paused";
    await mountLoaded();

    pressArrow("ArrowLeft");
    await settleSeek();

    expect(h.seekToTimeMs).toHaveBeenCalledWith(20_000);
    expect(h.pause).not.toHaveBeenCalled(); // wasn't playing → no pause
    expect(h.play).not.toHaveBeenCalled(); // wasn't playing → no resume
  });
});
