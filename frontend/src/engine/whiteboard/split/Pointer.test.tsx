import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { createRef } from "react";
import { Pointer } from "./Pointer";
import type { ElementMeta } from "../../../types/visuals";

/**
 * Pointer renders inside an SVG overlay and resolves bounds from the dictionary
 * fallback (jsdom has no layout, so getBoundingClientRect returns zeros and the
 * dictionary path wins — same pattern as MarginNote.test).
 */

function renderInSvg(ui: React.ReactNode) {
  return render(<svg>{ui}</svg>);
}

const DICT: Record<string, ElementMeta> = {
  vertex: {
    role: "vertex",
    semantic: "corner A",
    position: "center",
    bounds: [100, 100, 40, 40], // left edge x=100, cx=120, cy=120
  },
};

describe("Pointer", () => {
  it("renders a shaft + arrowhead when bounds resolve", () => {
    const stageRef = createRef<HTMLElement>();
    const overlayRef = createRef<SVGSVGElement>();
    const { container } = renderInSvg(
      <Pointer
        elementId="vertex"
        fromSide="left"
        dictionary={DICT}
        stageRef={stageRef}
        overlayRef={overlayRef}
      />,
    );
    expect(container.querySelector(".sb-pointer-shaft")).not.toBeNull();
    expect(container.querySelector(".sb-pointer-head")).not.toBeNull();
  });

  it("points from the left: shaft sits left of the element's left edge", () => {
    const stageRef = createRef<HTMLElement>();
    const overlayRef = createRef<SVGSVGElement>();
    const { container } = renderInSvg(
      <Pointer
        elementId="vertex"
        fromSide="left"
        dictionary={DICT}
        stageRef={stageRef}
        overlayRef={overlayRef}
      />,
    );
    const shaft = container.querySelector(".sb-pointer-shaft")!;
    expect(Number(shaft.getAttribute("x1"))).toBeLessThan(100);
    expect(Number(shaft.getAttribute("x2"))).toBeLessThan(100);
    // vertically centred on the element (cy = 120)
    expect(Number(shaft.getAttribute("y1"))).toBeCloseTo(120, 0);
  });

  it("renders nothing when bounds cannot be resolved", () => {
    const stageRef = createRef<HTMLElement>();
    const overlayRef = createRef<SVGSVGElement>();
    const { container } = renderInSvg(
      <Pointer
        elementId="missing"
        fromSide="left"
        dictionary={DICT}
        stageRef={stageRef}
        overlayRef={overlayRef}
      />,
    );
    expect(container.querySelector(".sb-pointer")).toBeNull();
  });

  it("supports all four sides", () => {
    for (const side of ["top", "bottom", "left", "right"] as const) {
      const stageRef = createRef<HTMLElement>();
      const overlayRef = createRef<SVGSVGElement>();
      const { container } = renderInSvg(
        <Pointer
          elementId="vertex"
          fromSide={side}
          dictionary={DICT}
          stageRef={stageRef}
          overlayRef={overlayRef}
        />,
      );
      expect(
        container.querySelector(`.sb-pointer[data-from-side="${side}"]`),
      ).not.toBeNull();
    }
  });
});
