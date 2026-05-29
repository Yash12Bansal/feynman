// TODO(DEADCODE): tests dead engine/whiteboard modules (Group 1/2); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
import { it } from "vitest";
it.skip("dead code (TODO(DEADCODE)) — file slated for deletion", () => {});
// import { render, screen } from "@testing-library/react";
// import { describe, it, expect, vi } from "vitest";
// import { DiagramContent } from "../content/DiagramContent";
// import type { DrawDiagramInstruction } from "../../types/visuals";

// // Mock GSAP — jsdom doesn't support real animations
// vi.mock("gsap", () => {
//   const tl = {
//     fromTo: vi.fn().mockReturnThis(),
//     to: vi.fn().mockReturnThis(),
//     kill: vi.fn(),
//   };
//   return {
//     default: {
//       timeline: () => tl,
//       set: vi.fn(),
//     },
//   };
// });

// const structuredInstruction: DrawDiagramInstruction = {
//   type: "draw_diagram",
//   diagram_type: "force_diagram",
//   title: "Free Body Diagram",
//   description: "Forces acting on a block.",
//   nodes: [
//     { id: "block", label: "Block (m)", shape: "rectangle", color: "#60a5fa" },
//     { id: "weight", label: "mg", shape: "circle", color: "#ef4444" },
//     { id: "normal", label: "N", shape: "circle", color: "#4ade80" },
//   ],
//   edges: [
//     { from_id: "block", to_id: "weight", label: "gravity", directed: true },
//     {
//       from_id: "block",
//       to_id: "normal",
//       label: "perpendicular",
//       directed: true,
//     },
//   ],
//   progressive: true,
// };

// const descriptionOnlyInstruction: DrawDiagramInstruction = {
//   type: "draw_diagram",
//   description: "A block on an inclined plane.",
// };

// // ── Structured rendering (nodes provided) ─────────────────────

// describe("DiagramContent — structured", () => {
//   it("renders SVG with correct viewBox", () => {
//     const { container } = render(
//       <DiagramContent instruction={structuredInstruction} />,
//     );
//     const svg = container.querySelector("svg");
//     expect(svg).toBeTruthy();
//     const viewBox = svg!.getAttribute("viewBox");
//     expect(viewBox).toBeTruthy();
//     // viewBox should have 4 numeric parts
//     const parts = viewBox!.split(" ").map(Number);
//     expect(parts).toHaveLength(4);
//     expect(parts[2]).toBeGreaterThan(0); // width
//     expect(parts[3]).toBeGreaterThan(0); // height
//   });

//   it("renders all nodes as data-node groups", () => {
//     const { container } = render(
//       <DiagramContent instruction={structuredInstruction} />,
//     );
//     const nodeEls = container.querySelectorAll("[data-node]");
//     expect(nodeEls).toHaveLength(3);
//     expect(nodeEls[0].getAttribute("data-node")).toBe("block");
//     expect(nodeEls[1].getAttribute("data-node")).toBe("weight");
//     expect(nodeEls[2].getAttribute("data-node")).toBe("normal");
//   });

//   it("renders edges as data-edge lines", () => {
//     const { container } = render(
//       <DiagramContent instruction={structuredInstruction} />,
//     );
//     const edgeEls = container.querySelectorAll("[data-edge]");
//     expect(edgeEls).toHaveLength(2);
//   });

//   it("renders arrowheads for directed edges", () => {
//     const { container } = render(
//       <DiagramContent instruction={structuredInstruction} />,
//     );
//     const arrowheads = container.querySelectorAll("[data-arrowhead]");
//     expect(arrowheads).toHaveLength(2);
//   });

//   it("omits arrowheads for undirected edges", () => {
//     const instruction: DrawDiagramInstruction = {
//       type: "draw_diagram",
//       nodes: [
//         { id: "a", label: "A" },
//         { id: "b", label: "B" },
//       ],
//       edges: [{ from_id: "a", to_id: "b", directed: false }],
//     };
//     const { container } = render(<DiagramContent instruction={instruction} />);
//     const arrowheads = container.querySelectorAll("[data-arrowhead]");
//     expect(arrowheads).toHaveLength(0);
//   });

//   it("renders title when provided", () => {
//     render(<DiagramContent instruction={structuredInstruction} />);
//     expect(screen.getByText("Free Body Diagram")).toBeTruthy();
//   });

//   it("renders description below SVG when provided", () => {
//     render(<DiagramContent instruction={structuredInstruction} />);
//     expect(screen.getByText("Forces acting on a block.")).toBeTruthy();
//   });

//   it("sets role=img and aria-label on SVG", () => {
//     const { container } = render(
//       <DiagramContent instruction={structuredInstruction} />,
//     );
//     const svg = container.querySelector("svg");
//     expect(svg!.getAttribute("role")).toBe("img");
//     expect(svg!.getAttribute("aria-label")).toBeTruthy();
//   });

//   it("renders correct strokeDasharray for dashed edges", () => {
//     const instruction: DrawDiagramInstruction = {
//       type: "draw_diagram",
//       nodes: [
//         { id: "a", label: "A" },
//         { id: "b", label: "B" },
//       ],
//       edges: [{ from_id: "a", to_id: "b", style: "dashed", directed: true }],
//     };
//     const { container } = render(<DiagramContent instruction={instruction} />);
//     const line = container.querySelector("[data-edge]");
//     expect(line!.getAttribute("stroke-dasharray")).toBe("8,4");
//   });

//   it("renders correct strokeDasharray for dotted edges", () => {
//     const instruction: DrawDiagramInstruction = {
//       type: "draw_diagram",
//       nodes: [
//         { id: "a", label: "A" },
//         { id: "b", label: "B" },
//       ],
//       edges: [{ from_id: "a", to_id: "b", style: "dotted", directed: true }],
//     };
//     const { container } = render(<DiagramContent instruction={instruction} />);
//     const line = container.querySelector("[data-edge]");
//     expect(line!.getAttribute("stroke-dasharray")).toBe("3,3");
//   });

//   it("renders edge labels", () => {
//     render(<DiagramContent instruction={structuredInstruction} />);
//     expect(screen.getByText("gravity")).toBeTruthy();
//     expect(screen.getByText("perpendicular")).toBeTruthy();
//   });

//   it("renders node labels", () => {
//     render(<DiagramContent instruction={structuredInstruction} />);
//     expect(screen.getByText("Block (m)")).toBeTruthy();
//     expect(screen.getByText("mg")).toBeTruthy();
//     expect(screen.getByText("N")).toBeTruthy();
//   });
// });

// // ── Fallback rendering (description only) ─────────────────────

// describe("DiagramContent — fallback", () => {
//   it("renders badge + description text when no nodes", () => {
//     render(<DiagramContent instruction={descriptionOnlyInstruction} />);
//     expect(screen.getByText("DIAGRAM")).toBeTruthy();
//     expect(screen.getByText("A block on an inclined plane.")).toBeTruthy();
//   });

//   it("does not render SVG when no nodes", () => {
//     const { container } = render(
//       <DiagramContent instruction={descriptionOnlyInstruction} />,
//     );
//     expect(container.querySelector("svg")).toBeNull();
//   });

//   it("shows correct badge for diagram type", () => {
//     const instruction: DrawDiagramInstruction = {
//       type: "draw_diagram",
//       diagram_type: "flowchart",
//       description: "A process flow.",
//     };
//     render(<DiagramContent instruction={instruction} />);
//     expect(screen.getByText("FLOWCHART")).toBeTruthy();
//   });

//   it("falls back to DIAGRAM for free_form type", () => {
//     const instruction: DrawDiagramInstruction = {
//       type: "draw_diagram",
//       diagram_type: "free_form",
//       description: "Something.",
//     };
//     render(<DiagramContent instruction={instruction} />);
//     expect(screen.getByText("DIAGRAM")).toBeTruthy();
//   });
// });
