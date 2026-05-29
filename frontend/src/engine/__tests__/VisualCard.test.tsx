// TODO(DEADCODE): tests dead engine/whiteboard modules (Group 1/2); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
import { it } from "vitest";
it.skip("dead code (TODO(DEADCODE)) — file slated for deletion", () => {});
// import { render } from "@testing-library/react";
// import { describe, it, expect, vi } from "vitest";
// import type { ReactNode } from "react";
// import { VisualCard } from "../VisualCard";
// import { ElementRegistryContext } from "../elements";
// import type { ElementRegistry } from "../elements";
// import type { VisualInstruction } from "../../types/visuals";

// function createMockRegistry(): ElementRegistry {
//   return {
//     register: vi.fn(),
//     unregister: vi.fn(),
//     get: vi.fn(),
//   };
// }

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

// describe("VisualCard", () => {
//   it("renders children inside a card div", () => {
//     const registry = createMockRegistry();
//     const instruction: VisualInstruction = {
//       type: "show_text",
//       text: "test",
//     };
//     const { container } = render(
//       <Wrapper registry={registry}>
//         <VisualCard instruction={instruction}>
//           <span>Content</span>
//         </VisualCard>
//       </Wrapper>,
//     );
//     const card = container.querySelector(".visual-card");
//     expect(card).toBeTruthy();
//     expect(card!.textContent).toBe("Content");
//   });

//   it("sets data-type attribute", () => {
//     const registry = createMockRegistry();
//     const instruction: VisualInstruction = {
//       type: "show_equation",
//       latex: "x=1",
//     };
//     const { container } = render(
//       <Wrapper registry={registry}>
//         <VisualCard instruction={instruction}>eq</VisualCard>
//       </Wrapper>,
//     );
//     const card = container.querySelector(".visual-card");
//     expect(card!.getAttribute("data-type")).toBe("show_equation");
//   });

//   it("registers element with id in registry on mount", () => {
//     const registry = createMockRegistry();
//     const instruction: VisualInstruction = {
//       type: "show_text",
//       element_id: "my-element",
//       text: "test",
//     };
//     render(
//       <Wrapper registry={registry}>
//         <VisualCard instruction={instruction}>hi</VisualCard>
//       </Wrapper>,
//     );
//     expect(registry.register).toHaveBeenCalledWith(
//       "my-element",
//       expect.any(HTMLDivElement),
//       instruction,
//     );
//   });

//   it("does not register when element_id is missing", () => {
//     const registry = createMockRegistry();
//     const instruction: VisualInstruction = {
//       type: "show_text",
//       text: "test",
//     };
//     render(
//       <Wrapper registry={registry}>
//         <VisualCard instruction={instruction}>hi</VisualCard>
//       </Wrapper>,
//     );
//     expect(registry.register).not.toHaveBeenCalled();
//   });

//   it("unregisters on unmount", () => {
//     const registry = createMockRegistry();
//     const instruction: VisualInstruction = {
//       type: "show_text",
//       element_id: "my-element",
//       text: "test",
//     };
//     const { unmount } = render(
//       <Wrapper registry={registry}>
//         <VisualCard instruction={instruction}>hi</VisualCard>
//       </Wrapper>,
//     );
//     unmount();
//     expect(registry.unregister).toHaveBeenCalledWith("my-element");
//   });
// });
