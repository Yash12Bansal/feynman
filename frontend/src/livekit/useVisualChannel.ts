import { useDataChannel } from "@livekit/components-react";
import { useCallback, useRef, useState } from "react";
import type {
  VisualInstruction,
  SwitchBoardInstruction,
  ClearInstruction,
  HighlightWalkInstruction,
  ScrollViewInstruction,
} from "../types/visuals";
import { useBoardStore } from "../engine/whiteboard/useBoardStore";
import type {
  BoardMeta,
  BoardTransition,
  CameraState,
  PendingSlide,
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
  cameraState: CameraState;
  /** Per-board pending-slide loader state. Set by `slide_pending`, cleared on slide arrival / board switch. */
  pendingSlide: Record<string, PendingSlide | undefined>;
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
  const { switchBoard, addInstruction, clearBoard, scrollTo } = store;

  const onMessage = useCallback(
    (msg: { payload: Uint8Array; topic?: string; from?: unknown }) => {
      try {
        const text = new TextDecoder().decode(msg.payload);
        const parsed = JSON.parse(text) as VisualInstruction;

        if (parsed.type === "switch_board") {
          switchBoard(parsed as SwitchBoardInstruction);
          // Clear walks on board switch — they're tied to the current board
          setActiveWalks([]);
        } else if (parsed.type === "scroll_view") {
          // Ephemeral — update camera position, don't store in board
          const scroll = parsed as ScrollViewInstruction;
          scrollTo(scroll.target_x, scroll.target_y);
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
          // Ephemeral — don't store in board (avoids re-render of diagram cards).
          // Replace any existing walk on the same target to prevent accumulation.
          const walk = parsed as HighlightWalkInstruction;
          setActiveWalks((prev) => [
            ...prev.filter((w) => w.target_id !== walk.target_id),
            walk,
          ]);

          // Auto-expire: remove walk after its duration to prevent stale registrations.
          const walkDuration =
            walk.duration_ms ?? (walk.steps?.length ?? 1) * 5000;
          setTimeout(() => {
            setActiveWalks((prev) => prev.filter((w) => w !== walk));
          }, walkDuration + 1000);
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
    [switchBoard, addInstruction, clearBoard, scrollTo],
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
    cameraState: store.cameraState,
    pendingSlide: store.pendingSlide,
    clearTransition: store.clearTransition,
    getBoardInstructions: store.getBoardInstructions,
    getBoardMeta: store.getBoardMeta,
  };
}
