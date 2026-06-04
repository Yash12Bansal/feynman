/**
 * SlideAnnotationLayer — live-annotation overlay on the slide panel.
 *
 * Hosts the doc 19 §12 live-annotation primitives layered over the active
 * design diagram: TRACE (stroke-draw), MARK_POINT (dot/cross/star) and
 * WRITE_MARGIN (margin note). The FOCUS spotlight (dimming overlay) and the
 * POINT_AT pointer arrow were removed — they rendered broken (a full-board
 * gray wash and stray blue arrows) and the feature was cut.
 *
 * Live-DOM bounds resolution is preserved (this is the truth source for
 * positioning) and exported as `useResolvedBounds` for the primitives to
 * consume.
 *
 * Reduced-motion: the layer reflects `prefers-reduced-motion: reduce` via
 * a `data-reduced-motion` attribute. CSS in `SlideAnnotationLayer.css`
 * reads that attribute to disable annotation animations.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type RefObject,
} from "react";
import type {
  AnnotationTarget,
  ElementBounds,
  ElementMeta,
} from "../../../types/visuals";
import { TraceOverlay } from "./TraceOverlay";
import { MarkPoint } from "./MarkPoint";
import { MarginNote } from "./MarginNote";
import { Pointer } from "./Pointer";
import { resolveTarget } from "./resolveTarget";
import type {
  MarginNoteState,
  MarkPointState,
  PointerState,
  TraceState,
} from "./types";
import "./SlideAnnotationLayer.css";

interface SlideAnnotationLayerProps {
  readonly viewBox: string;
  readonly dictionary: Record<string, ElementMeta> | undefined;
  /**
   * Ref to the slide stage container. The layer queries it for
   * `[data-design-element]` to read live bounds via
   * `getBoundingClientRect()`. The diagram SVG and KaTeX overlays live
   * inside this subtree.
   */
  readonly stageRef?: RefObject<HTMLElement | null>;
  /**
   * Doc 19 §12 live-annotation primitives. Each list accumulates as the
   * lesson choreography emits events; show_diagram + clear_annotations wipe
   * them. Order within each list is render order (and arrival order).
   */
  readonly traces?: readonly TraceState[];
  readonly markPoints?: readonly MarkPointState[];
  readonly marginNotes?: readonly MarginNoteState[];
  readonly pointers?: readonly PointerState[];
}

// ── Multi-kind target resolution ─────────────────────────────

/** Query the live DOM for the element a role/id target points at. */
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
      // Dictionary role → element ids (shared resolver) → first one in the DOM.
      for (const id of resolveTarget(target, dictionary, undefined)) {
        const el = scope.querySelector(
          `[data-design-element="${cssEscape(id)}"]`,
        );
        if (el) return el;
      }
      return null;
    }

    case "color": {
      const escaped = cssEscape(target.value);
      return (
        scope.querySelector(`[stroke="${escaped}"]`) ??
        scope.querySelector(`[fill="${escaped}"]`)
      );
    }

    case "near_text": {
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
  return value.replace(/(["'\\[\] <>])/g, "\\$1");
}

/**
 * Convert a live DOM element's rect to viewBox-space bounds using the
 * overlay SVG as the reference frame.
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
 *   convert to viewBox via overlay SVG's screenCTM.
 * Path 2 (fallback): dictionary bounds. Only id/role kinds have one.
 */
export function resolveBounds(
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
  if (target.kind === "id") {
    return dictionary?.[target.value]?.bounds ?? null;
  }
  if (target.kind === "role") {
    for (const id of resolveTarget(target, dictionary, undefined)) {
      const b = dictionary?.[id]?.bounds;
      if (b) return b;
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

// ── Live-DOM bounds hook (exported for annotation primitives) ─

/**
 * `useResolvedBounds` resolves an element's bounds in the overlay's viewBox
 * space and KEEPS THEM CORRECT across the things that historically broke it:
 *
 *  - layout timing — measure in a layout effect (post-DOM, pre-paint), so the
 *    screenCTM is valid on the first paint, not one frame late;
 *  - fonts / KaTeX — re-measure after `document.fonts.ready` (+ one rAF), since
 *    text bounds are wrong until the math/web fonts settle;
 *  - responsive resize / zoom — a `ResizeObserver` on the stage re-measures.
 *
 * On any failure it returns `null` (the caller renders nothing) — never a
 * degenerate rect that could mis-place an annotation.
 */
export function useResolvedBounds(
  target: AnnotationTarget | null,
  stageRef: RefObject<HTMLElement | null> | undefined,
  overlayRef: RefObject<SVGSVGElement | null>,
  dictionary: Record<string, ElementMeta> | undefined,
): ElementBounds | null {
  // Lazy initial value: resolve synchronously on first render (dictionary
  // fallback, since the overlay ref isn't attached yet) so there's no flash of
  // "no annotation" before the layout effect upgrades to live-DOM bounds.
  const [bounds, setBounds] = useState<ElementBounds | null>(() =>
    target
      ? resolveBounds(target, stageRef, overlayRef.current, dictionary)
      : null,
  );
  // Mirror of `bounds` so the measure can commit CONDITIONALLY (only on real
  // change) — avoids redundant re-renders on every resize/rAF tick.
  const boundsRef = useRef<ElementBounds | null>(bounds);
  const commitBounds = useCallback((next: ElementBounds | null) => {
    if (!boundsEqual(boundsRef.current, next)) {
      boundsRef.current = next;
      setBounds(next);
    }
  }, []);

  useLayoutEffect(() => {
    if (!target) {
      commitBounds(null);
      return;
    }
    let alive = true;
    let raf = 0;
    const measure = () => {
      if (!alive) return;
      commitBounds(
        resolveBounds(target, stageRef, overlayRef.current, dictionary),
      );
    };

    measure(); // pre-paint pass

    // Fonts/KaTeX settle after layout — re-measure once they're ready.
    const fonts = (
      typeof document !== "undefined"
        ? (document as Document & { fonts?: { ready?: Promise<unknown> } })
            .fonts
        : undefined
    )?.ready;
    if (fonts) {
      fonts
        .then(() => {
          if (alive) raf = requestAnimationFrame(measure);
        })
        .catch(() => {});
    }

    const stage = stageRef?.current;
    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(measure)
        : null;
    if (ro && stage) ro.observe(stage);

    if (typeof window !== "undefined") {
      window.addEventListener("resize", measure);
    }

    return () => {
      alive = false;
      if (raf) cancelAnimationFrame(raf);
      ro?.disconnect();
      if (typeof window !== "undefined") {
        window.removeEventListener("resize", measure);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    target?.kind,
    target?.value,
    target?.attr,
    dictionary,
    stageRef,
    overlayRef,
  ]);

  return bounds;
}

function boundsEqual(
  a: ElementBounds | null,
  b: ElementBounds | null,
): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2] && a[3] === b[3];
}

// ── Overlay rect (measure-and-match) ─────────────────────────
//
// The diagram SVG is `width:100%` + aspect-ratio height, centred inside a
// padded `.sb-slide-live` box; the stage flex-centres it. So a stretched
// (`inset:0`) overlay does NOT coincide with the diagram — viewBox-space
// annotations land offset (this is the "random outlining" bug). We measure the
// diagram SVG (`[data-design-root]`) relative to the stage and size the overlay
// to it EXACTLY, so the overlay's viewBox space == the diagram's, pixel-for-
// pixel. Re-measures on fonts-ready, resize, and diagram swap.

interface OverlayRect {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

function useOverlayRect(
  stageRef: RefObject<HTMLElement | null> | undefined,
  /** Changes per diagram (viewBox string) — re-binds the measure to the new SVG. */
  rebindKey: string,
): OverlayRect | null {
  const [rect, setRect] = useState<OverlayRect | null>(null);
  const rectRef = useRef<OverlayRect | null>(null);

  useLayoutEffect(() => {
    const stage = stageRef?.current;
    if (!stage) return;
    let alive = true;
    let raf = 0;
    const measure = () => {
      if (!alive) return;
      const root = stage.querySelector("[data-design-root]");
      if (!root) return; // keep last good rect rather than blanking
      const r = root.getBoundingClientRect();
      const s = stage.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;
      const next: OverlayRect = {
        left: r.left - s.left,
        top: r.top - s.top,
        width: r.width,
        height: r.height,
      };
      // Commit only on real change (conditional setState).
      const p = rectRef.current;
      if (
        !p ||
        p.left !== next.left ||
        p.top !== next.top ||
        p.width !== next.width ||
        p.height !== next.height
      ) {
        rectRef.current = next;
        setRect(next);
      }
    };

    measure();

    const fonts = (
      typeof document !== "undefined"
        ? (document as Document & { fonts?: { ready?: Promise<unknown> } })
            .fonts
        : undefined
    )?.ready;
    if (fonts) {
      fonts
        .then(() => {
          if (alive) raf = requestAnimationFrame(measure);
        })
        .catch(() => {});
    }

    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(measure)
        : null;
    ro?.observe(stage);
    const root = stage.querySelector("[data-design-root]");
    if (root && ro) ro.observe(root);
    if (typeof window !== "undefined") {
      window.addEventListener("resize", measure);
    }

    return () => {
      alive = false;
      if (raf) cancelAnimationFrame(raf);
      ro?.disconnect();
      if (typeof window !== "undefined") {
        window.removeEventListener("resize", measure);
      }
    };
  }, [stageRef, rebindKey]);

  return rect;
}

// ── Layer ────────────────────────────────────────────────────

export function SlideAnnotationLayer({
  viewBox,
  dictionary,
  stageRef,
  traces,
  markPoints,
  marginNotes,
  pointers,
}: SlideAnnotationLayerProps) {
  const reduced = useReducedMotion();
  const overlayRef = useRef<SVGSVGElement>(null);
  // Size the overlay to coincide with the diagram SVG exactly (see hook docs).
  // viewBox is the rebind key — it changes whenever the diagram is swapped.
  const overlayRect = useOverlayRect(stageRef, viewBox);

  const style: CSSProperties = overlayRect
    ? {
        position: "absolute",
        left: overlayRect.left,
        top: overlayRect.top,
        width: overlayRect.width,
        height: overlayRect.height,
      }
    : // Pre-measurement fallback: overlap the stage. One layout-effect pass
      // later this is replaced by the measured (diagram-matching) rect.
      { position: "absolute", inset: 0 };

  return (
    <svg
      ref={overlayRef}
      className="sb-slide-annotations"
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      style={style}
      data-reduced-motion={reduced ? "true" : undefined}
      aria-hidden="true"
    >
      {/* Doc 19 §12: live-annotation primitives. They share the diagram's
       * viewBox space and resolve element bounds via useResolvedBounds. */}
      {traces?.map((t) => (
        <TraceOverlay
          key={`trace-${t.key}`}
          elementId={t.elementId}
          durationMs={t.durationMs}
          dictionary={dictionary}
          stageRef={stageRef}
        />
      ))}
      {markPoints?.map((m) => (
        <MarkPoint
          key={`mark-${m.key}`}
          x={m.x}
          y={m.y}
          kind={m.kind}
          label={m.label}
        />
      ))}
      {pointers?.map((p) => (
        <Pointer
          key={`pointer-${p.key}`}
          elementId={p.elementId}
          fromSide={p.fromSide}
          dictionary={dictionary}
          stageRef={stageRef}
          overlayRef={overlayRef}
        />
      ))}
      {marginNotes?.map((n) => (
        <MarginNote
          key={`margin-${n.key}`}
          anchorElementId={n.anchorElementId}
          side={n.side}
          text={n.text}
          dictionary={dictionary}
          stageRef={stageRef}
          overlayRef={overlayRef}
        />
      ))}
    </svg>
  );
}
