/**
 * Playback engine for precomputed chapter manifests.
 *
 * Walks `chapter.events[]` sequentially:
 *   - `audio` → plays an MP3 via the consumer-supplied <audio> element, awaits
 *     "ended" (cancelable so pause() halts mid-fragment).
 *   - `pause` → cancelable setTimeout.
 *   - `topic_start` → updates currentTopicId / currentTopicLabel.
 *   - `show_diagram` → mounts a DrawDesignDiagramInstruction on SlideState.
 *   - `unfocus` / `clear_annotations` → clear the live annotation lists.
 *   - `trace` / `mark_point` / `write_margin` → live annotation lists.
 *   - `write_*` / `strikethrough` / `new_page` / `page_break` → notebook state.
 *
 * Pause semantics: pause() halts immediately, cancels the in-flight audio /
 * sleep, and (for audio specifically) rewinds the cursor by one event so
 * play() re-plays the interrupted fragment from start. This matches the
 * "lecture pauses for a doubt → resumes from where we left off" flow.
 *
 * The hook is headless. The consumer provides a <audio ref={...}> in the DOM
 * and reads `slide` / `notebook` / `currentTopicLabel` / `audioProgress` to
 * render their UI. No play/pause buttons are baked in.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AnswerEntry,
  EquationEntry,
  KeyPointEntry,
  NotebookEntry,
  NotebookState,
  SectionEntry,
  SlideState,
  StepEntry,
  TextEntry,
} from "../engine/whiteboard/split/types";
import type {
  DesignDiagramSpec,
  DrawDesignDiagramInstruction,
} from "../types/visuals";
import { deriveRevealPlan } from "../engine/whiteboard/split/defaultReveal";
import {
  resolveTarget,
  roleGroupForElement,
} from "../engine/whiteboard/split/resolveTarget";
import { buildTemplateSpec } from "../engine/whiteboard/diagram-templates/registry";

/**
 * True when the OS requests reduced motion. Staged reveal then collapses to
 * the full static diagram (INV-6). Guarded for SSR / test environments.
 */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

// ---------------------------------------------------------------------------
// Wire types — mirror preview_server.py's response shape
// ---------------------------------------------------------------------------

type AnnotationPosition = "above" | "below" | "left" | "right";
type CalloutDirection =
  | "up"
  | "down"
  | "up-right"
  | "up-left"
  | "down-right"
  | "down-left";
type BracketSide = "above" | "below" | "left" | "right";

export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}
export interface Placement {
  readonly page_index: number;
  readonly rect: Rect;
  readonly measured: boolean;
}

export type ManifestEvent =
  | { type: "audio"; url: string; duration_ms: number; text?: string }
  | { type: "pause"; duration_ms: number }
  | {
      type: "show_diagram";
      diagram_id: string;
      placement?: Placement | null;
      slide_element_bounds?: Record<string, Rect> | null;
      presentation_mode?: "build_up" | "overview" | null;
    }
  | { type: "topic_start"; topic_id: string }
  | {
      type: "write_section";
      id: string;
      title: string;
      placement?: Placement | null;
    }
  | {
      type: "write_equation";
      id: string;
      latex: string;
      align_group?: string | null;
      boxed?: boolean;
      placement?: Placement | null;
    }
  | {
      type: "write_step";
      id: string;
      text: string;
      indent?: number;
      placement?: Placement | null;
    }
  | {
      type: "write_text";
      id: string;
      text: string;
      placement?: Placement | null;
    }
  | {
      type: "write_key_point";
      id: string;
      text: string;
      placement?: Placement | null;
    }
  | {
      type: "write_answer";
      id: string;
      text: string;
      placement?: Placement | null;
    }
  | { type: "strikethrough"; target_id: string }
  | { type: "new_page"; carry_forward_ids?: string[] }
  | {
      type: "page_break";
      new_page_index: number;
      slide_action: "keep" | "swap" | "release";
      next_diagram_id?: string | null;
      notebook_carry_forward_ids?: string[];
      reason: "text_overflow" | "new_diagram" | "writer_marker";
    }
  | {
      type: "focus";
      diagram_id: string;
      target_element_id?: string | null;
      // Co-highlight: spotlight several elements at once (a relationship).
      target_element_ids?: string[] | null;
      target_role?: string | null;
      text?: string;
    }
  | { type: "unfocus"; diagram_id: string }
  | { type: "clear_annotations"; diagram_id: string }
  | {
      // Workstream B: advance the staged element reveal without moving the
      // spotlight. `step` jumps to (and fills up to) that group index; absent
      // → advance by one. No-op unless the diagram is staging (build_up).
      type: "reveal_step";
      diagram_id?: string;
      step?: number;
    }
  | {
      // Workstream A5: narration drives an interactive parameter's value (the
      // student doesn't touch a slider). Merged over the diagram's defaults;
      // reset by the next show_diagram.
      type: "set_parameter";
      diagram_id?: string;
      name: string;
      value: number;
    }
  | {
      // Workstream A5 (Phase 2): narration animates a parameter from `from` (or
      // its current value) to `to` over `duration_ms`. Reduced-motion or a seek
      // jumps straight to `to` (INV-6/INV-1). Reset by the next show_diagram.
      // For "watch the change" beats where the sweep IS the concept (INV-5).
      type: "animate_parameter";
      diagram_id?: string;
      name: string;
      to: number;
      from?: number;
      duration_ms?: number;
    }
  | {
      type: "trace";
      diagram_id: string;
      element_id: string;
      duration_ms?: number;
    }
  | {
      type: "mark_point";
      diagram_id: string;
      x: number;
      y: number;
      kind?: "dot" | "cross" | "star";
      label?: string;
    }
  | {
      type: "point_at";
      diagram_id: string;
      element_id: string;
      from_side?: "top" | "bottom" | "left" | "right";
    }
  | {
      type: "write_margin";
      diagram_id: string;
      anchor_element_id: string;
      side?: "top" | "bottom" | "left" | "right";
      text: string;
    }
  | {
      type: "pin";
      diagram_id: string;
      annotation_id: string;
      target_role: string;
      target_element_id?: string | null;
      text: string;
      position?: AnnotationPosition;
    }
  | {
      type: "callout";
      diagram_id: string;
      annotation_id: string;
      target_role: string;
      target_element_id?: string | null;
      text: string;
      direction?: CalloutDirection;
    }
  | {
      type: "bracket";
      diagram_id: string;
      annotation_id: string;
      target_role_a: string;
      target_role_b: string;
      target_element_id_a?: string | null;
      target_element_id_b?: string | null;
      label: string;
      side?: BracketSide;
    }
  | {
      type: "highlight";
      diagram_id: string;
      target_role: string;
      target_element_id?: string | null;
      duration_ms?: number;
      color_token?: string | null;
    }
  | {
      type: "pulse";
      diagram_id: string;
      target_role: string;
      target_element_id?: string | null;
      duration_ms?: number;
      color_token?: string | null;
    };

export interface DiagramEntry {
  url: string | null;
  description: string;
  spec: DesignDiagramSpec | null;
  /**
   * Workstream E: instant-canonical tier. When `spec` is null but a template
   * concept id is set, the spec is built on the client via `buildTemplateSpec`
   * — zero spec bytes on the wire, zero LLM, rendered in one frame.
   */
  template_concept_id?: string | null;
  template_params?: Record<string, number> | null;
}

export interface TopicEntry {
  name: string;
  section: string;
}

export interface TopicJumpEntry {
  readonly topicId: string;
  readonly eventIndex: number;
  readonly name: string;
  readonly section: string;
}

// Unified board state (feat/unify_boardstate). Authoritative slide +
// notebook layout at end-of-page, produced by the precompute composer.
// Consumers read this instead of querying the DOM.
export interface BoardElement {
  readonly element_id: string;
  readonly kind: "diagram" | "diagram_element" | "notebook_block";
  readonly rect: Rect;
  readonly parent_id?: string;
  readonly role?: string;
  readonly block_type?: string;
  readonly semantic?: string;
}

export interface BoardSnapshot {
  readonly page_index: number;
  readonly topic_id: string;
  readonly elements: readonly BoardElement[];
}

export interface ChapterPayload {
  chapter_id: string;
  title: string;
  chapter_index: number | null;
  events: ManifestEvent[];
  diagrams: Record<string, DiagramEntry>;
  topics: Record<string, TopicEntry>;
  // Parallel-indexed with the Chapter's `pages` array; empty for chapters
  // ingested before the unified-board-state feature shipped.
  board_snapshots?: readonly BoardSnapshot[];
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const PAGE_TURN_MS = 400;

export type PlaybackStatus = "idle" | "playing" | "paused" | "finished";

export interface UseExtractionPlaybackOptions {
  readonly chapter: ChapterPayload | null;
  readonly autoStart?: boolean;
  readonly onTopicChange?: (info: {
    topicId: string;
    topicName: string | null;
    section: string | null;
  }) => void;
  readonly onEvent?: (event: ManifestEvent, index: number) => void;
  readonly onComplete?: () => void;
}

export interface UseExtractionPlaybackResult {
  readonly status: PlaybackStatus;
  readonly cursor: number;
  readonly totalEvents: number;
  readonly currentTopicId: string | null;
  readonly currentTopicLabel: string;
  readonly currentTopicName: string | null;
  readonly audioProgress: { current: number; total: number };
  readonly slide: SlideState;
  readonly notebook: NotebookState;
  // Authoritative board state for the most-recently-closed page. Null while
  // the lecture is on page 0 (no page has closed yet) or when the chapter
  // was ingested before snapshots existed. Use this for "what was on the
  // board" lookups instead of measuring the DOM.
  readonly currentSnapshot: BoardSnapshot | null;
  // Text fragment currently being spoken by the TTS audio. Empty string when
  // no audio is playing or when the chapter lacks persisted narration_text.
  readonly currentNarrationText: string;
  // Player timing — total wall-clock ms across every timed event in the
  // chapter (audio + pause + page-turn sleeps) and ms elapsed so far from
  // chapter start. Drives the scrubber position and the displayed
  // timestamps. Both are 0 when the chapter hasn't loaded.
  readonly chapterDurationMs: number;
  readonly currentLectureMs: number;
  // Topic boundaries for the "Jump to topic" panel — one entry per
  // TopicStartEvent in order with the chapter event index to seek to.
  readonly topicJumps: readonly TopicJumpEntry[];
  // Time-based seek (scrubber): jump to the AudioEvent whose timeline
  // range covers the target ms. Caller calls play() afterwards if they
  // want playback to resume; seek itself doesn't change status.
  readonly seekToTimeMs: (ms: number) => void;
  readonly setAudioElement: (element: HTMLAudioElement | null) => void;
  readonly play: () => Promise<void>;
  readonly pause: () => void;
  readonly restart: () => void;
  readonly seekToEvent: (index: number) => void;
  // Resolves once any in-flight playback loop has finished unwinding.
  // After pause() flags abort + cancels, the loop only stops on the next
  // microtask — callers that want to mutate cursor / restart play() in the
  // same tick must await this first, or the loop's abort branch overwrites
  // their cursor change.
  readonly waitForIdle: () => Promise<void>;
  // Doubt board: begin clears to a blank scratch board (pause() already
  // snapshotted the lecture board); addDoubtDiagram registers a live-generated
  // spec; applyDoubtBoardEvents replays a beat's board events on it. play()
  // restores the lecture board.
  readonly beginDoubtBoard: () => void;
  readonly beginDoubtBoardFromCurrent: () => void;
  readonly addDoubtDiagram: (
    diagramId: string,
    spec: DesignDiagramSpec | null,
    templateConceptId?: string | null,
    templateParams?: Record<string, number> | null,
  ) => void;
  readonly applyDoubtBoardEvents: (events: readonly ManifestEvent[]) => void;
  readonly clearDoubtAnnotations: () => void;
}

interface Cancelable {
  readonly promise: Promise<void>;
  readonly cancel: () => void;
}

function makeCancelableAudio(audio: HTMLAudioElement, url: string): Cancelable {
  let canceled = false;
  let resolveOuter: () => void = () => {};
  const promise = new Promise<void>((resolve) => {
    resolveOuter = resolve;
    const cleanup = () => {
      audio.removeEventListener("ended", onEnd);
      audio.removeEventListener("error", onErr);
    };
    const onEnd = () => {
      cleanup();
      resolve();
    };
    const onErr = () => {
      cleanup();
      resolve();
    };
    audio.addEventListener("ended", onEnd);
    audio.addEventListener("error", onErr);
    audio.src = url;
    audio.play().catch(onErr);
  });
  const cancel = () => {
    if (canceled) return;
    canceled = true;
    audio.pause();
    resolveOuter();
  };
  return { promise, cancel };
}

function makeCancelableSleep(ms: number): Cancelable {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let resolveOuter: () => void = () => {};
  const promise = new Promise<void>((resolve) => {
    resolveOuter = resolve;
    timer = setTimeout(() => {
      timer = null;
      resolve();
    }, ms);
  });
  const cancel = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    resolveOuter();
  };
  return { promise, cancel };
}

function clampIndent(raw: number | undefined): 0 | 1 | 2 | 3 {
  if (raw == null) return 0;
  if (raw >= 3) return 3;
  if (raw <= 0) return 0;
  return raw as 1 | 2;
}

export function useExtractionPlayback(
  options: UseExtractionPlaybackOptions,
): UseExtractionPlaybackResult {
  const { chapter, autoStart, onTopicChange, onEvent, onComplete } = options;

  const [status, setStatus] = useState<PlaybackStatus>("idle");
  const [cursorState, setCursorState] = useState(0);
  // ms elapsed within the currently-playing event (audio OR sleep). For
  // audio events the value comes from the HTMLAudioElement.timeupdate event
  // (~4Hz). For sleep-bearing events (pause / new_page / page_break) a
  // requestAnimationFrame loop updates it from wall-clock — without that,
  // the scrubber would freeze for the entire pause duration.
  const [withinEventMs, setWithinEventMs] = useState(0);
  const [slide, setSlide] = useState<SlideState>({ status: "empty" });
  const [notebookEntries, setNotebookEntries] = useState<
    readonly NotebookEntry[]
  >([]);
  const [pageNum, setPageNum] = useState(1);
  const [pageTurning, setPageTurning] = useState(false);
  const [currentSnapshot, setCurrentSnapshot] = useState<BoardSnapshot | null>(
    null,
  );
  // Index of the next snapshot to consume on the NEXT page close. Snapshots
  // are emitted by the composer in the same order as pages — first close
  // consumes [0], second close [1], etc.
  const snapshotCursorRef = useRef(0);
  const [currentTopicId, setCurrentTopicId] = useState<string | null>(null);
  const [currentTopicLabel, setCurrentTopicLabel] = useState("");
  const [currentTopicName, setCurrentTopicName] = useState<string | null>(null);
  const [audioProgress, setAudioProgress] = useState({ current: 0, total: 0 });
  // Live transcript — the text fragment currently being spoken. Empty string
  // when no audio is playing (between fragments, or chapters without
  // narration_text persisted). The preview server attaches `.text` to each
  // AudioEvent at fetch time by re-chunking Chapter.narration_text.
  const [currentNarrationText, setCurrentNarrationText] = useState("");

  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  // Listener that surfaces audio.currentTime into withinEventMs. Created
  // once via useCallback so setAudioElement can attach/detach the same
  // function reference across remounts.
  const handleAudioTimeUpdate = useCallback(() => {
    const audio = audioElementRef.current;
    if (audio) setWithinEventMs(audio.currentTime * 1000);
  }, []);

  // Sleep-event wall-clock ticker. Active only while a non-audio timed
  // event (pause / new_page / page_break) is in flight. RAF gives smooth
  // scrubber motion without the cost of a JS-driven setInterval.
  const sleepStartedAtRef = useRef<number | null>(null);
  const sleepRafRef = useRef<number | null>(null);
  const startSleepTick = useCallback(() => {
    sleepStartedAtRef.current = performance.now();
    setWithinEventMs(0);
    const tick = () => {
      const start = sleepStartedAtRef.current;
      if (start === null) return;
      setWithinEventMs(performance.now() - start);
      sleepRafRef.current = requestAnimationFrame(tick);
    };
    sleepRafRef.current = requestAnimationFrame(tick);
  }, []);
  const stopSleepTick = useCallback(() => {
    sleepStartedAtRef.current = null;
    if (sleepRafRef.current !== null) {
      cancelAnimationFrame(sleepRafRef.current);
      sleepRafRef.current = null;
    }
  }, []);
  const setAudioElement = useCallback(
    (element: HTMLAudioElement | null) => {
      // Detach from the previous element (React strict mode + remounts).
      const prev = audioElementRef.current;
      if (prev) prev.removeEventListener("timeupdate", handleAudioTimeUpdate);
      audioElementRef.current = element;
      if (element)
        element.addEventListener("timeupdate", handleAudioTimeUpdate);
    },
    [handleAudioTimeUpdate],
  );
  const cursorRef = useRef(0);
  const audioIdxRef = useRef(0);
  const abortRef = useRef(false);
  const loopRef = useRef<Promise<void> | null>(null);
  const currentCancelableRef = useRef<Cancelable | null>(null);
  // Active `animate_parameter` rAF handle (Phase 2). Cancelled on
  // show_diagram/set_parameter/pause/seek/unmount so a tween never animates a
  // paused board, writes onto a stale diagram, or fights a newer interaction.
  const paramTweenRafRef = useRef<number | null>(null);
  // Phase 6: SlideState snapshot taken on pause() and restored on play()
  // so a doubt's diagram + annotations don't linger after the lecture
  // resumes. The snapshot captures whatever the lecture was showing right
  // before the student tapped Ask Feynman.
  const slideSnapshotRef = useRef<SlideState | null>(null);
  // Companion to slideSnapshotRef: the lecture notebook page captured at the
  // same instant, so play() restores the full board (slide + notebook) after a
  // doubt is taught on a cleared scratch board.
  const notebookSnapshotRef = useRef<{
    entries: readonly NotebookEntry[];
    pageNum: number;
  } | null>(null);
  // Diagrams generated live during a doubt (absent from chapter.diagrams),
  // keyed by the worker's deterministic doubt-gen id; merged into the chapter
  // view so show_diagram resolves them. Wiped at the start of each doubt.
  const doubtDiagramsRef = useRef<Record<string, DiagramEntry>>({});

  // Stable refs for callbacks so the loop closure doesn't need to be rebuilt.
  const onEventRef = useRef(onEvent);
  const onTopicChangeRef = useRef(onTopicChange);
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);
  useEffect(() => {
    onTopicChangeRef.current = onTopicChange;
  }, [onTopicChange]);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const totalEvents = chapter?.events.length ?? 0;
  const totalAudios = useMemo(
    () =>
      chapter ? chapter.events.filter((e) => e.type === "audio").length : 0,
    [chapter],
  );

  // Per-event duration table — covers every event that consumes wall-clock
  // time in the playback loop: audio fragments, explicit pauses, and the
  // half-PAGE_TURN_MS sleeps that drive page-turn animations. Sync-only
  // events (slide_*, notebook_*, topic_start) contribute 0.
  const eventDurationsMs = useMemo<readonly number[]>(() => {
    if (!chapter) return [];
    return chapter.events.map((ev) => {
      if (ev.type === "audio") return ev.duration_ms || 0;
      if (ev.type === "pause") return ev.duration_ms || 0;
      if (ev.type === "new_page" || ev.type === "page_break")
        return PAGE_TURN_MS / 2;
      return 0;
    });
  }, [chapter]);

  // Cumulative offsets in ms — index `i` holds the total ms BEFORE event `i`
  // starts. Length = events.length + 1; index events.length is the chapter's
  // full wall-clock duration. The scrubber maps (eventIndex ↔ ms) via this.
  const eventOffsetsMs = useMemo<readonly number[]>(() => {
    const out: number[] = [0];
    let cum = 0;
    for (const d of eventDurationsMs) {
      cum += d;
      out.push(cum);
    }
    return out;
  }, [eventDurationsMs]);

  const chapterDurationMs = eventOffsetsMs[eventOffsetsMs.length - 1] ?? 0;
  // Live elapsed time across the whole lecture: start of the current event +
  // ms elapsed within it. cursorState advances AFTER each event completes,
  // so during playback it points at the in-flight event. withinEventMs comes
  // from the audio timeupdate handler OR the sleep RAF ticker depending on
  // event type.
  const currentLectureMs = Math.min(
    (eventOffsetsMs[cursorState] ?? 0) + withinEventMs,
    chapterDurationMs,
  );

  // Topic-jump index — one entry per TopicStartEvent in the chapter, in
  // playback order. The scrubber's "Jump to topic" panel iterates this.
  const topicJumps = useMemo<readonly TopicJumpEntry[]>(() => {
    if (!chapter) return [];
    const out: TopicJumpEntry[] = [];
    chapter.events.forEach((ev, idx) => {
      if (ev.type === "topic_start") {
        const meta = chapter.topics[ev.topic_id];
        out.push({
          topicId: ev.topic_id,
          eventIndex: idx,
          name: meta?.name ?? ev.topic_id,
          section: meta?.section ?? "",
        });
      }
    });
    return out;
  }, [chapter]);

  // Reset everything when the chapter changes.
  useEffect(() => {
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    cursorRef.current = 0;
    audioIdxRef.current = 0;
    slideSnapshotRef.current = null;
    setCursorState(0);
    setStatus("idle");
    setSlide({ status: "empty" });
    setNotebookEntries([]);
    setPageNum(1);
    setPageTurning(false);
    setCurrentSnapshot(null);
    snapshotCursorRef.current = 0;
    setCurrentNarrationText("");
    setWithinEventMs(0);
    stopSleepTick();
    setCurrentTopicId(null);
    setCurrentTopicLabel("");
    setCurrentTopicName(null);
    setAudioProgress({ current: 0, total: totalAudios });
  }, [chapter, totalAudios, stopSleepTick]);

  const appendNotebookEntry = useCallback((entry: NotebookEntry) => {
    setNotebookEntries((prev) => {
      const idx = prev.findIndex((e) => e.id === entry.id);
      if (idx === -1) return [...prev, entry];
      const next = [...prev];
      next[idx] = entry;
      return next;
    });
  }, []);

  const resetSlideAnnotations = useCallback(() => {
    setSlide((prev) => ({
      ...prev,
      traces: [],
      markPoints: [],
      marginNotes: [],
      pointers: [],
      focusedElementId: null,
      focusedRole: null,
      focusedElementIds: null,
    }));
  }, []);

  // FOCUS — spotlight one element in place (glow+lift). Replaces any prior
  // focus (single focused element at a time); null clears it.
  const setFocus = useCallback(
    (
      elementId: string | null,
      role: string | null,
      elementIds?: readonly string[] | null,
    ) => {
      setSlide((prev) => ({
        ...prev,
        focusedElementId: elementId,
        focusedRole: role,
        focusedElementIds:
          elementIds && elementIds.length > 0 ? new Set(elementIds) : null,
      }));
    },
    [],
  );

  const appendPointer = useCallback(
    (elementId: string, fromSide: "top" | "bottom" | "left" | "right") => {
      setSlide((prev) => {
        const key = prev.nextAnnotationKey ?? 0;
        return {
          ...prev,
          nextAnnotationKey: key + 1,
          pointers: [...(prev.pointers ?? []), { key, elementId, fromSide }],
        };
      });
    },
    [],
  );

  const appendTrace = useCallback((elementId: string, durationMs: number) => {
    setSlide((prev) => {
      const key = prev.nextAnnotationKey ?? 0;
      return {
        ...prev,
        nextAnnotationKey: key + 1,
        traces: [...(prev.traces ?? []), { key, elementId, durationMs }],
      };
    });
  }, []);

  const appendMarkPoint = useCallback(
    (x: number, y: number, kind: "dot" | "cross" | "star", label: string) => {
      setSlide((prev) => {
        const key = prev.nextAnnotationKey ?? 0;
        return {
          ...prev,
          nextAnnotationKey: key + 1,
          markPoints: [...(prev.markPoints ?? []), { key, x, y, kind, label }],
        };
      });
    },
    [],
  );

  const appendMarginNote = useCallback(
    (
      anchorElementId: string,
      side: "top" | "bottom" | "left" | "right",
      text: string,
    ) => {
      setSlide((prev) => {
        const key = prev.nextAnnotationKey ?? 0;
        return {
          ...prev,
          nextAnnotationKey: key + 1,
          marginNotes: [
            ...(prev.marginNotes ?? []),
            { key, anchorElementId, side, text },
          ],
        };
      });
    },
    [],
  );

  // ── animate_parameter: narration-driven parameter tween (Phase 2) ────────
  // Lives outside applySyncEvent so pause/seek can stop it. Writes the same
  // `paramOverrides` channel as the synchronous `set_parameter`, so it composes
  // cleanly with sliders and reveal.
  const cancelParamTween = useCallback(() => {
    if (paramTweenRafRef.current != null) {
      cancelAnimationFrame(paramTweenRafRef.current);
      paramTweenRafRef.current = null;
    }
  }, []);

  const startParamTween = useCallback(
    (name: string, to: number, durationMs: number, from?: number): void => {
      cancelParamTween();
      // INV-6 (reduced motion) and degenerate durations jump straight to the
      // target — no intermediate frames, no rAF scheduled.
      if (durationMs <= 0 || prefersReducedMotion()) {
        setSlide((prev) =>
          prev.status === "ready"
            ? {
                ...prev,
                paramOverrides: { ...prev.paramOverrides, [name]: to },
              }
            : prev,
        );
        return;
      }
      const t0 = performance.now();
      let start = from ?? null;
      const tick = (now: number): void => {
        const p = Math.min(1, (now - t0) / durationMs);
        // easeInOutQuad — deliberate accel/decel, not a mechanical ramp.
        const eased = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2;
        setSlide((prev) => {
          if (prev.status !== "ready") return prev; // diagram gone → no-op
          // Resolve the start value once, from live state, when not provided.
          if (start == null) start = (prev.paramOverrides ?? {})[name] ?? to;
          // INV-1: the final frame writes EXACTLY `to`, not an eased approx.
          const value = p >= 1 ? to : start + (to - start) * eased;
          return {
            ...prev,
            paramOverrides: { ...prev.paramOverrides, [name]: value },
          };
        });
        paramTweenRafRef.current = p < 1 ? requestAnimationFrame(tick) : null;
      };
      paramTweenRafRef.current = requestAnimationFrame(tick);
    },
    [cancelParamTween],
  );

  // Cancel any running tween on unmount — no setState after the hook is gone.
  useEffect(() => cancelParamTween, [cancelParamTween]);

  // Synchronous events apply state immediately and never block the loop.
  const applySyncEvent = useCallback(
    (ev: ManifestEvent, c: ChapterPayload, immediate = false): void => {
      switch (ev.type) {
        case "topic_start": {
          const t = c.topics[ev.topic_id];
          setCurrentTopicId(ev.topic_id);
          if (t) {
            setCurrentTopicLabel(`${t.section}  ·  ${t.name}`);
            setCurrentTopicName(t.name);
            onTopicChangeRef.current?.({
              topicId: ev.topic_id,
              topicName: t.name,
              section: t.section,
            });
          } else {
            setCurrentTopicLabel(ev.topic_id);
            setCurrentTopicName(null);
            onTopicChangeRef.current?.({
              topicId: ev.topic_id,
              topicName: null,
              section: null,
            });
          }
          setSlide({ status: "loading", pendingTitle: t?.name });
          return;
        }
        case "show_diagram": {
          // A new diagram abandons any in-flight parameter tween.
          cancelParamTween();
          const d = c.diagrams[ev.diagram_id];
          if (!d) return;
          // Resolve the spec: a precomputed/generated spec, else the
          // instant-canonical template tier (Workstream E).
          const spec =
            d.spec ??
            (d.template_concept_id
              ? buildTemplateSpec(
                  d.template_concept_id,
                  d.template_params ?? undefined,
                )
              : null);
          if (!spec) return;
          const instr: DrawDesignDiagramInstruction = {
            type: "draw_design_diagram",
            element_id: ev.diagram_id,
            title: spec.title,
            description: d.description || spec.description,
            spec,
          };
          // Staged reveal (Workstream B): active only when build_up AND a
          // reveal plan exists AND motion is allowed. Otherwise
          // revealedElementIds = null → every element renders immediately
          // (static parity = INV-7; reduced-motion = INV-6).
          const mode =
            ev.presentation_mode ?? spec.presentation_mode ?? "overview";
          const plan =
            mode === "build_up" && !prefersReducedMotion()
              ? deriveRevealPlan(spec)
              : null;
          setSlide({
            status: "ready",
            liveInstruction: instr,
            presentationMode: mode,
            traces: [],
            markPoints: [],
            marginNotes: [],
            pointers: [],
            focusedElementId: null,
            focusedRole: null,
            focusedElementIds: null,
            nextAnnotationKey: 0,
            revealedElementIds: plan ? new Set<string>() : null,
            revealOrder: plan ? plan.order : null,
            revealCursor: plan ? -1 : undefined,
            paramOverrides: {},
          });
          return;
        }
        case "write_section": {
          const entry: SectionEntry = {
            id: ev.id,
            kind: "section_header",
            title: ev.title,
          };
          appendNotebookEntry(entry);
          return;
        }
        case "write_equation": {
          const entry: EquationEntry = {
            id: ev.id,
            kind: "equation",
            latex: ev.latex,
            alignGroup: ev.align_group ?? undefined,
            boxed: ev.boxed ?? false,
          };
          appendNotebookEntry(entry);
          return;
        }
        case "write_step": {
          const entry: StepEntry = {
            id: ev.id,
            kind: "step",
            text: ev.text,
            indent: clampIndent(ev.indent),
          };
          appendNotebookEntry(entry);
          return;
        }
        case "write_text": {
          const entry: TextEntry = {
            id: ev.id,
            kind: "text",
            text: ev.text,
          };
          appendNotebookEntry(entry);
          return;
        }
        case "write_key_point": {
          const entry: KeyPointEntry = {
            id: ev.id,
            kind: "key_point",
            text: ev.text,
          };
          appendNotebookEntry(entry);
          return;
        }
        case "write_answer": {
          const entry: AnswerEntry = {
            id: ev.id,
            kind: "answer",
            text: ev.text,
          };
          appendNotebookEntry(entry);
          return;
        }
        case "strikethrough": {
          setNotebookEntries((prev) =>
            prev.map((e) =>
              e.id === ev.target_id
                ? ({ ...e, struck: true } as NotebookEntry)
                : e,
            ),
          );
          return;
        }
        case "focus": {
          // Co-highlight: target_element_ids carries the full set; fall back to
          // the single target_element_id. The first id mirrors into the single
          // field for consumers that still read it.
          const focusIds =
            ev.target_element_ids && ev.target_element_ids.length > 0
              ? ev.target_element_ids
              : ev.target_element_id
                ? [ev.target_element_id]
                : [];
          setFocus(focusIds[0] ?? null, ev.target_role ?? null, focusIds);
          // Under build_up, focusing element(s) also reveals their role-group(s)
          // (monotonic union). overview / non-staging diagrams are untouched
          // — the guard returns the same state reference (no extra render).
          {
            const dict = c.diagrams[ev.diagram_id]?.spec?.dictionary;
            setSlide((prev) => {
              if (
                prev.revealedElementIds == null ||
                prev.presentationMode !== "build_up"
              ) {
                return prev;
              }
              const groupIds = new Set<string>();
              for (const id of focusIds) {
                for (const g of roleGroupForElement(id, dict)) groupIds.add(g);
              }
              if (focusIds.length === 0 && ev.target_role) {
                for (const g of resolveTarget(
                  { kind: "role", value: ev.target_role },
                  dict,
                  undefined,
                ))
                  groupIds.add(g);
              }
              if (groupIds.size === 0) return prev;
              const merged = new Set(prev.revealedElementIds);
              for (const id of groupIds) merged.add(id);
              return { ...prev, revealedElementIds: merged };
            });
          }
          return;
        }
        case "point_at": {
          appendPointer(ev.element_id, ev.from_side ?? "left");
          return;
        }
        case "unfocus":
        case "clear_annotations": {
          // Clears the spotlight + annotation overlays. Does NOT clear
          // revealedElementIds — reveal is monotonic; a teacher doesn't
          // un-draw. Only show_diagram resets the revealed set.
          resetSlideAnnotations();
          return;
        }
        case "reveal_step": {
          setSlide((prev) => {
            const order = prev.revealOrder;
            if (
              prev.revealedElementIds == null ||
              !order ||
              order.length === 0
            ) {
              return prev; // not staging → no-op
            }
            const target =
              ev.step != null ? ev.step : (prev.revealCursor ?? -1) + 1;
            const cursor = Math.min(Math.max(target, 0), order.length - 1);
            const merged = new Set(prev.revealedElementIds);
            // Reveal every group up to and including `cursor` (idempotent) so
            // an explicit step jump fills in any skipped groups.
            for (let i = 0; i <= cursor; i++)
              for (const id of order[i]) merged.add(id);
            return {
              ...prev,
              revealedElementIds: merged,
              revealCursor: cursor,
            };
          });
          return;
        }
        case "set_parameter": {
          // An explicit set wins over an in-flight tween of the same surface.
          cancelParamTween();
          setSlide((prev) => ({
            ...prev,
            paramOverrides: { ...prev.paramOverrides, [ev.name]: ev.value },
          }));
          return;
        }
        case "animate_parameter": {
          // Seek-replay (`immediate`) lands on the terminal value so the scrub
          // shows the post-animation state; live playback tweens. Reduced-motion
          // is handled inside startParamTween.
          if (immediate) {
            setSlide((prev) =>
              prev.status === "ready"
                ? {
                    ...prev,
                    paramOverrides: {
                      ...prev.paramOverrides,
                      [ev.name]: ev.to,
                    },
                  }
                : prev,
            );
          } else {
            startParamTween(ev.name, ev.to, ev.duration_ms ?? 700, ev.from);
          }
          return;
        }
        case "trace": {
          appendTrace(ev.element_id, ev.duration_ms ?? 1500);
          return;
        }
        case "mark_point": {
          appendMarkPoint(ev.x, ev.y, ev.kind ?? "dot", ev.label ?? "");
          return;
        }
        case "write_margin": {
          appendMarginNote(ev.anchor_element_id, ev.side ?? "right", ev.text);
          return;
        }
        // Legacy back-compat — drop silently.
        case "pin":
        case "callout":
        case "bracket":
        case "highlight":
        case "pulse":
          return;
        // Async events are handled outside this function.
        case "audio":
        case "pause":
        case "new_page":
        case "page_break":
          return;
      }
    },
    [
      appendNotebookEntry,
      appendMarkPoint,
      appendMarginNote,
      appendTrace,
      appendPointer,
      setFocus,
      resetSlideAnnotations,
      startParamTween,
      cancelParamTween,
    ],
  );

  // Snapshots are emitted by the composer in 1:1 order with closed pages.
  // Each page-close consumes the next one and exposes it as currentSnapshot.
  const advanceSnapshot = useCallback((c: ChapterPayload) => {
    const snaps = c.board_snapshots;
    if (!snaps || snaps.length === 0) return;
    const idx = snapshotCursorRef.current;
    if (idx >= snaps.length) return;
    snapshotCursorRef.current = idx + 1;
    setCurrentSnapshot(snaps[idx]);
  }, []);

  // Runs an event. Returns true if the event completed; false if the loop was
  // aborted mid-event (pause was called).
  const runEvent = useCallback(
    async (ev: ManifestEvent, c: ChapterPayload): Promise<boolean> => {
      switch (ev.type) {
        case "audio": {
          const audio = audioElementRef.current;
          if (!audio) return true;
          audioIdxRef.current += 1;
          setAudioProgress({
            current: audioIdxRef.current,
            total: totalAudios,
          });
          // New audio starts at t=0 within the fragment. Reset the live
          // within-event counter explicitly — the timeupdate event will
          // begin advancing it once playback resumes.
          stopSleepTick();
          setWithinEventMs(0);
          // Live transcript: surface the text fragment being spoken. The
          // preview server attaches `.text` per AudioEvent at fetch time
          // by re-chunking Chapter.narration_text. Empty string for
          // chapters where narration_text isn't persisted (back-compat).
          setCurrentNarrationText(ev.text ?? "");
          const c2 = makeCancelableAudio(audio, ev.url);
          currentCancelableRef.current = c2;
          await c2.promise;
          currentCancelableRef.current = null;
          return !abortRef.current;
        }
        case "pause": {
          startSleepTick();
          const c2 = makeCancelableSleep(ev.duration_ms);
          currentCancelableRef.current = c2;
          try {
            await c2.promise;
          } finally {
            stopSleepTick();
            currentCancelableRef.current = null;
          }
          return !abortRef.current;
        }
        case "new_page": {
          setPageTurning(true);
          startSleepTick();
          const c2 = makeCancelableSleep(PAGE_TURN_MS / 2);
          currentCancelableRef.current = c2;
          try {
            await c2.promise;
          } finally {
            stopSleepTick();
            currentCancelableRef.current = null;
          }
          if (abortRef.current) {
            setPageTurning(false);
            return false;
          }
          setNotebookEntries([]);
          setPageNum((n) => n + 1);
          advanceSnapshot(c);
          setPageTurning(false);
          return true;
        }
        case "page_break": {
          setPageTurning(true);
          startSleepTick();
          const c2 = makeCancelableSleep(PAGE_TURN_MS / 2);
          currentCancelableRef.current = c2;
          try {
            await c2.promise;
          } finally {
            stopSleepTick();
            currentCancelableRef.current = null;
          }
          if (abortRef.current) {
            setPageTurning(false);
            return false;
          }
          setNotebookEntries([]);
          setPageNum((n) => n + 1);
          if (ev.slide_action === "swap") {
            setSlide({ status: "loading" });
          } else if (ev.slide_action === "release") {
            setSlide({ status: "empty", annotations: [] });
          }
          advanceSnapshot(c);
          setPageTurning(false);
          return true;
        }
        default:
          applySyncEvent(ev, c);
          return true;
      }
    },
    [
      applySyncEvent,
      advanceSnapshot,
      totalAudios,
      startSleepTick,
      stopSleepTick,
    ],
  );

  const play = useCallback(async (): Promise<void> => {
    if (!chapter) return;
    if (loopRef.current) return; // already playing
    if (status === "finished" || cursorRef.current >= chapter.events.length) {
      return;
    }
    abortRef.current = false;
    // Phase 6: restore the pre-pause board (slide + notebook) before the loop
    // resumes, so the doubt's scratch work doesn't linger as the audio
    // fragment re-plays.
    if (slideSnapshotRef.current !== null) {
      setSlide(slideSnapshotRef.current);
      slideSnapshotRef.current = null;
    }
    if (notebookSnapshotRef.current !== null) {
      setNotebookEntries(notebookSnapshotRef.current.entries);
      setPageNum(notebookSnapshotRef.current.pageNum);
      notebookSnapshotRef.current = null;
    }
    doubtDiagramsRef.current = {};
    setStatus("playing");
    const loop = (async () => {
      while (cursorRef.current < chapter.events.length && !abortRef.current) {
        const i = cursorRef.current;
        const ev = chapter.events[i];
        onEventRef.current?.(ev, i);
        const completed = await runEvent(ev, chapter);
        if (!completed) {
          // Aborted mid-event. For audio, rewind one step so resume re-plays.
          if (ev.type === "audio") {
            audioIdxRef.current = Math.max(0, audioIdxRef.current - 1);
            setAudioProgress({
              current: audioIdxRef.current,
              total: totalAudios,
            });
          } else {
            cursorRef.current = i + 1;
            setCursorState(cursorRef.current);
          }
          return;
        }
        cursorRef.current = i + 1;
        setCursorState(cursorRef.current);
      }
      if (!abortRef.current && cursorRef.current >= chapter.events.length) {
        setStatus("finished");
        onCompleteRef.current?.();
      }
    })();
    loopRef.current = loop;
    try {
      await loop;
    } finally {
      loopRef.current = null;
    }
  }, [chapter, runEvent, status, totalAudios]);

  const waitForIdle = useCallback(async (): Promise<void> => {
    if (loopRef.current) {
      try {
        await loopRef.current;
      } catch {
        /* the loop never throws but be safe across refactors */
      }
    }
  }, []);

  const pause = useCallback(() => {
    if (!loopRef.current) return;
    // Phase 6: snapshot the slide + notebook so play() can restore the full
    // board after a doubt. Captured before abort + cancel so any in-flight
    // render is already reflected in state.
    slideSnapshotRef.current = slide;
    notebookSnapshotRef.current = { entries: notebookEntries, pageNum };
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    cancelParamTween(); // a paused board must not keep animating
    setStatus("paused");
  }, [slide, notebookEntries, pageNum, cancelParamTween]);

  const restart = useCallback(() => {
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    cursorRef.current = 0;
    audioIdxRef.current = 0;
    slideSnapshotRef.current = null;
    snapshotCursorRef.current = 0;
    setCursorState(0);
    setCurrentTopicId(null);
    setCurrentTopicLabel("");
    setCurrentTopicName(null);
    setSlide({ status: "empty" });
    setNotebookEntries([]);
    setPageNum(1);
    setPageTurning(false);
    setCurrentSnapshot(null);
    setCurrentNarrationText("");
    setAudioProgress({ current: 0, total: totalAudios });
    setStatus("idle");
  }, [totalAudios]);

  // Seek to an event index. To make the visual state match the audio
  // position (YouTube-like — scrub to 5:00 and you see what's at 5:00),
  // we RESET visual state to initial then REPLAY every sync event from 0
  // to the target. Audio + pause events are skipped (no playback during
  // replay); page_break / new_page apply their state mutations without
  // their animation delay; everything else routes through applySyncEvent.
  // Pure seek leaves status unchanged — caller calls play() to resume.
  const seekToEvent = useCallback(
    (index: number) => {
      abortRef.current = true;
      currentCancelableRef.current?.cancel();
      cancelParamTween();
      if (!chapter) return;
      const clamped = Math.max(0, Math.min(index, chapter.events.length));

      // RESET visual state to initial — clean slate for replay.
      setSlide({ status: "empty" });
      setNotebookEntries([]);
      setPageNum(1);
      setCurrentTopicId(null);
      setCurrentTopicLabel("");
      setCurrentTopicName(null);
      setCurrentSnapshot(null);
      snapshotCursorRef.current = 0;
      setCurrentNarrationText("");
      setWithinEventMs(0);
      stopSleepTick();
      slideSnapshotRef.current = null;

      // REPLAY sync state for events [0..clamped). React batches the
      // setState calls inside this synchronous function, so the user
      // sees one repaint to the target state — not a flash through
      // intermediate states.
      let audiosBefore = 0;
      for (let i = 0; i < clamped; i++) {
        const ev = chapter.events[i];
        switch (ev.type) {
          case "audio":
            audiosBefore += 1;
            break;
          case "pause":
            // skip — no state mutation, no replay-time delay
            break;
          case "new_page":
            setNotebookEntries([]);
            setPageNum((n) => n + 1);
            advanceSnapshot(chapter);
            break;
          case "page_break":
            setNotebookEntries([]);
            setPageNum((n) => n + 1);
            if (ev.slide_action === "swap") {
              setSlide({ status: "loading" });
            } else if (ev.slide_action === "release") {
              setSlide({ status: "empty", annotations: [] });
            }
            advanceSnapshot(chapter);
            break;
          default:
            // `immediate` → animate_parameter snaps to its terminal value so
            // the scrub lands on the post-animation state, not mid-tween.
            applySyncEvent(ev, chapter, true);
            break;
        }
      }

      audioIdxRef.current = audiosBefore;
      setAudioProgress({ current: audiosBefore, total: totalAudios });
      cursorRef.current = clamped;
      setCursorState(clamped);
    },
    [
      chapter,
      totalAudios,
      advanceSnapshot,
      applySyncEvent,
      stopSleepTick,
      cancelParamTween,
    ],
  );

  // Seek to a time offset in ms (scrubber consumer). Snaps to the START of
  // whichever event (audio OR pause OR page-turn) covers targetMs. Past the
  // chapter end → seek to the last event.
  const seekToTimeMs = useCallback(
    (targetMs: number) => {
      if (!chapter || eventOffsetsMs.length <= 1) return;
      const clamped = Math.max(0, Math.min(targetMs, chapterDurationMs));
      let eventIdx = eventOffsetsMs.length - 2;
      for (let i = 1; i < eventOffsetsMs.length; i++) {
        if (eventOffsetsMs[i] > clamped) {
          eventIdx = i - 1;
          break;
        }
      }
      seekToEvent(eventIdx);
    },
    [chapter, eventOffsetsMs, chapterDurationMs, seekToEvent],
  );

  // ── Phase 5: doubt-mode slide mutators ─────────────────────────
  //
  // During a doubt the playback engine is paused; the LectureViewer
  // imperatively pushes visual updates into the same SlideState the
  // lecture uses (one source of truth). Imperative because the data
  // arrives over the LiveKit data channel — not an event we step
  // through.

  // ── Doubt board: a separate slide + notebook taught during a doubt ─────
  //
  // Board events arrive over the data channel (not the manifest loop), in the
  // SAME ManifestEvent vocabulary the lecture uses — so we replay them through
  // the identical `applySyncEvent`, with the live-generated doubt diagrams
  // merged into the chapter view. `beginDoubtBoard` clears to a blank scratch
  // board (the lecture board was already snapshotted by pause()); play()
  // restores the lecture board on resume.

  const beginDoubtBoard = useCallback(() => {
    doubtDiagramsRef.current = {};
    setSlide({ status: "loading" });
    setNotebookEntries([]);
  }, []);

  // Carry-over variant: the doubt is about what's already on the board (a
  // local_clarification with a diagram on screen), so KEEP the current slide +
  // notebook as the doubt board's starting canvas and let the beats build on
  // it — copying "all that board text and diagram" across, exactly. Only the
  // live-generated-diagram map is reset (fresh doubt). The lecture board is
  // still restored from the pause() snapshot on resume, so edits here are safe.
  const beginDoubtBoardFromCurrent = useCallback(() => {
    doubtDiagramsRef.current = {};
  }, []);

  const addDoubtDiagram = useCallback(
    (
      diagramId: string,
      spec: DesignDiagramSpec | null,
      templateConceptId?: string | null,
      templateParams?: Record<string, number> | null,
    ) => {
      // A generated diagram carries a spec; a canonical template carries a
      // template_concept_id (spec null) and the show_diagram handler builds it
      // via buildTemplateSpec — the same instant-canonical path the lecture uses.
      doubtDiagramsRef.current = {
        ...doubtDiagramsRef.current,
        [diagramId]: {
          url: null,
          description: spec?.description ?? "",
          spec: spec ?? null,
          template_concept_id: templateConceptId ?? null,
          template_params: templateParams ?? null,
        },
      };
    },
    [],
  );

  const applyDoubtBoardEvents = useCallback(
    (events: readonly ManifestEvent[]) => {
      if (!chapter) return;
      // Merge live doubt diagrams so a show_diagram for a generated id (absent
      // from the precomputed set) still resolves against a real spec.
      const merged: ChapterPayload = {
        ...chapter,
        diagrams: { ...chapter.diagrams, ...doubtDiagramsRef.current },
      };
      for (const ev of events) {
        applySyncEvent(ev, merged);
      }
    },
    [chapter, applySyncEvent],
  );

  const clearDoubtAnnotations = useCallback(() => {
    resetSlideAnnotations();
  }, [resetSlideAnnotations]);

  // Auto-start when chapter loads, if requested.
  useEffect(() => {
    if (!autoStart || !chapter || status !== "idle") return;
    void play();
  }, [autoStart, chapter, status, play]);

  const notebook = useMemo<NotebookState>(
    () => ({
      page: { pageNum, entries: notebookEntries },
      turning: pageTurning,
    }),
    [notebookEntries, pageNum, pageTurning],
  );

  return {
    status,
    cursor: cursorState,
    totalEvents,
    currentTopicId,
    currentTopicLabel,
    currentTopicName,
    audioProgress,
    slide,
    notebook,
    currentSnapshot,
    currentNarrationText,
    chapterDurationMs,
    currentLectureMs,
    topicJumps,
    setAudioElement,
    play,
    pause,
    restart,
    seekToEvent,
    seekToTimeMs,
    waitForIdle,
    beginDoubtBoard,
    beginDoubtBoardFromCurrent,
    addDoubtDiagram,
    applyDoubtBoardEvents,
    clearDoubtAnnotations,
  };
}

// Doubt visuals now arrive as `board_events` in the lecture's ManifestEvent
// vocabulary (replayed via applyDoubtBoardEvents) + `doubt_diagram_ready`
// specs (registered via addDoubtDiagram) — see `livekit/doubt_delivery.py` and
// `agent/doubt_resolution/board_events.py`. The old per-beat annotation_actions
// shape was retired with the matcher path.
