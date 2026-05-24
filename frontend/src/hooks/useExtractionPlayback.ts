/**
 * Playback engine for precomputed chapter manifests.
 *
 * Walks `chapter.events[]` sequentially:
 *   - `audio` → plays an MP3 via the consumer-supplied <audio> element, awaits
 *     "ended" (cancelable so pause() halts mid-fragment).
 *   - `pause` → cancelable setTimeout.
 *   - `topic_start` → updates currentTopicId / currentTopicLabel.
 *   - `show_diagram` → mounts a DrawDesignDiagramInstruction on SlideState.
 *   - `focus` / `unfocus` / `clear_annotations` → spotlight state.
 *   - `trace` / `mark_point` / `point_at` / `write_margin` → live annotation lists.
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
  | { type: "audio"; url: string; duration_ms: number }
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

export interface ChapterPayload {
  chapter_id: string;
  title: string;
  chapter_index: number | null;
  events: ManifestEvent[];
  diagrams: Record<string, DiagramEntry>;
  topics: Record<string, TopicEntry>;
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
  readonly setAudioElement: (element: HTMLAudioElement | null) => void;
  readonly play: () => Promise<void>;
  readonly pause: () => void;
  readonly restart: () => void;
  readonly seekToEvent: (index: number) => void;
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
  const [slide, setSlide] = useState<SlideState>({ status: "empty" });
  const [notebookEntries, setNotebookEntries] = useState<
    readonly NotebookEntry[]
  >([]);
  const [pageNum, setPageNum] = useState(1);
  const [pageTurning, setPageTurning] = useState(false);
  const [currentTopicId, setCurrentTopicId] = useState<string | null>(null);
  const [currentTopicLabel, setCurrentTopicLabel] = useState("");
  const [currentTopicName, setCurrentTopicName] = useState<string | null>(null);
  const [audioProgress, setAudioProgress] = useState({ current: 0, total: 0 });

  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const setAudioElement = useCallback((element: HTMLAudioElement | null) => {
    audioElementRef.current = element;
  }, []);
  const cursorRef = useRef(0);
  const audioIdxRef = useRef(0);
  const abortRef = useRef(false);
  const loopRef = useRef<Promise<void> | null>(null);
  const currentCancelableRef = useRef<Cancelable | null>(null);

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

  // Reset everything when the chapter changes.
  useEffect(() => {
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    cursorRef.current = 0;
    audioIdxRef.current = 0;
    setCursorState(0);
    setStatus("idle");
    setSlide({ status: "empty" });
    setNotebookEntries([]);
    setPageNum(1);
    setPageTurning(false);
    setCurrentTopicId(null);
    setCurrentTopicLabel("");
    setCurrentTopicName(null);
    setAudioProgress({ current: 0, total: totalAudios });
  }, [chapter, totalAudios]);

  const appendNotebookEntry = useCallback((entry: NotebookEntry) => {
    setNotebookEntries((prev) => {
      const idx = prev.findIndex((e) => e.id === entry.id);
      if (idx === -1) return [...prev, entry];
      const next = [...prev];
      next[idx] = entry;
      return next;
    });
  }, []);

  const setFocusedTarget = useCallback(
    (elementId: string | null, role: string | null, label: string | null) => {
      setSlide((prev) => ({
        ...prev,
        focusedElementId: elementId,
        focusedRole: role,
        inlineLabelText: label,
      }));
    },
    [],
  );

  const resetSlideFocus = useCallback(() => {
    setSlide((prev) => ({
      ...prev,
      focusedElementId: null,
      focusedRole: null,
      inlineLabelText: null,
      traces: [],
      markPoints: [],
      pointers: [],
      marginNotes: [],
    }));
  }, []);

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
            focusedElementId: null,
            focusedRole: null,
            inlineLabelText: null,
            presentationMode:
              ev.presentation_mode ?? d.spec.presentation_mode ?? "overview",
            traces: [],
            markPoints: [],
            pointers: [],
            marginNotes: [],
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
          setFocusedTarget(
            ev.target_element_id ?? null,
            ev.target_role ?? null,
            ev.text?.trim() || null,
          );
          return;
        }
        case "unfocus":
        case "clear_annotations": {
          resetSlideFocus();
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
        case "point_at": {
          appendPointer(ev.element_id, ev.from_side ?? "left");
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
      appendPointer,
      appendTrace,
      resetSlideFocus,
      setFocusedTarget,
    ],
  );

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
          const c2 = makeCancelableAudio(audio, ev.url);
          currentCancelableRef.current = c2;
          await c2.promise;
          currentCancelableRef.current = null;
          return !abortRef.current;
        }
        case "pause": {
          const c2 = makeCancelableSleep(ev.duration_ms);
          currentCancelableRef.current = c2;
          await c2.promise;
          currentCancelableRef.current = null;
          return !abortRef.current;
        }
        case "new_page": {
          setPageTurning(true);
          const c2 = makeCancelableSleep(PAGE_TURN_MS / 2);
          currentCancelableRef.current = c2;
          await c2.promise;
          currentCancelableRef.current = null;
          if (abortRef.current) {
            setPageTurning(false);
            return false;
          }
          setNotebookEntries([]);
          setPageNum((n) => n + 1);
          setPageTurning(false);
          return true;
        }
        case "page_break": {
          setPageTurning(true);
          const c2 = makeCancelableSleep(PAGE_TURN_MS / 2);
          currentCancelableRef.current = c2;
          await c2.promise;
          currentCancelableRef.current = null;
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
          setPageTurning(false);
          return true;
        }
        default:
          applySyncEvent(ev, c);
          return true;
      }
    },
    [applySyncEvent, totalAudios],
  );

  const play = useCallback(async (): Promise<void> => {
    if (!chapter) return;
    if (loopRef.current) return; // already playing
    if (status === "finished" || cursorRef.current >= chapter.events.length) {
      return;
    }
    abortRef.current = false;
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

  const pause = useCallback(() => {
    if (!loopRef.current) return;
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    setStatus("paused");
  }, []);

  const restart = useCallback(() => {
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    cursorRef.current = 0;
    audioIdxRef.current = 0;
    setCursorState(0);
    setCurrentTopicId(null);
    setCurrentTopicLabel("");
    setCurrentTopicName(null);
    setSlide({ status: "empty" });
    setNotebookEntries([]);
    setPageNum(1);
    setPageTurning(false);
    setAudioProgress({ current: 0, total: totalAudios });
    setStatus("idle");
  }, [totalAudios]);

  const seekToEvent = useCallback((index: number) => {
    abortRef.current = true;
    currentCancelableRef.current?.cancel();
    cursorRef.current = Math.max(0, index);
    setCursorState(cursorRef.current);
  }, []);

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
            focusedElementId: null,
            focusedRole: null,
            inlineLabelText: null,
            presentationMode: entry.spec.presentation_mode ?? "overview",
            traces: [],
            markPoints: [],
            pointers: [],
            marginNotes: [],
            nextAnnotationKey: 0,
          });
        }
      }

      // Apply each annotation action via the same setters the lecture uses.
      for (const action of annotations) {
        switch (action.action) {
          case "focus":
            setFocusedTarget(
              action.target_element_id ?? null,
              action.target_role ?? null,
              action.text?.trim() || null,
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
    [setFocusedTarget, appendPointer, appendTrace, appendMarkPoint],
  );

  const clearDoubtAnnotations = useCallback(() => {
    resetSlideFocus();
  }, [resetSlideFocus]);

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
    setAudioElement,
    play,
    pause,
    restart,
    seekToEvent,
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
