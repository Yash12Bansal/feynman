/**
 * MarkPoint — doc 19 §12 marker primitive tests.
 */

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { MarkPoint } from "./MarkPoint";

function svgRoot(children: React.ReactNode) {
  return <svg viewBox="0 0 900 650">{children}</svg>;
}

describe("MarkPoint", () => {
  it("renders a dot at the given (x, y)", () => {
    const { container } = render(
      svgRoot(<MarkPoint x={120} y={240} kind="dot" label="" />),
    );
    const dot = container.querySelector(".sb-mark-point-shape-dot");
    expect(dot).not.toBeNull();
    expect(dot?.getAttribute("cx")).toBe("120");
    expect(dot?.getAttribute("cy")).toBe("240");
  });

  it("renders a cross with two intersecting lines centered at (x, y)", () => {
    const { container } = render(
      svgRoot(<MarkPoint x={100} y={100} kind="cross" label="" />),
    );
    const cross = container.querySelector(".sb-mark-point-shape-cross");
    expect(cross).not.toBeNull();
    const lines = cross?.querySelectorAll("line");
    expect(lines?.length).toBe(2);
    // First diagonal goes from upper-left to lower-right.
    expect(lines![0].getAttribute("x1")).toBe("92");
    expect(lines![0].getAttribute("y1")).toBe("92");
    expect(lines![0].getAttribute("x2")).toBe("108");
    expect(lines![0].getAttribute("y2")).toBe("108");
  });

  it("renders a star as an SVG path", () => {
    const { container } = render(
      svgRoot(<MarkPoint x={300} y={400} kind="star" label="" />),
    );
    const star = container.querySelector(".sb-mark-point-shape-star");
    expect(star).not.toBeNull();
    const d = star?.getAttribute("d") ?? "";
    expect(d.startsWith("M ")).toBe(true);
    expect(d.endsWith(" Z")).toBe(true);
    // 5-pointed star → 10 vertices → M + 9 L commands.
    const lCount = (d.match(/ L /g) ?? []).length;
    expect(lCount).toBe(9);
  });

  it("omits the inline label when text is empty", () => {
    const { container } = render(
      svgRoot(<MarkPoint x={10} y={10} kind="dot" label="" />),
    );
    expect(container.querySelector(".sb-mark-point-label")).toBeNull();
  });

  it("omits the inline label when text is whitespace-only", () => {
    const { container } = render(
      svgRoot(<MarkPoint x={10} y={10} kind="dot" label="   " />),
    );
    expect(container.querySelector(".sb-mark-point-label")).toBeNull();
  });

  it("renders the inline label pill + text when provided", () => {
    const { container, getByText } = render(
      svgRoot(<MarkPoint x={50} y={50} kind="dot" label="ground" />),
    );
    expect(container.querySelector(".sb-mark-point-label-pill")).not.toBeNull();
    expect(getByText("ground")).not.toBeNull();
  });

  it("tags the rendered group with the mark kind for debugging", () => {
    const { container } = render(
      svgRoot(<MarkPoint x={0} y={0} kind="star" label="" />),
    );
    const group = container.querySelector(".sb-mark-point");
    expect(group?.getAttribute("data-mark-kind")).toBe("star");
  });
});
