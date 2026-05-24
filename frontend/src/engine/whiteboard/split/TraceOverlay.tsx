/**
 * TraceOverlay — doc 19 §12 live-annotation primitive.
 *
 * Animates a stroke "drawing" along the original diagram element's geometry,
 * faithful to the shape (curve, line, polyline, circle, rect, ellipse). Used
 * by the lesson choreography to say things like "watch the parabola form" —
 * the path traces from start to end over `durationMs`, then settles at ~70%
 * opacity until the next clear_annotations / show_diagram.
 *
 * Implementation: on mount we look up the leaf shape inside the active
 * diagram's `[data-design-element="<elementId>"]` subtree, copy its geometry
 * attrs into local state, and render a sibling SVG element in the annotation
 * overlay with the SAME geometry plus a `sb-trace-stroke` class that runs the
 * stroke-dash animation.
 *
 * Fallback: if the matched DOM node doesn't expose a known leaf shape (e.g.,
 * it's a `<g>` wrapping latex / a graph), we render an axis-aligned rect over
 * the element's resolved bounds and trace its perimeter. Less faithful, but
 * still a visible "look here, this thing is being drawn" cue.
 */

import { useEffect, useState, type CSSProperties, type RefObject } from "react";
import type { ElementMeta } from "../../../types/visuals";

interface TraceOverlayProps {
  readonly elementId: string;
  readonly durationMs: number;
  readonly dictionary: Record<string, ElementMeta> | undefined;
  readonly stageRef: RefObject<HTMLElement | null> | undefined;
}

type LeafShape =
  | { kind: "path"; d: string; stroke: string }
  | {
      kind: "line";
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      stroke: string;
    }
  | { kind: "polyline"; points: string; stroke: string }
  | { kind: "polygon"; points: string; stroke: string }
  | { kind: "circle"; cx: number; cy: number; r: number; stroke: string }
  | {
      kind: "ellipse";
      cx: number;
      cy: number;
      rx: number;
      ry: number;
      stroke: string;
    }
  | {
      kind: "rect";
      x: number;
      y: number;
      width: number;
      height: number;
      stroke: string;
    }
  | { kind: "fallback_bounds"; bounds: [number, number, number, number] };

const LEAF_TAGS = new Set([
  "path",
  "line",
  "polyline",
  "polygon",
  "circle",
  "ellipse",
  "rect",
]);

const DEFAULT_STROKE = "var(--sb-neon, #7fd4ff)";

function readNumberAttr(el: Element, attr: string, fallback = 0): number {
  const raw = el.getAttribute(attr);
  if (raw === null) return fallback;
  const num = Number(raw);
  return Number.isFinite(num) ? num : fallback;
}

function readStroke(el: Element): string {
  const explicit = el.getAttribute("stroke");
  if (explicit && explicit !== "none") return explicit;
  // The original might inherit stroke from a parent; fall through to our
  // neon accent so the trace is always visible against the dim spotlight.
  return DEFAULT_STROKE;
}

function extractLeafShape(
  root: Element,
  dictionary: Record<string, ElementMeta> | undefined,
  elementId: string,
): LeafShape | null {
  // First, is the root itself a leaf?
  const candidates: Element[] = [];
  if (LEAF_TAGS.has(root.tagName.toLowerCase())) {
    candidates.push(root);
  }
  // Otherwise look at direct children + descendant SVG shape elements.
  // We bias towards the first one — design diagrams typically wrap a single
  // shape in their <g data-design-element="…">.
  for (const child of Array.from(root.querySelectorAll("*"))) {
    if (LEAF_TAGS.has(child.tagName.toLowerCase())) {
      candidates.push(child);
    }
  }
  const leaf = candidates[0];
  if (!leaf) {
    const meta = dictionary?.[elementId];
    if (
      meta?.bounds &&
      meta.bounds.length === 4 &&
      meta.bounds.every((n) => Number.isFinite(n))
    ) {
      return {
        kind: "fallback_bounds",
        bounds: [
          meta.bounds[0],
          meta.bounds[1],
          meta.bounds[2],
          meta.bounds[3],
        ],
      };
    }
    return null;
  }

  const tag = leaf.tagName.toLowerCase();
  const stroke = readStroke(leaf);
  switch (tag) {
    case "path": {
      const d = leaf.getAttribute("d") ?? "";
      if (!d) break;
      return { kind: "path", d, stroke };
    }
    case "line":
      return {
        kind: "line",
        x1: readNumberAttr(leaf, "x1"),
        y1: readNumberAttr(leaf, "y1"),
        x2: readNumberAttr(leaf, "x2"),
        y2: readNumberAttr(leaf, "y2"),
        stroke,
      };
    case "polyline":
    case "polygon": {
      const points = leaf.getAttribute("points") ?? "";
      if (!points) break;
      return { kind: tag, points, stroke };
    }
    case "circle":
      return {
        kind: "circle",
        cx: readNumberAttr(leaf, "cx"),
        cy: readNumberAttr(leaf, "cy"),
        r: readNumberAttr(leaf, "r"),
        stroke,
      };
    case "ellipse":
      return {
        kind: "ellipse",
        cx: readNumberAttr(leaf, "cx"),
        cy: readNumberAttr(leaf, "cy"),
        rx: readNumberAttr(leaf, "rx"),
        ry: readNumberAttr(leaf, "ry"),
        stroke,
      };
    case "rect":
      return {
        kind: "rect",
        x: readNumberAttr(leaf, "x"),
        y: readNumberAttr(leaf, "y"),
        width: readNumberAttr(leaf, "width"),
        height: readNumberAttr(leaf, "height"),
        stroke,
      };
  }
  // Recognized tag but missing geometry — fall back to bounds.
  const meta = dictionary?.[elementId];
  if (
    meta?.bounds &&
    meta.bounds.length === 4 &&
    meta.bounds.every((n) => Number.isFinite(n))
  ) {
    return {
      kind: "fallback_bounds",
      bounds: [meta.bounds[0], meta.bounds[1], meta.bounds[2], meta.bounds[3]],
    };
  }
  return null;
}

export function TraceOverlay({
  elementId,
  durationMs,
  dictionary,
  stageRef,
}: TraceOverlayProps) {
  const [shape, setShape] = useState<LeafShape | null>(null);

  useEffect(() => {
    const stage = stageRef?.current;
    if (!stage) {
      // No live stage to query — fall back to the dictionary bounds if we
      // have them, otherwise render nothing. Tests + storybook environments
      // hit this path; production always provides a stageRef.
      const fallbackMeta = dictionary?.[elementId];
      if (
        fallbackMeta?.bounds &&
        fallbackMeta.bounds.length === 4 &&
        fallbackMeta.bounds.every((n) => Number.isFinite(n))
      ) {
        setShape({
          kind: "fallback_bounds",
          bounds: [
            fallbackMeta.bounds[0],
            fallbackMeta.bounds[1],
            fallbackMeta.bounds[2],
            fallbackMeta.bounds[3],
          ],
        });
      } else {
        setShape(null);
      }
      return;
    }
    const escaped =
      typeof globalThis !== "undefined" &&
      typeof (globalThis as { CSS?: { escape?: (s: string) => string } }).CSS
        ?.escape === "function"
        ? (globalThis as { CSS: { escape: (s: string) => string } }).CSS.escape(
            elementId,
          )
        : elementId.replace(/(["\\])/g, "\\$1");
    const node = stage.querySelector(`[data-design-element="${escaped}"]`);
    if (!node) {
      // Try the bounds fallback before giving up.
      const meta = dictionary?.[elementId];
      if (
        meta?.bounds &&
        meta.bounds.length === 4 &&
        meta.bounds.every((n) => Number.isFinite(n))
      ) {
        setShape({
          kind: "fallback_bounds",
          bounds: [
            meta.bounds[0],
            meta.bounds[1],
            meta.bounds[2],
            meta.bounds[3],
          ],
        });
      } else {
        setShape(null);
      }
      return;
    }
    setShape(extractLeafShape(node, dictionary, elementId));
  }, [elementId, dictionary, stageRef]);

  if (!shape) return null;

  const style = {
    "--trace-duration": `${Math.max(0, durationMs)}ms`,
  } as CSSProperties;

  return (
    <g
      className="sb-trace"
      data-element-id={elementId}
      data-shape-kind={shape.kind}
    >
      {renderShape(shape, style)}
    </g>
  );
}

function renderShape(shape: LeafShape, style: CSSProperties) {
  switch (shape.kind) {
    case "path":
      return (
        <path
          className="sb-trace-stroke"
          d={shape.d}
          stroke={shape.stroke}
          style={style}
        />
      );
    case "line":
      return (
        <line
          className="sb-trace-stroke"
          x1={shape.x1}
          y1={shape.y1}
          x2={shape.x2}
          y2={shape.y2}
          stroke={shape.stroke}
          style={style}
        />
      );
    case "polyline":
      return (
        <polyline
          className="sb-trace-stroke"
          points={shape.points}
          stroke={shape.stroke}
          style={style}
        />
      );
    case "polygon":
      return (
        <polygon
          className="sb-trace-stroke"
          points={shape.points}
          stroke={shape.stroke}
          style={style}
        />
      );
    case "circle":
      return (
        <circle
          className="sb-trace-stroke"
          cx={shape.cx}
          cy={shape.cy}
          r={shape.r}
          stroke={shape.stroke}
          style={style}
        />
      );
    case "ellipse":
      return (
        <ellipse
          className="sb-trace-stroke"
          cx={shape.cx}
          cy={shape.cy}
          rx={shape.rx}
          ry={shape.ry}
          stroke={shape.stroke}
          style={style}
        />
      );
    case "rect":
      return (
        <rect
          className="sb-trace-stroke"
          x={shape.x}
          y={shape.y}
          width={shape.width}
          height={shape.height}
          stroke={shape.stroke}
          style={style}
        />
      );
    case "fallback_bounds": {
      const [x, y, w, h] = shape.bounds;
      return (
        <rect
          className="sb-trace-stroke sb-trace-stroke-fallback"
          x={x}
          y={y}
          width={w}
          height={h}
          stroke={DEFAULT_STROKE}
          style={style}
        />
      );
    }
  }
}
