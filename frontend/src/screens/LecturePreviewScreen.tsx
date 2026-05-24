/**
 * Lecture preview playground (dev-only route at #/lecture-preview).
 *
 * Wraps the headless `useExtractionPlayback` engine with playground UX:
 * chapter picker, play/pause button, audio-progress counter. The real
 * product mounts the same engine inside ClassroomScreen with no test
 * affordances.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { SplitBoard } from "../engine/whiteboard/split/SplitBoard";
import {
  useExtractionPlayback,
  type ChapterPayload,
} from "../hooks/useExtractionPlayback";

// ---------------------------------------------------------------------------
// Wire types — chapter list endpoint only (chapter payload comes from the hook)
// ---------------------------------------------------------------------------

interface ChapterListEntry {
  id: string;
  title: string | null;
  idx: number | null;
  has_manifest: boolean;
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

interface PlayerViewProps {
  chapterId: string;
}

function PlayerView({ chapterId }: PlayerViewProps) {
  const [chapter, setChapter] = useState<ChapterPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-prop-change pattern; resetting is intentional.
    setChapter(null);
    setError(null);
    fetch(`/lecture-api/chapter/${encodeURIComponent(chapterId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: ChapterPayload) => setChapter(data))
      .catch((e: Error) => setError(e.message));
  }, [chapterId]);

  const {
    status,
    cursor,
    currentTopicName,
    currentTopicLabel,
    audioProgress,
    slide,
    notebook,
    setAudioElement,
    play,
    pause,
    restart,
  } = useExtractionPlayback({ chapter });

  const onPlayClick = useCallback(() => {
    if (status === "playing") {
      pause();
    } else if (status === "finished") {
      restart();
      void play();
    } else {
      void play();
    }
  }, [status, pause, restart, play]);

  const buttonLabel = useMemo(() => {
    if (status === "playing") return "❚❚  Pause";
    if (status === "finished") return "↻  Restart";
    if (cursor > 0) return "▶  Resume";
    return "▶  Play";
  }, [status, cursor]);

  const progressLabel = useMemo(() => {
    const top = currentTopicName ? `  ·  ${currentTopicName}` : "";
    return `${audioProgress.current} / ${audioProgress.total}${top}`;
  }, [audioProgress, currentTopicName]);

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
      topicLabel={currentTopicLabel}
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
          notebook={notebook}
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
          {progressLabel}
        </div>
      </footer>
      <audio ref={setAudioElement} preload="auto" />
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
          {topicLabel || " "}
        </div>
      </header>
      {children}
    </div>
  );
}
