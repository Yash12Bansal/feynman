import { createContext, useContext } from "react";
import type { BoardLayout } from "./types";

export const BoardLayoutContext = createContext<BoardLayout | null>(null);

export function useBoardLayout(): BoardLayout {
  const ctx = useContext(BoardLayoutContext);
  if (!ctx) {
    throw new Error("useBoardLayout must be used within a WhiteboardScene");
  }
  return ctx;
}
