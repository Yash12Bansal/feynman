import { useRef, useEffect } from "react";
import type { ReactNode } from "react";
import type { VisualInstruction } from "../types/visuals";
import { useElementRegistry } from "./elements";

interface VisualCardProps {
  instruction: VisualInstruction;
  children: ReactNode;
}

export function VisualCard({ instruction, children }: VisualCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const registry = useElementRegistry();
  const elementId = instruction.element_id;

  useEffect(() => {
    const node = cardRef.current;
    if (!node || !elementId) return;

    registry.register(elementId, node, instruction);
    return () => registry.unregister(elementId);
  }, [elementId, registry, instruction]);

  return (
    <div
      ref={cardRef}
      className="visual-card"
      data-type={instruction.type}
      data-element-id={elementId}
    >
      {children}
    </div>
  );
}
