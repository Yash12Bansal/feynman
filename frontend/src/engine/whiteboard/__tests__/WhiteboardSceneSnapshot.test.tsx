// TODO(DEADCODE): tests dead engine/whiteboard modules (Group 1/2); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
import { it } from "vitest";
it.skip("dead code (TODO(DEADCODE)) — file slated for deletion", () => {});
// import { render } from "@testing-library/react";
// import { describe, it, expect, vi, beforeAll } from "vitest";
// import type { VisualInstruction } from "../../../types/visuals";

// // ── Mock GSAP ────────────────────────────────────────────────

// vi.mock("gsap", () => {
//   const tl = {
//     to: vi.fn().mockReturnThis(),
//     fromTo: vi.fn().mockReturnThis(),
//     kill: vi.fn(),
//   };
//   return {
//     default: {
//       timeline: () => tl,
//       set: vi.fn(),
//     },
//   };
// });

// // ── Stub getTotalLength on SVG paths ─────────────────────────

// const origCreateElementNS = document.createElementNS.bind(document);
// vi.spyOn(document, "createElementNS").mockImplementation(
//   (ns: string | null, tag: string) => {
//     const el = origCreateElementNS(ns!, tag);
//     if (tag === "path") {
//       (el as unknown as Record<string, unknown>).getTotalLength = () => 50;
//     }
//     return el;
//   },
// );

// // ── ResizeObserver mock ──────────────────────────────────────

// class MockResizeObserver {
//   observe() {}
//   unobserve() {}
//   disconnect() {}
// }

// beforeAll(() => {
//   vi.stubGlobal("ResizeObserver", MockResizeObserver);
// });

// // ── Lazy import (after mocks) ────────────────────────────────

// async function loadSnapshot() {
//   const mod = await import("../WhiteboardSceneSnapshot");
//   return mod.WhiteboardSceneSnapshot;
// }

// // ── Tests ────────────────────────────────────────────────────

// describe("WhiteboardSceneSnapshot", () => {
//   it("renders zone layout from instructions", async () => {
//     const Snapshot = await loadSnapshot();
//     const instructions: VisualInstruction[] = [
//       { type: "show_text", text: "Hello", zone: "top-left" },
//     ];
//     const { container } = render(<Snapshot instructions={instructions} />);
//     expect(
//       container.querySelector('.wb-zone[data-zone="top-left"]'),
//     ).toBeTruthy();
//   });

//   it("renders instruction content via WhiteboardCard", async () => {
//     const Snapshot = await loadSnapshot();
//     const instructions: VisualInstruction[] = [
//       {
//         type: "show_text",
//         text: "Snap",
//         element_id: "snap-1",
//         zone: "center-center",
//       },
//     ];
//     const { container } = render(<Snapshot instructions={instructions} />);
//     expect(container.querySelector('[data-element-id="snap-1"]')).toBeTruthy();
//     expect(container.querySelector(".wb-card")).toBeTruthy();
//   });

//   it("has wb-snapshot class (disables card-enter animation)", async () => {
//     const Snapshot = await loadSnapshot();
//     const { container } = render(<Snapshot instructions={[]} />);
//     expect(container.querySelector(".wb-snapshot")).toBeTruthy();
//   });

//   it("does not render AliveFilter", async () => {
//     const Snapshot = await loadSnapshot();
//     const { container } = render(<Snapshot instructions={[]} />);
//     // AliveFilter renders an SVG with aria-hidden="true"
//     expect(container.querySelector('svg[aria-hidden="true"]')).toBeNull();
//   });

//   it("strips highlights and annotations from rendering", async () => {
//     const Snapshot = await loadSnapshot();
//     const instructions: VisualInstruction[] = [
//       {
//         type: "show_text",
//         text: "target",
//         element_id: "t1",
//         zone: "top-left",
//       },
//       { type: "highlight", target_id: "t1", style: "glow" },
//       { type: "annotate", action: "circle", target_id: "t1" },
//     ];
//     const { container } = render(<Snapshot instructions={instructions} />);
//     // Only one card rendered (for the text), no highlights or annotations
//     const cards = container.querySelectorAll(".wb-card");
//     expect(cards.length).toBe(1);
//   });

//   it("filters out switch_board and clear instructions", async () => {
//     const Snapshot = await loadSnapshot();
//     const instructions: VisualInstruction[] = [
//       { type: "clear" },
//       { type: "switch_board", board_id: "b2" },
//       { type: "show_text", text: "visible", zone: "center-center" },
//     ];
//     const { container } = render(<Snapshot instructions={instructions} />);
//     const cards = container.querySelectorAll(".wb-card");
//     expect(cards.length).toBe(1);
//   });
// });
