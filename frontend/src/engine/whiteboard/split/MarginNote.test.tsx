/**
 * MarginNote — doc 19 §12 margin-text primitive tests.
 */

import { useRef, type RefObject } from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { MarginNote } from "./MarginNote";
import type { ElementMeta } from "../../../types/visuals";

interface HarnessProps {
  readonly anchorElementId: string;
  readonly side: "top" | "bottom" | "left" | "right";
  readonly text: string;
  readonly dictionary?: Record<string, ElementMeta>;
}

function Harness({ anchorElementId, side, text, dictionary }: HarnessProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<SVGSVGElement>(null);
  return (
    <div>
      <div ref={stageRef} />
      <svg ref={overlayRef} viewBox="0 0 900 650">
        <MarginNote
          anchorElementId={anchorElementId}
          side={side}
          text={text}
          dictionary={dictionary}
          stageRef={stageRef as unknown as RefObject<HTMLElement | null>}
          overlayRef={overlayRef as unknown as RefObject<SVGSVGElement | null>}
        />
      </svg>
    </div>
  );
}

const DICTIONARY: Record<string, ElementMeta> = {
  el_anchor: {
    role: "thing",
    semantic: "the anchor",
    position: "center",
    bounds: [400, 300, 80, 60],
  },
};

describe("MarginNote", () => {
  it("renders connector + text when bounds resolve", () => {
    const { container, getByText } = render(
      <Harness
        anchorElementId="el_anchor"
        side="right"
        text="= mg"
        dictionary={DICTIONARY}
      />,
    );
    expect(container.querySelector(".sb-margin-note")).not.toBeNull();
    expect(container.querySelector(".sb-margin-note-connector")).not.toBeNull();
    expect(getByText("= mg")).not.toBeNull();
  });

  it("renders nothing when anchor element_id is unknown", () => {
    const { container } = render(
      <Harness
        anchorElementId="ghost"
        side="right"
        text="hello"
        dictionary={DICTIONARY}
      />,
    );
    expect(container.querySelector(".sb-margin-note")).toBeNull();
  });

  it("renders nothing when text is whitespace-only", () => {
    const { container } = render(
      <Harness
        anchorElementId="el_anchor"
        side="right"
        text="   "
        dictionary={DICTIONARY}
      />,
    );
    expect(container.querySelector(".sb-margin-note")).toBeNull();
  });

  it("side=right: connector extends to the right of the element", () => {
    const { container } = render(
      <Harness
        anchorElementId="el_anchor"
        side="right"
        text="vmax"
        dictionary={DICTIONARY}
      />,
    );
    const conn = container.querySelector(
      ".sb-margin-note-connector",
    ) as SVGLineElement;
    // Bounds [400, 300, 80, 60]. Right edge x = 480. Center y = 330.
    // Connector extends CONNECTOR_LENGTH (28) further right.
    expect(conn.getAttribute("x1")).toBe("480");
    expect(conn.getAttribute("y1")).toBe("330");
    expect(conn.getAttribute("x2")).toBe("508");
    expect(conn.getAttribute("y2")).toBe("330");
  });

  it("side=left: connector extends to the left of the element", () => {
    const { container } = render(
      <Harness
        anchorElementId="el_anchor"
        side="left"
        text="t=0"
        dictionary={DICTIONARY}
      />,
    );
    const conn = container.querySelector(
      ".sb-margin-note-connector",
    ) as SVGLineElement;
    // Left edge x = 400. Connector extends 28 further left.
    expect(conn.getAttribute("x1")).toBe("400");
    expect(conn.getAttribute("x2")).toBe("372");
  });

  it("side=top: connector extends above the element", () => {
    const { container } = render(
      <Harness
        anchorElementId="el_anchor"
        side="top"
        text="vmax"
        dictionary={DICTIONARY}
      />,
    );
    const conn = container.querySelector(
      ".sb-margin-note-connector",
    ) as SVGLineElement;
    // Top edge y = 300. Connector ends at 272.
    expect(conn.getAttribute("y1")).toBe("300");
    expect(conn.getAttribute("y2")).toBe("272");
    // Connector is centered horizontally.
    expect(conn.getAttribute("x1")).toBe("440");
  });

  it("side=bottom: connector extends below the element", () => {
    const { container } = render(
      <Harness
        anchorElementId="el_anchor"
        side="bottom"
        text="ground"
        dictionary={DICTIONARY}
      />,
    );
    const conn = container.querySelector(
      ".sb-margin-note-connector",
    ) as SVGLineElement;
    // Bottom edge y = 360. Connector ends at 388.
    expect(conn.getAttribute("y1")).toBe("360");
    expect(conn.getAttribute("y2")).toBe("388");
  });

  it("tags the group with data attributes for debugging", () => {
    const { container } = render(
      <Harness
        anchorElementId="el_anchor"
        side="left"
        text="hi"
        dictionary={DICTIONARY}
      />,
    );
    const group = container.querySelector(".sb-margin-note");
    expect(group?.getAttribute("data-anchor-element-id")).toBe("el_anchor");
    expect(group?.getAttribute("data-side")).toBe("left");
  });
});
