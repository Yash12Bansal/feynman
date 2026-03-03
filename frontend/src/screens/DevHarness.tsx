import { useState, useCallback } from "react";
import { WhiteboardScene } from "../engine/whiteboard/WhiteboardScene";
import type { VisualInstruction, VisualType } from "../types/visuals";
import { ALL_FIXTURES, FIXTURES_BY_TYPE } from "./dev-fixtures";

const INSTRUCTION_TYPES: VisualType[] = [
  "show_text",
  "show_equation",
  "step_equation",
  "draw_diagram",
  "show_graph",
  "draw_scene",
  "highlight",
];

const TYPE_LABELS: Record<VisualType, string> = {
  show_text: "Text",
  show_equation: "Equation",
  step_equation: "Step Equation",
  draw_diagram: "Diagram",
  show_graph: "Graph",
  draw_scene: "Scene",
  highlight: "Highlight",
  annotate: "Annotate",
  clear: "Clear",
  switch_board: "Switch Board",
};

const TYPE_COLORS: Record<VisualType, string> = {
  show_text: "#60a5fa",
  show_equation: "#fbbf24",
  step_equation: "#fbbf24",
  draw_diagram: "#4ade80",
  show_graph: "#a78bfa",
  draw_scene: "#22d3ee",
  highlight: "#fb923c",
  annotate: "#f472b6",
  clear: "#6b7280",
  switch_board: "#94a3b8",
};

export function DevHarness() {
  const [enabled, setEnabled] = useState<Set<VisualType>>(
    () => new Set(INSTRUCTION_TYPES),
  );
  const [extraInstructions, setExtraInstructions] = useState<
    VisualInstruction[]
  >([]);

  const toggleType = useCallback((type: VisualType) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const activeInstructions: VisualInstruction[] = [
    ...ALL_FIXTURES.filter((i) => enabled.has(i.type)),
    ...extraInstructions,
  ];

  const addDynamic = useCallback(() => {
    const instruction: VisualInstruction = {
      type: "show_text",
      element_id: `dynamic-${Date.now()}`,
      title: "Dynamic Instruction",
      text: `This instruction was added at ${new Date().toLocaleTimeString()} — simulating a live instruction arriving from the backend.`,
      style: "example",
    };
    setExtraInstructions((prev) => [...prev, instruction]);
  }, []);

  const clearAll = useCallback(() => {
    setEnabled(new Set());
    setExtraInstructions([]);
  }, []);

  const resetAll = useCallback(() => {
    setEnabled(new Set(INSTRUCTION_TYPES));
    setExtraInstructions([]);
  }, []);

  return (
    <div style={styles.container}>
      {/* Sidebar */}
      <div style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <h2 style={styles.title}>Dev Harness</h2>
          <span style={styles.subtitle}>Visual Instruction Preview</span>
        </div>

        <div style={styles.section}>
          <span style={styles.sectionLabel}>Toggle Types</span>
          {INSTRUCTION_TYPES.map((type) => (
            <button
              key={type}
              onClick={() => toggleType(type)}
              style={{
                ...styles.toggleButton,
                borderColor: enabled.has(type)
                  ? TYPE_COLORS[type]
                  : "transparent",
                background: enabled.has(type)
                  ? `${TYPE_COLORS[type]}18`
                  : "#1a1a2e",
                color: enabled.has(type) ? TYPE_COLORS[type] : "#6b7280",
              }}
            >
              <span
                style={{
                  ...styles.dot,
                  background: enabled.has(type) ? TYPE_COLORS[type] : "#333",
                }}
              />
              {TYPE_LABELS[type]}
              <span style={styles.count}>
                {FIXTURES_BY_TYPE[type]?.length ?? 0}
              </span>
            </button>
          ))}
        </div>

        <div style={styles.section}>
          <span style={styles.sectionLabel}>Actions</span>
          <button onClick={addDynamic} style={styles.actionButton}>
            + Add Instruction
          </button>
          <button onClick={clearAll} style={styles.actionButtonMuted}>
            Clear All
          </button>
          <button onClick={resetAll} style={styles.actionButtonMuted}>
            Reset
          </button>
        </div>

        <div style={styles.stats}>
          {activeInstructions.length} instruction
          {activeInstructions.length !== 1 ? "s" : ""} active
          {extraInstructions.length > 0 && (
            <span style={{ color: "#6b7280" }}>
              {" "}
              ({extraInstructions.length} dynamic)
            </span>
          )}
        </div>
      </div>

      {/* Canvas area */}
      <div style={styles.canvasArea}>
        <WhiteboardScene instructions={activeInstructions} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    width: "100%",
    height: "100%",
    background: "#0a0a0a",
    color: "#f0f0f0",
  },
  sidebar: {
    width: 240,
    minWidth: 240,
    display: "flex",
    flexDirection: "column",
    gap: 16,
    padding: 20,
    borderRight: "1px solid #1e1e30",
    background: "#0f0f1a",
    overflowY: "auto",
  },
  sidebarHeader: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    paddingBottom: 12,
    borderBottom: "1px solid #1e1e30",
  },
  title: {
    margin: 0,
    fontSize: 18,
    fontWeight: 700,
    letterSpacing: "-0.02em",
  },
  subtitle: {
    fontSize: 12,
    color: "#6b7280",
  },
  section: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase" as const,
    color: "#6b7280",
    letterSpacing: "0.05em",
    marginBottom: 4,
  },
  toggleButton: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    border: "1px solid",
    borderRadius: 8,
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 500,
    fontFamily: "inherit",
    transition: "all 0.15s",
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    flexShrink: 0,
  },
  count: {
    marginLeft: "auto",
    fontSize: 11,
    opacity: 0.6,
  },
  actionButton: {
    padding: "8px 12px",
    border: "1px solid #3b82f6",
    borderRadius: 8,
    background: "#3b82f618",
    color: "#60a5fa",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 500,
    fontFamily: "inherit",
  },
  actionButtonMuted: {
    padding: "8px 12px",
    border: "1px solid #2a2a3a",
    borderRadius: 8,
    background: "#1a1a2e",
    color: "#9ca3af",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 500,
    fontFamily: "inherit",
  },
  stats: {
    marginTop: "auto",
    fontSize: 12,
    color: "#9ca3af",
    paddingTop: 12,
    borderTop: "1px solid #1e1e30",
  },
  canvasArea: {
    flex: 1,
    minWidth: 0,
    position: "relative" as const,
  },
};
