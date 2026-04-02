/**
 * Multi-board state management for the whiteboard.
 *
 * Partitions visual instructions by board_id, tracks the active board,
 * and manages transition state consumed by BoardNavigator.
 *
 * Uses useRef for Maps (no re-render per instruction) and useState
 * for activeBoardId / activeInstructions (re-render on board switch).
 */

import { useCallback, useRef, useState } from "react";
import type {
  VisualInstruction,
  SwitchBoardInstruction,
  BoardIntent,
} from "../../types/visuals";

const DEFAULT_BOARD_ID = "board-1";

export interface BoardMeta {
  id: string;
  label: string;
}

export interface BoardTransition {
  from: string;
  to: string;
  intent: BoardIntent;
  durationMs?: number;
}

export interface BoardStore {
  activeBoardId: string;
  activeInstructions: VisualInstruction[];
  activeBoardMeta: BoardMeta | null;
  pendingTransition: BoardTransition | null;
  addInstruction: (instr: VisualInstruction) => void;
  switchBoard: (instr: SwitchBoardInstruction) => void;
  clearBoard: (boardId?: string, targetId?: string) => void;
  getBoardInstructions: (boardId: string) => VisualInstruction[];
  getBoardMeta: (boardId: string) => BoardMeta | null;
  clearTransition: () => void;
}

export function useBoardStore(): BoardStore {
  const boardsRef = useRef<Map<string, VisualInstruction[]>>(
    new Map([[DEFAULT_BOARD_ID, []]]),
  );
  const metaRef = useRef<Map<string, BoardMeta>>(new Map());

  const [activeBoardId, setActiveBoardId] = useState(DEFAULT_BOARD_ID);
  const [activeInstructions, setActiveInstructions] = useState<
    VisualInstruction[]
  >([]);
  const [pendingTransition, setPendingTransition] =
    useState<BoardTransition | null>(null);
  const [activeBoardMeta, setActiveBoardMeta] = useState<BoardMeta | null>(
    null,
  );

  // Mirror activeBoardId in a ref so callbacks see the latest value
  // without needing it in their dependency arrays.
  const activeBoardIdRef = useRef(DEFAULT_BOARD_ID);

  const addInstruction = useCallback((instr: VisualInstruction) => {
    const boardId = instr.board_id ?? activeBoardIdRef.current;
    const boards = boardsRef.current;

    let list = boards.get(boardId);
    if (!list) {
      list = [];
      boards.set(boardId, list);
    }

    // In-place update: replace existing instruction with same element_id
    // (used by modify_design_diagram to update diagrams without duplication).
    if (instr.element_id) {
      const existingIdx = list.findIndex(
        (i) => i.element_id === instr.element_id,
      );
      if (existingIdx !== -1) {
        list[existingIdx] = instr;
      } else {
        list.push(instr);
      }
    } else {
      list.push(instr);
    }

    // Only trigger re-render if instruction targets the active board
    if (boardId === activeBoardIdRef.current) {
      setActiveInstructions([...list]);
    }
  }, []);

  const switchBoard = useCallback((instr: SwitchBoardInstruction) => {
    const targetBoardId = instr.board_id;
    if (!targetBoardId) return;

    const intent: BoardIntent = instr.intent ?? "new";
    const fromBoardId = activeBoardIdRef.current;

    // Ensure target board exists in the map
    const boards = boardsRef.current;
    if (!boards.has(targetBoardId)) {
      boards.set(targetBoardId, []);
    }

    // Store label metadata
    if (instr.label) {
      metaRef.current.set(targetBoardId, {
        id: targetBoardId,
        label: instr.label,
      });
    }

    // Set pending transition — consumed by BoardNavigator
    setPendingTransition({
      from: fromBoardId,
      to: targetBoardId,
      intent,
      durationMs: instr.duration_ms,
    });

    // Reference peeks don't change the active board
    if (intent === "reference") return;

    // Update active board for new/revisit intents
    activeBoardIdRef.current = targetBoardId;
    setActiveBoardId(targetBoardId);
    setActiveInstructions([...(boards.get(targetBoardId) ?? [])]);
    setActiveBoardMeta(metaRef.current.get(targetBoardId) ?? null);
  }, []);

  const clearBoard = useCallback((boardId?: string, targetId?: string) => {
    const resolvedId = boardId ?? activeBoardIdRef.current;
    const boards = boardsRef.current;

    if (targetId) {
      const list = boards.get(resolvedId);
      if (list) {
        const filtered = list.filter((i) => i.element_id !== targetId);
        boards.set(resolvedId, filtered);
        if (resolvedId === activeBoardIdRef.current) {
          setActiveInstructions([...filtered]);
        }
      }
    } else {
      boards.set(resolvedId, []);
      if (resolvedId === activeBoardIdRef.current) {
        setActiveInstructions([]);
      }
    }
  }, []);

  const getBoardInstructions = useCallback(
    (boardId: string): VisualInstruction[] => {
      return boardsRef.current.get(boardId) ?? [];
    },
    [],
  );

  const getBoardMeta = useCallback((boardId: string): BoardMeta | null => {
    return metaRef.current.get(boardId) ?? null;
  }, []);

  const clearTransition = useCallback(() => {
    setPendingTransition(null);
  }, []);

  return {
    activeBoardId,
    activeInstructions,
    activeBoardMeta,
    pendingTransition,
    addInstruction,
    switchBoard,
    clearBoard,
    getBoardInstructions,
    getBoardMeta,
    clearTransition,
  };
}
