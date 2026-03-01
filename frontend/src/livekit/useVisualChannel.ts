import { useDataChannel } from "@livekit/components-react";
import { useCallback, useRef, useState } from "react";
import type { VisualInstruction } from "../types/visuals";

export function useVisualChannel() {
  const [lastInstruction, setLastInstruction] =
    useState<VisualInstruction | null>(null);
  const instructionsRef = useRef<VisualInstruction[]>([]);
  const [instructions, setInstructions] = useState<VisualInstruction[]>([]);

  const onMessage = useCallback(
    (msg: { payload: Uint8Array; topic?: string; from?: unknown }) => {
      try {
        const text = new TextDecoder().decode(msg.payload);
        const parsed = JSON.parse(text) as VisualInstruction;

        if (parsed.type === "switch_board") {
          // Phase 11 handles board switching UI — skip for now.
        } else if (parsed.type === "clear") {
          if ("target_id" in parsed && parsed.target_id) {
            // Remove specific element
            instructionsRef.current = instructionsRef.current.filter(
              (i) => i.element_id !== parsed.target_id,
            );
          } else {
            // Clear all
            instructionsRef.current = [];
          }
        } else {
          instructionsRef.current = [...instructionsRef.current, parsed];
        }

        setInstructions(instructionsRef.current);
        setLastInstruction(parsed);
      } catch (err) {
        console.error("[VisualChannel] Failed to parse:", err);
      }
    },
    [],
  );

  useDataChannel("visuals", onMessage);

  return { lastInstruction, instructions };
}
