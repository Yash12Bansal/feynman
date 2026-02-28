import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useCreateElementRegistry } from "../elements";
import type { VisualInstruction } from "../../types/visuals";

const MOCK_INSTRUCTION: VisualInstruction = {
  type: "show_text",
  element_id: "test-1",
  text: "Hello",
};

describe("useCreateElementRegistry", () => {
  it("registers and retrieves an element", () => {
    const { result } = renderHook(() => useCreateElementRegistry());
    const div = document.createElement("div");

    act(() => {
      result.current.register("test-1", div, MOCK_INSTRUCTION);
    });

    const entry = result.current.get("test-1");
    expect(entry).toBeTruthy();
    expect(entry!.id).toBe("test-1");
    expect(entry!.ref).toBe(div);
    expect(entry!.instruction).toBe(MOCK_INSTRUCTION);
  });

  it("returns undefined for unregistered id", () => {
    const { result } = renderHook(() => useCreateElementRegistry());
    expect(result.current.get("nonexistent")).toBeUndefined();
  });

  it("unregisters an element", () => {
    const { result } = renderHook(() => useCreateElementRegistry());
    const div = document.createElement("div");

    act(() => {
      result.current.register("test-1", div, MOCK_INSTRUCTION);
    });
    expect(result.current.get("test-1")).toBeTruthy();

    act(() => {
      result.current.unregister("test-1");
    });
    expect(result.current.get("test-1")).toBeUndefined();
  });

  it("returns stable references across renders", () => {
    const { result, rerender } = renderHook(() => useCreateElementRegistry());
    const first = result.current;
    rerender();
    expect(result.current.register).toBe(first.register);
    expect(result.current.unregister).toBe(first.unregister);
    expect(result.current.get).toBe(first.get);
  });
});
