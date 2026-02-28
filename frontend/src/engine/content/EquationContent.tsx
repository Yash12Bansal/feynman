import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import gsap from "gsap";
import type { ShowEquationInstruction } from "../../types/visuals";
import { COLORS } from "../theme";

export function EquationContent({
  instruction,
}: {
  instruction: ShowEquationInstruction;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

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

    // Kill any previous animation
    timelineRef.current?.kill();

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
        const stagger = durationSec / terms.length;
        gsap.set(terms, { opacity: 0 });
        tl.to(terms, {
          opacity: 1,
          duration: 0.3,
          stagger,
        });
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
    };
  }, [instruction.latex, instruction.animation, instruction.duration_ms]);

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
