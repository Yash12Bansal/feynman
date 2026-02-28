import type { ShowGraphInstruction } from "../../types/visuals";
import { COLORS } from "../theme";

const GRAPH_TYPE_LABELS: Record<string, string> = {
  line: "LINE CHART",
  bar: "BAR CHART",
  scatter: "SCATTER PLOT",
  function: "FUNCTION GRAPH",
};

export function GraphContent({
  instruction,
}: {
  instruction: ShowGraphInstruction;
}) {
  const badge = GRAPH_TYPE_LABELS[instruction.graph_type] ?? "GRAPH";

  return (
    <div>
      {instruction.title && (
        <h3
          style={{
            margin: 0,
            marginBottom: 12,
            fontSize: 28,
            fontWeight: 700,
            lineHeight: "36px",
            color: COLORS.accentPurple,
          }}
        >
          {instruction.title}
        </h3>
      )}
      {/* Placeholder area — Phase 6 Chart.js mount point */}
      <div
        style={{
          height: 200,
          border: `2px dashed ${COLORS.accentPurple}30`,
          borderRadius: 8,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          position: "relative",
        }}
      >
        {instruction.y_axis?.label && (
          <span
            style={{
              position: "absolute",
              left: 12,
              top: "50%",
              transform: "translateY(-50%) rotate(-90deg)",
              fontSize: 13,
              color: COLORS.textSecondary,
              opacity: 0.6,
              whiteSpace: "nowrap",
            }}
          >
            {instruction.y_axis.label}
          </span>
        )}
        {instruction.x_axis?.label && (
          <span
            style={{
              position: "absolute",
              bottom: 8,
              left: "50%",
              transform: "translateX(-50%)",
              fontSize: 13,
              color: COLORS.textSecondary,
              opacity: 0.6,
            }}
          >
            {instruction.x_axis.label}
          </span>
        )}
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.05em",
            color: "#0a0a14",
            background: `${COLORS.accentPurple}99`,
            padding: "3px 8px",
            borderRadius: 4,
          }}
        >
          {badge}
        </span>
      </div>
    </div>
  );
}
