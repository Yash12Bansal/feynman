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
      target_role?: string | null;
      text?: string;
    }
  | { type: "unfocus"; diagram_id: string }
  | { type: "clear_annotations"; diagram_id: string }
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
  readonly applyDoubtBeat: (
    beat: {
      readonly target_diagram_id?: string | null;
      readonly annotation_actions?: readonly DoubtBeatAnnotation[];
    },
    sourceChapter: ChapterPayload,
  ) => void;
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
  // Phase 6: SlideState snapshot taken on pause() and restored on play()
  // so a doubt's diagram + annotations don't linger after the lecture
  // resumes. The snapshot captures whatever the lecture was showing right
  // before the student tapped Ask Feynman.
  const slideSnapshotRef = useRef<SlideState | null>(null);

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
    }));
  }, []);

  // FOCUS — spotlight one element in place (glow+lift). Replaces any prior
  // focus (single focused element at a time); null clears it.
  const setFocus = useCallback(
    (elementId: string | null, role: string | null) => {
      setSlide((prev) => ({
        ...prev,
        focusedElementId: elementId,
        focusedRole: role,
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

  // Synchronous events apply state immediately and never block the loop.
  const applySyncEvent = useCallback(
    (ev: ManifestEvent, c: ChapterPayload): void => {
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
          const d = c.diagrams[ev.diagram_id];
          if (!d || !d.spec) return;
          const instr: DrawDesignDiagramInstruction = {
            type: "draw_design_diagram",
            element_id: ev.diagram_id,
            title: d.spec.title,
            description: d.description || d.spec.description,
            spec: d.spec,
          };
          setSlide({
            status: "ready",
            liveInstruction: instr,
            traces: [],
            markPoints: [],
            marginNotes: [],
            pointers: [],
            focusedElementId: null,
            focusedRole: null,
            nextAnnotationKey: 0,
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
          setFocus(ev.target_element_id ?? null, ev.target_role ?? null);
          return;
        }
        case "point_at": {
          appendPointer(ev.element_id, ev.from_side ?? "left");
          return;
        }
        case "unfocus":
        case "clear_annotations": {
          resetSlideAnnotations();
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
    // Phase 6: restore the pre-pause slide before the loop resumes so the
    // doubt's diagram doesn't linger as the audio fragment re-plays.
    if (slideSnapshotRef.current !== null) {
      setSlide(slideSnapshotRef.current);
      slideSnapshotRef.current = null;
    }
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
    // Phase 6: snapshot the slide so play() can restore it after a doubt.
    // Captured before abort + cancel so any in-flight render is already
    // reflected in `slide`.
    slideSnapshotRef.current = slide;
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    setStatus("paused");
  }, [slide]);

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
            applySyncEvent(ev, chapter);
            break;
        }
      }

      audioIdxRef.current = audiosBefore;
      setAudioProgress({ current: audiosBefore, total: totalAudios });
      cursorRef.current = clamped;
      setCursorState(clamped);
    },
    [chapter, totalAudios, advanceSnapshot, applySyncEvent, stopSleepTick],
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

  const applyDoubtBeat = useCallback(
    (
      beat: {
        readonly target_diagram_id?: string | null;
        readonly annotation_actions?: readonly DoubtBeatAnnotation[];
      },
      sourceChapter: ChapterPayload,
    ) => {
      const targetId = beat.target_diagram_id ?? null;
      const annotations = beat.annotation_actions ?? [];

      // Swap the slide if a new diagram is named.
      if (targetId) {
        const entry = sourceChapter.diagrams[targetId];
        if (entry && entry.spec) {
          const instr: DrawDesignDiagramInstruction = {
            type: "draw_design_diagram",
            element_id: targetId,
            title: entry.spec.title,
            description: entry.description || entry.spec.description,
            spec: entry.spec,
          };
          setSlide({
            status: "ready",
            liveInstruction: instr,
            traces: [],
            markPoints: [],
            marginNotes: [],
            pointers: [],
            focusedElementId: null,
            focusedRole: null,
            nextAnnotationKey: 0,
          });
        }
      }

      // Apply each annotation action via the same setters the lecture uses, so
      // doubt highlighting renders identically to the precomputed lecture.
      for (const action of annotations) {
        switch (action.action) {
          case "focus":
            setFocus(
              action.target_element_id ?? null,
              action.target_role ?? null,
            );
            break;
          case "point_at":
            appendPointer(action.element_id, action.from_side ?? "left");
            break;
          case "trace":
            appendTrace(action.element_id, action.duration_ms ?? 1500);
            break;
          case "mark_point":
            appendMarkPoint(
              action.x,
              action.y,
              action.kind ?? "dot",
              action.label ?? "",
            );
            break;
        }
      }
    },
    [appendTrace, appendMarkPoint, appendPointer, setFocus],
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
    applyDoubtBeat,
    clearDoubtAnnotations,
  };
}

// ── Phase 5: shape of the annotation actions arriving from the worker ──
//
// Mirrors `backend/src/feynman/agent/doubt_resolution/models.py::AnnotationAction`.
// The hook stays agnostic about transport; the LectureViewer pulls these
// from the data channel and hands them off via `applyDoubtBeat`.
export type DoubtBeatAnnotation =
  | {
      readonly action: "focus";
      readonly target_element_id?: string | null;
      readonly target_role?: string | null;
      readonly text?: string | null;
    }
  | {
      readonly action: "point_at";
      readonly element_id: string;
      readonly from_side?: "top" | "bottom" | "left" | "right";
    }
  | {
      readonly action: "trace";
      readonly element_id: string;
      readonly duration_ms?: number;
    }
  | {
      readonly action: "mark_point";
      readonly x: number;
      readonly y: number;
      readonly kind?: "dot" | "cross" | "star";
      readonly label?: string;
    };
