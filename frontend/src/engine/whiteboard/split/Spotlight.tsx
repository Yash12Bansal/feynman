/**
 * Spotlight — doc 18 attention-direction primitive.
 *
 * Visual: a dim full-slide overlay with a "hole" cut around the focused
 * element using SVG mask, plus an optional 2-3 word inline label next to
 * it. Replaces the 5 annotation components the prior system had.
 *
 * Lives inside `<SlideAnnotationLayer>`'s SVG so it shares the viewBox
 * coordinate space. Uses the exported `useResolvedBounds` hook to read
 * the focused element's bounds from the live DOM.
 *
 * `presentationMode`:
 *   - "overview" (default): dim everything else to ~50% opacity overlay;
 *     focused area stays bright.
 *   - "build_up": dim harder (~70%) so non-revealed elements feel almost
 *     hidden. Matches a teacher drawing one thing at a time.
 *
 * No focused role → renders nothing (the mask defaults to fully transparent
 * dim layer, which would dim the whole slide; we skip the overlay entirely).
 */

import { useId, type RefObject } from "react";
import type { ElementMeta } from "../../../types/visuals";
import { useResolvedBounds } from "./SlideAnnotationLayer";

interface SpotlightProps {
  /**
   * Stable element_id from the diagram's dictionary. Preferred selector
   * (doc 19 §A-3). When present, the spotlight resolves bounds by element_id
   * and ignores `focusedRole`. Falls back to `focusedRole` for back-compat
   * with extraction files generated before the element_id switch.
   */
  readonly focusedElementId?: string | null;
  readonly focusedRole: string | null;
  readonly inlineLabelText: string | null;
  readonly presentationMode: "build_up" | "overview";
  readonly dictionary: Record<string, ElementMeta> | undefined;
  readonly stageRef: RefObject<HTMLElement | null> | undefined;
  readonly overlayRef: RefObject<SVGSVGElement | null>;
}

// Viewport units in the slide SVG viewBox. The dim overlay covers the whole
// viewport with generous slop so it works regardless of the diagram's actual
// width/height (the design_agent picks 900×650 typically).
const COVER_X = -10_000;
const COVER_Y = -10_000;
const COVER_W = 20_000;
const COVER_H = 20_000;

// Padding around the focused element's bounds when cutting the spotlight
// hole, in viewBox units. Slight halo so the focused element doesn't touch
// the dim edge.
const SPOTLIGHT_PAD = 14;
const SPOTLIGHT_RADIUS = 12;

// Label sizing — kept small and unobtrusive.
const LABEL_FONT = 18;
const LABEL_PAD = 8;
const LABEL_GAP = 12;

export function Spotlight({
  focusedElementId,
  focusedRole,
  inlineLabelText,
  presentationMode,
  dictionary,
  stageRef,
  overlayRef,
}: SpotlightProps) {
  // React 19's useId returns ":r0:"-style IDs. SVG url(#…) cannot reference an
  // ID that contains colons in many browsers — the reference silently fails and
  // the dim overlay renders with no mask hole, washing out the whole diagram.
  // Strip the colons so the SVG mask actually resolves.
  const rawId = useId();
  const maskId = `sb-spot-${rawId.replace(/[^a-zA-Z0-9_-]/g, "")}`;

  // Doc 19 §A-3: prefer element_id (stable, unambiguous) over role (collides
  // across same-role elements). Null target → render nothing.
  const target = focusedElementId
    ? { kind: "id" as const, value: focusedElementId }
    : focusedRole
      ? { kind: "role" as const, value: focusedRole }
      : null;
  const bounds = useResolvedBounds(target, stageRef, overlayRef, dictionary);
  const hasFocus = Boolean(focusedElementId || focusedRole);

  if (!hasFocus || !bounds) {
    // No focus or bounds not yet resolvable — render nothing. CSS transitions
    // on the parent's data-focused-role still fire on transitions.
    return null;
  }

  const [x, y, w, h] = bounds;
  const holeX = x - SPOTLIGHT_PAD;
  const holeY = y - SPOTLIGHT_PAD;
  const holeW = w + SPOTLIGHT_PAD * 2;
  const holeH = h + SPOTLIGHT_PAD * 2;

  // Opacity of the dim overlay. Build-up dims harder.
  const dimOpacity = presentationMode === "build_up" ? 0.7 : 0.5;

  // Label position: above the focused element if there's room, else below.
  // Approx — the layer's viewBox y origin is the top, so smaller y is up.
  const labelX = x + w / 2;
  const labelY = y - LABEL_GAP;

  return (
    <g
      className="sb-spotlight"
      data-focused-role={focusedRole ?? undefined}
      data-focused-element-id={focusedElementId ?? undefined}
      data-presentation-mode={presentationMode}
    >
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse">
          {/* White = visible overlay; Black = hole (no overlay drawn). */}
          <rect
            x={COVER_X}
            y={COVER_Y}
            width={COVER_W}
            height={COVER_H}
            fill="white"
          />
          <rect
            x={holeX}
            y={holeY}
            width={holeW}
            height={holeH}
            rx={SPOTLIGHT_RADIUS}
            ry={SPOTLIGHT_RADIUS}
            fill="black"
          />
        </mask>
      </defs>

      {/* Dim overlay everywhere except the spotlight hole. */}
      <rect
        className="sb-spotlight-dim"
        x={COVER_X}
        y={COVER_Y}
        width={COVER_W}
        height={COVER_H}
        fill="rgba(8, 8, 16, 1)"
        opacity={dimOpacity}
        mask={`url(#${maskId})`}
      />

      {/* Subtle outline around the spotlight hole — a soft highlight ring. */}
      <rect
        className="sb-spotlight-ring"
        x={holeX}
        y={holeY}
        width={holeW}
        height={holeH}
        rx={SPOTLIGHT_RADIUS}
        ry={SPOTLIGHT_RADIUS}
        fill="none"
      />

      {/* Optional inline label. */}
      {inlineLabelText && (
        <SpotlightLabel
          x={labelX}
          y={labelY}
          text={inlineLabelText}
          fallbackBelowY={y + h + LABEL_GAP + LABEL_FONT}
        />
      )}
    </g>
  );
}

function SpotlightLabel({
  x,
  y,
  text,
  fallbackBelowY,
}: {
  readonly x: number;
  readonly y: number;
  readonly text: string;
  readonly fallbackBelowY: number;
}) {
  // Approximate text width — used to size the pill background.
  const textWidth = Math.max(40, text.length * LABEL_FONT * 0.55);
  const pillW = textWidth + LABEL_PAD * 2;
  const pillH = LABEL_FONT + LABEL_PAD;

  // If the label would render off the top of typical slide content (y < 30),
  // flip to below the focused element. Cheap heuristic — works for the
  // typical 900×650 viewBox.
  const effectiveY = y - pillH < 0 ? fallbackBelowY : y;
  const pillX = x - pillW / 2;
  const pillY = effectiveY - pillH;

  return (
    <g className="sb-spotlight-label">
      <rect
        className="sb-spotlight-label-pill"
        x={pillX}
        y={pillY}
        width={pillW}
        height={pillH}
        rx={pillH / 2}
        ry={pillH / 2}
      />
      <text
        className="sb-spotlight-label-text"
        x={x}
        y={pillY + pillH / 2 + LABEL_FONT * 0.35}
        textAnchor="middle"
        fontSize={LABEL_FONT}
      >
        {text}
      </text>
    </g>
  );
}
