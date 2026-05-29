// TODO(DEADCODE): file unused in active pipelines (lecture-playback / ask-feynman) — interactive live-agent rendering (parked). See docs/engineering/13-redundant-code-audit.md Group 1/2. Safe to delete.
// /**
//  * Lightweight inert board for peek overlays.
//  *
//  * Renders the same zone layout and cards as WhiteboardScene but without:
//  * - AliveFilter (no organic wobble)
//  * - AnnotationLayer (no freehand marks)
//  * - HighlightOverlay (no highlights)
//  * - Card-enter animations (CSS class .wb-snapshot disables them)
//  *
//  * Provides its own ElementRegistryContext to avoid conflicts with the
//  * active board's registry. pointer-events: none (set via .wb-board-peek
//  * in CSS) makes it read-only.
//  */

// import { useMemo } from "react";
// import type { VisualInstruction } from "../../types/visuals";
// import type { BoardZone } from "./types";
// import { BOARD_WIDTH, BOARD_HEIGHT } from "./types";
// import { computeBoardLayout } from "./zone-layout";
// import { BoardLayoutContext } from "./board-layout-context";
// import { ElementRegistryContext, useCreateElementRegistry } from "../elements";
// import { WhiteboardCard } from "./WhiteboardCard";
// import { InstructionSwitch } from "./InstructionSwitch";

// const DEFAULT_ZONE: BoardZone = "center-center";

// export interface WhiteboardSceneSnapshotProps {
//   instructions: VisualInstruction[];
// }

// export function WhiteboardSceneSnapshot({
//   instructions,
// }: WhiteboardSceneSnapshotProps) {
//   const registry = useCreateElementRegistry();
//   const layout = useMemo(() => computeBoardLayout(), []);

//   // Filter to renderable elements only (skip clear, highlight, annotate, switch_board)
//   const elements = useMemo(() => {
//     const elems: VisualInstruction[] = [];
//     for (const instr of instructions) {
//       if (
//         instr.type !== "clear" &&
//         instr.type !== "highlight" &&
//         instr.type !== "annotate" &&
//         instr.type !== "switch_board"
//       ) {
//         elems.push(instr);
//       }
//     }
//     return elems;
//   }, [instructions]);

//   // Group by zone
//   const zoneGroups = useMemo(() => {
//     const groups = new Map<BoardZone, VisualInstruction[]>();
//     for (const instr of elements) {
//       const zone = instr.zone ?? DEFAULT_ZONE;
//       let list = groups.get(zone);
//       if (!list) {
//         list = [];
//         groups.set(zone, list);
//       }
//       list.push(instr);
//     }
//     return groups;
//   }, [elements]);

//   return (
//     <BoardLayoutContext.Provider value={layout}>
//       <ElementRegistryContext.Provider value={registry}>
//         <div
//           className="wb-snapshot"
//           style={{ width: BOARD_WIDTH, height: BOARD_HEIGHT }}
//         >
//           <div className="wb-board-surface">
//             {Array.from(zoneGroups.entries()).map(
//               ([zone, zoneInstructions]) => {
//                 const { inner } = layout.zones[zone];
//                 return (
//                   <div
//                     key={zone}
//                     className="wb-zone"
//                     data-zone={zone}
//                     style={{
//                       left: inner.x,
//                       top: inner.y,
//                       width: inner.width,
//                       height: inner.height,
//                     }}
//                   >
//                     {zoneInstructions.map((instr, idx) => (
//                       <WhiteboardCard
//                         key={instr.element_id ?? `wb-snap-${zone}-${idx}`}
//                         instruction={instr}
//                       >
//                         <InstructionSwitch instruction={instr} />
//                       </WhiteboardCard>
//                     ))}
//                   </div>
//                 );
//               },
//             )}
//           </div>
//         </div>
//       </ElementRegistryContext.Provider>
//     </BoardLayoutContext.Provider>
//   );
// }
