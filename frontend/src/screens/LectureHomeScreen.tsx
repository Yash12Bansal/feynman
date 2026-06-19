/**
 * Default landing screen for the live product (post sign-in).
 *
 * Fetches /lecture-api/chapters (served by preview_server.py) and renders a
 * card grid grouped into class tabs. Clicking a chapter navigates to
 * `?lecture=<chapter_id>`, which `MainApp`'s auto-start effect picks up and runs
 * through session creation → LectureViewer.
 *
 * Visuals: the light "Living Notebook" system shared with the marketing landing
 * page (styles/notebook-theme.css tokens + lecture-home.css layout) — warm
 * paper, Fraunces/Hanken/Caveat, ink accents, paper cards. Purely
 * presentational; every fetch / filter / nav / test marker is unchanged.
 *
 * NOTE: this component is rendered in tests WITHOUT an <AuthProvider>, so it must
 * not call the throwing `useAuth()` — the optional greeting reads the auth
 * context defensively via `useContext` and tolerates `undefined`.
 */

import { useContext, useEffect, useState } from "react";
import { AuthContext } from "../auth/authContext";
import { GlobalMemoryButton } from "../components/GlobalMemoryButton";
import "../styles/notebook-theme.css";
import "./lecture-home.css";

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

/** Human subject label from a `chapter:<subject>:<topic>` id (best-effort). */
function subjectLabel(id: string | null): string {
  if (!id) return "";
  const seg = id.split(":")[1] ?? "";
  const known: Record<string, string> = {
    mathematics: "Mathematics",
    physics: "Physics",
    physics_gemini: "Physics",
    physics_feynman: "Physics",
    chemistry: "Chemistry",
    biology: "Biology",
    deep_learning: "Deep Learning",
    accounting: "Accounting",
  };
  if (known[seg]) return known[seg];
  return seg.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
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

  // Defensive: undefined in tests (no provider) → neutral greeting.
  const auth = useContext(AuthContext);
  const firstName = auth?.profile?.name?.trim().split(/\s+/)[0] ?? null;

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
    <div className="fey-home notebook">
      <div className="nb-grain" aria-hidden />
      <div className="fey-home__grid-bg" aria-hidden />

      <div className="fey-home__content">
        <header className="fey-home__header">
          <span className="fey-home__brand">
            Feynman<span className="dot">.</span>
            <svg
              className="fey-home__brand-underline"
              viewBox="0 0 100 8"
              aria-hidden
            >
              <path d="M2 5 C 22 2, 52 7, 98 3" />
            </svg>
          </span>
          <h1 className="fey-home__greeting">
            Where shall we pick up{firstName ? `, ${firstName}` : ""}?
          </h1>
          <span className="fey-home__sub">ready when you are</span>
          <GlobalMemoryButton />
        </header>

        <main className="fey-home__main">
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

        <footer className="fey-home__footer" aria-hidden>
          one idea at a time.
        </footer>
      </div>
    </div>
  );
}

// ── Pieces ──────────────────────────────────────────────────────

interface ChapterGridProps {
  readonly chapters: ChapterListEntry[];
}

function ChapterGrid({ chapters }: ChapterGridProps) {
  return (
    <div className="fey-home__grid">
      {chapters.map((c, i) => (
        <ChapterCard key={c.id} chapter={c} index={i} />
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

/** Class-tabbed view — the default (live-app) path: an index-tab bar over the
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
        <p className="fey-home__class-empty">No lectures in this class yet.</p>
      ) : (
        // Keyed by tab → the grid remounts and the cards re-stagger on switch.
        <ChapterGrid key={activeIdx} chapters={visible} />
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
    <div className="fey-home__tabs" role="tablist" aria-label="Class">
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
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onSelect}
      data-testid={`class-tab-${label}`}
      className={active ? "fey-home__tab is-active" : "fey-home__tab"}
    >
      <span>{label}</span>
      <span className="fey-home__tab-count">{count}</span>
    </button>
  );
}

interface ChapterCardProps {
  readonly chapter: ChapterListEntry;
  readonly index: number;
}

function ChapterCard({ chapter, index }: ChapterCardProps) {
  const disabled = !chapter.has_manifest;

  const onActivate = () => {
    if (disabled) return;
    const url = new URL(window.location.href);
    url.searchParams.set("lecture", chapter.id);
    // Hard navigation — a clean React mount lets MainApp's auto-start effect
    // fire fresh and the lecture session creates cleanly.
    window.location.href = url.toString();
  };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onActivate}
      className="fey-home__card"
      style={cssVar(index)}
      data-testid="chapter-card"
      data-chapter-id={chapter.id}
    >
      <div className="fey-home__card-top">
        <span className="fey-home__subject">{subjectLabel(chapter.id)}</span>
        {chapter.idx != null && (
          <span className="fey-home__ch">Ch. {chapter.idx}</span>
        )}
      </div>
      <div className="fey-home__card-title">{chapter.title ?? chapter.id}</div>
      <div className="fey-home__card-footer">
        {disabled ? (
          <span className="fey-home__badge fey-home__badge--muted">
            no audio yet
          </span>
        ) : (
          <span className="fey-home__badge">
            <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
              <path d="M4 12.5 L9.5 18 L20 6" />
            </svg>
            ready
          </span>
        )}
        {!disabled && (
          <span className="fey-home__cta">
            Open{" "}
            <span className="fey-home__cta-arrow" aria-hidden>
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
    <div className="fey-home__grid" aria-busy>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="fey-home__card is-skeleton">
          <span aria-hidden className="fey-home__shimmer" />
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
    <div className="fey-home__status">
      <p className="fey-home__status-title">Can't reach the lecture server</p>
      <p className="fey-home__status-body">{message}</p>
      <p className="fey-home__status-hint">
        Run <code className="fey-home__code">make dev-preview-server</code> (or{" "}
        <code className="fey-home__code">make dev</code> to start everything
        together) and refresh.
      </p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="fey-home__status">
      <p className="fey-home__status-title">No lectures yet</p>
      <p className="fey-home__status-body">
        Ingest a chapter first:{" "}
        <code className="fey-home__code">
          poetry run lecture-pipeline-v2 ingest-book ...
        </code>
      </p>
    </div>
  );
}

/* custom-property style helper (needs a cast through CSSProperties) */
function cssVar(i: number): React.CSSProperties {
  return { "--i": i } as React.CSSProperties;
}
