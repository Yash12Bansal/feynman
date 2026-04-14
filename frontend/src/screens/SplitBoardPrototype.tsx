/**
 * Phase 1 prototype for the Split Board (Slide + Notebook).
 *
 * Drives a scripted "Newton's Second Law" lesson through the SplitBoard
 * components. Yash uses the control bar to step through the lesson and feel
 * whether the metaphor holds.
 *
 * Route: #/dev/split-board
 *
 * No backend. All state is local. If this feels right, Phase 2 wires the
 * real agent output into the same components.
 */

import { useCallback, useMemo, useState } from "react";
import { SplitBoard } from "../engine/whiteboard/split/SplitBoard";
import type {
  NotebookEntry,
  NotebookState,
  PanelMode,
  SlideSpec,
  SlideState,
  SectionEntry,
} from "../engine/whiteboard/split/types";

// ── Scripted slides ───────────────────────────────────────────

const FREE_BODY_SKETCH: SlideSpec = {
  id: "slide-free-body-1",
  title: "Free-body diagram",
  subtitle: "block on a horizontal surface",
  sketch: {
    viewBox: "0 0 440 320",
    paths: [
      // Ground with hatching
      { d: "M 40 230 L 400 230", stroke: "#8892a6", strokeWidth: 2 },
      { d: "M 60 230 L 50 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 100 230 L 90 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 140 230 L 130 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 180 230 L 170 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 220 230 L 210 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 260 230 L 250 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 300 230 L 290 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 340 230 L 330 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 380 230 L 370 248", stroke: "#5a6476", strokeWidth: 1.2 },
      // Block
      {
        d: "M 180 160 L 260 160 L 260 230 L 180 230 Z",
        stroke: "#e8e8ee",
        strokeWidth: 1.8,
        fill: "rgba(127,212,255,0.08)",
      },
      // Applied force arrow (right)
      {
        d: "M 260 195 L 360 195 M 360 195 L 348 189 M 360 195 L 348 201",
        stroke: "#9effc9",
        strokeWidth: 2.2,
        label: "F",
        labelX: 376,
        labelY: 200,
      },
      // Gravity arrow (down)
      {
        d: "M 220 230 L 220 300 M 220 300 L 214 288 M 220 300 L 226 288",
        stroke: "#ff7a8a",
        strokeWidth: 2.2,
        label: "mg",
        labelX: 220,
        labelY: 316,
      },
      // Normal arrow (up)
      {
        d: "M 220 160 L 220 90 M 220 90 L 214 102 M 220 90 L 226 102",
        stroke: "#7fd4ff",
        strokeWidth: 2.2,
        label: "N",
        labelX: 220,
        labelY: 82,
      },
    ],
  },
};

const FREE_BODY_SKETCH_2: SlideSpec = {
  id: "slide-free-body-2",
  title: "Free-body diagram (with values)",
  subtitle: "F = 10 N, m = 2 kg",
  sketch: {
    viewBox: "0 0 440 320",
    paths: [
      { d: "M 40 230 L 400 230", stroke: "#8892a6", strokeWidth: 2 },
      { d: "M 60 230 L 50 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 100 230 L 90 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 140 230 L 130 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 180 230 L 170 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 220 230 L 210 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 260 230 L 250 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 300 230 L 290 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 340 230 L 330 248", stroke: "#5a6476", strokeWidth: 1.2 },
      { d: "M 380 230 L 370 248", stroke: "#5a6476", strokeWidth: 1.2 },
      {
        d: "M 180 160 L 260 160 L 260 230 L 180 230 Z",
        stroke: "#e8e8ee",
        strokeWidth: 1.8,
        fill: "rgba(158,255,201,0.08)",
        label: "2 kg",
        labelX: 220,
        labelY: 200,
      },
      {
        d: "M 260 195 L 360 195 M 360 195 L 348 189 M 360 195 L 348 201",
        stroke: "#9effc9",
        strokeWidth: 2.2,
        label: "10 N",
        labelX: 376,
        labelY: 200,
      },
    ],
  },
};

// ── Scripted lesson steps ─────────────────────────────────────

interface LessonStep {
  readonly label: string;
  readonly slide?: SlideState;
  readonly notebookMutation:
    | { kind: "append"; entry: NotebookEntry }
    | { kind: "strike"; id: string }
    | { kind: "replace_all"; entries: readonly NotebookEntry[] }
    | { kind: "new_page"; carryForwardIds?: readonly string[] }
    | { kind: "noop" };
  readonly modeOverride?: PanelMode;
}

const LESSON: readonly LessonStep[] = [
  {
    label: "open section",
    slide: { status: "empty" },
    notebookMutation: {
      kind: "append",
      entry: {
        id: "section-1",
        kind: "section_header",
        title: "Newton's Second Law",
      },
    },
  },
  {
    label: "agent requests diagram → loader",
    slide: {
      status: "loading",
      pendingTitle: "Free-body diagram",
    },
    notebookMutation: { kind: "noop" },
  },
  {
    label: "slide arrives — stroke reveal",
    slide: {
      status: "ready",
      active: FREE_BODY_SKETCH,
    },
    notebookMutation: {
      kind: "append",
      entry: {
        id: "kp-1",
        kind: "key_point",
        text: "Net force equals mass times acceleration.",
      },
    },
  },
  {
    label: "state the law",
    notebookMutation: {
      kind: "append",
      entry: {
        id: "eq-1",
        kind: "equation",
        latex: "F_{\\mathrm{net}} = m \\, a",
        alignGroup: "g-solve",
      },
    },
  },
  {
    label: "intent: solve for a",
    notebookMutation: {
      kind: "append",
      entry: {
        id: "step-1",
        kind: "step",
        number: 1,
        text: "Solve for the acceleration.",
      },
    },
  },
  {
    label: "rearrange — aligned at =",
    notebookMutation: {
      kind: "append",
      entry: {
        id: "eq-2",
        kind: "equation",
        latex: "a = \\dfrac{F_{\\mathrm{net}}}{m}",
        alignGroup: "g-solve",
      },
    },
  },
  {
    label: "plug values (wrong, for demo)",
    slide: {
      status: "ready",
      active: FREE_BODY_SKETCH_2,
    },
    notebookMutation: {
      kind: "append",
      entry: {
        id: "eq-3-wrong",
        kind: "equation",
        latex: "a = \\dfrac{10}{4}\\ \\mathrm{m/s^2}",
        alignGroup: "g-solve",
      },
    },
  },
  {
    label: "catch the error — strikethrough",
    notebookMutation: { kind: "strike", id: "eq-3-wrong" },
  },
  {
    label: "write the correction",
    notebookMutation: {
      kind: "append",
      entry: {
        id: "eq-3",
        kind: "equation",
        latex: "a = \\dfrac{10\\ \\mathrm{N}}{2\\ \\mathrm{kg}}",
        alignGroup: "g-solve",
      },
    },
  },
  {
    label: "final answer — boxed",
    notebookMutation: {
      kind: "append",
      entry: {
        id: "ans-1",
        kind: "answer",
        latex: "a = 5\\ \\mathrm{m/s^2}",
      },
    },
  },
  {
    label: "turn the page for next concept",
    notebookMutation: {
      kind: "new_page",
    },
  },
  {
    label: "new concept — notebook-only mode",
    modeOverride: "notebook_full",
    notebookMutation: {
      kind: "append",
      entry: {
        id: "section-2",
        kind: "section_header",
        title: "What if the surface has friction?",
      },
    },
  },
];

// ── Driver screen ─────────────────────────────────────────────

// Initial notebook content derived from step 0 (which is just a section header
// append). Done via lazy init so StrictMode double-render doesn't re-append.
const STEP_0_SECTION: SectionEntry = (LESSON[0].notebookMutation as {
  kind: "append";
  entry: SectionEntry;
}).entry;

export function SplitBoardPrototype() {
  const [stepIdx, setStepIdx] = useState(0);
  const [slide, setSlide] = useState<SlideState>(
    () => LESSON[0].slide ?? { status: "empty" },
  );
  const [entries, setEntries] = useState<readonly NotebookEntry[]>(() => [
    STEP_0_SECTION,
  ]);
  const [pageNum, setPageNum] = useState(1);
  const [turning, setTurning] = useState(false);
  const [mode, setMode] = useState<PanelMode>("split");

  const applyStep = useCallback((idx: number) => {
    if (idx < 0 || idx >= LESSON.length) return;
    const step = LESSON[idx];
    if (step.slide) {
      setSlide(step.slide);
    }
    if (step.modeOverride) {
      setMode(step.modeOverride);
    }
    const mut = step.notebookMutation;
    switch (mut.kind) {
      case "append":
        setEntries((prev) => [...prev, mut.entry]);
        break;
      case "strike":
        setEntries((prev) =>
          prev.map((e) =>
            e.id === mut.id ? ({ ...e, struck: true } as NotebookEntry) : e,
          ),
        );
        break;
      case "replace_all":
        setEntries(mut.entries);
        break;
      case "new_page":
        setTurning(true);
        window.setTimeout(() => {
          setEntries([]);
          setPageNum((p) => p + 1);
          setTurning(false);
        }, 220);
        break;
      case "noop":
        break;
    }
  }, []);

  const next = useCallback(() => {
    if (stepIdx >= LESSON.length - 1) return;
    const nextIdx = stepIdx + 1;
    setStepIdx(nextIdx);
    applyStep(nextIdx);
  }, [stepIdx, applyStep]);

  const reset = useCallback(() => {
    setStepIdx(0);
    setSlide(LESSON[0].slide ?? { status: "empty" });
    setEntries([STEP_0_SECTION]);
    setPageNum(1);
    setTurning(false);
    setMode("split");
  }, []);

  const notebookState: NotebookState = useMemo(
    () => ({
      page: { pageNum, entries },
      turning,
    }),
    [pageNum, entries, turning],
  );

  const currentLabel = LESSON[stepIdx]?.label ?? "—";
  const atEnd = stepIdx >= LESSON.length - 1;

  return (
    <div style={styles.container}>
      <aside style={styles.sidebar}>
        <div style={styles.header}>
          <h2 style={styles.title}>Split Board</h2>
          <span style={styles.subtitle}>Phase 1 prototype</span>
        </div>

        <div style={styles.section}>
          <span style={styles.sectionLabel}>Lesson progress</span>
          <div style={styles.progressBox}>
            <div style={styles.progressStep}>
              step {stepIdx + 1} / {LESSON.length}
            </div>
            <div style={styles.progressLabel}>{currentLabel}</div>
          </div>
        </div>

        <div style={styles.section}>
          <span style={styles.sectionLabel}>Controls</span>
          <button
            onClick={next}
            disabled={atEnd}
            style={{
              ...styles.btnPrimary,
              opacity: atEnd ? 0.4 : 1,
              cursor: atEnd ? "default" : "pointer",
            }}
          >
            → Next step
          </button>
          <button onClick={reset} style={styles.btnMuted}>
            ↺ Reset lesson
          </button>
        </div>

        <div style={styles.section}>
          <span style={styles.sectionLabel}>Mode</span>
          <div style={styles.modeRow}>
            {(["split", "slide_full", "notebook_full"] as PanelMode[]).map(
              (m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  style={{
                    ...styles.modeBtn,
                    ...(mode === m ? styles.modeBtnActive : null),
                  }}
                >
                  {m.replace("_", " ")}
                </button>
              ),
            )}
          </div>
        </div>

        <div style={styles.section}>
          <span style={styles.sectionLabel}>What to feel for</span>
          <ul style={styles.feelList}>
            <li>Does the slide feel like a projector, not a card?</li>
            <li>Does the drafting loader feel authored, not dead?</li>
            <li>Do equations aligned at the = feel notebook-like?</li>
            <li>Does the strikethrough feel like a correction, not an error?</li>
            <li>Does the page turn feel deliberate, not sudden?</li>
          </ul>
        </div>

        <div style={styles.footer}>
          design doc: <code>docs/design/10-split-board.md</code>
        </div>
      </aside>

      <main style={styles.stage}>
        <SplitBoard
          slide={slide}
          notebook={notebookState}
          mode={mode}
          notebookTitle="Newton — Lesson 3"
        />
      </main>
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    width: "100%",
    height: "100%",
    background: "#050508",
    color: "#f0f0f0",
    fontFamily: "Inter, system-ui, -apple-system, sans-serif",
  },
  sidebar: {
    width: 300,
    minWidth: 300,
    borderRight: "1px solid #15151f",
    background: "#0a0a12",
    padding: 22,
    display: "flex",
    flexDirection: "column",
    gap: 22,
    overflowY: "auto",
  },
  header: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    paddingBottom: 14,
    borderBottom: "1px solid #15151f",
  },
  title: {
    margin: 0,
    fontSize: 19,
    fontWeight: 700,
    letterSpacing: "-0.02em",
  },
  subtitle: {
    fontSize: 12,
    color: "#6b7280",
    fontFamily: "JetBrains Mono, SF Mono, monospace",
    letterSpacing: "0.04em",
  },
  section: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase" as const,
    color: "#6b7280",
    letterSpacing: "0.08em",
  },
  progressBox: {
    padding: 12,
    background: "#12121f",
    border: "1px solid #1e1e30",
    borderRadius: 8,
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  progressStep: {
    fontSize: 11,
    color: "#6b7280",
    fontFamily: "JetBrains Mono, SF Mono, monospace",
  },
  progressLabel: {
    fontSize: 13,
    color: "#e8e8ee",
    fontWeight: 500,
  },
  btnPrimary: {
    padding: "10px 14px",
    border: "1px solid #7fd4ff",
    borderRadius: 8,
    background: "rgba(127, 212, 255, 0.1)",
    color: "#7fd4ff",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: "inherit",
    textAlign: "left" as const,
    transition: "background 0.15s",
  },
  btnMuted: {
    padding: "8px 14px",
    border: "1px solid #2a2a3a",
    borderRadius: 8,
    background: "#15151f",
    color: "#9ca3af",
    cursor: "pointer",
    fontSize: 13,
    fontFamily: "inherit",
    textAlign: "left" as const,
  },
  modeRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap" as const,
  },
  modeBtn: {
    padding: "6px 10px",
    border: "1px solid #2a2a3a",
    borderRadius: 6,
    background: "#15151f",
    color: "#9ca3af",
    cursor: "pointer",
    fontSize: 11,
    fontFamily: "JetBrains Mono, SF Mono, monospace",
    letterSpacing: "0.03em",
    textTransform: "lowercase" as const,
  },
  modeBtnActive: {
    borderColor: "#7fd4ff",
    background: "rgba(127, 212, 255, 0.12)",
    color: "#7fd4ff",
  },
  feelList: {
    margin: 0,
    paddingLeft: 18,
    fontSize: 12,
    lineHeight: 1.55,
    color: "#9ca3af",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  footer: {
    marginTop: "auto",
    paddingTop: 12,
    borderTop: "1px solid #15151f",
    fontSize: 11,
    color: "#4b5563",
  },
  stage: {
    flex: 1,
    minWidth: 0,
    position: "relative" as const,
  },
};
