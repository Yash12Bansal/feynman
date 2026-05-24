/**
 * Pointer — doc 19 §12 arrow primitive tests.
 *
 * The component resolves bounds via useResolvedBounds. In jsdom the live-DOM
 * bounds path returns null (no getBoundingClientRect dimensions), but the
 * dictionary-bounds fallback still works — so we exercise the geometry by
 * passing bounds through the dictionary.
 */

import { useRef, type RefObject } from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Pointer } from "./Pointer";
import type { ElementMeta } from "../../../types/visuals";

interface HarnessProps {
  readonly elementId: string;
  readonly fromSide: "top" | "bottom" | "left" | "right";
  readonly dictionary?: Record<string, ElementMeta>;
}

function Harness({ elementId, fromSide, dictionary }: HarnessProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<SVGSVGElement>(null);
  return (
    <div>
      <div ref={stageRef} />
      <svg ref={overlayRef} viewBox="0 0 900 650">
        <Pointer
          elementId={elementId}
          fromSide={fromSide}
          dictionary={dictionary}
          stageRef={stageRef as unknown as RefObject<HTMLElement | null>}
          overlayRef={overlayRef as unknown as RefObject<SVGSVGElement | null>}
        />
      </svg>
    </div>
  );
}

const DICTIONARY: Record<string, ElementMeta> = {
  el_target: {
    role: "thing",
    semantic: "the target",
    position: "center",
    bounds: [400, 300, 80, 60],
  },
};

describe("Pointer", () => {
  it("renders shaft + arrowhead when bounds resolve", () => {
    const { container } = render(
      <Harness
        elementId="el_target"
        fromSide="right"
        dictionary={DICTIONARY}
      />,
    );
    const pointer = container.querySelector(".sb-pointer");
    expect(pointer).not.toBeNull();
    expect(pointer?.querySelector(".sb-pointer-shaft")).not.toBeNull();
    expect(pointer?.querySelector(".sb-pointer-head")).not.toBeNull();
  });

  it("renders nothing when the element_id is unknown", () => {
    const { container } = render(
      <Harness elementId="ghost" fromSide="left" dictionary={DICTIONARY} />,
    );
    expect(container.querySelector(".sb-pointer")).toBeNull();
  });

  it("from_side=left places the tip on the element's left edge", () => {
    const { container } = render(
      <Harness elementId="el_target" fromSide="left" dictionary={DICTIONARY} />,
    );
    const shaft = container.querySelector(
      ".sb-pointer-shaft",
    ) as SVGLineElement;
    // Bounds: [400, 300, 80, 60]. Left edge x = 400. Vertical center y = 330.
    // Tip is TIP_GAP (6) outside, so x2 = 394, y2 = 330.
    expect(shaft.getAttribute("x2")).toBe("394");
    expect(shaft.getAttribute("y2")).toBe("330");
    // Tail is SHAFT_LENGTH (56) further left.
    expect(shaft.getAttribute("x1")).toBe("338");
    expect(shaft.getAttribute("y1")).toBe("330");
  });

  it("from_side=right places the tip on the element's right edge", () => {
    const { container } = render(
      <Harness
        elementId="el_target"
        fromSide="right"
        dictionary={DICTIONARY}
      />,
    );
    const shaft = container.querySelector(
      ".sb-pointer-shaft",
    ) as SVGLineElement;
    // Right edge x = 400 + 80 = 480. Tip just outside: 486.
    expect(shaft.getAttribute("x2")).toBe("486");
    expect(shaft.getAttribute("y2")).toBe("330");
    expect(shaft.getAttribute("x1")).toBe("542");
    expect(shaft.getAttribute("y1")).toBe("330");
  });

  it("from_side=top places the tip on the element's top edge", () => {
    const { container } = render(
      <Harness elementId="el_target" fromSide="top" dictionary={DICTIONARY} />,
    );
    const shaft = container.querySelector(
      ".sb-pointer-shaft",
    ) as SVGLineElement;
    // Top edge y = 300. Tip just above: 294. Horizontal center x = 440.
    expect(shaft.getAttribute("x2")).toBe("440");
    expect(shaft.getAttribute("y2")).toBe("294");
    expect(shaft.getAttribute("x1")).toBe("440");
    expect(shaft.getAttribute("y1")).toBe("238");
  });

  it("from_side=bottom places the tip on the element's bottom edge", () => {
    const { container } = render(
      <Harness
        elementId="el_target"
        fromSide="bottom"
        dictionary={DICTIONARY}
      />,
    );
    const shaft = container.querySelector(
      ".sb-pointer-shaft",
    ) as SVGLineElement;
    // Bottom edge y = 360. Tip just below: 366.
    expect(shaft.getAttribute("x2")).toBe("440");
    expect(shaft.getAttribute("y2")).toBe("366");
    expect(shaft.getAttribute("x1")).toBe("440");
    expect(shaft.getAttribute("y1")).toBe("422");
  });

  it("tags the rendered group with element_id and from_side", () => {
    const { container } = render(
      <Harness elementId="el_target" fromSide="top" dictionary={DICTIONARY} />,
    );
    const group = container.querySelector(".sb-pointer");
    expect(group?.getAttribute("data-element-id")).toBe("el_target");
    expect(group?.getAttribute("data-from-side")).toBe("top");
  });

  it("sets the bounce CSS variable on the group based on from_side", () => {
    const { container } = render(
      <Harness elementId="el_target" fromSide="left" dictionary={DICTIONARY} />,
    );
    const group = container.querySelector(".sb-pointer") as SVGGElement;
    const style = group.getAttribute("style") ?? "";
    expect(style).toContain("--pointer-bounce-x");
  });
});
