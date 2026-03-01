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
    expect(result.current.entries).toBe(first.entries);
  });

  it("entries() returns all registered elements", () => {
    const { result } = renderHook(() => useCreateElementRegistry());
    const div1 = document.createElement("div");
    const div2 = document.createElement("div");
    const instr2: VisualInstruction = {
      type: "show_equation",
      element_id: "eq-1",
      latex: "x=1",
    };

    act(() => {
      result.current.register("test-1", div1, MOCK_INSTRUCTION);
      result.current.register("eq-1", div2, instr2);
    });

    const entries = Array.from(result.current.entries());
    expect(entries).toHaveLength(2);
    const ids = entries.map(([id]) => id);
    expect(ids).toContain("test-1");
    expect(ids).toContain("eq-1");
  });

  it("entries() empty when no registrations", () => {
    const { result } = renderHook(() => useCreateElementRegistry());
    const entries = Array.from(result.current.entries());
    expect(entries).toHaveLength(0);
  });
});
