import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import gsap from "gsap";
import type { StepEquationInstruction } from "../../types/visuals";
import { COLORS } from "../theme";

export function StepEquationContent({
  instruction,
}: {
  instruction: StepEquationInstruction;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  // Render KaTeX for each step on mount / when steps change
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const stepEls = el.querySelectorAll<HTMLElement>("[data-step-katex]");
    stepEls.forEach((stepEl, i) => {
      const step = instruction.steps[i];
      if (!step) return;
      try {
        stepEl.innerHTML = katex.renderToString(step.latex, {
          trust: true,
          throwOnError: false,
          displayMode: true,
        });
      } catch {
        stepEl.textContent = step.latex;
      }
    });
  }, [instruction.steps]);

  // Animate steps after KaTeX renders
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const stepWrappers = el.querySelectorAll<HTMLElement>("[data-step]");
    if (stepWrappers.length === 0) return;

    timelineRef.current?.kill();

    const totalSteps = stepWrappers.length;
    const totalDuration =
      instruction.duration_ms != null
        ? instruction.duration_ms / 1000
        : (600 * totalSteps) / 1000;
    const stagger = totalDuration / totalSteps;

    const tl = gsap.timeline();
    timelineRef.current = tl;

    // Set all steps initially hidden
    gsap.set(stepWrappers, { opacity: 0, y: 10 });

    stepWrappers.forEach((wrapper, i) => {
      const isLast = i === totalSteps - 1;

      tl.to(
        wrapper,
        {
          opacity: 1,
          y: 0,
          duration: 0.3,
          ease: "power2.out",
        },
        i * stagger,
      );

      // Dim all previous steps when this step reveals
      if (i > 0) {
        const previousSteps = Array.from(stepWrappers).slice(0, i);
        tl.to(
          previousSteps,
          {
            opacity: 0.45,
            duration: 0.2,
          },
          i * stagger,
        );
      }

      // Highlight terms after the step reveals
      if (!isLast) return;
      const step = instruction.steps[i];
      if (!step?.highlight_terms?.length) return;

      const katexEl = wrapper.querySelector("[data-step-katex]");
      if (!katexEl) return;

      for (const termId of step.highlight_terms) {
        const termEl = katexEl.querySelector(`#${termId}`);
        if (termEl) {
          tl.to(
            termEl,
            {
              color: COLORS.accentAmber,
              duration: 0.2,
            },
            i * stagger + 0.3,
          );
        }
      }
    });

    return () => {
      tl.kill();
    };
  }, [instruction.steps, instruction.duration_ms]);

  return (
    <div ref={containerRef}>
      {instruction.title && (
        <div
          style={{
            fontSize: 20,
            fontStyle: "italic",
            lineHeight: "28px",
            color: COLORS.accentPurple,
            marginBottom: 16,
          }}
        >
          {instruction.title}
        </div>
      )}
      {instruction.steps.map((step, i) => (
        <div
          key={i}
          data-step={i}
          style={{
            marginBottom: i < instruction.steps.length - 1 ? 12 : 0,
          }}
        >
          {step.annotation && i > 0 && (
            <div
              data-step-annotation=""
              style={{
                fontSize: 14,
                fontStyle: "italic",
                color: COLORS.textSecondary,
                marginBottom: 6,
                paddingLeft: 16,
              }}
            >
              {"↳ "}
              {step.annotation}
            </div>
          )}
          <div data-step-katex="" style={{ textAlign: "center" }} />
        </div>
      ))}
    </div>
  );
}
