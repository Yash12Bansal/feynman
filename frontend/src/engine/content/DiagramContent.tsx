import type { DrawDiagramInstruction } from "../../types/visuals";
import { COLORS } from "../theme";

const DIAGRAM_TYPE_LABELS: Record<string, string> = {
  flowchart: "FLOWCHART",
  concept_map: "CONCEPT MAP",
  force_diagram: "FORCE DIAGRAM",
  tree: "TREE",
  cycle: "CYCLE",
  comparison: "COMPARISON",
  free_form: "DIAGRAM",
};

export function DiagramContent({
  instruction,
}: {
  instruction: DrawDiagramInstruction;
}) {
  const description = instruction.description ?? instruction.title ?? "";
  const badge =
    DIAGRAM_TYPE_LABELS[instruction.diagram_type ?? "free_form"] ?? "DIAGRAM";

  return (
    <div>
      {/* Placeholder area — Phase 5 SVG mount point */}
      <div
        style={{
          height: 160,
          border: `2px dashed ${COLORS.accentGreen}30`,
          borderRadius: 8,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          marginBottom: description ? 16 : 0,
        }}
      >
        <svg width="60" height="60" viewBox="0 0 60 60" fill="none">
          <circle
            cx="30"
            cy="12"
            r="6"
            stroke={COLORS.accentGreen}
            strokeOpacity="0.4"
            strokeWidth="2"
          />
          <circle
            cx="12"
            cy="48"
            r="6"
            stroke={COLORS.accentGreen}
            strokeOpacity="0.4"
            strokeWidth="2"
          />
          <circle
            cx="48"
            cy="48"
            r="6"
            stroke={COLORS.accentGreen}
            strokeOpacity="0.4"
            strokeWidth="2"
          />
          <line
            x1="30"
            y1="18"
            x2="12"
            y2="42"
            stroke={COLORS.accentGreen}
            strokeOpacity="0.4"
            strokeWidth="2"
          />
          <line
            x1="30"
            y1="18"
            x2="48"
            y2="42"
            stroke={COLORS.accentGreen}
            strokeOpacity="0.4"
            strokeWidth="2"
          />
          <line
            x1="18"
            y1="48"
            x2="42"
            y2="48"
            stroke={COLORS.accentGreen}
            strokeOpacity="0.4"
            strokeWidth="2"
          />
        </svg>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.05em",
            color: COLORS.diagramBg,
            background: `${COLORS.accentGreen}99`,
            padding: "3px 8px",
            borderRadius: 4,
          }}
        >
          {badge}
        </span>
      </div>
      {description && (
        <p
          style={{
            margin: 0,
            fontSize: 20,
            lineHeight: "32px",
            color: COLORS.textSecondary,
          }}
        >
          {description}
        </p>
      )}
    </div>
  );
}
