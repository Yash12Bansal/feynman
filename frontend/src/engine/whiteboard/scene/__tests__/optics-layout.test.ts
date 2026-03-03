import { describe, it, expect } from "vitest";
import { leftToRightOpticalBench } from "../layout/strategies/optics-layout";
import { defaultLayoutContext } from "../components/types";

// Components are registered via side-effect imports inside optics-layout.ts

const ctx = { ...defaultLayoutContext(), sceneWidth: 700 };

// ── Wave Optics Mode ─────────────────────────────────────────

describe("leftToRightOpticalBench — wave optics", () => {
  it("renders optical axis as dashed line", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source", label: "S" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 2, slit_separation: 50 },
        },
        { id: "det", kind: "screen", label: "Screen" },
      ],
      ctx,
    );

    const axis = result.paths.find((p) => p.id === "optical-axis");
    expect(axis).toBeDefined();
    expect(axis!.roughOptions?.strokeLineDash).toBeDefined();
  });

  it("renders source, barrier sections, and screen", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 2, slit_separation: 50 },
        },
        { id: "det", kind: "screen" },
      ],
      ctx,
    );

    // Source circle
    expect(result.paths.some((p) => p.id === "source-circle")).toBe(true);
    // Barrier sections (3 for 2 slits)
    const barrierPaths = result.paths.filter((p) =>
      p.id.startsWith("wall-section"),
    );
    expect(barrierPaths.length).toBe(3);
    // Screen
    expect(result.paths.some((p) => p.id === "det-line")).toBe(true);
  });

  it("generates rays from source to each slit", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 2, slit_separation: 50 },
        },
        { id: "det", kind: "screen" },
      ],
      ctx,
    );

    const rayPaths = result.paths.filter((p) =>
      p.id.startsWith("source-to-slit"),
    );
    expect(rayPaths.length).toBeGreaterThanOrEqual(2);
  });

  it("generates wavefront arcs from slits (2 slits × 3 radii = 6)", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 2, slit_separation: 50 },
        },
        { id: "det", kind: "screen" },
      ],
      ctx,
    );

    const wavefronts = result.paths.filter((p) =>
      p.id.startsWith("wavefront-"),
    );
    expect(wavefronts.length).toBe(6);
  });

  it("generates interference pattern for 2 slits (7 bright + 6 dark)", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 2, slit_separation: 50 },
        },
        { id: "det", kind: "screen" },
      ],
      ctx,
    );

    const brightBands = result.paths.filter((p) =>
      p.id.startsWith("bright-band"),
    );
    const darkBands = result.paths.filter((p) => p.id.startsWith("dark-band"));
    expect(brightBands.length).toBe(7);
    expect(darkBands.length).toBe(6);
  });

  it("single slit: wavefronts but no interference pattern", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 1, slit_separation: 0 },
        },
        { id: "det", kind: "screen" },
      ],
      ctx,
    );

    // Should still have wavefronts
    const wavefronts = result.paths.filter((p) =>
      p.id.startsWith("wavefront-"),
    );
    expect(wavefronts.length).toBe(3); // 1 slit × 3 radii

    // No interference pattern
    const brightBands = result.paths.filter((p) =>
      p.id.startsWith("bright-band"),
    );
    expect(brightBands.length).toBe(0);
  });

  it("computes non-zero tight bounds", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 2, slit_separation: 50 },
        },
        { id: "det", kind: "screen" },
      ],
      ctx,
    );

    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });

  it("has axisCenter anchor", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "source", kind: "point_source" },
        {
          id: "wall",
          kind: "barrier",
          extras: { slit_count: 2, slit_separation: 50 },
        },
        { id: "det", kind: "screen" },
      ],
      ctx,
    );

    expect(result.anchors?.axisCenter).toEqual({ x: 350, y: 200 });
  });
});

// ── Ray Optics Mode ──────────────────────────────────────────

describe("leftToRightOpticalBench — ray optics", () => {
  it("renders optical axis and convex lens", () => {
    const result = leftToRightOpticalBench(
      [
        {
          id: "lens",
          kind: "convex_lens",
          label: "L",
          extras: { focal_length: 80 },
        },
        {
          id: "obj",
          kind: "force_arrow",
          label: "Object",
          extras: { object_distance: 160, object_height: 50 },
        },
      ],
      ctx,
    );

    expect(result.paths.some((p) => p.id === "optical-axis")).toBe(true);
    expect(result.paths.some((p) => p.id === "lens-left")).toBe(true);
    expect(result.paths.some((p) => p.id === "lens-right")).toBe(true);
  });

  it("renders focal point markers (F and F')", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "lens", kind: "convex_lens", extras: { focal_length: 80 } },
        {
          id: "obj",
          kind: "force_arrow",
          extras: { object_distance: 160, object_height: 50 },
        },
      ],
      ctx,
    );

    expect(result.paths.some((p) => p.id === "focal-F")).toBe(true);
    expect(result.paths.some((p) => p.id === "focal-F'")).toBe(true);
    expect(result.labels.some((l) => l.text === "F")).toBe(true);
    expect(result.labels.some((l) => l.text === "F'")).toBe(true);
  });

  it("renders object and image arrows for convex lens", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "lens", kind: "convex_lens", extras: { focal_length: 80 } },
        {
          id: "obj",
          kind: "force_arrow",
          label: "Object",
          extras: { object_distance: 160, object_height: 50 },
        },
      ],
      ctx,
    );

    expect(result.paths.some((p) => p.id === "obj-obj-shaft")).toBe(true);
    expect(result.paths.some((p) => p.id === "obj-img-shaft")).toBe(true);
  });

  it("renders 3 principal rays (each has shaft path)", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "lens", kind: "convex_lens", extras: { focal_length: 80 } },
        {
          id: "obj",
          kind: "force_arrow",
          extras: { object_distance: 160, object_height: 50 },
        },
      ],
      ctx,
    );

    // Ray 1
    expect(result.paths.some((p) => p.id === "ray1-seg1-shaft")).toBe(true);
    expect(result.paths.some((p) => p.id === "ray1-seg2-shaft")).toBe(true);
    // Ray 2
    expect(result.paths.some((p) => p.id === "ray2-shaft")).toBe(true);
    // Ray 3
    expect(result.paths.some((p) => p.id === "ray3-seg1-shaft")).toBe(true);
    expect(result.paths.some((p) => p.id === "ray3-seg2-shaft")).toBe(true);
  });

  it("convex lens at 2f: real inverted image", () => {
    const f = 80;
    const result = leftToRightOpticalBench(
      [
        { id: "lens", kind: "convex_lens", extras: { focal_length: f } },
        {
          id: "obj",
          kind: "force_arrow",
          extras: { object_distance: f * 2, object_height: 50 },
        },
      ],
      ctx,
    );

    // Image arrow should exist (real image for convex at 2f)
    const imgPaths = result.paths.filter((p) => p.id.startsWith("obj-img"));
    expect(imgPaths.length).toBeGreaterThan(0);
  });

  it("concave lens: produces dashed virtual image extensions", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "lens", kind: "concave_lens", extras: { focal_length: 80 } },
        {
          id: "obj",
          kind: "force_arrow",
          extras: { object_distance: 120, object_height: 50 },
        },
      ],
      ctx,
    );

    // Should have dashed extension paths for virtual rays
    const extPaths = result.paths.filter((p) => p.id.includes("ext"));
    expect(extPaths.length).toBeGreaterThan(0);
  });

  it("lens only (no object): renders lens and focal points, no rays", () => {
    const result = leftToRightOpticalBench(
      [{ id: "lens", kind: "convex_lens", extras: { focal_length: 80 } }],
      ctx,
    );

    expect(result.paths.some((p) => p.id === "optical-axis")).toBe(true);
    expect(result.paths.some((p) => p.id === "lens-left")).toBe(true);
    // No ray tracing without object
    expect(result.paths.some((p) => p.id === "ray1-seg1-shaft")).toBe(false);
  });

  it("uses underscore-to-hyphen normalization for kinds", () => {
    const result = leftToRightOpticalBench(
      [
        { id: "lens", kind: "convex_lens", extras: { focal_length: 80 } },
        {
          id: "obj",
          kind: "force_arrow",
          extras: { object_distance: 160, object_height: 50 },
        },
      ],
      ctx,
    );

    // convex_lens → convex-lens should be found
    expect(result.paths.some((p) => p.id === "lens-left")).toBe(true);
  });
});
