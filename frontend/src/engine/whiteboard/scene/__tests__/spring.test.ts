import { describe, it, expect } from "vitest";
import { spring } from "../components/spring";

describe("spring", () => {
  it("returns one coil path for a horizontal spring", () => {
    const result = spring({
      x1: 0,
      y1: 100,
      x2: 200,
      y2: 100,
      coils: 6,
      id: "h-spring",
    });

    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("h-spring-coil");
  });

  it("path starts at (x1, y1) and ends at (x2, y2)", () => {
    const result = spring({
      x1: 10,
      y1: 50,
      x2: 200,
      y2: 50,
      id: "start-end",
    });

    const d = result.paths[0].d;
    expect(d).toMatch(/^M 10 50/);
    expect(d).toMatch(/L 200 50$/);
  });

  it("contains correct number of zigzag L commands", () => {
    const coils = 6;
    const result = spring({
      x1: 0,
      y1: 0,
      x2: 200,
      y2: 0,
      coils,
      id: "count",
    });

    const d = result.paths[0].d;
    // M start, L lead-in, (coils*2) zigzag L commands, L lead-out
    const lCount = (d.match(/ L /g) || []).length;
    // lead-in + coils*2 zigzags + lead-out = 1 + 12 + 1 = 14
    expect(lCount).toBe(1 + coils * 2 + 1);
  });

  it("returns correct anchors", () => {
    const result = spring({
      x1: 10,
      y1: 20,
      x2: 300,
      y2: 20,
      id: "anchors",
    });

    expect(result.anchors?.start).toEqual({ x: 10, y: 20 });
    expect(result.anchors?.end).toEqual({ x: 300, y: 20 });
  });

  it("handles vertical springs", () => {
    const result = spring({
      x1: 100,
      y1: 0,
      x2: 100,
      y2: 200,
      coils: 4,
      id: "vertical",
    });

    expect(result.paths).toHaveLength(1);
    // Zigzag should be horizontal (perpendicular to vertical axis)
    const d = result.paths[0].d;
    expect(d).toBeTruthy();
  });

  it("handles diagonal springs", () => {
    const result = spring({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 100,
      coils: 4,
      id: "diagonal",
    });

    expect(result.paths).toHaveLength(1);
    expect(result.anchors?.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors?.end).toEqual({ x: 100, y: 100 });
  });

  it("returns empty paths for zero-length spring", () => {
    const result = spring({
      x1: 50,
      y1: 50,
      x2: 50,
      y2: 50,
      id: "zero",
    });

    expect(result.paths).toHaveLength(0);
  });

  it("uses default coils when not specified", () => {
    const result = spring({
      x1: 0,
      y1: 0,
      x2: 200,
      y2: 0,
      id: "defaults",
    });

    const d = result.paths[0].d;
    // Default 8 coils → 16 zigzag L + 1 lead-in + 1 lead-out = 18
    const lCount = (d.match(/ L /g) || []).length;
    expect(lCount).toBe(1 + 16 + 1);
  });

  it("applies custom color to rough options", () => {
    const result = spring({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "colored",
      color: "#ff0000",
    });

    expect(result.paths[0].roughOptions?.stroke).toBe("#ff0000");
  });

  it("has no labels", () => {
    const result = spring({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "nolabels",
    });

    expect(result.labels).toHaveLength(0);
  });

  it("bounds cover the amplitude", () => {
    const amp = 20;
    const result = spring({
      x1: 0,
      y1: 100,
      x2: 200,
      y2: 100,
      amplitude: amp,
      id: "amp-bounds",
    });

    // For horizontal spring, perpendicular is vertical
    // Bounds should extend above and below y=100
    expect(result.bounds.y).toBeLessThanOrEqual(100 - amp);
    expect(result.bounds.y + result.bounds.height).toBeGreaterThanOrEqual(
      100 + amp,
    );
  });
});
