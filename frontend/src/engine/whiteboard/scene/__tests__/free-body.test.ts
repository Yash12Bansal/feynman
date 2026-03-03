import { describe, it, expect } from "vitest";
import { freeBodyDiagram } from "../templates/free-body";

describe("freeBodyDiagram", () => {
  it("always includes block + surface + hatch paths", () => {
    const result = freeBodyDiagram({
      showWeight: false,
      showNormal: false,
    });

    const blockPath = result.paths.find((p) => p.id === "block");
    const surfacePath = result.paths.find((p) => p.id === "surface");
    expect(blockPath).toBeTruthy();
    expect(surfacePath).toBeTruthy();
  });

  it("includes block label", () => {
    const result = freeBodyDiagram();
    const blockLabel = result.labels.find((l) => l.id === "block-label");
    expect(blockLabel).toBeTruthy();
    expect(blockLabel!.text).toBe("m");
  });

  it("includes weight arrow paths when showWeight=true", () => {
    const result = freeBodyDiagram({ showWeight: true, showNormal: false });
    const weightShaft = result.paths.find((p) => p.id === "weight-shaft");
    const weightHead = result.paths.find((p) => p.id === "weight-head");
    expect(weightShaft).toBeTruthy();
    expect(weightHead).toBeTruthy();
  });

  it("includes weight label when showWeight=true", () => {
    const result = freeBodyDiagram({ showWeight: true });
    const weightLabel = result.labels.find((l) => l.id === "weight-label");
    expect(weightLabel).toBeTruthy();
    expect(weightLabel!.text).toBe("W");
  });

  it("omits weight when showWeight=false", () => {
    const result = freeBodyDiagram({ showWeight: false });
    const weightPaths = result.paths.filter((p) => p.id.startsWith("weight"));
    expect(weightPaths).toHaveLength(0);
  });

  it("includes normal arrow when showNormal=true", () => {
    const result = freeBodyDiagram({ showNormal: true });
    const normalShaft = result.paths.find((p) => p.id === "normal-shaft");
    expect(normalShaft).toBeTruthy();
  });

  it("includes friction arrow when showFriction=true", () => {
    const result = freeBodyDiagram({ showFriction: true });
    const frictionShaft = result.paths.find((p) => p.id === "friction-shaft");
    expect(frictionShaft).toBeTruthy();
    const frictionLabel = result.labels.find((l) => l.id === "friction-label");
    expect(frictionLabel).toBeTruthy();
    expect(frictionLabel!.text).toBe("f");
  });

  it("omits friction when showFriction=false (default)", () => {
    const result = freeBodyDiagram();
    const frictionPaths = result.paths.filter((p) =>
      p.id.startsWith("friction"),
    );
    expect(frictionPaths).toHaveLength(0);
  });

  it("includes applied force when showApplied=true", () => {
    const result = freeBodyDiagram({ showApplied: true });
    const appliedShaft = result.paths.find((p) => p.id === "applied-shaft");
    expect(appliedShaft).toBeTruthy();
    const appliedLabel = result.labels.find((l) => l.id === "applied-label");
    expect(appliedLabel).toBeTruthy();
    expect(appliedLabel!.text).toBe("F");
  });

  it("includes spring + wall when showSpring=true", () => {
    const result = freeBodyDiagram({ showSpring: true });
    const wallPath = result.paths.find((p) => p.id === "wall");
    const springCoil = result.paths.find((p) => p.id === "spring-coil");
    expect(wallPath).toBeTruthy();
    expect(springCoil).toBeTruthy();
  });

  it("omits spring/wall when showSpring=false (default)", () => {
    const result = freeBodyDiagram();
    const wallPath = result.paths.find((p) => p.id === "wall");
    const springCoil = result.paths.find((p) => p.id === "spring-coil");
    expect(wallPath).toBeUndefined();
    expect(springCoil).toBeUndefined();
  });

  it("returns tight bounds containing all content", () => {
    const result = freeBodyDiagram();
    // Tight bounds should be smaller than the old 500x400 fixed canvas
    // but large enough to contain all content with padding
    expect(result.bounds.width).toBeGreaterThan(200);
    expect(result.bounds.width).toBeLessThan(500);
    expect(result.bounds.height).toBeGreaterThan(150);
    expect(result.bounds.height).toBeLessThan(400);

    // Should have positive extent (not degenerate)
    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });

  it("full diagram has larger bounds than minimal diagram", () => {
    const minimal = freeBodyDiagram({
      showWeight: false,
      showNormal: false,
    });
    const full = freeBodyDiagram({
      showWeight: true,
      showNormal: true,
      showFriction: true,
      showApplied: true,
      showSpring: true,
    });
    // Full diagram with arrows + spring extends further
    expect(full.bounds.width * full.bounds.height).toBeGreaterThan(
      minimal.bounds.width * minimal.bounds.height,
    );
  });

  it("has blockCenter anchor", () => {
    const result = freeBodyDiagram();
    expect(result.anchors?.blockCenter).toEqual({ x: 250, y: 200 });
  });

  it("full diagram has all expected components", () => {
    const result = freeBodyDiagram({
      showWeight: true,
      showNormal: true,
      showFriction: true,
      showApplied: true,
      showSpring: true,
    });

    // All major component IDs should be present
    const pathIds = result.paths.map((p) => p.id);
    expect(pathIds).toContain("block");
    expect(pathIds).toContain("surface");
    expect(pathIds).toContain("weight-shaft");
    expect(pathIds).toContain("normal-shaft");
    expect(pathIds).toContain("friction-shaft");
    expect(pathIds).toContain("applied-shaft");
    expect(pathIds).toContain("spring-coil");
    expect(pathIds).toContain("wall");
  });

  it("default params produce weight + normal only", () => {
    const result = freeBodyDiagram({});
    const pathIds = result.paths.map((p) => p.id);

    // Should have weight and normal
    expect(pathIds).toContain("weight-shaft");
    expect(pathIds).toContain("normal-shaft");

    // Should NOT have friction, applied, spring
    expect(pathIds).not.toContain("friction-shaft");
    expect(pathIds).not.toContain("applied-shaft");
    expect(pathIds).not.toContain("spring-coil");
  });
});
