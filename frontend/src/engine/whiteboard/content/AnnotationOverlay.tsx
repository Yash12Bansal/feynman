/**
 * Renders a single freehand annotation mark (circle, underline, or arrow).
 *
 * Pipeline:
 * 1. Look up target element(s) via ElementRegistry
 * 2. Convert getBoundingClientRect() → board-space coords
 * 3. Generate input points via pure math functions
 * 4. Pass through Perfect Freehand → outline polygon
 * 5. Render as filled SVG <path> masked by a centerline stroke path
 * 6. GSAP animates mask strokeDashoffset (draw-in) → hold → fade out
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import gsap from "gsap";
import type { AnnotateInstruction } from "../../../types/visuals";
import { useElementRegistry } from "../../elements";
import { COLORS } from "../../theme";
import { ALIVE_FILTER_ID } from "../AliveFilter";
import { viewportToBoard } from "../board-coords";
import {
  annotationSeed,
  bezierCenterline,
  computeArrowhead,
  ellipseCenterline,
  estimatePathLength,
  inputPointsToPath,
  lineCenterline,
  sampleEllipse,
  sampleLine,
  sampleQuadBezier,
} from "./annotation-paths";

// ── Constants ─────────────────────────────────────────────────

const DRAW_DURATION = 0.6; // seconds
const HOLD_DURATION = 2.0;
const FADE_DURATION = 0.4;
const PADDING = 16; // extra space around target for circle/underline
const MASK_ID_PREFIX = "ann-mask-";

// ── Component ─────────────────────────────────────────────────

export interface AnnotationOverlayProps {
  instruction: AnnotateInstruction;
  boardRef: RefObject<HTMLDivElement | null>;
  scale: number;
}

export function AnnotationOverlay({
  instruction,
  boardRef,
  scale,
}: AnnotationOverlayProps) {
  const registry = useElementRegistry();
  const groupRef = useRef<SVGGElement>(null);
  const maskPathRef = useRef<SVGPathElement>(null);
  const [visible, setVisible] = useState(true);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);
  const { action, target_id, from_id, to_id, color, duration_ms } = instruction;

  const strokeColor = color || COLORS.accentRed;
  const holdTime = duration_ms != null ? duration_ms / 1000 : HOLD_DURATION;

  const buildAnnotation = useCallback(() => {
    const boardEl = boardRef.current;
    if (!boardEl) return null;
    const boardRect = boardEl.getBoundingClientRect();

    if (action === "circle" || action === "underline") {
      const entry = registry.get(target_id ?? "");
      if (!entry) return null;
      const rect = viewportToBoard(
        entry.ref.getBoundingClientRect(),
        boardRect,
        scale,
      );
      const seed = annotationSeed(target_id ?? "circle");

      if (action === "circle") {
        const cx = rect.x + rect.width / 2;
        const cy = rect.y + rect.height / 2;
        const rx = rect.width / 2 + PADDING;
        const ry = rect.height / 2 + PADDING;
        const points = sampleEllipse(cx, cy, rx, ry, 72, seed);
        const fillPath = inputPointsToPath(points);
        const centerline = ellipseCenterline(cx, cy, rx, ry);
        const pathLen = estimatePathLength("ellipse", { rx, ry });
        return { fillPath, centerline, pathLen };
      } else {
        // underline
        const x1 = rect.x - 4;
        const y1 = rect.y + rect.height + 6;
        const x2 = rect.x + rect.width + 4;
        const y2 = y1;
        const points = sampleLine(x1, y1, x2, y2, 32, seed);
        const fillPath = inputPointsToPath(points);
        const centerline = lineCenterline(x1, y1, x2, y2);
        const pathLen = estimatePathLength("line", { x1, y1, x2, y2 });
        return { fillPath, centerline, pathLen };
      }
    } else if (action === "arrow") {
      const fromEntry = registry.get(from_id ?? "");
      const toEntry = registry.get(to_id ?? "");
      if (!fromEntry || !toEntry) return null;

      const fromRect = viewportToBoard(
        fromEntry.ref.getBoundingClientRect(),
        boardRect,
        scale,
      );
      const toRect = viewportToBoard(
        toEntry.ref.getBoundingClientRect(),
        boardRect,
        scale,
      );

      const p0: [number, number] = [
        fromRect.x + fromRect.width / 2,
        fromRect.y + fromRect.height / 2,
      ];
      const p2: [number, number] = [
        toRect.x + toRect.width / 2,
        toRect.y + toRect.height / 2,
      ];
      // Control point: offset perpendicular to midpoint
      const mx = (p0[0] + p2[0]) / 2;
      const my = (p0[1] + p2[1]) / 2;
      const dx = p2[0] - p0[0];
      const dy = p2[1] - p0[1];
      const dist = Math.sqrt(dx * dx + dy * dy);
      const offset = Math.min(dist * 0.25, 80);
      const cp: [number, number] = [
        mx - (dy / dist) * offset,
        my + (dx / dist) * offset,
      ];

      const seed = annotationSeed(`${from_id}-${to_id}`);
      const points = sampleQuadBezier(p0, cp, p2, 48, seed);
      const fillPath = inputPointsToPath(points);
      const centerline = bezierCenterline(p0, cp, p2);
      const pathLen = estimatePathLength("bezier", { p0, cp, p2 });

      // Arrowhead at endpoint
      const angle = Math.atan2(p2[1] - cp[1], p2[0] - cp[0]);
      const arrowhead = computeArrowhead(p2, angle);
      const arrowPath = `M ${arrowhead.tip[0]} ${arrowhead.tip[1]} L ${arrowhead.left[0]} ${arrowhead.left[1]} L ${arrowhead.right[0]} ${arrowhead.right[1]} Z`;

      return { fillPath, centerline, pathLen, arrowPath };
    }
    return null;
  }, [action, boardRef, from_id, registry, scale, target_id, to_id]);

  useEffect(() => {
    let retryFrame: number | undefined;

    function tryRender() {
      const data = buildAnnotation();
      if (!data) {
        // Target not yet mounted — retry next frame
        retryFrame = requestAnimationFrame(tryRender);
        return;
      }

      const group = groupRef.current;
      const maskPath = maskPathRef.current;
      if (!group || !maskPath) return;

      // Set mask path
      maskPath.setAttribute("d", data.centerline);
      const len = data.pathLen;
      maskPath.style.strokeDasharray = `${len}`;
      maskPath.style.strokeDashoffset = `${len}`;

      // Set fill path(s) on the group's children
      const fillEl = group.querySelector<SVGPathElement>("[data-fill]");
      if (fillEl) fillEl.setAttribute("d", data.fillPath);

      const arrowEl = group.querySelector<SVGPathElement>("[data-arrow]");
      if (arrowEl && "arrowPath" in data && data.arrowPath) {
        arrowEl.setAttribute("d", data.arrowPath);
      }

      // Animate
      const tl = gsap.timeline({
        onComplete: () => setVisible(false),
      });
      timelineRef.current = tl;

      // Draw-in: animate mask strokeDashoffset to 0
      tl.to(maskPath, {
        strokeDashoffset: 0,
        duration: DRAW_DURATION,
        ease: "power2.out",
      });

      // Hold
      tl.to(group, { duration: holdTime });

      // Fade out
      tl.to(group, {
        opacity: 0,
        duration: FADE_DURATION,
        ease: "power2.in",
      });
    }

    tryRender();

    return () => {
      if (retryFrame != null) cancelAnimationFrame(retryFrame);
      if (timelineRef.current) timelineRef.current.kill();
    };
  }, [buildAnnotation, holdTime]);

  if (!visible) return null;

  // Unique mask ID per instruction
  const maskId = `${MASK_ID_PREFIX}${instruction.element_id ?? action}`;

  return (
    <g ref={groupRef} style={{ filter: `url(#${ALIVE_FILTER_ID})` }}>
      <defs>
        <mask id={maskId}>
          <path
            ref={maskPathRef}
            stroke="white"
            strokeWidth="20"
            fill="none"
            strokeLinecap="round"
          />
        </mask>
      </defs>
      <g mask={`url(#${maskId})`}>
        <path data-fill="" fill={strokeColor} fillOpacity={0.85} />
        {action === "arrow" && (
          <path data-arrow="" fill={strokeColor} fillOpacity={0.9} />
        )}
      </g>
    </g>
  );
}
