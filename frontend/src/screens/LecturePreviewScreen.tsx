/**
 * Lecture preview — drives the existing SplitBoard from v2 precompute output.
 *
 * Fetches the chapter manifest from preview_server.py (proxied via Vite as
 * /lecture-api/*) and walks the events:
 *   - audio       → plays MP3 fragment via <audio>, awaits "ended"
 *   - show_diagram → builds a DrawDesignDiagramInstruction from the diagram's
 *                    DiagramSpec and pushes it as the slide's liveInstruction
 *   - pause       → setTimeout
 *   - topic_start → updates the topic banner
 *
 * Slide-only mode for now — notebook stays empty. Notebook will get content
 * in Path C once the lecture-script writer emits equation/step markers.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SplitBoard } from "../engine/whiteboard/split/SplitBoard";
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

interface ChapterListEntry {
  id: string;
  title: string | null;
  idx: number | null;
  has_manifest: boolean;
}

type AnnotationPosition = "above" | "below" | "left" | "right";
type CalloutDirection =
  | "up"
  | "down"
  | "up-right"
  | "up-left"
  | "down-right"
  | "down-left";
type BracketSide = "above" | "below" | "left" | "right";

// Phase 3 geometry primitives — stamped on placement-aware events.
interface Rect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}
interface Placement {
  readonly page_index: number;
  readonly rect: Rect;
  readonly measured: boolean;
}

type ManifestEvent =
  | { type: "audio"; url: string; duration_ms: number }
  | { type: "pause"; duration_ms: number }
  | {
      type: "show_diagram";
      diagram_id: string;
      placement?: Placement | null;
      slide_element_bounds?: Record<string, Rect> | null;
      // Doc 18 §4.3 — how the diagram should reveal. Defaults to "overview"
      // at render time when missing (older manifests).
      presentation_mode?: "build_up" | "overview" | null;
    }
  | { type: "topic_start"; topic_id: string }
  // Path C notebook events — appear "as the teacher writes them"
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
  // Phase 3 deterministic page break — replaces the old new_page marker
  // when the precompute layout planner is in charge. slide_action says
  // whether the slide stays, swaps to a new diagram, or releases to empty.
  | {
      type: "page_break";
      new_page_index: number;
      slide_action: "keep" | "swap" | "release";
      next_diagram_id?: string | null;
      notebook_carry_forward_ids?: string[];
      reason: "text_overflow" | "new_diagram" | "writer_marker";
    }
  // Phase 2 annotation events — point at parts of the active diagram while
  // the voice is speaking. Backend uses semantic names (pin/callout/...);
  // we translate to frontend instruction shapes (pin_label/draw_callout/...)
  // in the handler. Frontend resolves role → live-DOM element_id at render.
  // Doc 18 spotlight events — replace the 5-marker annotation system.
  | {
      type: "focus";
      diagram_id: string;
      // Doc 19 §A-3: target_element_id is the preferred selector. target_role
      // stays for back-compat with extraction files generated before the
      // switch — at least one must be present (backend FocusEvent enforces).
      target_element_id?: string | null;
      target_role?: string | null;
      text?: string;
    }
  | {
      type: "unfocus";
      diagram_id: string;
    }
  | { type: "clear_annotations"; diagram_id: string }
  // Doc 19 §12: live-annotation primitives that extend the spotlight surface.
  // Each event mirrors the matching backend Pydantic model in
  // data_pre_compute_v2/.../curriculum/models.py.
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
  // ── Legacy back-compat (back-end no longer emits; handlers no-op) ──
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

interface DiagramEntry {
  url: string | null;
  description: string;
  spec: DesignDiagramSpec | null;
}

interface TopicEntry {
  name: string;
  section: string;
}

interface ChapterPayload {
  chapter_id: string;
  title: string;
  chapter_index: number | null;
  events: ManifestEvent[];
  diagrams: Record<string, DiagramEntry>;
  topics: Record<string, TopicEntry>;
}

// ---------------------------------------------------------------------------
// Hash parsing
// ---------------------------------------------------------------------------

function getChapterFromHash(): string | null {
  const hash = window.location.hash;
  const q = hash.indexOf("?");
  if (q === -1) return null;
  const params = new URLSearchParams(hash.slice(q + 1));
  return params.get("chapter");
}

function useChapterIdFromHash(): string | null {
  const [id, setId] = useState<string | null>(getChapterFromHash);
  useEffect(() => {
    const onChange = () => setId(getChapterFromHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return id;
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

export function LecturePreviewScreen() {
  const chapterId = useChapterIdFromHash();
  if (!chapterId) {
    return <ChapterListView />;
  }
  return <PlayerView chapterId={chapterId} />;
}

// ---------------------------------------------------------------------------
// Chapter list
// ---------------------------------------------------------------------------

function ChapterListView() {
  const [chapters, setChapters] = useState<ChapterListEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/lecture-api/chapters")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: ChapterListEntry[]) => setChapters(data))
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0a0a0a",
        color: "#fafafa",
        padding: "48px 64px",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <h1
        style={{
          fontSize: "1.4rem",
          fontWeight: 500,
          opacity: 0.85,
          marginBottom: 24,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        Lecture preview — v2 precompute
        <span
          style={{
            fontSize: "0.65rem",
            padding: "3px 10px",
            borderRadius: 14,
            background: "#1b3a4a",
            color: "#7fd4ff",
            letterSpacing: "0.04em",
            fontWeight: 600,
            textTransform: "uppercase",
          }}
        >
          SplitBoard · localhost:5173
        </span>
      </h1>
      {error && (
        <p style={{ color: "#ef4444" }}>
          Failed to fetch chapters: {error}. Is preview_server.py running on
          port 8080?
        </p>
      )}
      {chapters === null && !error && <p style={{ opacity: 0.6 }}>Loading…</p>}
      {chapters && chapters.length === 0 && (
        <p style={{ opacity: 0.6 }}>
          No chapters in Neo4j. Run ingest-book first.
        </p>
      )}
      {chapters && chapters.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {chapters.map((c) => (
            <li
              key={c.id}
              style={{
                padding: "14px 18px",
                background: "#18191c",
                borderRadius: 10,
                marginBottom: 10,
              }}
            >
              {c.has_manifest ? (
                <a
                  href={`#/lecture-preview?chapter=${encodeURIComponent(c.id)}`}
                  style={{
                    color: "#e8e8e8",
                    textDecoration: "none",
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                  }}
                >
                  <span
                    style={{
                      color: "#6b7280",
                      minWidth: 28,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {c.idx ?? "?"}.
                  </span>
                  <span style={{ flex: 1, fontSize: "1.05rem" }}>
                    {c.title ?? c.id}
                  </span>
                  <span
                    style={{
                      fontSize: "0.8rem",
                      padding: "2px 10px",
                      borderRadius: 12,
                      background: "#2a3543",
                      color: "#7fd4ff",
                    }}
                  >
                    ready
                  </span>
                </a>
              ) : (
                <span
                  style={{
                    color: "#666",
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                  }}
                >
                  <span style={{ minWidth: 28 }}>{c.idx ?? "?"}.</span>
                  <span style={{ flex: 1 }}>{c.title ?? c.id}</span>
                  <span
                    style={{
                      fontSize: "0.8rem",
                      padding: "2px 10px",
                      borderRadius: 12,
                      background: "#2a2a2a",
                      color: "#555",
                    }}
                  >
                    no audio yet
                  </span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Player
// ---------------------------------------------------------------------------

const PAGE_TURN_MS = 400;

interface PlayerViewProps {
  chapterId: string;
}

function PlayerView({ chapterId }: PlayerViewProps) {
  const [chapter, setChapter] = useState<ChapterPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slide, setSlide] = useState<SlideState>({ status: "empty" });
  // Notebook state — mirrors SplitBoardPrototype's pattern.
  const [notebookEntries, setNotebookEntries] = useState<
    readonly NotebookEntry[]
  >([]);
  const [pageNum, setPageNum] = useState(1);
  const [pageTurning, setPageTurning] = useState(false);
  const [topicLabel, setTopicLabel] = useState<string>("");
  const [progress, setProgress] = useState<string>("—");
  const [isPlaying, setIsPlaying] = useState(false);
  const [isDone, setIsDone] = useState(false);

  // Refs that survive re-renders without triggering them.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cursorRef = useRef<number>(0);
  const audioIdxRef = useRef<number>(0);
  const totalAudiosRef = useRef<number>(0);
  const currentTopicNameRef = useRef<string | null>(null);
  const abortRef = useRef<boolean>(false);

  // Load chapter on mount / id change.
  useEffect(() => {
    setChapter(null);
    setError(null);
    setSlide({ status: "empty" });
    setNotebookEntries([]);
    setPageNum(1);
    setPageTurning(false);
    setTopicLabel("");
    setProgress("—");
    setIsDone(false);
    cursorRef.current = 0;
    audioIdxRef.current = 0;

    fetch(`/lecture-api/chapter/${encodeURIComponent(chapterId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: ChapterPayload) => {
        setChapter(data);
        totalAudiosRef.current = data.events.filter(
          (e) => e.type === "audio",
        ).length;
        setProgress(`0 / ${totalAudiosRef.current}`);
      })
      .catch((e: Error) => setError(e.message));
  }, [chapterId]);

  const updateProgress = useCallback(() => {
    const top = currentTopicNameRef.current
      ? `  ·  ${currentTopicNameRef.current}`
      : "";
    setProgress(`${audioIdxRef.current} / ${totalAudiosRef.current}${top}`);
  }, []);

  const playAudio = useCallback((url: string): Promise<void> => {
    return new Promise((resolve) => {
      const el = audioRef.current;
      if (!el) {
        resolve();
        return;
      }
      const cleanup = () => {
        el.removeEventListener("ended", onEnd);
        el.removeEventListener("error", onErr);
      };
      const onEnd = () => {
        cleanup();
        resolve();
      };
      const onErr = () => {
        // eslint-disable-next-line no-console
        console.warn("audio error", url);
        cleanup();
        resolve();
      };
      el.addEventListener("ended", onEnd);
      el.addEventListener("error", onErr);
      el.src = url;
      el.play().catch(onErr);
    });
  }, []);

  const appendNotebookEntry = useCallback((entry: NotebookEntry) => {
    setNotebookEntries((prev) => {
      // Replace if same id already exists, otherwise append.
      const idx = prev.findIndex((e) => e.id === entry.id);
      if (idx === -1) return [...prev, entry];
      const next = [...prev];
      next[idx] = entry;
      return next;
    });
  }, []);

  /**
   * Doc 18 + doc 19 §A-3 spotlight setters. Focus replaces previous focus
   * (sticky until next focus / unfocus / reset / show_diagram). Inline label
   * clears when focus moves on if not supplied with the new focus. New events
   * carry both element_id (preferred) and role (back-compat); we plumb both
   * into the SlideState so the Spotlight can pick.
   */
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
    // Doc 19 §12: clear_annotations wipes the full live-annotation surface,
    // not just the focus. Traces, marks, pointers, and margin notes all reset
    // so the planner can clear a layered slide in a single event.
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

  // Doc 19 §12 appenders. Each new event pushes onto the relevant list with
  // a monotonic React-key so re-emitting the same element_id still retriggers
  // its animation cleanly (key changes → fresh component mount).
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

  const handleEvent = useCallback(
    async (ev: ManifestEvent, c: ChapterPayload): Promise<void> => {
      switch (ev.type) {
        case "topic_start": {
          const t = c.topics[ev.topic_id];
          if (t) {
            setTopicLabel(`${t.section}  ·  ${t.name}`);
            currentTopicNameRef.current = t.name;
          } else {
            setTopicLabel(ev.topic_id);
            currentTopicNameRef.current = null;
          }
          // Drafting loader between topic_start and the first diagram for
          // this topic. If no diagram fires before the next topic_start, the
          // loader keeps showing — but the notebook should still fill up.
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
          // Doc 18 + 19 §12: a new diagram is a blank annotation slate.
          // Reset focus state AND the four live-annotation lists. Presentation
          // mode comes from the event (or falls back to the spec's declared
          // mode at render time).
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
        case "pause": {
          await sleep(ev.duration_ms);
          return;
        }
        case "audio": {
          audioIdxRef.current += 1;
          updateProgress();
          await playAudio(ev.url);
          return;
        }

        // ─── Notebook events (Path C) ─────────────────────────────────────

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
          const indent = clampIndent(ev.indent);
          const entry: StepEntry = {
            id: ev.id,
            kind: "step",
            text: ev.text,
            indent,
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
        case "new_page": {
          // Mirror the prototype's flip: brief turning animation, then
          // clear + bump page number. Carried entries are an optional
          // future enhancement; for now we just turn.
          setPageTurning(true);
          await sleep(PAGE_TURN_MS / 2);
          setNotebookEntries([]);
          setPageNum((n) => n + 1);
          setPageTurning(false);
          return;
        }
        case "page_break": {
          // Phase 3 deterministic page break. The slide_action determines
          // whether the slide stays, swaps to a new diagram, or releases
          // to a soft placeholder. The notebook ALWAYS flips and clears
          // (carry-forward IDs preserved only if explicitly requested).
          setPageTurning(true);
          await sleep(PAGE_TURN_MS / 2);
          setNotebookEntries([]);
          setPageNum((n) => n + 1);
          if (ev.slide_action === "swap") {
            // Slide is about to receive a new diagram (next show_diagram
            // event). Clear annotations and let the next show_diagram fill.
            setSlide({ status: "loading" });
          } else if (ev.slide_action === "release") {
            // Soft placeholder — slide goes empty until a future
            // show_diagram lands.
            setSlide({ status: "empty", annotations: [] });
          }
          // "keep": leave slide alone; annotations on the carried slide
          // reset is handled at composer level via PageState.
          setPageTurning(false);
          return;
        }

        // ─── Doc 18 spotlight events ───────────────────────────────────────
        // FOCUS spotlights one role on the active diagram; UNFOCUS releases
        // it; CLEAR_ANNOTATIONS resets focus state for the active diagram.

        case "focus": {
          // Doc 19 §A-3: prefer element_id (stable id from dictionary). Fall
          // back to role for old extraction files that pre-date the switch.
          setFocusedTarget(
            ev.target_element_id ?? null,
            ev.target_role ?? null,
            ev.text?.trim() || null,
          );
          return;
        }
        case "unfocus": {
          resetSlideFocus();
          return;
        }
        case "clear_annotations": {
          // RESET_FOCUS alias — wipe spotlight state AND every accumulated
          // live-annotation primitive for the active diagram.
          resetSlideFocus();
          return;
        }

        // ─── Doc 19 §12 live-annotation events ─────────────────────────────
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

        // ─── Legacy annotation events (back-compat no-ops) ────────────────
        // Older extraction files emit pin / callout / bracket / highlight /
        // pulse. Doc 18 deprecates these; the walker drops them at compose
        // time, but stored manifests may still contain them. We ignore them
        // here rather than crash.
        case "pin":
        case "callout":
        case "bracket":
        case "highlight":
        case "pulse":
          return;
      }
    },
    [
      appendNotebookEntry,
      playAudio,
      resetSlideFocus,
      setFocusedTarget,
      appendTrace,
      appendMarkPoint,
      appendPointer,
      appendMarginNote,
      updateProgress,
    ],
  );

  const startPlayback = useCallback(async () => {
    if (!chapter) return;
    if (isPlaying) return;
    setIsPlaying(true);
    setIsDone(false);
    abortRef.current = false;
    while (cursorRef.current < chapter.events.length && !abortRef.current) {
      const ev = chapter.events[cursorRef.current];
      await handleEvent(ev, chapter);
      cursorRef.current += 1;
    }
    setIsPlaying(false);
    if (cursorRef.current >= chapter.events.length) {
      setIsDone(true);
    }
  }, [chapter, handleEvent, isPlaying]);

  const pausePlayback = useCallback(() => {
    abortRef.current = true;
    setIsPlaying(false);
    if (audioRef.current) audioRef.current.pause();
  }, []);

  const restart = useCallback(() => {
    pausePlayback();
    cursorRef.current = 0;
    audioIdxRef.current = 0;
    currentTopicNameRef.current = null;
    setTopicLabel("");
    setSlide({ status: "empty" });
    setNotebookEntries([]);
    setPageNum(1);
    setPageTurning(false);
    setIsDone(false);
    setProgress(`0 / ${totalAudiosRef.current}`);
  }, [pausePlayback]);

  const notebookState = useMemo<NotebookState>(
    () => ({
      page: { pageNum, entries: notebookEntries },
      turning: pageTurning,
    }),
    [notebookEntries, pageNum, pageTurning],
  );

  const onPlayClick = useCallback(() => {
    if (isPlaying) {
      pausePlayback();
    } else if (isDone) {
      restart();
    } else {
      startPlayback();
    }
  }, [isPlaying, isDone, pausePlayback, restart, startPlayback]);

  const buttonLabel = useMemo(() => {
    if (isPlaying) return "❚❚  Pause";
    if (isDone) return "↻  Restart";
    if (cursorRef.current > 0) return "▶  Resume";
    return "▶  Play";
  }, [isPlaying, isDone]);

  if (error) {
    return (
      <ScreenChrome topicLabel="" chapterTitle="Error" chapterIdx={null}>
        <div style={{ padding: 32, color: "#ef4444" }}>{error}</div>
      </ScreenChrome>
    );
  }

  if (!chapter) {
    return (
      <ScreenChrome topicLabel="" chapterTitle="Loading…" chapterIdx={null}>
        <div style={{ padding: 32, color: "#6b7280" }}>Loading chapter…</div>
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome
      topicLabel={topicLabel}
      chapterTitle={chapter.title}
      chapterIdx={chapter.chapter_index}
    >
      <div
        style={{
          flex: 1,
          display: "flex",
          minHeight: 0,
          width: "100%",
          margin: "14px 0",
        }}
      >
        <SplitBoard
          slide={slide}
          notebook={notebookState}
          mode="split"
          notebookTitle={chapter.title}
          viewport="preview"
        />
      </div>
      <footer
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 28,
          padding: "14px 0 22px",
        }}
      >
        <button
          onClick={onPlayClick}
          style={{
            padding: "12px 32px",
            fontSize: "1.05rem",
            background: "#4dc4ff",
            color: "#08090b",
            border: "none",
            borderRadius: 10,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {buttonLabel}
        </button>
        <div
          style={{
            fontSize: "0.9rem",
            color: "#6b7280",
            minWidth: 280,
            textAlign: "center",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {progress}
        </div>
      </footer>
      <audio ref={audioRef} preload="auto" />
    </ScreenChrome>
  );
}

// ---------------------------------------------------------------------------
// Chrome
// ---------------------------------------------------------------------------

interface ChromeProps {
  readonly topicLabel: string;
  readonly chapterTitle: string;
  readonly chapterIdx: number | null;
  readonly children: React.ReactNode;
}

function ScreenChrome({
  topicLabel,
  chapterTitle,
  chapterIdx,
  children,
}: ChromeProps) {
  return (
    <div
      style={{
        height: "100vh",
        background: "#0a0a0a",
        color: "#fafafa",
        display: "flex",
        flexDirection: "column",
        padding: "24px 32px",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        overflow: "hidden",
      }}
    >
      <header
        style={{
          paddingBottom: 16,
          borderBottom: "1px solid #1f2024",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          {chapterIdx != null && (
            <span style={{ color: "#6b7280", fontSize: "0.95rem" }}>
              Ch. {chapterIdx}
            </span>
          )}
          <h1
            style={{
              fontSize: "1.05rem",
              fontWeight: 500,
              opacity: 0.75,
              margin: 0,
            }}
          >
            {chapterTitle}
          </h1>
          <span
            style={{
              marginLeft: 12,
              fontSize: "0.7rem",
              padding: "3px 10px",
              borderRadius: 14,
              background: "#1b3a4a",
              color: "#7fd4ff",
              letterSpacing: "0.04em",
              fontWeight: 600,
              textTransform: "uppercase",
            }}
            title="Rendered via SplitBoard engine — distinct from the plain HTML preview on port 8080"
          >
            SplitBoard · v2
          </span>
          <a
            href="#/lecture-preview"
            style={{
              marginLeft: "auto",
              fontSize: "0.85rem",
              color: "#6b7280",
              textDecoration: "none",
            }}
          >
            ← chapters
          </a>
        </div>
        <div
          style={{
            fontSize: "1.5rem",
            fontWeight: 600,
            color: "#4dc4ff",
            marginTop: 14,
            minHeight: "2rem",
            letterSpacing: "-0.01em",
          }}
        >
          {topicLabel || " "}
        </div>
      </header>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function clampIndent(raw: number | undefined): 0 | 1 | 2 | 3 {
  if (raw == null) return 0;
  if (raw >= 3) return 3;
  if (raw <= 0) return 0;
  return raw as 1 | 2;
}
