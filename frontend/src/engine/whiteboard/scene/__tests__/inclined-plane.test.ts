import { describe, it, expect } from "vitest";
import { inclinedPlane } from "../components/inclined-plane";
import { COLORS } from "../../../theme";

describe("inclinedPlane", () => {
  it("returns a triangle outline (closed path with Z)", () => {
    const result = inclinedPlane({ x: 100, y: 300, id: "ip1" });

    const outline = result.paths.find((p) => p.id === "ip1-outline");
    expect(outline).toBeDefined();
    expect(outline!.d).toContain("Z");
  });

  it("triangle has three vertices in the path", () => {
    const result = inclinedPlane({
      x: 100,
      y: 300,
      baseWidth: 200,
      angle: 30,
      id: "tri",
    });

    const d = result.paths[0].d;
    // M baseLeft L baseRight L peak Z
    expect(d).toContain("M 100 300");
    expect(d).toContain("L 300 300");
    // peak y = 300 - 200*tan(30°) ≈ 300 - 115.47
    const peakY = 300 - 200 * Math.tan((30 * Math.PI) / 180);
    expect(d).toContain(`L 300 ${peakY}`);
  });

  it("returns all 5 anchors at correct positions", () => {
    const result = inclinedPlane({
      x: 50,
      y: 400,
      baseWidth: 200,
      angle: 45,
      id: "anch",
    });

    const height = 200 * Math.tan((45 * Math.PI) / 180);
    const anchors = result.anchors!;

    expect(anchors.baseLeft).toEqual({ x: 50, y: 400 });
    expect(anchors.baseRight).toEqual({ x: 250, y: 400 });
    expect(anchors.peak.x).toBeCloseTo(250);
    expect(anchors.peak.y).toBeCloseTo(400 - height);
    expect(anchors.slopeCenter.x).toBeCloseTo((50 + 250) / 2);
    expect(anchors.slopeCenter.y).toBeCloseTo((400 + 400 - height) / 2);
    expect(anchors.baseCenter).toEqual({ x: 150, y: 400 });
  });

  it("peak height = baseWidth * tan(angle)", () => {
    const baseWidth = 150;
    const angle = 40;
    const result = inclinedPlane({
      x: 0,
      y: 300,
      baseWidth,
      angle,
      id: "height",
    });

    const expectedHeight = baseWidth * Math.tan((angle * Math.PI) / 180);
    expect(result.anchors!.peak.y).toBeCloseTo(300 - expectedHeight);
  });

  it("default angle is 30 degrees", () => {
    const result = inclinedPlane({
      x: 0,
      y: 300,
      baseWidth: 200,
      id: "default-angle",
    });

    const expectedHeight = 200 * Math.tan((30 * Math.PI) / 180);
    expect(result.anchors!.peak.y).toBeCloseTo(300 - expectedHeight);
  });

  it("angle arc present by default", () => {
    const result = inclinedPlane({ x: 0, y: 300, id: "arc" });

    const arcPath = result.paths.find((p) => p.id === "arc-angle-arc");
    expect(arcPath).toBeDefined();
    expect(arcPath!.d).toContain("A"); // SVG arc command
  });

  it("angle arc absent when showAngle is false", () => {
    const result = inclinedPlane({
      x: 0,
      y: 300,
      showAngle: false,
      id: "noarc",
    });

    const arcPath = result.paths.find((p) => p.id === "noarc-angle-arc");
    expect(arcPath).toBeUndefined();
  });

  it("angle label present when provided", () => {
    const result = inclinedPlane({
      x: 0,
      y: 300,
      angleLabel: "θ",
      id: "labeled",
    });

    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("θ");
    expect(result.labels[0].id).toBe("labeled-angle-label");
  });

  it("hatch marks present when showHatch is true", () => {
    const result = inclinedPlane({
      x: 0,
      y: 300,
      showHatch: true,
      id: "hatch",
    });

    const hatchPaths = result.paths.filter((p) => p.id.includes("hatch"));
    expect(hatchPaths.length).toBeGreaterThan(0);
  });

  it("hatch marks absent by default", () => {
    const result = inclinedPlane({ x: 0, y: 300, id: "plain" });

    const hatchPaths = result.paths.filter((p) => p.id.includes("-hatch-"));
    expect(hatchPaths).toHaveLength(0);
  });

  it("applies custom color", () => {
    const result = inclinedPlane({
      x: 0,
      y: 300,
      color: "#00ff00",
      id: "colored",
    });

    expect(result.paths[0].roughOptions?.stroke).toBe("#00ff00");
  });

  it("uses textSecondary as default color", () => {
    const result = inclinedPlane({ x: 0, y: 300, id: "default-color" });

    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textSecondary);
  });

  it("bounds encompass the full triangle", () => {
    const result = inclinedPlane({
      x: 50,
      y: 400,
      baseWidth: 200,
      angle: 45,
      id: "bounds",
    });

    const height = 200 * Math.tan((45 * Math.PI) / 180);
    expect(result.bounds.x).toBe(50);
    expect(result.bounds.y).toBeCloseTo(400 - height);
    expect(result.bounds.width).toBe(200);
    expect(result.bounds.height).toBeCloseTo(height);
  });
});
