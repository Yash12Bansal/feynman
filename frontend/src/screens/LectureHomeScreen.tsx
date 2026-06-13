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
 *
 * Visuals: the "Premium Deep-Space Glass" system shared with the login + lecture
 * surfaces — a drifting aurora backdrop (reused from auth), glass chapter cards
 * with a cursor-follow spotlight, Space Grotesk display type, cyan/violet
 * accents. Purely presentational; every fetch / filter / nav / test marker below
 * is unchanged from the flat version.
 */

import { useEffect, useRef, useState } from "react";
import { AuroraBackground } from "../auth/AuroraBackground";
import { GlobalMemoryButton } from "../components/GlobalMemoryButton";
import { DISPLAY_FONT, MONO_FONT } from "../styles/fonts";

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

interface ClassGroup {
  /** Tab label, e.g. "9th". */
  readonly label: string;
  /** Chapter ids in this class, in display order. */
  readonly ids: readonly string[];
}

/**
 * Curated lectures shown on the home screen (the cohort front door), grouped
 * into class-wise tabs. This is an allow-list: ONLY these chapters appear, only
 * under their class, in this order. Several topics were ingested more than once
 * (physics / physics_gemini / physics_feynman) — we surface the best single
 * version of each. Edit this to change what the cohort sees / how it's grouped.
 */
const CLASS_GROUPS: readonly ClassGroup[] = [
  {
    label: "9th",
    ids: [
      "chapter:mathematics:arithmetic_progressions", // Arithmetic Progressions
      "chapter:physics:describing_motion_around_us", // Describing Motion Around Us
      "chapter:mathematics:surface_areas_and_volumes", // Surface Areas and Volumes
    ],
  },
  {
    label: "10th",
    ids: [
      "chapter:mathematics:introduction_to_trigonometry", // Introduction to Trigonometry
      "chapter:physics:magnetic_effects_of_electric_current", // Magnetic Effects of Electric Current
      "chapter:chemistry:chemical_reactions_and_equations", // Chemical Reactions and Equations
      "chapter:chemistry:carbon_and_its_compounds", // Carbon and its Compounds
    ],
  },
  {
    label: "11th",
    ids: [
      "chapter:physics:physics_and_mathematics", // Physics and Mathematics
      "chapter:physics:friction", // Friction
      "chapter:physics:fluid_mechanics", // Fluid Mechanics
      "chapter:physics:rotational_mechanics", // Rotational Mechanics (HC Verma)
      "chapter:physics:simple_harmonic_motion", // Simple Harmonic Motion (HC Verma)
    ],
  },
  {
    label: "12th",
    ids: [
      "chapter:physics_gemini:semiconductors_and_semiconductor_devices", // Semiconductors
      "chapter:physics_feynman:the_special_theory_of_relativity", // The Special Theory of Relativity (Feynman)
      "chapter:chemistry:organic_chemistry", // Organic Chemistry
      "chapter:deep_learning:deep_feedforward_networks", // Deep Feedforward Networks (graduate)
    ],
  },
  {
    label: "CA",
    ids: [
      "chapter:accounting:ind_as_116_leases", // Ind AS 116 — Leases (ICAI Educational Material)
    ],
  },
];

/** Filter + order a fetched chapter list down to the curated allow-list.
 *  `visibleIds === null` disables curation (every chapter, in fetch order). */
function curateChapters(
  chapters: ChapterListEntry[],
  visibleIds: readonly string[] | null,
): ChapterListEntry[] {
  if (visibleIds == null) return chapters;
  const order = new Map(visibleIds.map((id, i) => [id, i] as const));
  return chapters
    .filter((c) => c.id != null && order.has(c.id))
    .sort((a, b) => order.get(a.id!)! - order.get(b.id!)!);
}

interface LectureHomeScreenProps {
  /** Legacy flat allow-list (chapter ids, in display order). When provided
   *  (including `null`) the screen renders ONE flat grid with no class tabs —
   *  back-compat for tests/embeds; `null` shows every fetched chapter in fetch
   *  order. When OMITTED (the default, i.e. the live app), lectures are grouped
   *  into the class tabs below. */
  readonly visibleChapterIds?: readonly string[] | null;
  /** Class-wise tab groups for the default (tabbed) path. */
  readonly classGroups?: readonly ClassGroup[];
}

export function LectureHomeScreen({
  visibleChapterIds,
  classGroups = CLASS_GROUPS,
}: LectureHomeScreenProps = {}) {
  const [state, setState] = useState<FetchState>({ status: "loading" });
  // Default (no `visibleChapterIds` prop) → class tabs. An explicit prop
  // (including `null`) opts into the flat, untabbed list.
  const tabbed = visibleChapterIds === undefined;
  const [activeIdx, setActiveIdx] = useState(0);

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
    <>
      {/* Fixed drifting-aurora backdrop (no children → pure decorative layer),
          shared verbatim with the login page. The scroll container sits above. */}
      <AuroraBackground />
      <div style={pageStyle}>
        <header style={headerStyle}>
          <h1 style={wordmarkStyle}>Feynman</h1>
          <div style={wordmarkUnderlineStyle} aria-hidden />
          <p style={subtitleStyle}>Choose a lecture</p>
          <GlobalMemoryButton />
        </header>

        <main style={mainStyle}>
          {state.status === "loading" && <LoadingSkeleton />}
          {state.status === "error" && <ErrorState message={state.message} />}
          {state.status === "loaded" &&
            (state.chapters.length === 0 ? (
              // Nothing ingested at all → the full-screen empty state (both
              // paths). A populated catalog with an empty *class* shows a
              // lighter per-tab note instead (see TabbedChapters).
              <EmptyState />
            ) : tabbed ? (
              <TabbedChapters
                chapters={state.chapters}
                groups={classGroups}
                activeIdx={activeIdx}
                onSelect={setActiveIdx}
              />
            ) : (
              <FlatChapters
                chapters={curateChapters(
                  state.chapters,
                  visibleChapterIds ?? null,
                )}
              />
            ))}
        </main>
      </div>
    </>
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

/** Flat, untabbed list — the legacy `visibleChapterIds` prop path (tests/embeds).
 *  An empty fetch falls through to the full-screen "No lectures yet" state. */
function FlatChapters({ chapters }: { readonly chapters: ChapterListEntry[] }) {
  if (chapters.length === 0) return <EmptyState />;
  return <ChapterGrid chapters={chapters} />;
}

interface TabbedChaptersProps {
  readonly chapters: ChapterListEntry[];
  readonly groups: readonly ClassGroup[];
  readonly activeIdx: number;
  readonly onSelect: (idx: number) => void;
}

/** Class-tabbed view — the default (live-app) path: a glass tab bar over the
 *  selected class's grid. */
function TabbedChapters({
  chapters,
  groups,
  activeIdx,
  onSelect,
}: TabbedChaptersProps) {
  const active = groups[activeIdx] ?? groups[0];
  const visible = active ? curateChapters(chapters, active.ids) : [];
  return (
    <>
      <ClassTabs
        chapters={chapters}
        groups={groups}
        activeIdx={activeIdx}
        onSelect={onSelect}
      />
      {visible.length === 0 ? (
        <p style={classEmptyStyle}>No lectures in this class yet.</p>
      ) : (
        // Keyed by tab → the grid remounts and fades in on each switch.
        <div key={activeIdx} data-home-grid style={gridFadeStyle}>
          <ChapterGrid chapters={visible} />
        </div>
      )}
    </>
  );
}

interface ClassTabsProps {
  readonly chapters: ChapterListEntry[];
  readonly groups: readonly ClassGroup[];
  readonly activeIdx: number;
  readonly onSelect: (idx: number) => void;
}

function ClassTabs({ chapters, groups, activeIdx, onSelect }: ClassTabsProps) {
  return (
    <div style={tabBarStyle} role="tablist" aria-label="Class">
      {groups.map((g, i) => (
        <ClassTab
          key={g.label}
          label={g.label}
          count={curateChapters(chapters, g.ids).length}
          active={i === activeIdx}
          onSelect={() => onSelect(i)}
        />
      ))}
    </div>
  );
}

interface ClassTabProps {
  readonly label: string;
  readonly count: number;
  readonly active: boolean;
  readonly onSelect: () => void;
}

function ClassTab({ label, count, active, onSelect }: ClassTabProps) {
  const [hover, setHover] = useState(false);
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onSelect}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      data-testid={`class-tab-${label}`}
      style={{
        ...tabStyle,
        ...(hover && !active ? tabHoverStyle : null),
        ...(active ? tabActiveStyle : null),
      }}
    >
      <span>{label}</span>
      <span
        style={{ ...tabCountStyle, ...(active ? tabCountActiveStyle : null) }}
      >
        {count}
      </span>
    </button>
  );
}

interface ChapterCardProps {
  readonly chapter: ChapterListEntry;
}

function ChapterCard({ chapter }: ChapterCardProps) {
  const [hover, setHover] = useState(false);
  const cardRef = useRef<HTMLButtonElement>(null);
  const disabled = !chapter.has_manifest;

  const onActivate = () => {
    if (disabled) return;
    const url = new URL(window.location.href);
    url.searchParams.set("lecture", chapter.id);
    // Hard navigation — clean React mount lets MainApp's auto-start effect
    // fire fresh and the lecture session creates cleanly.
    window.location.href = url.toString();
  };

  // Cursor-follow spotlight: pin the card's top radial to the pointer by writing
  // --mx/--my straight to the node (no React state → no re-render). Same idiom
  // as the sign-in card. The background's var() fallback handles the resting
  // state, so we just removeProperty on leave.
  const onMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const el = cardRef.current;
    if (!el || disabled) return;
    const rect = el.getBoundingClientRect();
    const mx = ((e.clientX - rect.left) / rect.width) * 100;
    const my = ((e.clientY - rect.top) / rect.height) * 100;
    el.style.setProperty("--mx", `${mx.toFixed(1)}%`);
    el.style.setProperty("--my", `${my.toFixed(1)}%`);
  };

  return (
    <button
      ref={cardRef}
      type="button"
      disabled={disabled}
      onClick={onActivate}
      onMouseEnter={() => setHover(true)}
      onMouseMove={onMove}
      onMouseLeave={(e) => {
        setHover(false);
        e.currentTarget.style.removeProperty("--mx");
        e.currentTarget.style.removeProperty("--my");
      }}
      style={{
        ...cardStyle,
        ...(disabled ? cardDisabledStyle : null),
        ...(hover && !disabled ? cardHoverStyle : null),
      }}
      data-testid="chapter-card"
      data-chapter-id={chapter.id}
    >
      {/* Top accent hairline — lights up on hover. */}
      <span
        aria-hidden
        style={{
          ...cardAccentLineStyle,
          opacity: hover && !disabled ? 1 : 0,
        }}
      />
      <div style={cardIndexStyle}>
        {chapter.idx != null ? `Ch. ${chapter.idx}` : ""}
      </div>
      <div style={cardTitleStyle}>{chapter.title ?? chapter.id}</div>
      <div style={cardFooterStyle}>
        <span style={disabled ? cardBadgeMutedStyle : cardBadgeReadyStyle}>
          {!disabled && <span style={badgeDotStyle} aria-hidden />}
          {disabled ? "no audio yet" : "ready"}
        </span>
        {!disabled && (
          <span style={cardCtaStyle}>
            Watch{" "}
            <span
              style={{
                ...cardCtaArrowStyle,
                transform: hover ? "translateX(3px)" : "translateX(0)",
              }}
            >
              →
            </span>
          </span>
        )}
      </div>
    </button>
  );
}

function LoadingSkeleton() {
  return (
    <div style={gridStyle} aria-busy>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} style={{ ...cardStyle, ...skeletonStyle }}>
          <span aria-hidden data-home-shimmer style={shimmerStyle} />
        </div>
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
  // Own scroll container: #root is height:100% + overflow:hidden (for the
  // fixed-fullscreen classroom), so the home screen must scroll internally —
  // otherwise a long lecture list is clipped with no way to reach lower cards.
  // Transparent so the fixed AuroraBackground shows through (incl. through the
  // glass cards). Sits above the backdrop via position/zIndex.
  position: "relative",
  zIndex: 1,
  height: "100vh",
  overflowY: "auto",
  background: "transparent",
  color: "#f4f6fb",
  fontFamily: DISPLAY_FONT,
  display: "flex",
  flexDirection: "column",
};

const headerStyle: React.CSSProperties = {
  padding: "76px 64px 30px",
  textAlign: "center",
};

const wordmarkStyle: React.CSSProperties = {
  fontSize: "2.9rem",
  fontWeight: 700,
  margin: 0,
  letterSpacing: "-0.02em",
  // Signature gradient text fill + a soft cyan bloom.
  backgroundImage: "linear-gradient(135deg, #7fd4ff, #6aa8ff, #a78bfa)",
  WebkitBackgroundClip: "text",
  backgroundClip: "text",
  WebkitTextFillColor: "transparent",
  color: "transparent",
  filter: "drop-shadow(0 0 22px rgba(127,212,255,0.22))",
};

const wordmarkUnderlineStyle: React.CSSProperties = {
  width: 64,
  height: 2,
  margin: "14px auto 0",
  borderRadius: 999,
  background:
    "linear-gradient(90deg, transparent, #7fd4ff, #a78bfa, transparent)",
  opacity: 0.8,
};

const subtitleStyle: React.CSSProperties = {
  fontFamily: MONO_FONT,
  fontSize: "0.74rem",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.22em",
  color: "rgba(244,246,251,0.5)",
  marginTop: "0.85rem",
};

const mainStyle: React.CSSProperties = {
  flex: 1,
  padding: "16px 64px 72px",
  maxWidth: 1100,
  width: "100%",
  margin: "0 auto",
  boxSizing: "border-box",
};

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
  gap: 18,
};

const gridFadeStyle: React.CSSProperties = {
  animation: "home-fade 260ms ease",
};

// ── Class tabs (segmented control) ───────────────────────────────

const tabBarStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  justifyContent: "center",
  gap: 10,
  margin: "0 0 26px",
};

const tabStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "9px 18px",
  borderRadius: 999,
  border: "1px solid rgba(255, 255, 255, 0.08)",
  background: "rgba(255, 255, 255, 0.03)",
  color: "rgba(244,246,251,0.6)",
  fontFamily: DISPLAY_FONT,
  fontSize: "0.9rem",
  fontWeight: 600,
  letterSpacing: "0.01em",
  cursor: "pointer",
  transition:
    "background 160ms ease, border-color 160ms ease, color 160ms ease, box-shadow 160ms ease, transform 160ms ease",
};

const tabHoverStyle: React.CSSProperties = {
  borderColor: "rgba(127, 212, 255, 0.3)",
  color: "rgba(244,246,251,0.85)",
  transform: "translateY(-1px)",
};

const tabActiveStyle: React.CSSProperties = {
  background: "rgba(18, 32, 48, 0.6)",
  borderColor: "rgba(127, 212, 255, 0.4)",
  color: "#9fdcff",
  boxShadow:
    "0 0 0 1px rgba(127,212,255,0.15), 0 8px 24px rgba(127,212,255,0.12), inset 0 1px 0 rgba(255,255,255,0.06)",
};

const tabCountStyle: React.CSSProperties = {
  fontFamily: MONO_FONT,
  fontSize: "0.7rem",
  fontWeight: 600,
  color: "rgba(244,246,251,0.35)",
  background: "rgba(255, 255, 255, 0.05)",
  borderRadius: 999,
  padding: "1px 7px",
  minWidth: 18,
  textAlign: "center",
  fontVariantNumeric: "tabular-nums",
};

const tabCountActiveStyle: React.CSSProperties = {
  color: "#9fdcff",
  background: "rgba(127, 212, 255, 0.12)",
};

const classEmptyStyle: React.CSSProperties = {
  textAlign: "center",
  padding: "56px 24px",
  color: "rgba(244,246,251,0.4)",
  fontSize: "0.95rem",
};

const cardStyle: React.CSSProperties = {
  position: "relative",
  overflow: "hidden",
  textAlign: "left",
  padding: "24px 24px 22px",
  // Two-layer glass: a cyan spotlight (follows the cursor via --mx/--my, resting
  // top-center) over a deep translucent base.
  background:
    "radial-gradient(150% 120% at var(--mx, 50%) var(--my, 0%), rgba(127,212,255,0.10), transparent 55%)," +
    "linear-gradient(180deg, rgba(20,22,32,0.66), rgba(14,15,23,0.62))",
  backdropFilter: "blur(18px) saturate(1.2)",
  WebkitBackdropFilter: "blur(18px) saturate(1.2)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  borderRadius: 16,
  boxShadow:
    "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07)",
  color: "inherit",
  fontFamily: "inherit",
  cursor: "pointer",
  display: "flex",
  flexDirection: "column",
  gap: 14,
  minHeight: 152,
  transition:
    "border-color 200ms ease, box-shadow 200ms ease, transform 200ms ease",
};

const cardHoverStyle: React.CSSProperties = {
  // NOTE: must not set `background` — that would clobber the cursor spotlight.
  borderColor: "rgba(127, 212, 255, 0.45)",
  transform: "translateY(-3px)",
  boxShadow:
    "0 0 0 1px rgba(127,212,255,0.22), 0 16px 44px rgba(0,0,0,0.55), 0 8px 40px rgba(127,212,255,0.16), inset 0 1px 0 rgba(255,255,255,0.08)",
};

const cardDisabledStyle: React.CSSProperties = {
  cursor: "not-allowed",
  opacity: 0.45,
};

const cardAccentLineStyle: React.CSSProperties = {
  position: "absolute",
  top: 0,
  left: 0,
  right: 0,
  height: 2,
  background: "linear-gradient(90deg, #7fd4ff, #6aa8ff, #a78bfa)",
  transition: "opacity 220ms ease",
  pointerEvents: "none",
};

const cardIndexStyle: React.CSSProperties = {
  fontFamily: MONO_FONT,
  fontSize: "0.7rem",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  color: "rgba(127, 212, 255, 0.7)",
  fontVariantNumeric: "tabular-nums",
};

const cardTitleStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "1.18rem",
  fontWeight: 600,
  lineHeight: 1.32,
  letterSpacing: "-0.01em",
  color: "#f4f6fb",
  flex: 1,
};

const cardFooterStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
};

const cardBadgeReadyStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  fontSize: "0.68rem",
  padding: "4px 11px",
  borderRadius: 999,
  background: "rgba(18, 32, 48, 0.6)",
  border: "1px solid rgba(127, 212, 255, 0.3)",
  color: "#9fdcff",
  letterSpacing: "0.06em",
  fontWeight: 600,
  textTransform: "uppercase",
};

const badgeDotStyle: React.CSSProperties = {
  width: 6,
  height: 6,
  borderRadius: "50%",
  background: "#7fd4ff",
  boxShadow: "0 0 8px rgba(127,212,255,0.8)",
};

const cardBadgeMutedStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  fontSize: "0.68rem",
  padding: "4px 11px",
  borderRadius: 999,
  background: "rgba(255, 255, 255, 0.04)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  color: "rgba(244,246,251,0.3)",
  letterSpacing: "0.06em",
  fontWeight: 600,
  textTransform: "uppercase",
};

const cardCtaStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 2,
  fontSize: "0.85rem",
  fontWeight: 600,
  color: "#9fdcff",
  letterSpacing: "0.01em",
};

const cardCtaArrowStyle: React.CSSProperties = {
  display: "inline-block",
  transition: "transform 200ms ease",
};

const skeletonStyle: React.CSSProperties = {
  background:
    "linear-gradient(180deg, rgba(20,22,32,0.5), rgba(14,15,23,0.45))",
  borderColor: "rgba(255,255,255,0.05)",
  cursor: "default",
};

const shimmerStyle: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  background:
    "linear-gradient(100deg, transparent 30%, rgba(127,212,255,0.09) 50%, transparent 70%)",
  transform: "translateX(-120%)",
  animation: "home-shimmer 1.5s ease-in-out infinite",
  pointerEvents: "none",
};

const statusBlockStyle: React.CSSProperties = {
  textAlign: "center",
  padding: "48px 36px",
  color: "rgba(244,246,251,0.55)",
  maxWidth: 560,
  margin: "32px auto 0",
  // Glass panel.
  background:
    "radial-gradient(120% 100% at 50% 0%, rgba(127,212,255,0.05), transparent 55%), rgba(11,12,20,0.7)",
  backdropFilter: "blur(20px) saturate(1.2)",
  WebkitBackdropFilter: "blur(20px) saturate(1.2)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 20,
  boxShadow:
    "0 24px 70px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.06)",
  boxSizing: "border-box",
};

const statusTitleStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "1.1rem",
  fontWeight: 700,
  color: "#f4f6fb",
  margin: 0,
  marginBottom: 10,
  letterSpacing: "-0.01em",
};

const statusBodyStyle: React.CSSProperties = {
  fontSize: "0.95rem",
  color: "rgba(244,246,251,0.55)",
  margin: 0,
  marginBottom: 14,
  lineHeight: 1.5,
};

const statusHintStyle: React.CSSProperties = {
  fontSize: "0.85rem",
  color: "rgba(244,246,251,0.4)",
  margin: 0,
  lineHeight: 1.7,
};

const codeStyle: React.CSSProperties = {
  fontFamily: MONO_FONT,
  fontSize: "0.82em",
  background: "rgba(127, 212, 255, 0.08)",
  border: "1px solid rgba(127, 212, 255, 0.16)",
  padding: "2px 8px",
  borderRadius: 6,
  color: "#9fdcff",
};

// Inject the skeleton shimmer keyframe once (inline styles can't carry
// @keyframes); guard by id + honor reduced-motion, mirroring AuroraBackground.
if (typeof document !== "undefined") {
  const KEY = "home-screen-keyframes";
  if (!document.getElementById(KEY)) {
    const style = document.createElement("style");
    style.id = KEY;
    style.textContent = `
@keyframes home-shimmer {
  0%   { transform: translateX(-120%); }
  100% { transform: translateX(120%); }
}
@keyframes home-fade {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  [data-home-shimmer] { animation: none !important; }
  [data-home-grid] { animation: none !important; }
}`;
    document.head.appendChild(style);
  }
}
