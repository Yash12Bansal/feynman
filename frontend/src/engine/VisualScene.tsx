import { useEffect, useMemo, useRef } from "react";
import type { VisualInstruction, HighlightInstruction } from "../types/visuals";
import { ElementRegistryContext, useCreateElementRegistry } from "./elements";
import { injectThemeVars } from "./theme";
import { VisualCard } from "./VisualCard";
import { InstructionSwitch } from "./InstructionSwitch";
import { HighlightOverlay } from "./content/HighlightOverlay";
import "./VisualScene.css";

interface VisualSceneProps {
  instructions: VisualInstruction[];
}

export function VisualScene({ instructions }: VisualSceneProps) {
  const registry = useCreateElementRegistry();
  const viewportRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(0);

  // Separate renderable elements from effects
  const { elements, highlights } = useMemo(() => {
    const elems: VisualInstruction[] = [];
    const hlights: HighlightInstruction[] = [];

    for (const instr of instructions) {
      if (instr.type === "highlight") {
        hlights.push(instr);
      } else if (instr.type !== "clear") {
        elems.push(instr);
      }
    }

    return { elements: elems, highlights: hlights };
  }, [instructions]);

  // Inject theme CSS variables on mount
  useEffect(() => {
    if (viewportRef.current) {
      injectThemeVars(viewportRef.current);
    }
  }, []);

  // Auto-scroll when new elements arrive
  useEffect(() => {
    if (elements.length > prevCountRef.current && viewportRef.current) {
      const cards = viewportRef.current.querySelectorAll(".visual-card");
      const lastCard = cards[cards.length - 1];
      if (lastCard) {
        lastCard.scrollIntoView?.({ behavior: "smooth", block: "end" });
      }
    }
    prevCountRef.current = elements.length;
  }, [elements.length]);

  return (
    <ElementRegistryContext.Provider value={registry}>
      <div ref={viewportRef} className="scene-viewport">
        <div className="scene-content">
          {elements.map((instr, idx) => (
            <VisualCard
              key={instr.element_id ?? `instr-${idx}`}
              instruction={instr}
            >
              <InstructionSwitch instruction={instr} />
            </VisualCard>
          ))}
        </div>
      </div>
      {highlights.map((h, idx) => (
        <HighlightOverlay
          key={`highlight-${h.target_id}-${idx}`}
          instruction={h}
        />
      ))}
    </ElementRegistryContext.Provider>
  );
}
