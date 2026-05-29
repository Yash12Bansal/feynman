// TODO(DEADCODE): tests dead engine/whiteboard modules (Group 1/2); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
import { it } from "vitest";
it.skip("dead code (TODO(DEADCODE)) — file slated for deletion", () => {});
// import { render } from "@testing-library/react";
// import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
// import type { ReactNode } from "react";
// import { HighlightOverlay } from "../content/HighlightOverlay";
// import { ElementRegistryContext } from "../elements";
// import type { ElementRegistry } from "../elements";
// import type { HighlightInstruction } from "../../types/visuals";

// function Wrapper({
//   registry,
//   children,
// }: {
//   registry: ElementRegistry;
//   children: ReactNode;
// }) {
//   return (
//     <ElementRegistryContext.Provider value={registry}>
//       {children}
//     </ElementRegistryContext.Provider>
//   );
// }

// describe("HighlightOverlay", () => {
//   beforeEach(() => {
//     vi.useFakeTimers();
//   });

//   afterEach(() => {
//     vi.useRealTimers();
//   });

//   it("applies highlight class to target element", () => {
//     const targetDiv = document.createElement("div");
//     const registry: ElementRegistry = {
//       register: vi.fn(),
//       unregister: vi.fn(),
//       get: vi.fn().mockReturnValue({
//         id: "target-1",
//         ref: targetDiv,
//         instruction: { type: "show_text", text: "test" },
//       }),
//     };

//     const instruction: HighlightInstruction = {
//       type: "highlight",
//       target_id: "target-1",
//       style: "glow",
//       duration_ms: 2000,
//     };

//     render(
//       <Wrapper registry={registry}>
//         <HighlightOverlay instruction={instruction} />
//       </Wrapper>,
//     );

//     expect(targetDiv.getAttribute("data-highlight")).toBe("glow");
//   });

//   it("removes highlight after duration", () => {
//     const targetDiv = document.createElement("div");
//     const registry: ElementRegistry = {
//       register: vi.fn(),
//       unregister: vi.fn(),
//       get: vi.fn().mockReturnValue({
//         id: "target-1",
//         ref: targetDiv,
//         instruction: { type: "show_text", text: "test" },
//       }),
//     };

//     const instruction: HighlightInstruction = {
//       type: "highlight",
//       target_id: "target-1",
//       style: "pulse",
//       duration_ms: 1000,
//     };

//     render(
//       <Wrapper registry={registry}>
//         <HighlightOverlay instruction={instruction} />
//       </Wrapper>,
//     );

//     expect(targetDiv.getAttribute("data-highlight")).toBe("pulse");
//     vi.advanceTimersByTime(1000);
//     expect(targetDiv.getAttribute("data-highlight")).toBeNull();
//   });

//   it("sets custom highlight color as CSS variable", () => {
//     const targetDiv = document.createElement("div");
//     const registry: ElementRegistry = {
//       register: vi.fn(),
//       unregister: vi.fn(),
//       get: vi.fn().mockReturnValue({
//         id: "target-1",
//         ref: targetDiv,
//         instruction: { type: "show_text", text: "test" },
//       }),
//     };

//     const instruction: HighlightInstruction = {
//       type: "highlight",
//       target_id: "target-1",
//       style: "box",
//       color: "#ff0000",
//     };

//     render(
//       <Wrapper registry={registry}>
//         <HighlightOverlay instruction={instruction} />
//       </Wrapper>,
//     );

//     expect(targetDiv.style.getPropertyValue("--highlight-color")).toBe(
//       "#ff0000",
//     );
//   });

//   it("warns when target not found", () => {
//     const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
//     const registry: ElementRegistry = {
//       register: vi.fn(),
//       unregister: vi.fn(),
//       get: vi.fn().mockReturnValue(undefined),
//     };

//     const instruction: HighlightInstruction = {
//       type: "highlight",
//       target_id: "nonexistent",
//       style: "glow",
//     };

//     render(
//       <Wrapper registry={registry}>
//         <HighlightOverlay instruction={instruction} />
//       </Wrapper>,
//     );

//     // Trigger the requestAnimationFrame retry
//     vi.advanceTimersByTime(16);

//     expect(warnSpy).toHaveBeenCalledWith(
//       expect.stringContaining("nonexistent"),
//     );
//     warnSpy.mockRestore();
//   });

//   it("cleans up highlight on unmount", () => {
//     const targetDiv = document.createElement("div");
//     const registry: ElementRegistry = {
//       register: vi.fn(),
//       unregister: vi.fn(),
//       get: vi.fn().mockReturnValue({
//         id: "target-1",
//         ref: targetDiv,
//         instruction: { type: "show_text", text: "test" },
//       }),
//     };

//     const instruction: HighlightInstruction = {
//       type: "highlight",
//       target_id: "target-1",
//       style: "glow",
//       duration_ms: 5000,
//     };

//     const { unmount } = render(
//       <Wrapper registry={registry}>
//         <HighlightOverlay instruction={instruction} />
//       </Wrapper>,
//     );

//     expect(targetDiv.getAttribute("data-highlight")).toBe("glow");
//     unmount();
//     expect(targetDiv.getAttribute("data-highlight")).toBeNull();
//   });
// });
