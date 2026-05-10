/**
 * SlideAnnotationLayer — sibling SVG overlay on the slide panel.
 *
 * Renders the four annotation types (`pin_label`, `draw_callout`, `bracket`,
 * `highlight_pulse`) above the active design diagram. Shares the diagram's
 * viewBox so the backend's `bounds: [x, y, w, h]` (in DiagramSpec coordinates)
 * map directly to overlay coordinates — no DOM measurement needed.
 *
 * Annotations are anchored to the current diagram. `useSplitBoardState`
 * resets the list on every fresh `draw_*_diagram`, so stale overlays never
 * outlive their target.
 *
 * Reduced-motion: the layer reflects `prefers-reduced-motion: reduce` via a
 * `data-reduced-motion` attribute. CSS in `SlideAnnotationLayer.css` reads
 * that attribute to disable entry animations and freeze the pulse.
 */

import { useEffect, useState } from "react";
import type {
  AnnotationInstruction,
  BracketInstruction,
  DrawCalloutInstruction,
  ElementBounds,
  ElementMeta,
  HighlightPulseInstruction,
  PinLabelInstruction,
} from "../../../types/visuals";
import "./SlideAnnotationLayer.css";

// Tunables in viewBox units. The diagram is typically 900×650, so these
// translate to a few pixels at typical render sizes.
const PIN_PAD = 12;
const PIN_FONT = 18;
const CALLOUT_GAP = 16;
const CALLOUT_PAD = 10;
const CALLOUT_FONT = 16;
const CALLOUT_LINE_HEIGHT = 20;
const CALLOUT_BUBBLE_RADIUS = 10;
const BRACKET_GAP = 16;
const BRACKET_DEPTH = 14;
const BRACKET_FONT = 16;
const PULSE_PAD = 6;
const PULSE_DEFAULT_DURATION_MS = 1200;
const PULSE_DEFAULT_COLOR_TOKEN = "--sb-neon";

interface SlideAnnotationLayerProps {
  readonly viewBox: string;
  readonly dictionary: Record<string, ElementMeta> | undefined;
  readonly annotations: readonly AnnotationInstruction[];
}

function lookupBounds(
  dictionary: Record<string, ElementMeta> | undefined,
  id: string,
): ElementBounds | null {
  const bounds = dictionary?.[id]?.bounds;
  if (!bounds) {
    if (import.meta.env.DEV) {
      console.debug("[SlideAnnotationLayer] missing bounds for element_id", id);
    }
    return null;
  }
  return bounds;
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = () => setReduced(mql.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return reduced;
}

export function SlideAnnotationLayer({
  viewBox,
  dictionary,
  annotations,
}: SlideAnnotationLayerProps) {
  const reduced = useReducedMotion();

  if (annotations.length === 0) return null;

  return (
    <svg
      className="sb-slide-annotations"
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      data-reduced-motion={reduced ? "true" : undefined}
      aria-hidden="true"
    >
      {annotations.map((annotation, idx) => (
        <Annotation
          key={annotation.element_id ?? `${annotation.type}-${idx}`}
          annotation={annotation}
          dictionary={dictionary}
        />
      ))}
    </svg>
  );
}

function Annotation({
  annotation,
  dictionary,
}: {
  readonly annotation: AnnotationInstruction;
  readonly dictionary: Record<string, ElementMeta> | undefined;
}) {
  switch (annotation.type) {
    case "pin_label":
      return <PinLabel instr={annotation} dictionary={dictionary} />;
    case "draw_callout":
      return <Callout instr={annotation} dictionary={dictionary} />;
    case "bracket":
      return <Bracket instr={annotation} dictionary={dictionary} />;
    case "highlight_pulse":
      return <HighlightPulse instr={annotation} dictionary={dictionary} />;
  }
}

// ── Pin label ─────────────────────────────────────────────────

function PinLabel({
  instr,
  dictionary,
}: {
  readonly instr: PinLabelInstruction;
  readonly dictionary: Record<string, ElementMeta> | undefined;
}) {
  const bounds = lookupBounds(dictionary, instr.target_element_id);
  if (!bounds) return null;
  const [x, y, w, h] = bounds;
  const position = instr.position ?? "above";

  let textX: number;
  let textY: number;
  let anchor: "middle" | "start" | "end";
  let lineX1: number;
  let lineY1: number;
  let lineX2: number;
  let lineY2: number;

  switch (position) {
    case "above":
      textX = x + w / 2;
      textY = y - PIN_PAD;
      anchor = "middle";
      lineX1 = textX;
      lineY1 = textY + 4;
      lineX2 = textX;
      lineY2 = y;
      break;
    case "below":
      textX = x + w / 2;
      textY = y + h + PIN_PAD + PIN_FONT * 0.8;
      anchor = "middle";
      lineX1 = textX;
      lineY1 = textY - PIN_FONT;
      lineX2 = textX;
      lineY2 = y + h;
      break;
    case "left":
      textX = x - PIN_PAD;
      textY = y + h / 2 + PIN_FONT / 3;
      anchor = "end";
      lineX1 = textX + 4;
      lineY1 = y + h / 2;
      lineX2 = x;
      lineY2 = y + h / 2;
      break;
    case "right":
      textX = x + w + PIN_PAD;
      textY = y + h / 2 + PIN_FONT / 3;
      anchor = "start";
      lineX1 = textX - 4;
      lineY1 = y + h / 2;
      lineX2 = x + w;
      lineY2 = y + h / 2;
      break;
  }

  return (
    <g
      className="sb-annot sb-annot-pin"
      data-annotation-type="pin_label"
      data-target-element-id={instr.target_element_id}
    >
      <line
        className="sb-annot-pin-connector"
        x1={lineX1}
        y1={lineY1}
        x2={lineX2}
        y2={lineY2}
      />
      <text
        className="sb-annot-pin-text"
        x={textX}
        y={textY}
        textAnchor={anchor}
        fontSize={PIN_FONT}
      >
        {instr.text}
      </text>
    </g>
  );
}

// ── Callout ───────────────────────────────────────────────────

function Callout({
  instr,
  dictionary,
}: {
  readonly instr: DrawCalloutInstruction;
  readonly dictionary: Record<string, ElementMeta> | undefined;
}) {
  const bounds = lookupBounds(dictionary, instr.target_element_id);
  if (!bounds) return null;
  const [x, y, w, h] = bounds;
  const direction = instr.direction ?? "up-right";

  // Estimate bubble size from text length. Cheap heuristic — good enough for
  // ≤200-char strings; a perfect fit needs a measure pass we don't want.
  const charW = CALLOUT_FONT * 0.55;
  const lines = wrapText(instr.text, 28);
  const bubbleW = Math.min(
    Math.max(80, Math.ceil(charW * longest(lines)) + CALLOUT_PAD * 2),
    320,
  );
  const bubbleH = lines.length * CALLOUT_LINE_HEIGHT + CALLOUT_PAD * 2;

  const cx = x + w / 2;
  const cy = y + h / 2;

  let bubbleX: number;
  let bubbleY: number;

  switch (direction) {
    case "up":
      bubbleX = cx - bubbleW / 2;
      bubbleY = y - CALLOUT_GAP - bubbleH;
      break;
    case "down":
      bubbleX = cx - bubbleW / 2;
      bubbleY = y + h + CALLOUT_GAP;
      break;
    case "up-right":
      bubbleX = x + w + CALLOUT_GAP;
      bubbleY = y - CALLOUT_GAP - bubbleH;
      break;
    case "up-left":
      bubbleX = x - CALLOUT_GAP - bubbleW;
      bubbleY = y - CALLOUT_GAP - bubbleH;
      break;
    case "down-right":
      bubbleX = x + w + CALLOUT_GAP;
      bubbleY = y + h + CALLOUT_GAP;
      break;
    case "down-left":
      bubbleX = x - CALLOUT_GAP - bubbleW;
      bubbleY = y + h + CALLOUT_GAP;
      break;
  }

  // Tail: from bubble edge nearest the target back to the target's edge.
  const tailFromX = Math.min(
    Math.max(cx, bubbleX + 12),
    bubbleX + bubbleW - 12,
  );
  const tailFromY = bubbleY < cy ? bubbleY + bubbleH : bubbleY;
  const tailPath = `M ${tailFromX - 6} ${tailFromY} L ${cx} ${cy} L ${tailFromX + 6} ${tailFromY} Z`;

  return (
    <g
      className="sb-annot sb-annot-callout"
      data-annotation-type="draw_callout"
      data-target-element-id={instr.target_element_id}
    >
      <path className="sb-annot-callout-tail" d={tailPath} />
      <rect
        className="sb-annot-callout-bubble"
        x={bubbleX}
        y={bubbleY}
        width={bubbleW}
        height={bubbleH}
        rx={CALLOUT_BUBBLE_RADIUS}
        ry={CALLOUT_BUBBLE_RADIUS}
      />
      <text
        className="sb-annot-callout-text"
        x={bubbleX + CALLOUT_PAD}
        y={bubbleY + CALLOUT_PAD + CALLOUT_FONT * 0.85}
        fontSize={CALLOUT_FONT}
      >
        {lines.map((line, i) => (
          <tspan
            key={i}
            x={bubbleX + CALLOUT_PAD}
            dy={i === 0 ? 0 : CALLOUT_LINE_HEIGHT}
          >
            {line}
          </tspan>
        ))}
      </text>
    </g>
  );
}

function wrapText(text: string, maxCharsPerLine: number): string[] {
  if (text.length <= maxCharsPerLine) return [text];
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    if (current.length === 0) {
      current = word;
    } else if (current.length + 1 + word.length <= maxCharsPerLine) {
      current += ` ${word}`;
    } else {
      lines.push(current);
      current = word;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function longest(lines: readonly string[]): number {
  return lines.reduce((m, l) => Math.max(m, l.length), 0);
}

// ── Bracket ───────────────────────────────────────────────────

function Bracket({
  instr,
  dictionary,
}: {
  readonly instr: BracketInstruction;
  readonly dictionary: Record<string, ElementMeta> | undefined;
}) {
  const a = lookupBounds(dictionary, instr.element_a_id);
  const b = lookupBounds(dictionary, instr.element_b_id);
  if (!a || !b) return null;
  const side = instr.side ?? "above";

  const [ax, ay, aw, ah] = a;
  const [bx, by, bw, bh] = b;

  // Combined bbox of both elements.
  const minX = Math.min(ax, bx);
  const maxX = Math.max(ax + aw, bx + bw);
  const minY = Math.min(ay, by);
  const maxY = Math.max(ay + ah, by + bh);

  let path: string;
  let labelX: number;
  let labelY: number;
  let labelAnchor: "middle" | "start" | "end" = "middle";

  switch (side) {
    case "above": {
      const yLine = minY - BRACKET_GAP;
      const yTip = yLine - BRACKET_DEPTH;
      path = `M ${minX} ${yLine} Q ${minX} ${yTip} ${minX + 8} ${yTip} L ${(minX + maxX) / 2 - 6} ${yTip} Q ${(minX + maxX) / 2} ${yTip} ${(minX + maxX) / 2} ${yTip - 6} Q ${(minX + maxX) / 2} ${yTip} ${(minX + maxX) / 2 + 6} ${yTip} L ${maxX - 8} ${yTip} Q ${maxX} ${yTip} ${maxX} ${yLine}`;
      labelX = (minX + maxX) / 2;
      labelY = yTip - 8;
      break;
    }
    case "below": {
      const yLine = maxY + BRACKET_GAP;
      const yTip = yLine + BRACKET_DEPTH;
      path = `M ${minX} ${yLine} Q ${minX} ${yTip} ${minX + 8} ${yTip} L ${(minX + maxX) / 2 - 6} ${yTip} Q ${(minX + maxX) / 2} ${yTip} ${(minX + maxX) / 2} ${yTip + 6} Q ${(minX + maxX) / 2} ${yTip} ${(minX + maxX) / 2 + 6} ${yTip} L ${maxX - 8} ${yTip} Q ${maxX} ${yTip} ${maxX} ${yLine}`;
      labelX = (minX + maxX) / 2;
      labelY = yTip + BRACKET_FONT + 4;
      break;
    }
    case "left": {
      const xLine = minX - BRACKET_GAP;
      const xTip = xLine - BRACKET_DEPTH;
      path = `M ${xLine} ${minY} Q ${xTip} ${minY} ${xTip} ${minY + 8} L ${xTip} ${(minY + maxY) / 2 - 6} Q ${xTip} ${(minY + maxY) / 2} ${xTip - 6} ${(minY + maxY) / 2} Q ${xTip} ${(minY + maxY) / 2} ${xTip} ${(minY + maxY) / 2 + 6} L ${xTip} ${maxY - 8} Q ${xTip} ${maxY} ${xLine} ${maxY}`;
      labelX = xTip - 8;
      labelY = (minY + maxY) / 2 + BRACKET_FONT / 3;
      labelAnchor = "end";
      break;
    }
    case "right": {
      const xLine = maxX + BRACKET_GAP;
      const xTip = xLine + BRACKET_DEPTH;
      path = `M ${xLine} ${minY} Q ${xTip} ${minY} ${xTip} ${minY + 8} L ${xTip} ${(minY + maxY) / 2 - 6} Q ${xTip} ${(minY + maxY) / 2} ${xTip + 6} ${(minY + maxY) / 2} Q ${xTip} ${(minY + maxY) / 2} ${xTip} ${(minY + maxY) / 2 + 6} L ${xTip} ${maxY - 8} Q ${xTip} ${maxY} ${xLine} ${maxY}`;
      labelX = xTip + 8;
      labelY = (minY + maxY) / 2 + BRACKET_FONT / 3;
      labelAnchor = "start";
      break;
    }
  }

  return (
    <g
      className="sb-annot sb-annot-bracket"
      data-annotation-type="bracket"
      data-side={side}
    >
      <path className="sb-annot-bracket-path" d={path} fill="none" />
      <text
        className="sb-annot-bracket-label"
        x={labelX}
        y={labelY}
        textAnchor={labelAnchor}
        fontSize={BRACKET_FONT}
      >
        {instr.label}
      </text>
    </g>
  );
}

// ── Highlight pulse ───────────────────────────────────────────

function HighlightPulse({
  instr,
  dictionary,
}: {
  readonly instr: HighlightPulseInstruction;
  readonly dictionary: Record<string, ElementMeta> | undefined;
}) {
  const bounds = lookupBounds(dictionary, instr.target_element_id);
  if (!bounds) return null;
  const [x, y, w, h] = bounds;
  const duration = instr.duration_ms ?? PULSE_DEFAULT_DURATION_MS;
  const colorToken = instr.color_token ?? PULSE_DEFAULT_COLOR_TOKEN;

  const style: React.CSSProperties & {
    "--sb-pulse-duration"?: string;
    "--sb-pulse-color"?: string;
  } = {
    "--sb-pulse-duration": `${duration}ms`,
    "--sb-pulse-color": `var(${colorToken})`,
  };

  return (
    <rect
      className="sb-annot sb-annot-pulse"
      data-annotation-type="highlight_pulse"
      data-target-element-id={instr.target_element_id}
      x={x - PULSE_PAD}
      y={y - PULSE_PAD}
      width={w + PULSE_PAD * 2}
      height={h + PULSE_PAD * 2}
      rx={6}
      ry={6}
      style={style}
    />
  );
}
