/**
 * SlideAnnotationLayer — sibling SVG overlay on the slide panel.
 *
 * Renders the four annotation types (`pin_label`, `draw_callout`, `bracket`,
 * `highlight_pulse`) above the active design diagram.
 *
 * Phase 1 (diagram-awareness re-architecture): bounds are resolved against
 * the **live DOM** of the rendered diagram (via `getBoundingClientRect()`
 * converted into our viewBox coordinate space through the overlay SVG's
 * `screenCTM`). This replaces the prior path of trusting LLM-estimated
 * `spec.dictionary[id].bounds`, which drifted from rendered reality for
 * text metrics, arc bboxes, and transformed groups.
 *
 * Resolution order:
 *   1. Live-DOM query within `stageRef` (handles both SVG geometry and
 *      HTML KaTeX overlays — both stamped with `data-design-element`).
 *   2. Dictionary `bounds` fallback — only hits during the brief race
 *      between annotation arrival and diagram fade-in completing, and as
 *      a last-resort for elements that haven't been stamped.
 *
 * Multi-kind targets (`AnnotationTarget`): when present, the instruction's
 * `target` field carries `{kind, value, attr?}`. Kinds: `id`, `role`,
 * `color`, `near_text`, `data_attr`. When absent, we synthesize an
 * `{kind: "id", value: target_element_id}` from the legacy field.
 *
 * Annotations are anchored to the current diagram. `useSplitBoardState`
 * resets the list on every fresh `draw_*_diagram`, so stale overlays never
 * outlive their target.
 *
 * Reduced-motion: the layer reflects `prefers-reduced-motion: reduce` via a
 * `data-reduced-motion` attribute. CSS in `SlideAnnotationLayer.css` reads
 * that attribute to disable entry animations and freeze the pulse.
 */

import { useEffect, useRef, useState, type RefObject } from "react";
import type {
  AnnotationInstruction,
  AnnotationTarget,
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
  /**
   * Ref to the slide stage container. The layer queries it for
   * `[data-design-element]` to read live bounds via
   * `getBoundingClientRect()`. The diagram SVG and KaTeX overlays live
   * inside this subtree.
   */
  readonly stageRef?: RefObject<HTMLElement | null>;
}

// ── Multi-kind target resolution ─────────────────────────────

/** Normalize the legacy `target_element_id` into the structured target. */
function asTarget(
  target: AnnotationTarget | null | undefined,
  legacyId: string,
): AnnotationTarget {
  if (target) return target;
  return { kind: "id", value: legacyId };
}

/** Query the live DOM for the element this target points at. */
function queryTargetElement(
  scope: HTMLElement,
  target: AnnotationTarget,
  dictionary: Record<string, ElementMeta> | undefined,
): Element | null {
  switch (target.kind) {
    case "id":
      return scope.querySelector(
        `[data-design-element="${cssEscape(target.value)}"]`,
      );

    case "role": {
      // Walk the dictionary for a matching role → element_id → DOM.
      if (!dictionary) return null;
      for (const [id, meta] of Object.entries(dictionary)) {
        if (meta?.role === target.value) {
          const el = scope.querySelector(
            `[data-design-element="${cssEscape(id)}"]`,
          );
          if (el) return el;
        }
      }
      return null;
    }

    case "color": {
      // Best-effort: try stroke first, then fill. The LLM emits the value
      // as it'd write it in CSS, but DiagramSpec uses both hex (`#ff0000`)
      // and named colors. We accept either.
      const escaped = cssEscape(target.value);
      return (
        scope.querySelector(`[stroke="${escaped}"]`) ??
        scope.querySelector(`[fill="${escaped}"]`)
      );
    }

    case "near_text": {
      // Find a <text> whose content includes the substring; return its
      // parent group (more useful annotation anchor) if available, else
      // the text node itself.
      const texts = scope.querySelectorAll("text");
      for (const t of Array.from(texts)) {
        if ((t.textContent ?? "").includes(target.value)) {
          return t.closest("[data-design-element]") ?? t;
        }
      }
      return null;
    }

    case "data_attr": {
      const attr = target.attr;
      if (!attr) return null;
      // Allow plain `foo` or `data-foo` — normalize to `data-foo`.
      const attrName = attr.startsWith("data-") ? attr : `data-${attr}`;
      return scope.querySelector(`[${attrName}="${cssEscape(target.value)}"]`);
    }
  }
}

/** CSS.escape with a safe fallback (jsdom may not provide it). */
function cssEscape(value: string): string {
  if (
    typeof globalThis !== "undefined" &&
    typeof (globalThis as { CSS?: { escape?: (s: string) => string } }).CSS
      ?.escape === "function"
  ) {
    return (
      globalThis as { CSS: { escape: (s: string) => string } }
    ).CSS.escape(value);
  }
  // Conservative fallback: only escape characters that could break the
  // selector grammar. Element ids and roles in our pipeline are
  // hyphen/underscore/alphanumeric in practice.
  return value.replace(/(["'\\[\] <>])/g, "\\$1");
}

/**
 * Convert a live DOM element's rect to viewBox-space bounds using the
 * overlay SVG as the reference frame. Returns null if any required
 * matrix is unavailable (degenerate render state — fall back to dict).
 */
function liveBoundsViaScreenCTM(
  overlaySvg: SVGSVGElement,
  el: Element,
): ElementBounds | null {
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;

  const screenCTM = overlaySvg.getScreenCTM();
  if (!screenCTM) return null;
  const inverse = screenCTM.inverse();

  const topLeft = overlaySvg.createSVGPoint();
  topLeft.x = rect.left;
  topLeft.y = rect.top;
  const tl = topLeft.matrixTransform(inverse);

  const bottomRight = overlaySvg.createSVGPoint();
  bottomRight.x = rect.right;
  bottomRight.y = rect.bottom;
  const br = bottomRight.matrixTransform(inverse);

  return [tl.x, tl.y, br.x - tl.x, br.y - tl.y];
}

/**
 * Resolve a target to bounds in viewBox space.
 *
 * Path 1 (preferred): query the live DOM, measure via getBoundingClientRect,
 *   convert to viewBox via overlay SVG's screenCTM. This is the truth source.
 * Path 2 (fallback): the dictionary's stale bounds — used while the diagram
 *   is fading in and `stageRef` may not yet contain it, and for
 *   element_ids/roles that don't appear in the DOM. Only kinds `id` and
 *   `role` have a dictionary path.
 */
function resolveBounds(
  target: AnnotationTarget,
  stageRef: RefObject<HTMLElement | null> | undefined,
  overlaySvg: SVGSVGElement | null,
  dictionary: Record<string, ElementMeta> | undefined,
): ElementBounds | null {
  const scope = stageRef?.current;
  if (scope && overlaySvg) {
    const el = queryTargetElement(scope, target, dictionary);
    if (el) {
      const bounds = liveBoundsViaScreenCTM(overlaySvg, el);
      if (bounds) return bounds;
    }
  }
  // Dictionary fallback — only meaningful for id/role kinds.
  if (target.kind === "id") {
    return dictionary?.[target.value]?.bounds ?? null;
  }
  if (target.kind === "role" && dictionary) {
    for (const meta of Object.values(dictionary)) {
      if (meta?.role === target.value && meta.bounds) return meta.bounds;
    }
  }
  if (import.meta.env.DEV) {
    console.debug(
      "[SlideAnnotationLayer] no bounds resolved for target",
      target,
    );
  }
  return null;
}

// ── Reduced motion ───────────────────────────────────────────

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

// ── Layer ────────────────────────────────────────────────────

export function SlideAnnotationLayer({
  viewBox,
  dictionary,
  annotations,
  stageRef,
}: SlideAnnotationLayerProps) {
  const reduced = useReducedMotion();
  const overlayRef = useRef<SVGSVGElement>(null);

  if (annotations.length === 0) return null;

  return (
    <svg
      ref={overlayRef}
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
          stageRef={stageRef}
          overlayRef={overlayRef}
        />
      ))}
    </svg>
  );
}

interface AnnotationProps {
  readonly annotation: AnnotationInstruction;
  readonly dictionary: Record<string, ElementMeta> | undefined;
  readonly stageRef: RefObject<HTMLElement | null> | undefined;
  readonly overlayRef: RefObject<SVGSVGElement | null>;
}

function Annotation(props: AnnotationProps) {
  switch (props.annotation.type) {
    case "pin_label":
      return <PinLabel {...props} instr={props.annotation} />;
    case "draw_callout":
      return <Callout {...props} instr={props.annotation} />;
    case "bracket":
      return <Bracket {...props} instr={props.annotation} />;
    case "highlight_pulse":
      return <HighlightPulse {...props} instr={props.annotation} />;
  }
}

/**
 * `useResolvedBounds` recomputes bounds on every layout pass tied to
 * `annotations`. The screenCTM is only valid post-render, so we resolve in
 * a layout effect and store in state — the first render gets dictionary
 * bounds (or null), the second gets live-DOM bounds.
 */
function useResolvedBounds(
  target: AnnotationTarget,
  stageRef: RefObject<HTMLElement | null> | undefined,
  overlayRef: RefObject<SVGSVGElement | null>,
  dictionary: Record<string, ElementMeta> | undefined,
): ElementBounds | null {
  const [bounds, setBounds] = useState<ElementBounds | null>(() =>
    resolveBounds(target, stageRef, overlayRef.current, dictionary),
  );

  useEffect(() => {
    const next = resolveBounds(
      target,
      stageRef,
      overlayRef.current,
      dictionary,
    );
    setBounds(next);
    // Resize listeners keep annotation alignment when the viewport changes.
    if (typeof window === "undefined") return;
    const onResize = () => {
      setBounds(
        resolveBounds(target, stageRef, overlayRef.current, dictionary),
      );
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // We intentionally key on target.kind/value/attr — passing the full
    // target object would re-run every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    target.kind,
    target.value,
    target.attr,
    dictionary,
    stageRef,
    overlayRef,
  ]);

  return bounds;
}

// ── Pin label ─────────────────────────────────────────────────

function PinLabel({
  instr,
  dictionary,
  stageRef,
  overlayRef,
}: AnnotationProps & { readonly instr: PinLabelInstruction }) {
  const target = asTarget(instr.target, instr.target_element_id);
  const bounds = useResolvedBounds(target, stageRef, overlayRef, dictionary);
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
      data-target-kind={target.kind}
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
  stageRef,
  overlayRef,
}: AnnotationProps & { readonly instr: DrawCalloutInstruction }) {
  const target = asTarget(instr.target, instr.target_element_id);
  const bounds = useResolvedBounds(target, stageRef, overlayRef, dictionary);
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
      data-target-kind={target.kind}
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
  stageRef,
  overlayRef,
}: AnnotationProps & { readonly instr: BracketInstruction }) {
  const targetA = asTarget(instr.target_a, instr.element_a_id);
  const targetB = asTarget(instr.target_b, instr.element_b_id);
  const a = useResolvedBounds(targetA, stageRef, overlayRef, dictionary);
  const b = useResolvedBounds(targetB, stageRef, overlayRef, dictionary);
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
  stageRef,
  overlayRef,
}: AnnotationProps & { readonly instr: HighlightPulseInstruction }) {
  const target = asTarget(instr.target, instr.target_element_id);
  const bounds = useResolvedBounds(target, stageRef, overlayRef, dictionary);
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
      data-target-kind={target.kind}
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
