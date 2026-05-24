/**
 * Default landing screen for the live product.
 *
 * Fetches /lecture-api/chapters (served by preview_server.py) and renders a
 * polished card grid. Clicking a chapter navigates to `?lecture=<chapter_id>`
 * which `MainApp`'s auto-start effect picks up and runs through session
 * creation → LectureViewer.
 *
 * Legacy free-form "type a topic, start a class" flow lives behind
 * `#/dev/live-teacher`. This screen is the product front door.
 */

import { useEffect, useState } from "react";

interface ChapterListEntry {
  id: string;
  title: string | null;
  idx: number | null;
  has_manifest: boolean;
}

type FetchState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; chapters: ChapterListEntry[] };

export function LectureHomeScreen() {
  const [state, setState] = useState<FetchState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetch("/lecture-api/chapters")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: ChapterListEntry[]) => {
        if (!cancelled) setState({ status: "loaded", chapters: data });
      })
      .catch((e: Error) => {
        if (!cancelled) setState({ status: "error", message: e.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div style={pageStyle}>
      <header style={headerStyle}>
        <h1 style={wordmarkStyle}>Feynman</h1>
        <p style={subtitleStyle}>Choose a lecture</p>
      </header>

      <main style={mainStyle}>
        {state.status === "loading" && <LoadingSkeleton />}
        {state.status === "error" && <ErrorState message={state.message} />}
        {state.status === "loaded" && state.chapters.length === 0 && (
          <EmptyState />
        )}
        {state.status === "loaded" && state.chapters.length > 0 && (
          <ChapterGrid chapters={state.chapters} />
        )}
      </main>
    </div>
  );
}

// ── Pieces ──────────────────────────────────────────────────────

interface ChapterGridProps {
  readonly chapters: ChapterListEntry[];
}

function ChapterGrid({ chapters }: ChapterGridProps) {
  return (
    <div style={gridStyle}>
      {chapters.map((c) => (
        <ChapterCard key={c.id} chapter={c} />
      ))}
    </div>
  );
}

interface ChapterCardProps {
  readonly chapter: ChapterListEntry;
}

function ChapterCard({ chapter }: ChapterCardProps) {
  const [hover, setHover] = useState(false);
  const disabled = !chapter.has_manifest;

  const onActivate = () => {
    if (disabled) return;
    const url = new URL(window.location.href);
    url.searchParams.set("lecture", chapter.id);
    // Hard navigation — clean React mount lets MainApp's auto-start effect
    // fire fresh and the lecture session creates cleanly.
    window.location.href = url.toString();
  };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onActivate}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        ...cardStyle,
        ...(disabled ? cardDisabledStyle : null),
        ...(hover && !disabled ? cardHoverStyle : null),
      }}
      data-testid="chapter-card"
      data-chapter-id={chapter.id}
    >
      <div style={cardIndexStyle}>
        {chapter.idx != null ? `Ch. ${chapter.idx}` : ""}
      </div>
      <div style={cardTitleStyle}>{chapter.title ?? chapter.id}</div>
      <div style={cardFooterStyle}>
        <span style={disabled ? cardBadgeMutedStyle : cardBadgeReadyStyle}>
          {disabled ? "no audio yet" : "ready"}
        </span>
        {!disabled && (
          <span style={cardCtaStyle}>{hover ? "Watch →" : "Watch"}</span>
        )}
      </div>
    </button>
  );
}

function LoadingSkeleton() {
  return (
    <div style={gridStyle} aria-busy>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} style={{ ...cardStyle, ...skeletonStyle }} />
      ))}
    </div>
  );
}

interface ErrorStateProps {
  readonly message: string;
}

function ErrorState({ message }: ErrorStateProps) {
  return (
    <div style={statusBlockStyle}>
      <p style={statusTitleStyle}>Can't reach the lecture server</p>
      <p style={statusBodyStyle}>{message}</p>
      <p style={statusHintStyle}>
        Run <code style={codeStyle}>make dev-preview-server</code> (or{" "}
        <code style={codeStyle}>make dev</code> to start everything together)
        and refresh.
      </p>
    </div>
  );
}

function EmptyState() {
  return (
    <div style={statusBlockStyle}>
      <p style={statusTitleStyle}>No lectures yet</p>
      <p style={statusBodyStyle}>
        Ingest a chapter first:{" "}
        <code style={codeStyle}>
          poetry run lecture-pipeline-v2 ingest-book ...
        </code>
      </p>
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────

const pageStyle: React.CSSProperties = {
  minHeight: "100vh",
  background: "#0a0a0a",
  color: "#fafafa",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  display: "flex",
  flexDirection: "column",
};

const headerStyle: React.CSSProperties = {
  padding: "72px 64px 32px",
  textAlign: "center",
};

const wordmarkStyle: React.CSSProperties = {
  fontSize: "2.6rem",
  fontWeight: 700,
  margin: 0,
  letterSpacing: "-0.02em",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "1rem",
  color: "#6b7280",
  marginTop: "0.75rem",
  letterSpacing: "0.02em",
};

const mainStyle: React.CSSProperties = {
  flex: 1,
  padding: "16px 64px 64px",
  maxWidth: 1100,
  width: "100%",
  margin: "0 auto",
  boxSizing: "border-box",
};

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
  gap: 16,
};

const cardStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "24px 24px 22px",
  background: "#141417",
  border: "1px solid #1f2024",
  borderRadius: 14,
  color: "inherit",
  fontFamily: "inherit",
  cursor: "pointer",
  display: "flex",
  flexDirection: "column",
  gap: 14,
  minHeight: 150,
  transition:
    "border-color 180ms ease, background 180ms ease, transform 180ms ease",
};

const cardHoverStyle: React.CSSProperties = {
  borderColor: "#2d4a5d",
  background: "#181a1f",
  transform: "translateY(-1px)",
};

const cardDisabledStyle: React.CSSProperties = {
  cursor: "not-allowed",
  opacity: 0.5,
};

const cardIndexStyle: React.CSSProperties = {
  fontSize: "0.72rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "#6b7280",
  fontVariantNumeric: "tabular-nums",
};

const cardTitleStyle: React.CSSProperties = {
  fontSize: "1.15rem",
  fontWeight: 600,
  lineHeight: 1.35,
  color: "#e8e8ee",
  flex: 1,
};

const cardFooterStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
};

const cardBadgeReadyStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  padding: "3px 10px",
  borderRadius: 999,
  background: "#1b3a4a",
  color: "#7fd4ff",
  letterSpacing: "0.04em",
  fontWeight: 600,
  textTransform: "uppercase",
};

const cardBadgeMutedStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  padding: "3px 10px",
  borderRadius: 999,
  background: "#1f1f22",
  color: "#555",
  letterSpacing: "0.04em",
  fontWeight: 600,
  textTransform: "uppercase",
};

const cardCtaStyle: React.CSSProperties = {
  fontSize: "0.85rem",
  color: "#7fd4ff",
  letterSpacing: "0.02em",
};

const skeletonStyle: React.CSSProperties = {
  background: "#111114",
  borderColor: "#18191c",
  opacity: 0.6,
  cursor: "default",
};

const statusBlockStyle: React.CSSProperties = {
  textAlign: "center",
  padding: "80px 24px",
  color: "#6b7280",
  maxWidth: 560,
  margin: "0 auto",
};

const statusTitleStyle: React.CSSProperties = {
  fontSize: "1.05rem",
  color: "#e8e8ee",
  margin: 0,
  marginBottom: 10,
};

const statusBodyStyle: React.CSSProperties = {
  fontSize: "0.95rem",
  color: "#6b7280",
  margin: 0,
  marginBottom: 14,
  lineHeight: 1.5,
};

const statusHintStyle: React.CSSProperties = {
  fontSize: "0.85rem",
  color: "#888",
  margin: 0,
  lineHeight: 1.6,
};

const codeStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
  fontSize: "0.82em",
  background: "#1a1c20",
  padding: "2px 8px",
  borderRadius: 4,
  color: "#cbd5e1",
};
