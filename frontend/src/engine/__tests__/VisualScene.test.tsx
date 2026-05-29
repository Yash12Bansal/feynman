// TODO(DEADCODE): tests dead engine/whiteboard modules (Group 1/2); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
import { it } from "vitest";
it.skip("dead code (TODO(DEADCODE)) — file slated for deletion", () => {});
// import { render, screen } from "@testing-library/react";
// import { describe, it, expect } from "vitest";
// import { VisualScene } from "../VisualScene";
// import type { VisualInstruction } from "../../types/visuals";

// describe("VisualScene", () => {
//   it("renders empty when no instructions", () => {
//     const { container } = render(<VisualScene instructions={[]} />);
//     const content = container.querySelector(".scene-content");
//     expect(content).toBeTruthy();
//     expect(content!.children.length).toBe(0);
//   });

//   it("renders text instruction as a card", () => {
//     const instructions: VisualInstruction[] = [
//       {
//         type: "show_text",
//         element_id: "text-1",
//         title: "Hello",
//         text: "World",
//       },
//     ];
//     render(<VisualScene instructions={instructions} />);
//     expect(screen.getByText("Hello")).toBeTruthy();
//     expect(screen.getByText("World")).toBeTruthy();
//   });

//   it("renders mixed instruction types", () => {
//     const instructions: VisualInstruction[] = [
//       { type: "show_text", element_id: "t1", text: "Text card" },
//       { type: "show_equation", element_id: "e1", latex: "E=mc^2" },
//       {
//         type: "draw_diagram",
//         element_id: "d1",
//         diagram_type: "flowchart",
//         title: "Flow",
//       },
//       { type: "show_graph", element_id: "g1", graph_type: "line" },
//     ];
//     const { container } = render(<VisualScene instructions={instructions} />);
//     const cards = container.querySelectorAll(".visual-card");
//     expect(cards.length).toBe(4);
//   });

//   it("filters out clear instructions from rendered elements", () => {
//     const instructions: VisualInstruction[] = [
//       { type: "show_text", element_id: "t1", text: "visible" },
//       { type: "clear" },
//     ];
//     const { container } = render(<VisualScene instructions={instructions} />);
//     const cards = container.querySelectorAll(".visual-card");
//     expect(cards.length).toBe(1);
//   });

//   it("separates highlights from rendered cards", () => {
//     const instructions: VisualInstruction[] = [
//       {
//         type: "show_text",
//         element_id: "t1",
//         title: "Target",
//         text: "content",
//       },
//       { type: "highlight", target_id: "t1", style: "glow" },
//     ];
//     const { container } = render(<VisualScene instructions={instructions} />);
//     // Only 1 visual card, not 2
//     const cards = container.querySelectorAll(".visual-card");
//     expect(cards.length).toBe(1);
//   });

//   it("appends new instructions without destroying existing DOM", () => {
//     const initial: VisualInstruction[] = [
//       { type: "show_text", element_id: "t1", text: "First" },
//     ];
//     const { container, rerender } = render(
//       <VisualScene instructions={initial} />,
//     );
//     const firstCard = container.querySelector('[data-element-id="t1"]');
//     expect(firstCard).toBeTruthy();

//     const updated: VisualInstruction[] = [
//       ...initial,
//       { type: "show_text", element_id: "t2", text: "Second" },
//     ];
//     rerender(<VisualScene instructions={updated} />);

//     // First card should be the same DOM node
//     const firstCardAfter = container.querySelector('[data-element-id="t1"]');
//     expect(firstCardAfter).toBe(firstCard);

//     // Second card should exist
//     const secondCard = container.querySelector('[data-element-id="t2"]');
//     expect(secondCard).toBeTruthy();

//     expect(container.querySelectorAll(".visual-card").length).toBe(2);
//   });

//   it("sets data-type on cards correctly", () => {
//     const instructions: VisualInstruction[] = [
//       { type: "show_text", element_id: "t1", text: "a" },
//       { type: "show_equation", element_id: "e1", latex: "x" },
//     ];
//     const { container } = render(<VisualScene instructions={instructions} />);
//     expect(
//       container
//         .querySelector('[data-element-id="t1"]')
//         ?.getAttribute("data-type"),
//     ).toBe("show_text");
//     expect(
//       container
//         .querySelector('[data-element-id="e1"]')
//         ?.getAttribute("data-type"),
//     ).toBe("show_equation");
//   });
// });
