/**
 * SlideAnnotationLayer — doc 18 spotlight overlay on the slide panel.
 *
 * Renders ONE thing at a time: a `<Spotlight>` for the currently focused
 * role on the active design diagram. The 5-marker annotation system
 * (pin_label / draw_callout / bracket / highlight_pulse) and the four
 * sub-components that rendered them were deleted per doc 18 §3 — see
 * `docs/design/18-attention-direction-redesign.md`.
 *
 * Live-DOM bounds resolution is preserved (this is the truth source for
 * positioning) and exported as `useResolvedBounds` for the Spotlight
 * component to consume.
 *
 * Reduced-motion: the layer reflects `prefers-reduced-motion: reduce` via
 * a `data-reduced-motion` attribute. CSS in `SlideAnnotationLayer.css`
 * reads that attribute to disable spotlight transitions.
 */

import { useEffect, useRef, useState, type RefObject } from "react";
import type {
  AnnotationTarget,
  ElementBounds,
  ElementMeta,
} from "../../../types/visuals";
import { Spotlight } from "./Spotlight";
import { TraceOverlay } from "./TraceOverlay";
import { MarkPoint } from "./MarkPoint";
import { Pointer } from "./Pointer";
import { MarginNote } from "./MarginNote";
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
   * Stable element_id from the diagram's dictionary (doc 19 §A-3 preferred
   * selector). When present, the spotlight ignores `focusedRole` and resolves
   * bounds directly by id.
   */
  readonly focusedElementId?: string | null;
  /**
   * Role currently in focus (deprecated alias; back-compat with extraction
   * files generated before the element_id switch). Null/undefined when
   * nothing is focused.
   */
  readonly focusedRole: string | null | undefined;
  /**
   * Optional 2-3 word inline label rendered next to the focused element.
   */
  readonly inlineLabelText?: string | null;
  /**
   * Doc 18 §4.3: dim treatment for the rest of the diagram. "build_up"
   * dims harder (non-revealed elements are invisible-ish); "overview"
   * dims softly. Defaults to "overview".
   */
  readonly presentationMode?: "build_up" | "overview";
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
   * all four. Order within each list is render order (and arrival order).
   */
  readonly traces?: readonly TraceState[];
  readonly markPoints?: readonly MarkPointState[];
  readonly pointers?: readonly PointerState[];
  readonly marginNotes?: readonly MarginNoteState[];
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

// ── Live-DOM bounds hook (exported for Spotlight) ─────────────

/**
 * `useResolvedBounds` recomputes bounds on every layout pass tied to
 * `target`. The screenCTM is only valid post-render, so we resolve in
 * a layout effect and store in state — the first render gets dictionary
 * bounds (or null), the second gets live-DOM bounds.
 */
export function useResolvedBounds(
  target: AnnotationTarget | null,
  stageRef: RefObject<HTMLElement | null> | undefined,
  overlayRef: RefObject<SVGSVGElement | null>,
  dictionary: Record<string, ElementMeta> | undefined,
): ElementBounds | null {
  const [bounds, setBounds] = useState<ElementBounds | null>(() =>
    target
      ? resolveBounds(target, stageRef, overlayRef.current, dictionary)
      : null,
  );

  useEffect(() => {
    if (!target) {
      setBounds(null);
      return;
    }
    const next = resolveBounds(
      target,
      stageRef,
      overlayRef.current,
      dictionary,
    );
    setBounds(next);
    if (typeof window === "undefined") return;
    const onResize = () => {
      setBounds(
        resolveBounds(target, stageRef, overlayRef.current, dictionary),
      );
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
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

// ── Layer ────────────────────────────────────────────────────

export function SlideAnnotationLayer({
  viewBox,
  dictionary,
  focusedElementId,
  focusedRole,
  inlineLabelText,
  presentationMode,
  stageRef,
  traces,
  markPoints,
  pointers,
  marginNotes,
}: SlideAnnotationLayerProps) {
  const reduced = useReducedMotion();
  const overlayRef = useRef<SVGSVGElement>(null);

  // Render the SVG overlay even when there's no focus — that lets the
  // Spotlight component's CSS transitions reset cleanly when focus changes.
  return (
    <svg
      ref={overlayRef}
      className="sb-slide-annotations"
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      data-reduced-motion={reduced ? "true" : undefined}
      data-presentation-mode={presentationMode ?? "overview"}
      data-focused-role={focusedRole ?? undefined}
      data-focused-element-id={focusedElementId ?? undefined}
      aria-hidden="true"
    >
      <Spotlight
        focusedElementId={focusedElementId ?? null}
        focusedRole={focusedRole ?? null}
        inlineLabelText={inlineLabelText ?? null}
        presentationMode={presentationMode ?? "overview"}
        dictionary={dictionary}
        stageRef={stageRef}
        overlayRef={overlayRef}
      />
      {/* Doc 19 §12: live-annotation primitives layered on top of the
       * spotlight dim. They share the same viewBox space and resolve element
       * bounds via the same useResolvedBounds path. */}
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
