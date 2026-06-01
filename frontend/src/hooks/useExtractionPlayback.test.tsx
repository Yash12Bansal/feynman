/**
 * Tests for the playback engine.
 *
 * Focus areas:
 * - autoStart fires play() once the chapter is provided
 * - play() walks events and fires onComplete at the end
 * - pause() halts mid-audio and on resume the same fragment re-plays
 * - restart() resets cursor + audio progress + slide
 * - topic_start / show_diagram events update derived state
 *
 * The <audio> element is mocked via a controllable fake; tests manually fire
 * its "ended" event to advance the loop deterministically.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
  useExtractionPlayback,
  type ChapterPayload,
  type ManifestEvent,
} from "./useExtractionPlayback";

// ── Fake audio element ─────────────────────────────────────────

interface FakeAudio {
  src: string;
  play: ReturnType<typeof vi.fn>;
  pause: ReturnType<typeof vi.fn>;
  addEventListener: (event: string, cb: () => void) => void;
  removeEventListener: (event: string, cb: () => void) => void;
  fireEnded: () => void;
  fireError: () => void;
}

function makeFakeAudio(): FakeAudio {
  const listeners: Record<string, Array<() => void>> = {};
  return {
    src: "",
    play: vi.fn(() => Promise.resolve()),
    pause: vi.fn(),
    addEventListener: (event: string, cb: () => void) => {
      (listeners[event] ??= []).push(cb);
    },
    removeEventListener: (event: string, cb: () => void) => {
      listeners[event] = (listeners[event] ?? []).filter((c) => c !== cb);
    },
    fireEnded: () => {
      // Copy so removals during iteration don't clobber dispatch.
      const subs = [...(listeners.ended ?? [])];
      for (const cb of subs) cb();
    },
    fireError: () => {
      const subs = [...(listeners.error ?? [])];
      for (const cb of subs) cb();
    },
  };
}

// ── Chapter fixture builders ────────────────────────────────────

function mkChapter(events: ManifestEvent[]): ChapterPayload {
  return {
    chapter_id: "chapter:test",
    title: "Test Chapter",
    chapter_index: 1,
    events,
    diagrams: {
      "diagram:test:d1": {
        url: null,
        description: "test diagram",
        spec: {
          title: "Title",
          description: "desc",
          render_data: { elements: [] },
          presentation_mode: "overview",
        } as never,
      },
    },
    topics: {
      "topic:t1": { name: "First Topic", section: "1.1" },
      "topic:t2": { name: "Second Topic", section: "1.2" },
    },
  };
}

// Bind a fake audio to the engine via the callback ref.
function attach(
  setAudioElement: (el: HTMLAudioElement | null) => void,
  fake: FakeAudio,
): void {
  setAudioElement(fake as unknown as HTMLAudioElement);
}

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests ──────────────────────────────────────────────────────

describe("useExtractionPlayback", () => {
  it("starts idle when no chapter is provided", () => {
    const { result } = renderHook(() =>
      useExtractionPlayback({ chapter: null }),
    );
    expect(result.current.status).toBe("idle");
    expect(result.current.cursor).toBe(0);
    expect(result.current.totalEvents).toBe(0);
  });

  it("walks an event sequence to completion and fires onComplete", async () => {
    const onComplete = vi.fn();
    const chapter = mkChapter([
      { type: "topic_start", topic_id: "topic:t1" },
      { type: "audio", url: "/a/1.mp3", duration_ms: 100 },
      { type: "audio", url: "/a/2.mp3", duration_ms: 100 },
    ]);

    const fake = makeFakeAudio();
    const { result } = renderHook(() =>
      useExtractionPlayback({ chapter, onComplete }),
    );
    attach(result.current.setAudioElement, fake);

    await act(async () => {
      void result.current.play();
    });

    await waitFor(() => expect(result.current.status).toBe("playing"));
    expect(fake.src).toBe("/a/1.mp3");

    await act(async () => {
      fake.fireEnded();
    });
    await waitFor(() => expect(fake.src).toBe("/a/2.mp3"));

    await act(async () => {
      fake.fireEnded();
    });

    await waitFor(() => expect(result.current.status).toBe("finished"));
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(result.current.audioProgress).toEqual({ current: 2, total: 2 });
    expect(result.current.currentTopicId).toBe("topic:t1");
  });

  it("autoStart kicks off playback once the chapter is provided", async () => {
    // autoStart fires in a useEffect — no opportunity to attach a fake audio
    // before the loop starts, so observe via the onEvent callback instead.
    // topic_start is a sync event and doesn't need the audio element.
    const onEvent = vi.fn();
    const chapter = mkChapter([{ type: "topic_start", topic_id: "topic:t1" }]);
    renderHook(() =>
      useExtractionPlayback({ chapter, autoStart: true, onEvent }),
    );
    await waitFor(() => expect(onEvent).toHaveBeenCalled());
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: "topic_start" }),
      0,
    );
  });

  it("pause halts mid-audio and resume re-plays the same fragment", async () => {
    const chapter = mkChapter([
      { type: "audio", url: "/a/first.mp3", duration_ms: 100 },
      { type: "audio", url: "/a/second.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);

    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.status).toBe("playing"));
    expect(fake.src).toBe("/a/first.mp3");
    // First audio incremented the counter.
    expect(result.current.audioProgress.current).toBe(1);

    await act(async () => {
      result.current.pause();
    });
    await waitFor(() => expect(result.current.status).toBe("paused"));
    expect(fake.pause).toHaveBeenCalled();
    // Mid-audio pause rewinds the counter so the resume re-counts the fragment.
    expect(result.current.audioProgress.current).toBe(0);

    // Resume — same fragment must replay before the loop advances.
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.status).toBe("playing"));
    expect(fake.src).toBe("/a/first.mp3");
    expect(result.current.audioProgress.current).toBe(1);

    await act(async () => {
      fake.fireEnded();
    });
    await waitFor(() => expect(fake.src).toBe("/a/second.mp3"));

    await act(async () => {
      fake.fireEnded();
    });
    await waitFor(() => expect(result.current.status).toBe("finished"));
  });

  it("topic_start updates currentTopicId + onTopicChange", async () => {
    const onTopicChange = vi.fn();
    const chapter = mkChapter([
      { type: "topic_start", topic_id: "topic:t1" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
      { type: "topic_start", topic_id: "topic:t2" },
      { type: "audio", url: "/a/y.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() =>
      useExtractionPlayback({ chapter, onTopicChange }),
    );
    attach(result.current.setAudioElement, fake);

    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.currentTopicId).toBe("topic:t1"));
    expect(result.current.currentTopicLabel).toBe("1.1  ·  First Topic");

    await act(async () => {
      fake.fireEnded();
    });
    await waitFor(() => expect(result.current.currentTopicId).toBe("topic:t2"));
    expect(result.current.currentTopicLabel).toBe("1.2  ·  Second Topic");

    expect(onTopicChange).toHaveBeenCalledWith({
      topicId: "topic:t1",
      topicName: "First Topic",
      section: "1.1",
    });
    expect(onTopicChange).toHaveBeenCalledWith({
      topicId: "topic:t2",
      topicName: "Second Topic",
      section: "1.2",
    });
  });

  it("show_diagram mounts a liveInstruction on the slide", async () => {
    const chapter = mkChapter([
      { type: "show_diagram", diagram_id: "diagram:test:d1" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);

    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.slide.status).toBe("ready"));
    expect(result.current.slide.liveInstruction?.element_id).toBe(
      "diagram:test:d1",
    );
  });

  it("restart resets cursor + audio progress + slide", async () => {
    const chapter = mkChapter([
      { type: "topic_start", topic_id: "topic:t1" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);

    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.audioProgress.current).toBe(1));

    await act(async () => {
      fake.fireEnded();
    });
    await waitFor(() => expect(result.current.status).toBe("finished"));

    await act(async () => {
      result.current.restart();
    });
    expect(result.current.status).toBe("idle");
    expect(result.current.cursor).toBe(0);
    expect(result.current.audioProgress.current).toBe(0);
    expect(result.current.currentTopicId).toBeNull();
    expect(result.current.slide.status).toBe("empty");
  });
});

// ── Phase 6: slide snapshot/restore on pause/resume ─────────────

describe("useExtractionPlayback — slide snapshot/restore (Phase 6)", () => {
  it("pause + applyDoubtBeat + play restores the pre-doubt slide", async () => {
    // Step 1: lecture renders a diagram via show_diagram.
    // Step 2: pause + applyDoubtBeat mutates the slide to a different diagram.
    // Step 3: play() should restore the snapshot taken at pause time.
    const chapter = mkChapter([
      { type: "show_diagram", diagram_id: "diagram:test:d1" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    // Add a second diagram so applyDoubtBeat has somewhere to switch to.
    chapter.diagrams["diagram:test:doubt"] = {
      url: null,
      description: "doubt diagram",
      spec: {
        title: "Doubt",
        description: "doubt",
        render_data: { elements: [] },
        presentation_mode: "overview",
      } as never,
    };

    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);

    // Run the lecture to the audio event. show_diagram has fired by now.
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() =>
      expect(result.current.slide.liveInstruction?.element_id).toBe(
        "diagram:test:d1",
      ),
    );

    // Pause — should snapshot the current slide (showing d1).
    await act(async () => {
      result.current.pause();
    });
    await waitFor(() => expect(result.current.status).toBe("paused"));

    // Mutate the slide via applyDoubtBeat (simulates the doubt overlay).
    await act(async () => {
      result.current.applyDoubtBeat(
        { target_diagram_id: "diagram:test:doubt", annotation_actions: [] },
        chapter,
      );
    });
    expect(result.current.slide.liveInstruction?.element_id).toBe(
      "diagram:test:doubt",
    );

    // Resume — the snapshot should restore d1 immediately.
    await act(async () => {
      void result.current.play();
    });
    expect(result.current.slide.liveInstruction?.element_id).toBe(
      "diagram:test:d1",
    );
  });
});

// ── FOCUS + POINT_AT wiring (P1/P2) — both entry points ─────────
//
// These prove the load-bearing claim: focus/point_at light up the SAME slide
// state in BOTH the precomputed lecture (applySyncEvent, via seekToEvent's
// replay) AND the live doubt path (applyDoubtBeat). Same render downstream.

describe("useExtractionPlayback — FOCUS + POINT_AT", () => {
  it("lecture: focus event sets focusedElementId/Role; point_at appends a pointer", () => {
    const chapter = mkChapter([
      {
        type: "focus",
        diagram_id: "d",
        target_element_id: "hyp",
        target_role: "hypotenuse",
      },
      {
        type: "point_at",
        diagram_id: "d",
        element_id: "vertex",
        from_side: "left",
      },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const { result } = renderHook(() =>
      useExtractionPlayback({ chapter, autoStart: false }),
    );
    act(() => {
      result.current.seekToEvent(2); // replays events 0..1
    });
    expect(result.current.slide.focusedElementId).toBe("hyp");
    expect(result.current.slide.focusedRole).toBe("hypotenuse");
    expect(result.current.slide.pointers?.length).toBe(1);
    expect(result.current.slide.pointers?.[0].elementId).toBe("vertex");
    expect(result.current.slide.pointers?.[0].fromSide).toBe("left");
  });

  it("lecture: clear_annotations clears focus + pointers", () => {
    const chapter = mkChapter([
      { type: "focus", diagram_id: "d", target_element_id: "hyp" },
      { type: "point_at", diagram_id: "d", element_id: "v", from_side: "top" },
      { type: "clear_annotations", diagram_id: "d" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const { result } = renderHook(() =>
      useExtractionPlayback({ chapter, autoStart: false }),
    );
    act(() => {
      result.current.seekToEvent(3); // replays events 0..2
    });
    expect(result.current.slide.focusedElementId).toBeNull();
    expect(result.current.slide.pointers?.length ?? 0).toBe(0);
  });

  it("doubt: applyDoubtBeat wires focus + point_at (same setters as the lecture)", () => {
    const chapter = mkChapter([]);
    const { result } = renderHook(() =>
      useExtractionPlayback({ chapter, autoStart: false }),
    );
    act(() => {
      result.current.applyDoubtBeat(
        {
          target_diagram_id: "diagram:test:d1",
          annotation_actions: [
            {
              action: "focus",
              target_element_id: "hyp",
              target_role: "hypotenuse",
            },
            { action: "point_at", element_id: "v", from_side: "right" },
          ],
        },
        chapter,
      );
    });
    expect(result.current.slide.focusedElementId).toBe("hyp");
    expect(result.current.slide.pointers?.length).toBe(1);
    expect(result.current.slide.pointers?.[0].fromSide).toBe("right");
  });

  it("show_diagram resets a prior topic's focus + pointers", () => {
    const chapter = mkChapter([
      { type: "focus", diagram_id: "d", target_element_id: "old" },
      { type: "show_diagram", diagram_id: "diagram:test:d1" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const { result } = renderHook(() =>
      useExtractionPlayback({ chapter, autoStart: false }),
    );
    act(() => {
      result.current.seekToEvent(2); // replays focus(0) then show_diagram(1)
    });
    expect(result.current.slide.focusedElementId).toBeNull();
    expect(result.current.slide.pointers?.length ?? 0).toBe(0);
  });
});
