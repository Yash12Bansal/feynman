/**
 * Transition orchestrator for multi-board navigation.
 *
 * Wraps the active board surface in a .wb-board-layer and runs GSAP
 * animations when the agent switches boards:
 *
 * - new:       slide in from right  (0.5s)
 * - revisit:   slide in from left   (0.5s)
 * - reference: PiP peek overlay     (fade in → hold → fade out)
 *
 * Respects prefers-reduced-motion (instant swaps, no animation).
 */

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import gsap from "gsap";
import type { BoardTransition, BoardMeta } from "./useBoardStore";
import type { VisualInstruction } from "../../types/visuals";
import { WhiteboardSceneSnapshot } from "./WhiteboardSceneSnapshot";

const TRANSITION_DURATION = 0.5;
const PEEK_HOLD_DEFAULT = 3;
const PEEK_FADE_IN = 0.3;
const PEEK_FADE_OUT = 0.3;

export interface BoardNavigatorProps {
  activeBoardMeta: BoardMeta | null;
  pendingTransition: BoardTransition | null;
  onTransitionComplete: () => void;
  getBoardInstructions: (boardId: string) => VisualInstruction[];
  children: ReactNode;
}

export function BoardNavigator({
  activeBoardMeta,
  pendingTransition,
  onTransitionComplete,
  getBoardInstructions,
  children,
}: BoardNavigatorProps) {
  const layerRef = useRef<HTMLDivElement>(null);
  const peekRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  // Derive peek instructions from transition — no state, no effect setState.
  // When transition is reference, peek element renders in the same commit,
  // so peekRef.current is available when the effect runs.
  const peekInstructions =
    pendingTransition?.intent === "reference"
      ? getBoardInstructions(pendingTransition.to)
      : null;

  useEffect(() => {
    if (!pendingTransition) return;

    const layer = layerRef.current;
    if (!layer) return;

    // Kill any in-progress animation
    if (timelineRef.current) {
      timelineRef.current.kill();
      timelineRef.current = null;
    }
    // Clear GSAP inline styles from previous transitions
    gsap.set(layer, { clearProps: "x,opacity" });

    const { intent, durationMs } = pendingTransition;
    const prefersReduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (intent === "reference") {
      const peekEl = peekRef.current;
      if (!peekEl) {
        onTransitionComplete();
        return;
      }

      const holdTime =
        durationMs != null ? durationMs / 1000 : PEEK_HOLD_DEFAULT;

      if (prefersReduced) {
        const tl = gsap.timeline({ onComplete: onTransitionComplete });
        timelineRef.current = tl;
        tl.to({}, { duration: holdTime });
      } else {
        const tl = gsap.timeline({ onComplete: onTransitionComplete });
        timelineRef.current = tl;

        // Dim active board + fade in peek simultaneously
        tl.to(
          layer,
          { opacity: 0.4, duration: PEEK_FADE_IN, ease: "power2.out" },
          0,
        );
        tl.fromTo(
          peekEl,
          { opacity: 0, scale: 0.9 },
          {
            opacity: 1,
            scale: 1,
            duration: PEEK_FADE_IN,
            ease: "power2.out",
          },
          0,
        );

        // Hold
        tl.to({}, { duration: holdTime });

        // Fade out peek + restore active board
        tl.to(peekEl, {
          opacity: 0,
          duration: PEEK_FADE_OUT,
          ease: "power2.in",
        });
        tl.to(
          layer,
          { opacity: 1, duration: PEEK_FADE_OUT, ease: "power2.out" },
          `>-${PEEK_FADE_OUT}`,
        );
      }
    } else if (prefersReduced) {
      onTransitionComplete();
    } else {
      // Slide in from right (new) or left (revisit)
      const fromX = intent === "revisit" ? "-100%" : "100%";
      const tl = gsap.timeline({ onComplete: onTransitionComplete });
      timelineRef.current = tl;
      tl.fromTo(
        layer,
        { x: fromX, opacity: 0 },
        {
          x: "0%",
          opacity: 1,
          duration: TRANSITION_DURATION,
          ease: "power2.out",
        },
      );
    }

    return () => {
      if (timelineRef.current) {
        timelineRef.current.kill();
        timelineRef.current = null;
      }
      if (layer) gsap.set(layer, { clearProps: "x,opacity" });
    };
  }, [pendingTransition, onTransitionComplete, getBoardInstructions]);

  // Key the label on the board ID so CSS animation re-triggers on switch
  const labelKey = activeBoardMeta?.id ?? "";

  return (
    <div className="wb-navigator">
      <div ref={layerRef} className="wb-board-layer">
        {children}
      </div>

      {peekInstructions && (
        <div ref={peekRef} className="wb-board-peek">
          <WhiteboardSceneSnapshot instructions={peekInstructions} />
        </div>
      )}

      {activeBoardMeta?.label && (
        <div key={labelKey} className="wb-board-label">
          {activeBoardMeta.label}
        </div>
      )}
    </div>
  );
}
