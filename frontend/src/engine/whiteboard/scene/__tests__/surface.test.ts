import { describe, it, expect } from "vitest";
import { surface } from "../components/surface";
import { COLORS } from "../../../theme";

describe("surface", () => {
  it("returns a surface line path", () => {
    const result = surface({ x1: 60, y: 230, x2: 440, id: "s1" });

    expect(result.paths.length).toBeGreaterThanOrEqual(1);
    expect(result.paths[0].id).toBe("s1-line");
    expect(result.paths[0].d).toContain("M 60 230");
    expect(result.paths[0].d).toContain("L 440 230");
  });

  it("hatch marks present by default", () => {
    const result = surface({ x1: 60, y: 200, x2: 440, id: "hatch" });

    const hatchPaths = result.paths.filter((p) => p.id.includes("hatch"));
    expect(hatchPaths.length).toBeGreaterThan(0);
  });

  it("hatch marks absent when showHatch is false", () => {
    const result = surface({
      x1: 60,
      y: 200,
      x2: 440,
      showHatch: false,
      id: "nohatch",
    });

    expect(result.paths).toHaveLength(1); // Only the surface line
    expect(result.paths[0].id).toBe("nohatch-line");
  });

  it("hatch count matches spacing", () => {
    // Surface from 0 to 100, spacing 20 → hatches at 20, 40, 60, 80
    const result = surface({
      x1: 0,
      y: 100,
      x2: 100,
      hatchSpacing: 20,
      id: "count",
    });

    const hatchPaths = result.paths.filter((p) => p.id.includes("hatch"));
    expect(hatchPaths).toHaveLength(4);
  });

  it("returns 3 correct anchors", () => {
    const result = surface({ x1: 50, y: 200, x2: 350, id: "anchors" });

    expect(result.anchors!.left).toEqual({ x: 50, y: 200 });
    expect(result.anchors!.right).toEqual({ x: 350, y: 200 });
    expect(result.anchors!.center).toEqual({ x: 200, y: 200 });
  });

  it("applies custom color", () => {
    const result = surface({
      x1: 0,
      y: 0,
      x2: 100,
      color: "#ff0000",
      id: "colored",
    });

    expect(result.paths[0].roughOptions?.stroke).toBe("#ff0000");
  });

  it("uses textSecondary as default color", () => {
    const result = surface({ x1: 0, y: 0, x2: 100, id: "default-color" });

    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textSecondary);
  });

  it("normalizes x1 > x2 (swap endpoints)", () => {
    const result = surface({ x1: 400, y: 100, x2: 100, id: "reversed" });

    // Surface line should go left to right regardless
    expect(result.paths[0].d).toContain("M 100 100");
    expect(result.paths[0].d).toContain("L 400 100");
    expect(result.anchors!.left).toEqual({ x: 100, y: 100 });
    expect(result.anchors!.right).toEqual({ x: 400, y: 100 });
  });

  it("hatch marks use diagonal lines below surface", () => {
    const result = surface({
      x1: 0,
      y: 100,
      x2: 100,
      hatchSpacing: 50,
      hatchLength: 12,
      id: "diag",
    });

    const hatch = result.paths.find((p) => p.id.includes("hatch"));
    expect(hatch).toBeDefined();
    // Hatch goes from (hx, y) to (hx-8, y+hatchLength)
    expect(hatch!.d).toContain("100"); // y coordinate
    expect(hatch!.d).toContain("112"); // y + hatchLength
  });

  it("bounds include hatch extent", () => {
    const result = surface({
      x1: 50,
      y: 200,
      x2: 350,
      hatchLength: 15,
      id: "bounds",
    });

    expect(result.bounds.y).toBe(200);
    expect(result.bounds.height).toBeGreaterThanOrEqual(15);
  });
});
