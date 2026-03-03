import { describe, it, expect } from "vitest";
import { box } from "../components/box";
import { COLORS } from "../../../theme";

describe("box", () => {
  it("returns a rect path with correct id", () => {
    const result = box({ cx: 100, cy: 100, id: "b1" });

    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("b1-rect");
  });

  it("rect path is a closed rectangle (contains Z)", () => {
    const result = box({ cx: 200, cy: 150, id: "closed" });

    expect(result.paths[0].d).toContain("Z");
  });

  it("rect path has correct corners for default size", () => {
    const result = box({ cx: 200, cy: 150, id: "corners" });
    const d = result.paths[0].d;

    // Default 80x60 → left=160, top=120, right=240, bottom=180
    expect(d).toContain("M 160 120");
    expect(d).toContain("L 240 120");
    expect(d).toContain("L 240 180");
    expect(d).toContain("L 160 180");
  });

  it("returns all 9 anchors at correct positions", () => {
    const result = box({ cx: 200, cy: 150, width: 80, height: 60, id: "a" });
    const anchors = result.anchors!;

    expect(anchors.center).toEqual({ x: 200, y: 150 });
    expect(anchors.top).toEqual({ x: 200, y: 120 });
    expect(anchors.bottom).toEqual({ x: 200, y: 180 });
    expect(anchors.left).toEqual({ x: 160, y: 150 });
    expect(anchors.right).toEqual({ x: 240, y: 150 });
    expect(anchors.topLeft).toEqual({ x: 160, y: 120 });
    expect(anchors.topRight).toEqual({ x: 240, y: 120 });
    expect(anchors.bottomLeft).toEqual({ x: 160, y: 180 });
    expect(anchors.bottomRight).toEqual({ x: 240, y: 180 });
  });

  it("includes label when provided", () => {
    const result = box({ cx: 100, cy: 100, label: "m", id: "labeled" });

    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("m");
    expect(result.labels[0].id).toBe("labeled-label");
    expect(result.labels[0].x).toBe(100);
    expect(result.labels[0].anchor).toBe("middle");
  });

  it("omits label when not provided", () => {
    const result = box({ cx: 100, cy: 100, id: "nolabel" });

    expect(result.labels).toHaveLength(0);
  });

  it("custom width and height change bounds and anchors", () => {
    const result = box({
      cx: 100,
      cy: 100,
      width: 120,
      height: 80,
      id: "custom",
    });

    expect(result.bounds).toEqual({ x: 40, y: 60, width: 120, height: 80 });
    expect(result.anchors!.topLeft).toEqual({ x: 40, y: 60 });
    expect(result.anchors!.bottomRight).toEqual({ x: 160, y: 140 });
  });

  it("applies custom color to stroke and fill", () => {
    const result = box({
      cx: 100,
      cy: 100,
      color: "#ff0000",
      id: "colored",
    });

    expect(result.paths[0].roughOptions?.stroke).toBe("#ff0000");
    expect(result.paths[0].roughOptions?.fill).toBe("#ff000022");
  });

  it("uses accentBlue as default color", () => {
    const result = box({ cx: 100, cy: 100, id: "default-color" });

    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.accentBlue);
  });

  it("uses hachure fill style", () => {
    const result = box({ cx: 100, cy: 100, id: "fill" });

    expect(result.paths[0].roughOptions?.fillStyle).toBe("hachure");
  });

  it("handles very small dimensions", () => {
    const result = box({
      cx: 50,
      cy: 50,
      width: 2,
      height: 2,
      id: "tiny",
    });

    expect(result.bounds.width).toBe(2);
    expect(result.bounds.height).toBe(2);
    expect(result.paths).toHaveLength(1);
  });
});
