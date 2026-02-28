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
        instructionsRef.current = [...instructionsRef.current, parsed];
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
