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
  NotebookState,
  SlideState,
} from "../engine/whiteboard/split/types";
import type {
  DrawDesignDiagramInstruction,
  DesignDiagramSpec,
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

type ManifestEvent =
  | { type: "audio"; url: string; duration_ms: number }
  | { type: "pause"; duration_ms: number }
  | { type: "show_diagram"; diagram_id: string }
  | { type: "topic_start"; topic_id: string };

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
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
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

const EMPTY_NOTEBOOK: NotebookState = {
  page: { pageNum: 1, entries: [] },
  turning: false,
};

interface PlayerViewProps {
  chapterId: string;
}

function PlayerView({ chapterId }: PlayerViewProps) {
  const [chapter, setChapter] = useState<ChapterPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slide, setSlide] = useState<SlideState>({ status: "empty" });
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
    setProgress(
      `${audioIdxRef.current} / ${totalAudiosRef.current}${top}`,
    );
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
          // Show "drafting" loader between topic_start and the first diagram
          // for this topic. If no diagram fires before the next topic_start,
          // the loader keeps showing — that's the script writer's call.
          setSlide({
            status: "loading",
            pendingTitle: t?.name,
          });
          return;
        }
        case "show_diagram": {
          const d = c.diagrams[ev.diagram_id];
          if (!d || !d.spec) {
            // Spec missing — fall back to fallback image via raw <img>?
            // For simplicity, leave the loader visible.
            return;
          }
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
      }
    },
    [playAudio, updateProgress],
  );

  const startPlayback = useCallback(async () => {
    if (!chapter) return;
    if (isPlaying) return;
    setIsPlaying(true);
    setIsDone(false);
    abortRef.current = false;
    while (
      cursorRef.current < chapter.events.length &&
      !abortRef.current
    ) {
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
    setIsDone(false);
    setProgress(`0 / ${totalAudiosRef.current}`);
  }, [pausePlayback]);

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
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <SplitBoard
          slide={slide}
          notebook={EMPTY_NOTEBOOK}
          mode="slide_full"
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
        minHeight: "100vh",
        background: "#0a0a0a",
        color: "#fafafa",
        display: "flex",
        flexDirection: "column",
        padding: "24px 32px",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
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
