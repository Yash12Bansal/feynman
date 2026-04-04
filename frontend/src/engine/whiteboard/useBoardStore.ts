/**
 * Multi-board state management for the whiteboard.
 *
 * Partitions visual instructions by board_id, tracks the active board,
 * manages transition state consumed by BoardNavigator, and tracks
 * camera state per board for infinite canvas scrolling.
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

export interface CameraState {
  tileX: number;
  tileY: number;
}

export interface BoardStore {
  activeBoardId: string;
  activeInstructions: VisualInstruction[];
  activeBoardMeta: BoardMeta | null;
  pendingTransition: BoardTransition | null;
  cameraState: CameraState;
  addInstruction: (instr: VisualInstruction) => void;
  switchBoard: (instr: SwitchBoardInstruction) => void;
  clearBoard: (boardId?: string, targetId?: string) => void;
  getBoardInstructions: (boardId: string) => VisualInstruction[];
  getBoardMeta: (boardId: string) => BoardMeta | null;
  clearTransition: () => void;
  scrollTo: (tileX: number, tileY: number) => void;
}

export function useBoardStore(): BoardStore {
  const boardsRef = useRef<Map<string, VisualInstruction[]>>(
    new Map([[DEFAULT_BOARD_ID, []]]),
  );
  const metaRef = useRef<Map<string, BoardMeta>>(new Map());
  const camerasRef = useRef<Map<string, CameraState>>(new Map());

  const [activeBoardId, setActiveBoardId] = useState(DEFAULT_BOARD_ID);
  const [activeInstructions, setActiveInstructions] = useState<
    VisualInstruction[]
  >([]);
  const [pendingTransition, setPendingTransition] =
    useState<BoardTransition | null>(null);
  const [activeBoardMeta, setActiveBoardMeta] = useState<BoardMeta | null>(
    null,
  );
  const [cameraState, setCameraState] = useState<CameraState>({
    tileX: 0,
    tileY: 0,
  });

  // Mirror activeBoardId in a ref so callbacks see the latest value
  // without needing it in their dependency arrays.
  const activeBoardIdRef = useRef(DEFAULT_BOARD_ID);

  /** Get camera for current board (defaults to 0,0). */
  const getCamera = useCallback(
    (boardId: string): CameraState =>
      camerasRef.current.get(boardId) ?? { tileX: 0, tileY: 0 },
    [],
  );

  const addInstruction = useCallback(
    (instr: VisualInstruction) => {
      const boardId = instr.board_id ?? activeBoardIdRef.current;
      const boards = boardsRef.current;

      let list = boards.get(boardId);
      if (!list) {
        list = [];
        boards.set(boardId, list);
      }

      // Stamp tile coordinates from current camera position
      const cam = getCamera(boardId);
      instr._tileX = cam.tileX;
      instr._tileY = cam.tileY;

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
    },
    [getCamera],
  );

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

    // Restore camera state for the target board (new boards start at 0,0)
    const cam = camerasRef.current.get(targetBoardId) ?? {
      tileX: 0,
      tileY: 0,
    };
    setCameraState(cam);
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
      // Reset camera on full board clear
      camerasRef.current.set(resolvedId, { tileX: 0, tileY: 0 });
      if (resolvedId === activeBoardIdRef.current) {
        setCameraState({ tileX: 0, tileY: 0 });
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

  const scrollTo = useCallback((tileX: number, tileY: number) => {
    const boardId = activeBoardIdRef.current;
    const cam = { tileX, tileY };
    camerasRef.current.set(boardId, cam);
    setCameraState(cam);
  }, []);

  return {
    activeBoardId,
    activeInstructions,
    activeBoardMeta,
    pendingTransition,
    cameraState,
    addInstruction,
    switchBoard,
    clearBoard,
    getBoardInstructions,
    getBoardMeta,
    clearTransition,
    scrollTo,
  };
}
