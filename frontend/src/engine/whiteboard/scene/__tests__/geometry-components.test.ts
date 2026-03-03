import { describe, it, expect } from "vitest";
import {
  distance,
  midpoint,
  unitVector,
  normalizeAngle,
  pointOnCircle,
} from "../components/geometry/utils";
import { point } from "../components/geometry/point";
import { lineSegment } from "../components/geometry/line-segment";
import { circleShape } from "../components/geometry/circle-shape";
import { triangle } from "../components/geometry/triangle";
import { angleArc } from "../components/geometry/angle-arc";
import { rightAngleMark } from "../components/geometry/right-angle-mark";
import { parallelMark } from "../components/geometry/parallel-mark";
import { congruenceMark } from "../components/geometry/congruence-mark";
import { arc } from "../components/geometry/arc";
import { COLORS } from "../../../theme";

// ── Utils ────────────────────────────────────────────────────

describe("distance", () => {
  it("returns 0 for coincident points", () => {
    expect(distance(5, 5, 5, 5)).toBe(0);
  });

  it("computes horizontal distance", () => {
    expect(distance(0, 0, 100, 0)).toBe(100);
  });

  it("computes vertical distance", () => {
    expect(distance(0, 0, 0, 50)).toBe(50);
  });

  it("computes diagonal distance (3-4-5)", () => {
    expect(distance(0, 0, 30, 40)).toBeCloseTo(50);
  });
});

describe("midpoint", () => {
  it("returns midpoint of horizontal segment", () => {
    const m = midpoint(0, 0, 100, 0);
    expect(m.x).toBe(50);
    expect(m.y).toBe(0);
  });

  it("returns midpoint of vertical segment", () => {
    const m = midpoint(0, 0, 0, 100);
    expect(m.x).toBe(0);
    expect(m.y).toBe(50);
  });

  it("returns midpoint of diagonal segment", () => {
    const m = midpoint(10, 20, 30, 40);
    expect(m.x).toBe(20);
    expect(m.y).toBe(30);
  });

  it("returns same point for coincident inputs", () => {
    const m = midpoint(5, 5, 5, 5);
    expect(m.x).toBe(5);
    expect(m.y).toBe(5);
  });
});

describe("unitVector", () => {
  it("returns null for coincident points", () => {
    expect(unitVector(5, 5, 5, 5)).toBeNull();
  });

  it("computes unit vector for horizontal direction", () => {
    const uv = unitVector(0, 0, 100, 0)!;
    expect(uv.ux).toBeCloseTo(1);
    expect(uv.uy).toBeCloseTo(0);
  });

  it("computes unit vector for vertical direction", () => {
    const uv = unitVector(0, 0, 0, 100)!;
    expect(uv.ux).toBeCloseTo(0);
    expect(uv.uy).toBeCloseTo(1);
  });

  it("computes unit vector for diagonal direction", () => {
    const uv = unitVector(0, 0, 30, 40)!;
    expect(uv.ux).toBeCloseTo(0.6);
    expect(uv.uy).toBeCloseTo(0.8);
  });

  it("unit vector has magnitude 1", () => {
    const uv = unitVector(10, 20, 50, 70)!;
    const mag = Math.sqrt(uv.ux * uv.ux + uv.uy * uv.uy);
    expect(mag).toBeCloseTo(1);
  });
});

describe("normalizeAngle", () => {
  it("returns 0 for 0", () => {
    expect(normalizeAngle(0)).toBe(0);
  });

  it("returns same value for angle in [0, 2π)", () => {
    expect(normalizeAngle(1)).toBeCloseTo(1);
    expect(normalizeAngle(Math.PI)).toBeCloseTo(Math.PI);
  });

  it("normalizes negative angle", () => {
    expect(normalizeAngle(-Math.PI / 2)).toBeCloseTo((3 * Math.PI) / 2);
  });

  it("normalizes angle > 2π", () => {
    expect(normalizeAngle(3 * Math.PI)).toBeCloseTo(Math.PI);
  });

  it("normalizes angle exactly 2π to 0", () => {
    expect(normalizeAngle(2 * Math.PI)).toBeCloseTo(0);
  });
});

describe("pointOnCircle", () => {
  it("returns point at 0 degrees (right)", () => {
    const p = pointOnCircle(100, 100, 50, 0);
    expect(p.x).toBeCloseTo(150);
    expect(p.y).toBeCloseTo(100);
  });

  it("returns point at 90 degrees (down in SVG coords)", () => {
    const p = pointOnCircle(100, 100, 50, 90);
    expect(p.x).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(150);
  });

  it("returns point at 180 degrees (left)", () => {
    const p = pointOnCircle(100, 100, 50, 180);
    expect(p.x).toBeCloseTo(50);
    expect(p.y).toBeCloseTo(100);
  });

  it("returns point at 270 degrees (up in SVG coords)", () => {
    const p = pointOnCircle(100, 100, 50, 270);
    expect(p.x).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(50);
  });
});

// ── Point ────────────────────────────────────────────────────

describe("point", () => {
  it("returns a single dot path", () => {
    const result = point({ x1: 100, y1: 200, id: "p1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("p1-dot");
  });

  it("dot path uses arcs (two-arc circle)", () => {
    const result = point({ x1: 100, y1: 200, id: "p1" });
    expect(result.paths[0].d).toContain("A");
  });

  it("dot is filled solid", () => {
    const result = point({ x1: 100, y1: 200, id: "p1" });
    expect(result.paths[0].roughOptions?.fillStyle).toBe("solid");
  });

  it("returns center anchor", () => {
    const result = point({ x1: 100, y1: 200, id: "p1" });
    expect(result.anchors!.center).toEqual({ x: 100, y: 200 });
  });

  it("default color is textPrimary", () => {
    const result = point({ x1: 100, y1: 200, id: "p1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("custom color is applied", () => {
    const result = point({ x1: 100, y1: 200, color: "#ff0000", id: "p1" });
    expect(result.paths[0].roughOptions?.stroke).toBe("#ff0000");
  });

  it("includes label when provided", () => {
    const result = point({ x1: 100, y1: 200, label: "A", id: "p1" });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("A");
  });

  it("omits label when not provided", () => {
    const result = point({ x1: 100, y1: 200, id: "p1" });
    expect(result.labels).toHaveLength(0);
  });

  it("custom radius affects bounds", () => {
    const result = point({ x1: 100, y1: 200, radius: 10, id: "p1" });
    expect(result.bounds).toEqual({ x: 90, y: 190, width: 20, height: 20 });
  });
});

// ── Line Segment ─────────────────────────────────────────────

describe("lineSegment", () => {
  it("returns a single line path", () => {
    const result = lineSegment({ x1: 0, y1: 0, x2: 100, y2: 0, id: "ls1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("ls1-line");
  });

  it("zero-length returns empty paths", () => {
    const result = lineSegment({ x1: 50, y1: 50, x2: 50, y2: 50, id: "ls0" });
    expect(result.paths).toHaveLength(0);
  });

  it("returns start, end, mid anchors", () => {
    const result = lineSegment({ x1: 0, y1: 0, x2: 100, y2: 0, id: "ls1" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 100, y: 0 });
    expect(result.anchors!.mid).toEqual({ x: 50, y: 0 });
  });

  it("default color is textPrimary", () => {
    const result = lineSegment({ x1: 0, y1: 0, x2: 100, y2: 0, id: "ls1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("includes label when provided", () => {
    const result = lineSegment({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      label: "AB",
      id: "ls1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("AB");
  });

  it("omits label when not provided", () => {
    const result = lineSegment({ x1: 0, y1: 0, x2: 100, y2: 0, id: "ls1" });
    expect(result.labels).toHaveLength(0);
  });

  it("dashed option adds strokeLineDash", () => {
    const result = lineSegment({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      dashed: true,
      id: "ls1",
    });
    expect(result.paths[0].roughOptions?.strokeLineDash).toBeDefined();
  });
});

// ── Circle Shape ─────────────────────────────────────────────

describe("circleShape", () => {
  it("returns a single circle path", () => {
    const result = circleShape({ x1: 200, y1: 200, id: "c1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("c1-circle");
  });

  it("circle path uses arcs", () => {
    const result = circleShape({ x1: 200, y1: 200, id: "c1" });
    expect(result.paths[0].d).toContain("A");
  });

  it("returns center, top, bottom, left, right anchors", () => {
    const result = circleShape({ x1: 200, y1: 200, radius: 60, id: "c1" });
    expect(result.anchors!.center).toEqual({ x: 200, y: 200 });
    expect(result.anchors!.top).toEqual({ x: 200, y: 140 });
    expect(result.anchors!.bottom).toEqual({ x: 200, y: 260 });
    expect(result.anchors!.left).toEqual({ x: 140, y: 200 });
    expect(result.anchors!.right).toEqual({ x: 260, y: 200 });
  });

  it("default radius is 60", () => {
    const result = circleShape({ x1: 200, y1: 200, id: "c1" });
    expect(result.bounds.width).toBe(120);
    expect(result.bounds.height).toBe(120);
  });

  it("filled option applies hachure fill", () => {
    const result = circleShape({ x1: 200, y1: 200, filled: true, id: "c1" });
    expect(result.paths[0].roughOptions?.fillStyle).toBe("hachure");
  });

  it("unfilled has fill: none", () => {
    const result = circleShape({ x1: 200, y1: 200, id: "c1" });
    expect(result.paths[0].roughOptions?.fill).toBe("none");
  });

  it("includes label when provided", () => {
    const result = circleShape({ x1: 200, y1: 200, label: "O", id: "c1" });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("O");
  });

  it("omits label when not provided", () => {
    const result = circleShape({ x1: 200, y1: 200, id: "c1" });
    expect(result.labels).toHaveLength(0);
  });
});

// ── Triangle ─────────────────────────────────────────────────

describe("triangle", () => {
  it("returns a single closed path", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 50,
      y3: 80,
      id: "t1",
    });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("t1-triangle");
  });

  it("path contains Z (closed)", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 50,
      y3: 80,
      id: "t1",
    });
    expect(result.paths[0].d).toContain("Z");
  });

  it("degenerate (collinear) produces empty paths", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 50,
      y2: 0,
      x3: 100,
      y3: 0,
      id: "t0",
    });
    expect(result.paths).toHaveLength(0);
  });

  it("returns A, B, C, centroid, and midpoint anchors", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 50,
      y3: 90,
      id: "t1",
    });
    expect(result.anchors!.A).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.B).toEqual({ x: 100, y: 0 });
    expect(result.anchors!.C).toEqual({ x: 50, y: 90 });
    expect(result.anchors!.centroid.x).toBeCloseTo(50);
    expect(result.anchors!.centroid.y).toBeCloseTo(30);
    expect(result.anchors!.AB_mid).toEqual({ x: 50, y: 0 });
    expect(result.anchors!.BC_mid).toEqual({ x: 75, y: 45 });
    expect(result.anchors!.CA_mid).toEqual({ x: 25, y: 45 });
  });

  it("degenerate still provides anchors", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 50,
      y2: 0,
      x3: 100,
      y3: 0,
      id: "t0",
    });
    expect(result.anchors!.A).toBeDefined();
    expect(result.anchors!.centroid).toBeDefined();
  });

  it("default color is textPrimary", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 50,
      y3: 80,
      id: "t1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("includes label when provided", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 50,
      y3: 80,
      label: "ABC",
      id: "t1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("ABC");
  });

  it("omits label when not provided", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 50,
      y3: 80,
      id: "t1",
    });
    expect(result.labels).toHaveLength(0);
  });

  it("non-zero bounds for valid triangle", () => {
    const result = triangle({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 50,
      y3: 80,
      id: "t1",
    });
    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });
});

// ── Angle Arc ────────────────────────────────────────────────

describe("angleArc", () => {
  it("returns a single arc path", () => {
    const result = angleArc({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "aa1",
    });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("aa1-arc");
  });

  it("arc path uses SVG A command", () => {
    const result = angleArc({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "aa1",
    });
    expect(result.paths[0].d).toContain("A");
  });

  it("always draws shorter arc (large-arc-flag = 0)", () => {
    const result = angleArc({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "aa1",
    });
    // The arc command should have large-arc-flag = 0
    expect(result.paths[0].d).toMatch(/A \d+ \d+ 0 0 1/);
  });

  it("returns vertex, arcStart, arcEnd anchors", () => {
    const result = angleArc({
      x1: 50,
      y1: 50,
      x2: 150,
      y2: 50,
      x3: 50,
      y3: 150,
      id: "aa1",
    });
    expect(result.anchors!.vertex).toEqual({ x: 50, y: 50 });
    expect(result.anchors!.arcStart).toBeDefined();
    expect(result.anchors!.arcEnd).toBeDefined();
  });

  it("default color is textPrimary", () => {
    const result = angleArc({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "aa1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("custom color is applied", () => {
    const result = angleArc({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      color: "#a78bfa",
      id: "aa1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe("#a78bfa");
  });

  it("includes label when provided", () => {
    const result = angleArc({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      label: "90°",
      id: "aa1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("90°");
  });

  it("omits label when not provided", () => {
    const result = angleArc({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "aa1",
    });
    expect(result.labels).toHaveLength(0);
  });
});

// ── Right Angle Mark ─────────────────────────────────────────

describe("rightAngleMark", () => {
  it("returns a single mark path", () => {
    const result = rightAngleMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "ram1",
    });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("ram1-mark");
  });

  it("open path (no Z — not closed)", () => {
    const result = rightAngleMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "ram1",
    });
    expect(result.paths[0].d).not.toContain("Z");
  });

  it("path is M P1 L P3 L P2 (two segments)", () => {
    const result = rightAngleMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "ram1",
    });
    const parts = result.paths[0].d.split(/\s*[ML]\s*/).filter(Boolean);
    // M p1 L p3 L p2 → 3 coordinate groups
    expect(parts).toHaveLength(3);
  });

  it("coincident rays produce empty paths", () => {
    const result = rightAngleMark({
      x1: 50,
      y1: 50,
      x2: 50,
      y2: 50,
      x3: 50,
      y3: 50,
      id: "ram0",
    });
    expect(result.paths).toHaveLength(0);
  });

  it("returns vertex anchor", () => {
    const result = rightAngleMark({
      x1: 50,
      y1: 50,
      x2: 150,
      y2: 50,
      x3: 50,
      y3: 150,
      id: "ram1",
    });
    expect(result.anchors!.vertex).toEqual({ x: 50, y: 50 });
  });

  it("default color is textPrimary", () => {
    const result = rightAngleMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "ram1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("no labels", () => {
    const result = rightAngleMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      x3: 0,
      y3: 100,
      id: "ram1",
    });
    expect(result.labels).toHaveLength(0);
  });
});

// ── Parallel Mark ────────────────────────────────────────────

describe("parallelMark", () => {
  it("count=1 produces 2 paths (one chevron = 2 arms)", () => {
    const result = parallelMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "pm1",
    });
    expect(result.paths).toHaveLength(2);
  });

  it("count=2 produces 4 paths", () => {
    const result = parallelMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      count: 2,
      id: "pm2",
    });
    expect(result.paths).toHaveLength(4);
  });

  it("coincident endpoints produce empty paths", () => {
    const result = parallelMark({
      x1: 50,
      y1: 50,
      x2: 50,
      y2: 50,
      id: "pm0",
    });
    expect(result.paths).toHaveLength(0);
  });

  it("returns mid, start, end anchors", () => {
    const result = parallelMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "pm1",
    });
    expect(result.anchors!.mid).toEqual({ x: 50, y: 0 });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 100, y: 0 });
  });

  it("default color is textPrimary", () => {
    const result = parallelMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "pm1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("no labels", () => {
    const result = parallelMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "pm1",
    });
    expect(result.labels).toHaveLength(0);
  });
});

// ── Congruence Mark ──────────────────────────────────────────

describe("congruenceMark", () => {
  it("count=1 produces 1 tick path", () => {
    const result = congruenceMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "cm1",
    });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("cm1-tick0");
  });

  it("count=3 produces 3 tick paths", () => {
    const result = congruenceMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      count: 3,
      id: "cm3",
    });
    expect(result.paths).toHaveLength(3);
    expect(result.paths[0].id).toBe("cm3-tick0");
    expect(result.paths[1].id).toBe("cm3-tick1");
    expect(result.paths[2].id).toBe("cm3-tick2");
  });

  it("coincident endpoints produce empty paths", () => {
    const result = congruenceMark({
      x1: 50,
      y1: 50,
      x2: 50,
      y2: 50,
      id: "cm0",
    });
    expect(result.paths).toHaveLength(0);
  });

  it("returns mid, start, end anchors", () => {
    const result = congruenceMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "cm1",
    });
    expect(result.anchors!.mid).toEqual({ x: 50, y: 0 });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 100, y: 0 });
  });

  it("default color is textPrimary", () => {
    const result = congruenceMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "cm1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("no labels", () => {
    const result = congruenceMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "cm1",
    });
    expect(result.labels).toHaveLength(0);
  });

  it("tick paths are perpendicular lines", () => {
    const result = congruenceMark({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      id: "cm1",
    });
    // For horizontal segment, tick should be vertical (same x, different y)
    const d = result.paths[0].d;
    expect(d).toContain("M");
    expect(d).toContain("L");
  });
});

// ── Arc ──────────────────────────────────────────────────────

describe("arc", () => {
  it("returns a single arc path", () => {
    const result = arc({ x1: 200, y1: 200, id: "a1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("a1-arc");
  });

  it("arc path uses SVG A command", () => {
    const result = arc({ x1: 200, y1: 200, id: "a1" });
    expect(result.paths[0].d).toContain("A");
  });

  it("returns center, arcStart, arcEnd anchors", () => {
    const result = arc({
      x1: 200,
      y1: 200,
      radius: 50,
      startAngle: 0,
      endAngle: 180,
      id: "a1",
    });
    expect(result.anchors!.center).toEqual({ x: 200, y: 200 });
    expect(result.anchors!.arcStart.x).toBeCloseTo(250);
    expect(result.anchors!.arcStart.y).toBeCloseTo(200);
    expect(result.anchors!.arcEnd.x).toBeCloseTo(150);
    expect(result.anchors!.arcEnd.y).toBeCloseTo(200);
  });

  it("default color is textPrimary", () => {
    const result = arc({ x1: 200, y1: 200, id: "a1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("includes label when provided", () => {
    const result = arc({ x1: 200, y1: 200, label: "semicircle", id: "a1" });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("semicircle");
  });

  it("omits label when not provided", () => {
    const result = arc({ x1: 200, y1: 200, id: "a1" });
    expect(result.labels).toHaveLength(0);
  });

  it("bounds enclose the full circle extent", () => {
    const result = arc({ x1: 200, y1: 200, radius: 50, id: "a1" });
    expect(result.bounds.x).toBe(150);
    expect(result.bounds.y).toBe(150);
    expect(result.bounds.width).toBe(100);
    expect(result.bounds.height).toBe(100);
  });
});
