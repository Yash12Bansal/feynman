import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import gsap from "gsap";
import type { ShowEquationInstruction } from "../../types/visuals";
import { COLORS } from "../theme";
import { useSyncManager } from "../useSyncManager";

export function EquationContent({
  instruction,
}: {
  instruction: ShowEquationInstruction;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const syncManager = useSyncManager();

  // Render KaTeX on mount / when latex changes
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    try {
      el.innerHTML = katex.renderToString(instruction.latex, {
        trust: true,
        throwOnError: false,
        displayMode: true,
      });
      el.removeAttribute("data-error");
    } catch {
      // Catastrophic fallback — show raw LaTeX as monospace
      el.textContent = instruction.latex;
      el.setAttribute("data-error", "true");
    }
  }, [instruction.latex]);

  // Run animation after KaTeX renders
  useEffect(() => {
    const el = containerRef.current;
    if (!el || el.hasAttribute("data-error")) return;

    const animation = instruction.animation ?? "fade_in";
    const durationSec = (instruction.duration_ms ?? 800) / 1000;

    // Kill any previous animation and cleanup sync registrations
    timelineRef.current?.kill();
    cleanupRef.current?.();
    cleanupRef.current = null;

    if (animation === "none") return;

    const tl = gsap.timeline();
    timelineRef.current = tl;

    switch (animation) {
      case "fade_in":
        tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: durationSec });
        break;

      case "term_by_term": {
        const terms = el.querySelectorAll<HTMLElement>('[id^="term-"]');
        if (terms.length === 0) {
          // No tagged terms — fall back to fade_in
          tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: durationSec });
          break;
        }
        gsap.set(terms, { opacity: 0 });

        if (
          instruction.sync_mode === "term_sync" &&
          instruction.term_hints &&
          syncManager
        ) {
          // SYNC MODE: terms reveal when trigger words are spoken
          const syncId = instruction.element_id ?? `eq-${Date.now()}`;
          const callbacks = new Map<string, () => void>();
          terms.forEach((term) => {
            callbacks.set(term.id, () => {
              gsap.to(term, {
                opacity: 1,
                duration: 0.25,
                ease: "power2.out",
              });
            });
          });
          const unregister = syncManager.register(
            syncId,
            instruction.term_hints,
            callbacks,
          );
          // Fallback: auto-reveal after duration if sync doesn't match all terms
          const fallbackTimer = window.setTimeout(() => {
            syncManager.revealAll(syncId);
          }, instruction.duration_ms ?? 8000);
          cleanupRef.current = () => {
            unregister();
            clearTimeout(fallbackTimer);
          };
        } else {
          // NON-SYNC MODE: auto-stagger (existing behavior)
          const stagger = durationSec / terms.length;
          tl.to(terms, {
            opacity: 1,
            duration: 0.3,
            stagger,
          });
        }
        break;
      }

      case "write_on":
        tl.fromTo(
          el,
          { clipPath: "inset(0 100% 0 0)" },
          { clipPath: "inset(0 0% 0 0)", duration: durationSec, ease: "none" },
        );
        break;
    }

    return () => {
      tl.kill();
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, [
    instruction.latex,
    instruction.animation,
    instruction.duration_ms,
    instruction.sync_mode,
    instruction.term_hints,
    instruction.element_id,
    syncManager,
  ]);

  return (
    <div>
      {instruction.label && (
        <div
          style={{
            fontSize: 20,
            fontStyle: "italic",
            lineHeight: "28px",
            color: COLORS.accentPurple,
            marginBottom: 12,
          }}
        >
          {instruction.label}
        </div>
      )}
      <div
        ref={containerRef}
        data-katex-target=""
        data-animation={instruction.animation ?? "fade_in"}
        style={{ textAlign: "center" }}
      />
    </div>
  );
}
