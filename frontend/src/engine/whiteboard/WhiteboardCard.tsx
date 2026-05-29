// TODO(DEADCODE): file unused in active pipelines (lecture-playback / ask-feynman) — interactive live-agent rendering (parked). See docs/engineering/13-redundant-code-audit.md Group 1/2. Safe to delete.
// import { useRef, useEffect } from "react";
// import type { ReactNode } from "react";
// import type { VisualInstruction } from "../../types/visuals";
// import { useElementRegistry } from "../elements";

// interface WhiteboardCardProps {
//   instruction: VisualInstruction;
//   children: ReactNode;
// }

// /**
//  * Registers an instruction element in the ElementRegistry for HighlightOverlay
//  * targeting. Renders as a flow element within its zone container — no card
//  * styling, no accent stripes (whiteboard aesthetic is spatial, not card-list).
//  */
// export function WhiteboardCard({ instruction, children }: WhiteboardCardProps) {
//   const cardRef = useRef<HTMLDivElement>(null);
//   const registry = useElementRegistry();
//   const elementId = instruction.element_id;

//   useEffect(() => {
//     const node = cardRef.current;
//     if (!node || !elementId) return;

//     registry.register(elementId, node, instruction);
//     return () => registry.unregister(elementId);
//   }, [elementId, registry, instruction]);

//   return (
//     <div
//       ref={cardRef}
//       className="wb-card"
//       data-type={instruction.type}
//       data-element-id={elementId}
//     >
//       {children}
//     </div>
//   );
// }
