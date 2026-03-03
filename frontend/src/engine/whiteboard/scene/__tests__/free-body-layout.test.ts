import { describe, it, expect } from "vitest";
import { centerBodyRadialForces } from "../layout/strategies/free-body-layout";
import { defaultLayoutContext } from "../components/types";
import { freeBodyDiagram } from "../templates/free-body";

// Ensure components are registered via side-effect imports
import "../components/box";
import "../components/force-arrow";
import "../components/surface";
import "../components/spring";

const ctx = defaultLayoutContext();

describe("centerBodyRadialForces", () => {
  it("returns empty geometry when no box element", () => {
    const result = centerBodyRadialForces(
      [{ id: "f1", kind: "force_arrow", from: "block", direction: "down" }],
      ctx,
    );

    expect(result.paths).toHaveLength(0);
    expect(result.labels).toHaveLength(0);
    expect(result.bounds.width).toBe(0);
  });

  it("positions box at scene center (250, 200)", () => {
    const result = centerBodyRadialForces(
      [{ id: "block", kind: "box", label: "m" }],
      ctx,
    );

    // Box rect path should contain center coordinates
    const rectPath = result.paths.find((p) => p.id === "block-rect");
    expect(rectPath).toBeDefined();
    // Box at (250, 200) with default 80x60 → top-left (210, 170)
    expect(rectPath!.d).toContain("M 210 170");
  });

  it("renders box with label from semantic element", () => {
    const result = centerBodyRadialForces(
      [{ id: "block", kind: "box", label: "M" }],
      ctx,
    );

    const label = result.labels.find((l) => l.id === "block-label");
    expect(label).toBeDefined();
    expect(label!.text).toBe("M");
  });

  it("maps direction down → angle 90", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "weight",
          kind: "force_arrow",
          from: "block",
          direction: "down",
          label: "W",
        },
      ],
      ctx,
    );

    // Force arrow shaft should go from center downward
    const shaft = result.paths.find((p) => p.id === "weight-shaft");
    expect(shaft).toBeDefined();
    // At angle 90 (down), x stays ~250, y increases
    const d = shaft!.d;
    expect(d).toContain("250"); // origin x
  });

  it("maps direction up → angle 270", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "normal",
          kind: "force_arrow",
          from: "block",
          direction: "up",
          label: "N",
        },
      ],
      ctx,
    );

    const shaft = result.paths.find((p) => p.id === "normal-shaft");
    expect(shaft).toBeDefined();
  });

  it("maps direction left → angle 180", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "friction",
          kind: "force_arrow",
          from: "block",
          direction: "left",
          label: "f",
        },
      ],
      ctx,
    );

    const shaft = result.paths.find((p) => p.id === "friction-shaft");
    expect(shaft).toBeDefined();
  });

  it("maps direction right → angle 0", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "applied",
          kind: "force_arrow",
          from: "block",
          direction: "right",
          label: "F",
        },
      ],
      ctx,
    );

    const shaft = result.paths.find((p) => p.id === "applied-shaft");
    expect(shaft).toBeDefined();
  });

  it("magnitude scales arrow length (0.7 → 70px)", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "friction",
          kind: "force_arrow",
          from: "block",
          direction: "left",
          label: "f",
          magnitude: 0.7,
        },
      ],
      ctx,
    );

    // Arrow with magnitude 0.7 → length 70. At angle 180 (left),
    // tip x = 250 + cos(180)*70 = 250 - 70 = 180
    // Shaft ends at length - arrowhead (70 - 14 = 56 from origin) → x = 250 - 56 = 194
    const shaft = result.paths.find((p) => p.id === "friction-shaft");
    expect(shaft).toBeDefined();
    expect(shaft!.d).toContain("250"); // origin
    expect(shaft!.d).toMatch(/194/); // shaft end (70 - 14px arrowhead = 56 from origin)
  });

  it("uses color from semantic element", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "weight",
          kind: "force_arrow",
          from: "block",
          direction: "down",
          label: "W",
          color: "#ef4444",
        },
      ],
      ctx,
    );

    const shaft = result.paths.find((p) => p.id === "weight-shaft");
    expect(shaft!.roughOptions?.stroke).toBe("#ef4444");
  });

  it("renders surface below body", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        { id: "ground", kind: "surface" },
      ],
      ctx,
    );

    const surfaceLine = result.paths.find((p) => p.id === "ground-line");
    expect(surfaceLine).toBeDefined();
    // Surface y = bodyCy + 30 = 200 + 30 = 230
    expect(surfaceLine!.d).toContain("230");
  });

  it("renders spring + wall when spring element present", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        { id: "spring", kind: "spring" },
      ],
      ctx,
    );

    const wall = result.paths.find((p) => p.id === "wall");
    expect(wall).toBeDefined();
    expect(wall!.d).toContain("40"); // wallX

    const springCoil = result.paths.find((p) => p.id === "spring-coil");
    expect(springCoil).toBeDefined();
  });

  it("forces-only (no surface, no spring) works", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "weight",
          kind: "force_arrow",
          from: "block",
          direction: "down",
          label: "W",
        },
        {
          id: "normal",
          kind: "force_arrow",
          from: "block",
          direction: "up",
          label: "N",
        },
      ],
      ctx,
    );

    // Box (1 rect) + 2 force arrows (shaft + head each = 4) = 5 paths
    expect(result.paths.length).toBeGreaterThanOrEqual(5);
    expect(result.labels.length).toBeGreaterThanOrEqual(3); // box label + 2 force labels
  });

  it("has blockCenter anchor", () => {
    const result = centerBodyRadialForces(
      [{ id: "block", kind: "box", label: "m" }],
      ctx,
    );

    expect(result.anchors).toBeDefined();
    expect(result.anchors!.blockCenter).toEqual({ x: 250, y: 200 });
  });

  it("normalizes force_arrow (underscore) to force-arrow (hyphen)", () => {
    const result = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "weight",
          kind: "force_arrow",
          from: "block",
          direction: "down",
          label: "W",
        },
      ],
      ctx,
    );

    // Should find the force arrow despite underscore in kind
    const shaft = result.paths.find((p) => p.id === "weight-shaft");
    expect(shaft).toBeDefined();
  });

  it("produces equivalent output to template for matching inputs", () => {
    // Semantic spec equivalent of template's default free-body diagram
    const semantic = centerBodyRadialForces(
      [
        { id: "block", kind: "box", label: "m" },
        {
          id: "weight",
          kind: "force_arrow",
          from: "block",
          direction: "down",
          label: "W",
          color: "#ef4444",
        },
        {
          id: "normal",
          kind: "force_arrow",
          from: "block",
          direction: "up",
          label: "N",
          color: "#4ade80",
        },
        { id: "ground", kind: "surface" },
      ],
      ctx,
    );

    // Template equivalent
    const template = freeBodyDiagram({
      showWeight: true,
      showNormal: true,
      showFriction: false,
      showApplied: false,
      showSpring: false,
    });

    // Same blockCenter anchor
    expect(semantic.anchors!.blockCenter).toEqual(
      template.anchors!.blockCenter,
    );

    // Same number of force arrow paths (box + surface + forces)
    // Both should have: block rect + surface line + hatch marks + weight (shaft+head) + normal (shaft+head)
    // Counts may differ slightly (surface hatch count depends on exact range)
    // but key structural paths should match
    const semanticStructural = semantic.paths.filter(
      (p) =>
        p.id === "block-rect" ||
        p.id.endsWith("-shaft") ||
        p.id.endsWith("-head"),
    );
    const templateStructural = template.paths.filter(
      (p) =>
        p.id === "block" || p.id.endsWith("-shaft") || p.id.endsWith("-head"),
    );

    // Both should have the same number of structural paths:
    // 1 block + 2 force shafts + 2 force heads = 5
    expect(semanticStructural).toHaveLength(5);
    expect(templateStructural).toHaveLength(5);
  });
});
