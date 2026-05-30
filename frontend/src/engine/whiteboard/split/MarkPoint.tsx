/**
 * MarkPoint — doc 19 §12 live-annotation primitive.
 *
 * Drops a small marker (dot / cross / star) at a viewBox-space coordinate
 * with an optional inline label. Used for: landing points, intersections,
 * ad-hoc reference points the original diagram dictionary doesn't carry.
 *
 * No bounds resolution — the backend MarkPointEvent already carries (x, y)
 * in the diagram's viewBox space, set by the planner directly.
 */

const DOT_RADIUS = 6;
const CROSS_REACH = 8;
const STAR_RADIUS = 10;
const LABEL_OFFSET_X = 14;
const LABEL_OFFSET_Y = -10;
const LABEL_FONT = 16;
const LABEL_PAD = 6;

interface MarkPointProps {
  readonly x: number;
  readonly y: number;
  readonly kind: "dot" | "cross" | "star";
  readonly label: string;
}

export function MarkPoint({ x, y, kind, label }: MarkPointProps) {
  return (
    <g className="sb-mark-point" data-mark-kind={kind}>
      {renderGlyph(x, y, kind)}
      {label.trim() ? <MarkPointLabel x={x} y={y} text={label.trim()} /> : null}
    </g>
  );
}

function renderGlyph(x: number, y: number, kind: "dot" | "cross" | "star") {
  switch (kind) {
    case "dot":
      return (
        <circle
          className="sb-mark-point-shape sb-mark-point-shape-dot"
          cx={x}
          cy={y}
          r={DOT_RADIUS}
        />
      );
    case "cross":
      return (
        <g className="sb-mark-point-shape sb-mark-point-shape-cross">
          <line
            x1={x - CROSS_REACH}
            y1={y - CROSS_REACH}
            x2={x + CROSS_REACH}
            y2={y + CROSS_REACH}
          />
          <line
            x1={x - CROSS_REACH}
            y1={y + CROSS_REACH}
            x2={x + CROSS_REACH}
            y2={y - CROSS_REACH}
          />
        </g>
      );
    case "star":
      return (
        <path
          className="sb-mark-point-shape sb-mark-point-shape-star"
          d={buildStarPath(x, y, STAR_RADIUS)}
        />
      );
  }
}

function buildStarPath(cx: number, cy: number, r: number): string {
  // 5-pointed star, outer radius r, inner radius ~r * 0.42.
  const inner = r * 0.42;
  const points: string[] = [];
  for (let i = 0; i < 10; i += 1) {
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    const radius = i % 2 === 0 ? r : inner;
    const px = cx + Math.cos(angle) * radius;
    const py = cy + Math.sin(angle) * radius;
    points.push(`${px.toFixed(2)},${py.toFixed(2)}`);
  }
  return `M ${points[0]} L ${points.slice(1).join(" L ")} Z`;
}

function MarkPointLabel({
  x,
  y,
  text,
}: {
  readonly x: number;
  readonly y: number;
  readonly text: string;
}) {
  // Approximate the text width — cheap heuristic for sizing the label pill.
  const textWidth = Math.max(28, text.length * LABEL_FONT * 0.55);
  const pillW = textWidth + LABEL_PAD * 2;
  const pillH = LABEL_FONT + LABEL_PAD;
  const pillX = x + LABEL_OFFSET_X;
  const pillY = y + LABEL_OFFSET_Y - pillH / 2;

  return (
    <g className="sb-mark-point-label">
      <rect
        className="sb-mark-point-label-pill"
        x={pillX}
        y={pillY}
        width={pillW}
        height={pillH}
        rx={pillH / 2}
        ry={pillH / 2}
      />
      <text
        className="sb-mark-point-label-text"
        x={pillX + pillW / 2}
        y={pillY + pillH / 2 + LABEL_FONT * 0.35}
        textAnchor="middle"
        fontSize={LABEL_FONT}
      >
        {text}
      </text>
    </g>
  );
}
