import { useDataChannel } from "@livekit/components-react";
import { useCallback, useRef, useState } from "react";
import type {
  VisualInstruction,
  SwitchBoardInstruction,
  ClearInstruction,
  HighlightWalkInstruction,
} from "../types/visuals";
import { useBoardStore } from "../engine/whiteboard/useBoardStore";
import type {
  BoardMeta,
  BoardTransition,
} from "../engine/whiteboard/useBoardStore";

export interface VisualChannelResult {
  lastInstruction: VisualInstruction | null;
  /** Flat instruction array — legacy compat for non-whiteboard renderers. */
  instructions: VisualInstruction[];
  /** Active board's instructions — use for WhiteboardScene. */
  activeInstructions: VisualInstruction[];
  /** Active highlight walks — ephemeral, not stored in board. */
  activeWalks: HighlightWalkInstruction[];
  activeBoardId: string;
  activeBoardMeta: BoardMeta | null;
  pendingTransition: BoardTransition | null;
  clearTransition: () => void;
  getBoardInstructions: (boardId: string) => VisualInstruction[];
  getBoardMeta: (boardId: string) => BoardMeta | null;
}

export function useVisualChannel(): VisualChannelResult {
  const [lastInstruction, setLastInstruction] =
    useState<VisualInstruction | null>(null);
  // Legacy flat array for non-whiteboard renderers (VisualScene card-list)
  const instructionsRef = useRef<VisualInstruction[]>([]);
  const [instructions, setInstructions] = useState<VisualInstruction[]>([]);

  // Highlight walks are ephemeral — separate channel, not stored in board.
  const [activeWalks, setActiveWalks] = useState<HighlightWalkInstruction[]>(
    [],
  );

  const store = useBoardStore();
  // Destructure stable methods (all wrapped in useCallback with [] deps)
  const { switchBoard, addInstruction, clearBoard } = store;

  const onMessage = useCallback(
    (msg: { payload: Uint8Array; topic?: string; from?: unknown }) => {
      try {
        const text = new TextDecoder().decode(msg.payload);
        const parsed = JSON.parse(text) as VisualInstruction;

        if (parsed.type === "switch_board") {
          switchBoard(parsed as SwitchBoardInstruction);
          // Clear walks on board switch — they're tied to the current board
          setActiveWalks([]);
        } else if (parsed.type === "clear") {
          const clear = parsed as ClearInstruction;
          // boardId defaults to active board inside clearBoard when undefined
          clearBoard(clear.board_id, clear.target_id);

          // Legacy flat array
          if (clear.target_id) {
            instructionsRef.current = instructionsRef.current.filter(
              (i) => i.element_id !== clear.target_id,
            );
          } else {
            instructionsRef.current = [];
          }

          // Clear walks if board is cleared
          if (!clear.target_id) {
            setActiveWalks([]);
          }
        } else if (parsed.type === "highlight_walk") {
          // Ephemeral — don't store in board (avoids re-render of diagram cards)
          setActiveWalks((prev) => [
            ...prev,
            parsed as HighlightWalkInstruction,
          ]);
        } else {
          addInstruction(parsed);

          // Legacy flat array
          instructionsRef.current = [...instructionsRef.current, parsed];
        }

        setInstructions(instructionsRef.current);
        setLastInstruction(parsed);
      } catch (err) {
        console.error("[VisualChannel] Failed to parse:", err);
      }
    },
    [switchBoard, addInstruction, clearBoard],
  );

  useDataChannel("visuals", onMessage);

  return {
    lastInstruction,
    instructions,
    activeInstructions: store.activeInstructions,
    activeWalks,
    activeBoardId: store.activeBoardId,
    activeBoardMeta: store.activeBoardMeta,
    pendingTransition: store.pendingTransition,
    clearTransition: store.clearTransition,
    getBoardInstructions: store.getBoardInstructions,
    getBoardMeta: store.getBoardMeta,
  };
}
