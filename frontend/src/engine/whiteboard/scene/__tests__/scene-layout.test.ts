import { describe, it, expect } from "vitest";
import { computeTightBounds, extractPathCoords } from "../scene-layout";
import type { ScenePath, SceneLabel } from "../scene-types";

describe("extractPathCoords", () => {
  it("extracts M and L coordinates", () => {
    const coords = extractPathCoords("M 10 20 L 30 40 L 50 60");
    expect(coords).toEqual([
      { x: 10, y: 20 },
      { x: 30, y: 40 },
      { x: 50, y: 60 },
    ]);
  });

  it("extracts arc endpoint coordinates", () => {
    // Arc: A rx ry rotation large-arc sweep x y
    const coords = extractPathCoords("M 100 50 A 40 40 0 0 1 100 130");
    expect(coords).toEqual([
      { x: 100, y: 50 },
      { x: 100, y: 130 },
    ]);
  });

  it("handles Z commands without crashing", () => {
    const coords = extractPathCoords("M 0 0 L 100 0 L 100 100 L 0 100 Z");
    expect(coords).toHaveLength(4);
  });

  it("returns empty array for empty string", () => {
    expect(extractPathCoords("")).toEqual([]);
  });

  it("handles negative coordinates", () => {
    const coords = extractPathCoords("M -10 -20 L 30 -40");
    expect(coords).toEqual([
      { x: -10, y: -20 },
      { x: 30, y: -40 },
    ]);
  });
});

describe("computeTightBounds", () => {
  it("computes tight bounds from paths", () => {
    const paths: ScenePath[] = [
      { id: "p1", d: "M 50 100 L 200 100 L 200 300 L 50 300 Z" },
    ];
    const result = computeTightBounds(paths, [], 0);
    expect(result).toEqual({ x: 50, y: 100, width: 150, height: 200 });
  });

  it("applies padding on all sides", () => {
    const paths: ScenePath[] = [{ id: "p1", d: "M 50 100 L 200 300" }];
    const result = computeTightBounds(paths, [], 20);
    expect(result).toEqual({ x: 30, y: 80, width: 190, height: 240 });
  });

  it("uses default padding of 30", () => {
    const paths: ScenePath[] = [{ id: "p1", d: "M 0 0 L 100 100" }];
    const result = computeTightBounds(paths, []);
    expect(result).toEqual({ x: -30, y: -30, width: 160, height: 160 });
  });

  it("includes label positions in bounds", () => {
    const paths: ScenePath[] = [{ id: "p1", d: "M 100 100 L 200 200" }];
    const labels: SceneLabel[] = [
      {
        id: "l1",
        text: "Hello",
        x: 300,
        y: 150,
        anchor: "start",
        fontSize: 14,
      },
    ];
    const result = computeTightBounds(paths, labels, 0);
    // Label "Hello" (5 chars × 14 × 0.6 = 42 wide) at x=300 extends to 342
    // Label y extends from 150-14=136 to 150
    // Paths: x=[100,200], y=[100,200]
    // Combined: x=[100,342], y=[100,200] (136 > 100 so min y stays 100)
    expect(result.x).toBe(100);
    expect(result.y).toBe(100);
    expect(result.width).toBeCloseTo(242, 0);
    expect(result.height).toBe(100);
  });

  it("handles middle-anchored labels", () => {
    const labels: SceneLabel[] = [
      { id: "l1", text: "AB", x: 100, y: 50, anchor: "middle", fontSize: 20 },
    ];
    const result = computeTightBounds([], labels, 0);
    // "AB" = 2 chars × 20 × 0.6 = 24 wide, centered at 100 → left=88, right=112
    // y: 50 - 20 = 30 to 50
    expect(result.x).toBe(88);
    expect(result.y).toBe(30);
    expect(result.width).toBe(24);
    expect(result.height).toBe(20);
  });

  it("returns zero bounds for empty input", () => {
    const result = computeTightBounds([], []);
    expect(result).toEqual({ x: 0, y: 0, width: 0, height: 0 });
  });

  it("combines multiple paths", () => {
    const paths: ScenePath[] = [
      { id: "p1", d: "M 10 10 L 50 50" },
      { id: "p2", d: "M 200 200 L 300 300" },
    ];
    const result = computeTightBounds(paths, [], 0);
    expect(result).toEqual({ x: 10, y: 10, width: 290, height: 290 });
  });
});
