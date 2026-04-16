import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useBoardStore } from "../useBoardStore";
import type {
  DrawDesignDiagramInstruction,
  SlidePendingInstruction,
  VisualInstruction,
  SwitchBoardInstruction,
} from "../../../types/visuals";

// ── Helpers ───────────────────────────────────────────────────

function textInstr(
  overrides: Partial<VisualInstruction> & { text: string },
): VisualInstruction {
  return { type: "show_text", ...overrides } as VisualInstruction;
}

function switchInstr(
  overrides: Partial<SwitchBoardInstruction>,
): SwitchBoardInstruction {
  return { type: "switch_board", ...overrides } as SwitchBoardInstruction;
}

function pendingInstr(
  overrides: Partial<SlidePendingInstruction> = {},
): SlidePendingInstruction {
  return {
    type: "slide_pending",
    title: "Newton's Second Law",
    ...overrides,
  } as SlidePendingInstruction;
}

function designDiagramInstr(
  overrides: Partial<DrawDesignDiagramInstruction> = {},
): DrawDesignDiagramInstruction {
  return {
    type: "draw_design_diagram",
    spec: { title: "t", elements: [] },
    ...overrides,
  } as DrawDesignDiagramInstruction;
}

// ── Tests ─────────────────────────────────────────────────────

describe("useBoardStore", () => {
  it("default active board is board-1", () => {
    const { result } = renderHook(() => useBoardStore());
    expect(result.current.activeBoardId).toBe("board-1");
  });

  it("starts with empty active instructions", () => {
    const { result } = renderHook(() => useBoardStore());
    expect(result.current.activeInstructions).toEqual([]);
  });

  it("addInstruction routes to active board when no board_id", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(textInstr({ text: "hello" }));
    });
    expect(result.current.activeInstructions).toHaveLength(1);
    expect(result.current.getBoardInstructions("board-1")).toHaveLength(1);
  });

  it("addInstruction routes to specified board_id", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(
        textInstr({ text: "other", board_id: "board-2" }),
      );
    });
    // Active board (board-1) should be empty
    expect(result.current.activeInstructions).toHaveLength(0);
    // board-2 should have the instruction
    expect(result.current.getBoardInstructions("board-2")).toHaveLength(1);
  });

  it("switchBoard with intent: new creates new board and switches", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(textInstr({ text: "on board-1" }));
    });
    act(() => {
      result.current.switchBoard(
        switchInstr({ board_id: "board-2", intent: "new", label: "Doubt #1" }),
      );
    });
    expect(result.current.activeBoardId).toBe("board-2");
    expect(result.current.activeInstructions).toEqual([]);
    expect(result.current.activeBoardMeta).toEqual({
      id: "board-2",
      label: "Doubt #1",
    });
    // board-1 still has its instruction
    expect(result.current.getBoardInstructions("board-1")).toHaveLength(1);
  });

  it("switchBoard with intent: revisit switches to existing board", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(
        textInstr({ text: "original", element_id: "e1" }),
      );
    });
    act(() => {
      result.current.switchBoard(
        switchInstr({ board_id: "board-2", intent: "new" }),
      );
    });
    act(() => {
      result.current.switchBoard(
        switchInstr({ board_id: "board-1", intent: "revisit" }),
      );
    });
    expect(result.current.activeBoardId).toBe("board-1");
    expect(result.current.activeInstructions).toHaveLength(1);
  });

  it("switchBoard sets pendingTransition", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.switchBoard(
        switchInstr({ board_id: "board-2", intent: "new" }),
      );
    });
    expect(result.current.pendingTransition).toEqual({
      from: "board-1",
      to: "board-2",
      intent: "new",
      durationMs: undefined,
    });
  });

  it("switchBoard with reference intent does NOT change active board", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(textInstr({ text: "stay here" }));
    });
    act(() => {
      result.current.switchBoard(
        switchInstr({
          board_id: "board-2",
          intent: "reference",
          duration_ms: 5000,
        }),
      );
    });
    // Active board should still be board-1
    expect(result.current.activeBoardId).toBe("board-1");
    expect(result.current.activeInstructions).toHaveLength(1);
    // Transition should reflect reference intent
    expect(result.current.pendingTransition?.intent).toBe("reference");
    expect(result.current.pendingTransition?.durationMs).toBe(5000);
  });

  it("clearTransition resets pending", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.switchBoard(
        switchInstr({ board_id: "board-2", intent: "new" }),
      );
    });
    expect(result.current.pendingTransition).not.toBeNull();
    act(() => {
      result.current.clearTransition();
    });
    expect(result.current.pendingTransition).toBeNull();
  });

  it("clearBoard with targetId removes specific element", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(
        textInstr({ text: "keep", element_id: "e1" }),
      );
      result.current.addInstruction(
        textInstr({ text: "remove", element_id: "e2" }),
      );
    });
    act(() => {
      result.current.clearBoard("board-1", "e2");
    });
    expect(result.current.activeInstructions).toHaveLength(1);
    expect(result.current.activeInstructions[0].element_id).toBe("e1");
  });

  it("clearBoard without targetId clears all", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(textInstr({ text: "a" }));
      result.current.addInstruction(textInstr({ text: "b" }));
    });
    act(() => {
      result.current.clearBoard("board-1");
    });
    expect(result.current.activeInstructions).toHaveLength(0);
  });

  it("clearBoard on inactive board does not trigger re-render of active", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(
        textInstr({ text: "on-2", board_id: "board-2", element_id: "e1" }),
      );
      result.current.addInstruction(textInstr({ text: "on-1" }));
    });
    const instrsBefore = result.current.activeInstructions;
    act(() => {
      result.current.clearBoard("board-2", "e1");
    });
    // Active instructions length should still be 1 (board-1 instruction)
    expect(result.current.activeInstructions).toHaveLength(1);
    // Should be the same reference (no re-render triggered)
    expect(result.current.activeInstructions).toBe(instrsBefore);
  });

  it("getBoardInstructions returns correct array", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(textInstr({ text: "a" }));
      result.current.addInstruction(
        textInstr({ text: "b", board_id: "board-2" }),
      );
    });
    expect(result.current.getBoardInstructions("board-1")).toHaveLength(1);
    expect(result.current.getBoardInstructions("board-2")).toHaveLength(1);
    expect(result.current.getBoardInstructions("board-99")).toEqual([]);
  });

  it("getBoardMeta returns null for unknown boards", () => {
    const { result } = renderHook(() => useBoardStore());
    expect(result.current.getBoardMeta("nonexistent")).toBeNull();
  });

  it("boardMeta tracks labels", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.switchBoard(
        switchInstr({
          board_id: "board-2",
          intent: "new",
          label: "Forces Diagram",
        }),
      );
    });
    expect(result.current.getBoardMeta("board-2")).toEqual({
      id: "board-2",
      label: "Forces Diagram",
    });
  });

  it("multiple rapid switches produce correct final state", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.switchBoard(
        switchInstr({ board_id: "board-2", intent: "new", label: "B2" }),
      );
      result.current.switchBoard(
        switchInstr({ board_id: "board-3", intent: "new", label: "B3" }),
      );
      result.current.switchBoard(
        switchInstr({ board_id: "board-1", intent: "revisit" }),
      );
    });
    expect(result.current.activeBoardId).toBe("board-1");
    // Last transition should be the revisit back to board-1
    expect(result.current.pendingTransition).toEqual({
      from: "board-3",
      to: "board-1",
      intent: "revisit",
      durationMs: undefined,
    });
  });

  it("switchBoard without board_id is a no-op", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.switchBoard(switchInstr({}));
    });
    expect(result.current.activeBoardId).toBe("board-1");
    expect(result.current.pendingTransition).toBeNull();
  });

  // ── Phase 4: slide_pending loader state ───────────────────

  it("slide_pending sets pendingSlide entry without adding to instructions", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(
        pendingInstr({ board_id: "board-1", title: "Newton's 2nd Law" }),
      );
    });
    expect(result.current.pendingSlide["board-1"]).toEqual({
      title: "Newton's 2nd Law",
    });
    // Pending must not pollute the instruction list.
    expect(result.current.activeInstructions).toHaveLength(0);
    expect(result.current.getBoardInstructions("board-1")).toHaveLength(0);
  });

  it("a slide-typed instruction clears the pending entry for the same board", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(
        pendingInstr({ board_id: "board-1", title: "Loading…" }),
      );
    });
    expect(result.current.pendingSlide["board-1"]).toBeDefined();

    act(() => {
      result.current.addInstruction(
        designDiagramInstr({ board_id: "board-1", element_id: "design-1" }),
      );
    });
    expect(result.current.pendingSlide["board-1"]).toBeUndefined();
    expect(result.current.activeInstructions).toHaveLength(1);
  });

  it("switchBoard clears pendingSlide on the source board", () => {
    const { result } = renderHook(() => useBoardStore());
    act(() => {
      result.current.addInstruction(
        pendingInstr({ board_id: "board-1", title: "Half-rendered" }),
      );
    });
    expect(result.current.pendingSlide["board-1"]).toBeDefined();

    act(() => {
      result.current.switchBoard(
        switchInstr({ board_id: "board-2", intent: "new", label: "Doubt" }),
      );
    });
    expect(result.current.pendingSlide["board-1"]).toBeUndefined();
  });
});
