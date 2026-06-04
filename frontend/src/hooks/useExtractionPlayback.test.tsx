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
import type { DrawDesignDiagramInstruction } from "../types/visuals";

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
  // Remove globals set via vi.stubGlobal (e.g. mockReducedMotion's matchMedia).
  // restoreAllMocks only neuters them to return undefined, which would make a
  // later prefersReducedMotion() read `.matches` of undefined and throw.
  vi.unstubAllGlobals();
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

// ── Doubt board: separate scratch board with slide + notebook restore ──

describe("useExtractionPlayback — doubt board snapshot/restore", () => {
  it("pause + beginDoubtBoard + applyDoubtBoardEvents, then play restores slide + notebook", async () => {
    // Lecture: render d1 on the slide and write one notebook step.
    const chapter = mkChapter([
      { type: "show_diagram", diagram_id: "diagram:test:d1" },
      { type: "write_step", id: "lec-1", text: "lecture step", indent: 0 },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);

    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);

    await act(async () => {
      void result.current.play();
    });
    await waitFor(() =>
      expect(result.current.slide.liveInstruction?.element_id).toBe(
        "diagram:test:d1",
      ),
    );
    expect(result.current.notebook.page.entries).toHaveLength(1);

    // Tap Ask Feynman: pause (snapshots slide + notebook) then clear the board.
    await act(async () => {
      result.current.pause();
    });
    await waitFor(() => expect(result.current.status).toBe("paused"));
    await act(async () => {
      result.current.beginDoubtBoard();
    });
    expect(result.current.notebook.page.entries).toHaveLength(0);

    // Doubt teaches on the scratch board: a live-generated diagram + a note.
    await act(async () => {
      result.current.addDoubtDiagram("doubt-gen-1", {
        title: "Doubt",
        description: "doubt diagram",
        render_data: { elements: [] },
        presentation_mode: "overview",
      } as never);
      result.current.applyDoubtBoardEvents([
        { type: "show_diagram", diagram_id: "doubt-gen-1" },
        { type: "write_step", id: "doubt-1", text: "doubt step", indent: 0 },
      ] as ManifestEvent[]);
    });
    expect(result.current.slide.liveInstruction?.element_id).toBe(
      "doubt-gen-1",
    );
    expect(result.current.notebook.page.entries).toHaveLength(1);
    expect(result.current.notebook.page.entries[0].id).toBe("doubt-1");

    // Resume: the lecture board (slide d1 + its notebook) is restored.
    await act(async () => {
      void result.current.play();
    });
    expect(result.current.slide.liveInstruction?.element_id).toBe(
      "diagram:test:d1",
    );
    expect(result.current.notebook.page.entries).toHaveLength(1);
    expect(result.current.notebook.page.entries[0].id).toBe("lec-1");
  });

  it("doubt template directive builds the canonical spec via buildTemplateSpec", async () => {
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
    await waitFor(() =>
      expect(result.current.slide.liveInstruction?.element_id).toBe(
        "diagram:test:d1",
      ),
    );
    await act(async () => {
      result.current.pause();
    });
    await waitFor(() => expect(result.current.status).toBe("paused"));
    await act(async () => {
      result.current.beginDoubtBoard();
    });

    // A Phase V-B `template` directive ships no spec — just a concept id.
    // addDoubtDiagram stores it; the doubt show_diagram builds the figure from
    // the registry, exactly like the lecture's instant-canonical path.
    await act(async () => {
      result.current.addDoubtDiagram(
        "doubt-tpl-0",
        null,
        "right-triangle-trig",
        {
          theta: 30,
        },
      );
      result.current.applyDoubtBoardEvents([
        { type: "show_diagram", diagram_id: "doubt-tpl-0" },
      ] as ManifestEvent[]);
    });
    await waitFor(() =>
      expect(
        (result.current.slide.liveInstruction as DrawDesignDiagramInstruction)
          ?.spec?.elements?.length,
      ).toBeGreaterThan(0),
    );
    expect(
      (result.current.slide.liveInstruction as DrawDesignDiagramInstruction)
        ?.title,
    ).toBe("Right-triangle trigonometry");
  });
});

// ── Staged element reveal (Workstream B) ───────────────────────

const REVEAL_SPEC = {
  title: "Reveal",
  width: 900,
  height: 650,
  presentation_mode: "build_up",
  elements: [
    { type: "svg_line", id: "ground", x1: 0, y1: 600, x2: 900, y2: 600 },
    { type: "svg_circle", id: "ball", cx: 450, cy: 300, r: 40 },
    { type: "svg_arrow", id: "v1", x1: 450, y1: 300, x2: 500, y2: 250 },
    { type: "svg_arrow", id: "v2", x1: 450, y1: 300, x2: 400, y2: 250 },
    { type: "svg_text", id: "lbl", x: 450, y: 120, text: "label" },
  ],
  dictionary: {
    ground: { role: "surface", semantic: "", position: "bottom" },
    ball: { role: "object", semantic: "", position: "center" },
    v1: { role: "velocity", semantic: "", position: "center" },
    v2: { role: "velocity", semantic: "", position: "center" },
    lbl: { role: "label", semantic: "", position: "top" },
  },
};

function mkRevealChapter(events: ManifestEvent[]): ChapterPayload {
  return {
    chapter_id: "chapter:reveal",
    title: "Reveal Chapter",
    chapter_index: 1,
    events,
    diagrams: {
      "diagram:reveal:rd": {
        url: null,
        description: "reveal diagram",
        spec: REVEAL_SPEC as never,
      },
    },
    topics: {},
  };
}

function mockReducedMotion(matches: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

describe("useExtractionPlayback — staged element reveal", () => {
  it("overview leaves revealedElementIds null (static parity, INV-7)", async () => {
    const chapter = mkRevealChapter([
      {
        type: "show_diagram",
        diagram_id: "diagram:reveal:rd",
        presentation_mode: "overview",
      },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.slide.status).toBe("ready"));
    expect(result.current.slide.revealedElementIds).toBeNull();
  });

  it("build_up starts with an empty revealed set; focus reveals the role-group", async () => {
    const chapter = mkRevealChapter([
      { type: "show_diagram", diagram_id: "diagram:reveal:rd" },
      {
        type: "focus",
        diagram_id: "diagram:reveal:rd",
        target_element_id: "v1",
      },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    // Focusing v1 (role "velocity") reveals its whole role-group: v1 + v2.
    await waitFor(() =>
      expect(result.current.slide.revealedElementIds?.has("v1")).toBe(true),
    );
    const revealed = result.current.slide.revealedElementIds;
    expect(revealed).not.toBeNull();
    expect(revealed?.has("v2")).toBe(true);
    expect(revealed?.has("ball")).toBe(false);
    expect(result.current.slide.focusedElementId).toBe("v1");
  });

  it("focus under overview does not mutate the revealed set", async () => {
    const chapter = mkRevealChapter([
      {
        type: "show_diagram",
        diagram_id: "diagram:reveal:rd",
        presentation_mode: "overview",
      },
      {
        type: "focus",
        diagram_id: "diagram:reveal:rd",
        target_element_id: "v1",
      },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() =>
      expect(result.current.slide.focusedElementId).toBe("v1"),
    );
    expect(result.current.slide.revealedElementIds).toBeNull();
  });

  it("clear_annotations keeps the revealed set (reveal is monotonic)", async () => {
    const chapter = mkRevealChapter([
      { type: "show_diagram", diagram_id: "diagram:reveal:rd" },
      {
        type: "focus",
        diagram_id: "diagram:reveal:rd",
        target_element_id: "ball",
      },
      { type: "clear_annotations", diagram_id: "diagram:reveal:rd" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() =>
      expect(result.current.slide.revealedElementIds?.has("ball")).toBe(true),
    );
    // Spotlight cleared, but the drawn element stays drawn.
    expect(result.current.slide.focusedElementId).toBeNull();
    expect(result.current.slide.revealedElementIds?.has("ball")).toBe(true);
  });

  it("reveal_step walks the groups; the last step reveals everything (INV-1)", async () => {
    const chapter = mkRevealChapter([
      { type: "show_diagram", diagram_id: "diagram:reveal:rd" },
      // 4 reveal groups: [ground],[ball],[v1,v2],[lbl].
      { type: "reveal_step" },
      { type: "reveal_step" },
      { type: "reveal_step" },
      { type: "reveal_step" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() =>
      expect(result.current.slide.revealedElementIds?.size).toBe(5),
    );
    const ids = result.current.slide.revealedElementIds!;
    for (const id of ["ground", "ball", "v1", "v2", "lbl"]) {
      expect(ids.has(id)).toBe(true);
    }
  });

  it("reduced motion disables staging (revealedElementIds null, INV-6)", async () => {
    mockReducedMotion(true);
    const chapter = mkRevealChapter([
      { type: "show_diagram", diagram_id: "diagram:reveal:rd" },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.slide.status).toBe("ready"));
    expect(result.current.slide.revealedElementIds).toBeNull();
  });
});

describe("useExtractionPlayback — instant-canonical templates (E)", () => {
  it("builds a template spec on show_diagram when the entry has no spec", async () => {
    const chapter: ChapterPayload = {
      chapter_id: "c",
      title: "t",
      chapter_index: 1,
      events: [
        { type: "show_diagram", diagram_id: "d:tmpl" },
        { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
      ],
      diagrams: {
        "d:tmpl": {
          url: null,
          description: "",
          spec: null,
          template_concept_id: "right-triangle-trig",
        },
      },
      topics: {},
    };
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.slide.status).toBe("ready"));
    expect(
      (result.current.slide.liveInstruction as DrawDesignDiagramInstruction)
        ?.spec?.elements?.length,
    ).toBeGreaterThan(0);
    expect(
      (result.current.slide.liveInstruction as DrawDesignDiagramInstruction)
        ?.title,
    ).toBe("Right-triangle trigonometry");
  });

  it("skips a diagram with neither a spec nor a known template id", async () => {
    const chapter: ChapterPayload = {
      chapter_id: "c",
      title: "t",
      chapter_index: 1,
      events: [
        { type: "show_diagram", diagram_id: "d:bad" },
        { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
      ],
      diagrams: {
        "d:bad": {
          url: null,
          description: "",
          spec: null,
          template_concept_id: "no-such-template",
        },
      },
      topics: {},
    };
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() => expect(result.current.audioProgress.current).toBe(1));
    expect(result.current.slide.liveInstruction).toBeUndefined();
  });
});

describe("useExtractionPlayback — narration-driven parameters (A5)", () => {
  it("set_parameter writes paramOverrides on the slide", async () => {
    const chapter = mkRevealChapter([
      {
        type: "show_diagram",
        diagram_id: "diagram:reveal:rd",
        presentation_mode: "overview",
      },
      { type: "set_parameter", name: "theta", value: 30 },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() =>
      expect(result.current.slide.paramOverrides?.theta).toBe(30),
    );
  });

  it("animate_parameter tweens and lands EXACTLY on `to` (INV-1)", async () => {
    // Real jsdom rAF + a short duration; we assert the terminal value only
    // (intermediate frames are timing-dependent). The final frame must write
    // exactly `to`, never an eased approximation.
    const chapter = mkRevealChapter([
      {
        type: "show_diagram",
        diagram_id: "diagram:reveal:rd",
        presentation_mode: "overview",
      },
      {
        type: "animate_parameter",
        name: "theta",
        from: 10,
        to: 50,
        duration_ms: 60,
      },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    await waitFor(() =>
      expect(result.current.slide.paramOverrides?.theta).toBe(50),
    );
  });

  it("reduced motion jumps straight to `to`, no tween (INV-6/INV-1)", async () => {
    mockReducedMotion(true);
    const chapter = mkRevealChapter([
      {
        type: "show_diagram",
        diagram_id: "diagram:reveal:rd",
        presentation_mode: "overview",
      },
      {
        type: "animate_parameter",
        name: "theta",
        from: 10,
        to: 50,
        duration_ms: 600,
      },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    // Synchronous jump — the target is set without waiting for any frame.
    await waitFor(() =>
      expect(result.current.slide.paramOverrides?.theta).toBe(50),
    );
  });

  it("seek snaps animate_parameter to its terminal value, not mid-tween", async () => {
    const chapter = mkRevealChapter([
      {
        type: "show_diagram",
        diagram_id: "diagram:reveal:rd",
        presentation_mode: "overview",
      },
      {
        type: "animate_parameter",
        name: "theta",
        from: 10,
        to: 50,
        duration_ms: 5000,
      },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    // Scrub past the animate event (index 2) — replay must land on theta=50.
    act(() => {
      result.current.seekToEvent(2);
    });
    expect(result.current.slide.paramOverrides?.theta).toBe(50);
  });

  it("set_parameter cancels an in-flight tween and wins", async () => {
    const chapter = mkRevealChapter([
      {
        type: "show_diagram",
        diagram_id: "diagram:reveal:rd",
        presentation_mode: "overview",
      },
      // A long tween that would crawl from 10 toward 50...
      {
        type: "animate_parameter",
        name: "theta",
        from: 10,
        to: 50,
        duration_ms: 5000,
      },
      // ...immediately overridden by an explicit set.
      { type: "set_parameter", name: "theta", value: 99 },
      { type: "audio", url: "/a/x.mp3", duration_ms: 100 },
    ]);
    const fake = makeFakeAudio();
    const { result } = renderHook(() => useExtractionPlayback({ chapter }));
    attach(result.current.setAudioElement, fake);
    await act(async () => {
      void result.current.play();
    });
    expect(result.current.slide.paramOverrides?.theta).toBe(99);
    // Let several real frames pass — a non-cancelled tween would overwrite 99
    // with values crawling up from 10. It stays 99 → the tween was cancelled.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60));
    });
    expect(result.current.slide.paramOverrides?.theta).toBe(99);
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

  // (Removed the obsolete `applyDoubtBeat` test — that per-beat annotation
  // API was retired in favour of `applyDoubtBoardEvents` (board events in the
  // ManifestEvent vocabulary), which is exercised by the doubt-board tests
  // above.)

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
