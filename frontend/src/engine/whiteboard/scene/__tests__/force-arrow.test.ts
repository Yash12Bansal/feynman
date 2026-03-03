import { describe, it, expect } from "vitest";
import { forceArrow } from "../components/force-arrow";

describe("forceArrow", () => {
  it("returns shaft and head paths for a valid arrow", () => {
    const result = forceArrow({
      x: 100,
      y: 100,
      angle: 0,
      length: 80,
      color: "#ff0000",
      label: "F",
      id: "test",
    });

    expect(result.paths).toHaveLength(2); // shaft + head
    expect(result.paths[0].id).toBe("test-shaft");
    expect(result.paths[1].id).toBe("test-head");
  });

  it("shaft path starts at origin", () => {
    const result = forceArrow({
      x: 50,
      y: 75,
      angle: 0,
      length: 80,
      id: "t",
    });

    expect(result.paths[0].d).toContain("M 50 75");
  });

  it("returns correct anchors for rightward arrow", () => {
    const result = forceArrow({
      x: 100,
      y: 200,
      angle: 0,
      length: 60,
      id: "right",
    });

    expect(result.anchors?.tail).toEqual({ x: 100, y: 200 });
    // tip should be to the right
    expect(result.anchors!.tip.x).toBeCloseTo(160);
    expect(result.anchors!.tip.y).toBeCloseTo(200);
  });

  it("returns correct tip for downward arrow (90 degrees)", () => {
    const result = forceArrow({
      x: 100,
      y: 100,
      angle: 90,
      length: 50,
      id: "down",
    });

    expect(result.anchors!.tip.x).toBeCloseTo(100);
    expect(result.anchors!.tip.y).toBeCloseTo(150);
  });

  it("returns correct tip for upward arrow (270 degrees)", () => {
    const result = forceArrow({
      x: 100,
      y: 200,
      angle: 270,
      length: 80,
      id: "up",
    });

    expect(result.anchors!.tip.x).toBeCloseTo(100);
    expect(result.anchors!.tip.y).toBeCloseTo(120);
  });

  it("returns correct tip for leftward arrow (180 degrees)", () => {
    const result = forceArrow({
      x: 200,
      y: 100,
      angle: 180,
      length: 60,
      id: "left",
    });

    expect(result.anchors!.tip.x).toBeCloseTo(140);
    expect(result.anchors!.tip.y).toBeCloseTo(100);
  });

  it("includes a label when provided", () => {
    const result = forceArrow({
      x: 0,
      y: 0,
      angle: 0,
      length: 80,
      label: "Weight",
      id: "w",
    });

    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("Weight");
    expect(result.labels[0].id).toBe("w-label");
  });

  it("omits label when not provided", () => {
    const result = forceArrow({
      x: 0,
      y: 0,
      angle: 0,
      length: 80,
      id: "nolabel",
    });

    expect(result.labels).toHaveLength(0);
  });

  it("returns empty paths for zero length", () => {
    const result = forceArrow({
      x: 100,
      y: 100,
      angle: 45,
      length: 0,
      id: "zero",
    });

    expect(result.paths).toHaveLength(0);
    expect(result.anchors?.tail).toEqual({ x: 100, y: 100 });
    expect(result.anchors?.tip).toEqual({ x: 100, y: 100 });
  });

  it("returns empty paths for negative length", () => {
    const result = forceArrow({
      x: 0,
      y: 0,
      angle: 0,
      length: -10,
      id: "neg",
    });

    expect(result.paths).toHaveLength(0);
  });

  it("applies color to rough options", () => {
    const result = forceArrow({
      x: 0,
      y: 0,
      angle: 0,
      length: 80,
      color: "#00ff00",
      id: "colored",
    });

    expect(result.paths[0].roughOptions?.stroke).toBe("#00ff00");
  });

  it("arrowhead path contains Z (closed shape)", () => {
    const result = forceArrow({
      x: 0,
      y: 0,
      angle: 0,
      length: 80,
      id: "closed",
    });

    const headPath = result.paths.find((p) => p.id === "closed-head");
    expect(headPath?.d).toContain("Z");
  });

  it("skips arrowhead when arrow is too short", () => {
    const result = forceArrow({
      x: 0,
      y: 0,
      angle: 0,
      length: 10, // shorter than ARROWHEAD_LENGTH (14)
      id: "short",
    });

    // Only shaft, no head
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("short-shaft");
  });

  it("bounds encompass tail and tip", () => {
    const result = forceArrow({
      x: 50,
      y: 50,
      angle: 0,
      length: 100,
      id: "bounds",
    });

    const { bounds } = result;
    expect(bounds.x).toBeLessThanOrEqual(50);
    expect(bounds.y).toBeLessThanOrEqual(50);
    expect(bounds.x + bounds.width).toBeGreaterThanOrEqual(150);
  });
});
