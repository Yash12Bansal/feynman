import { describe, it, expect } from "vitest";
import {
  sampleEllipse,
  sampleLine,
  sampleQuadBezier,
  outlineToSvgPath,
  ellipseCenterline,
  lineCenterline,
  bezierCenterline,
  computeArrowhead,
  estimatePathLength,
  inputPointsToPath,
  annotationSeed,
} from "../content/annotation-paths";

// ── sampleEllipse ─────────────────────────────────────────────

describe("sampleEllipse", () => {
  it("returns correct number of points", () => {
    const points = sampleEllipse(100, 100, 50, 30, 36);
    // n+1 points (inclusive ends)
    expect(points.length).toBe(37);
  });

  it("points stay within expected bounds", () => {
    const cx = 200;
    const cy = 150;
    const rx = 60;
    const ry = 40;
    const points = sampleEllipse(cx, cy, rx, ry, 72);
    for (const p of points) {
      // Allow wobble margin
      expect(p.x).toBeGreaterThan(cx - rx - 10);
      expect(p.x).toBeLessThan(cx + rx + 10);
      expect(p.y).toBeGreaterThan(cy - ry - 10);
      expect(p.y).toBeLessThan(cy + ry + 10);
    }
  });

  it("pressure values are between 0 and 1", () => {
    const points = sampleEllipse(0, 0, 50, 50, 72);
    for (const p of points) {
      expect(p.pressure).toBeGreaterThanOrEqual(0);
      expect(p.pressure).toBeLessThanOrEqual(1);
    }
  });

  it("first and last points are near each other (closed path)", () => {
    const points = sampleEllipse(100, 100, 50, 50, 72);
    const first = points[0];
    const last = points[points.length - 1];
    const dist = Math.sqrt((first.x - last.x) ** 2 + (first.y - last.y) ** 2);
    expect(dist).toBeLessThan(5);
  });
});

// ── sampleLine ────────────────────────────────────────────────

describe("sampleLine", () => {
  it("returns correct number of points", () => {
    const points = sampleLine(0, 0, 100, 0, 20);
    expect(points.length).toBe(21);
  });

  it("first point is near start, last near end", () => {
    const points = sampleLine(10, 20, 200, 20, 32);
    expect(Math.abs(points[0].x - 10)).toBeLessThan(5);
    expect(Math.abs(points[0].y - 20)).toBeLessThan(5);
    expect(Math.abs(points[points.length - 1].x - 200)).toBeLessThan(5);
    expect(Math.abs(points[points.length - 1].y - 20)).toBeLessThan(5);
  });

  it("pressure has correct shape (ramp-hold-taper)", () => {
    const points = sampleLine(0, 0, 100, 0, 100);
    // First point has lower pressure (ramp)
    expect(points[0].pressure).toBeLessThan(points[20].pressure);
    // Mid-range is at hold
    expect(points[50].pressure).toBeCloseTo(0.7, 1);
    // Last point tapers down
    expect(points[points.length - 1].pressure).toBeLessThan(0.1);
  });
});

// ── sampleQuadBezier ──────────────────────────────────────────

describe("sampleQuadBezier", () => {
  it("returns correct number of points", () => {
    const points = sampleQuadBezier([0, 0], [50, -30], [100, 0], 24);
    expect(points.length).toBe(25);
  });

  it("endpoints are near p0 and p2", () => {
    const p0: [number, number] = [10, 20];
    const cp: [number, number] = [50, -30];
    const p2: [number, number] = [90, 20];
    const points = sampleQuadBezier(p0, cp, p2, 48);
    expect(Math.abs(points[0].x - p0[0])).toBeLessThan(5);
    expect(Math.abs(points[0].y - p0[1])).toBeLessThan(5);
    expect(Math.abs(points[points.length - 1].x - p2[0])).toBeLessThan(5);
    expect(Math.abs(points[points.length - 1].y - p2[1])).toBeLessThan(5);
  });
});

// ── ellipseCenterline ─────────────────────────────────────────

describe("ellipseCenterline", () => {
  it("returns valid SVG arc path", () => {
    const path = ellipseCenterline(100, 100, 50, 30);
    expect(path).toContain("M ");
    expect(path).toContain("A ");
    expect(path).toContain("50 30"); // rx ry
  });
});

// ── lineCenterline ────────────────────────────────────────────

describe("lineCenterline", () => {
  it("returns M..L path string", () => {
    const path = lineCenterline(10, 20, 100, 20);
    expect(path).toBe("M 10 20 L 100 20");
  });
});

// ── bezierCenterline ──────────────────────────────────────────

describe("bezierCenterline", () => {
  it("returns M..Q path string", () => {
    const path = bezierCenterline([10, 20], [50, -10], [90, 20]);
    expect(path).toBe("M 10 20 Q 50 -10 90 20");
  });
});

// ── computeArrowhead ──────────────────────────────────────────

describe("computeArrowhead", () => {
  it("returns three vertices", () => {
    const ah = computeArrowhead([100, 50], 0, 14);
    expect(ah.tip).toEqual([100, 50]);
    expect(ah.left).toBeDefined();
    expect(ah.right).toBeDefined();
  });

  it("left and right are symmetric about the arrow axis", () => {
    const ah = computeArrowhead([100, 50], 0, 14);
    // For angle=0, left and right should have same x offset but mirrored y
    const leftDy = ah.left[1] - 50;
    const rightDy = ah.right[1] - 50;
    expect(Math.abs(leftDy + rightDy)).toBeLessThan(0.01);
  });

  it("arrow points in correct direction", () => {
    // Pointing right (angle=0): left and right should be to the left of tip
    const ah = computeArrowhead([100, 50], 0, 14);
    expect(ah.left[0]).toBeLessThan(100);
    expect(ah.right[0]).toBeLessThan(100);
  });
});

// ── estimatePathLength ────────────────────────────────────────

describe("estimatePathLength", () => {
  it("circle (equal radii) gives ~2*pi*r", () => {
    const r = 50;
    const len = estimatePathLength("ellipse", { rx: r, ry: r });
    expect(len).toBeCloseTo(2 * Math.PI * r, 0);
  });

  it("line length is Pythagorean", () => {
    const len = estimatePathLength("line", { x1: 0, y1: 0, x2: 3, y2: 4 });
    expect(len).toBeCloseTo(5, 6);
  });

  it("straight bezier ≈ line length", () => {
    const p0: [number, number] = [0, 0];
    const cp: [number, number] = [50, 0]; // midpoint control = straight
    const p2: [number, number] = [100, 0];
    const len = estimatePathLength("bezier", { p0, cp, p2 });
    expect(len).toBeCloseTo(100, 0);
  });

  it("curved bezier is longer than direct distance", () => {
    const p0: [number, number] = [0, 0];
    const cp: [number, number] = [50, -100]; // big curve
    const p2: [number, number] = [100, 0];
    const len = estimatePathLength("bezier", { p0, cp, p2 });
    const direct = 100;
    expect(len).toBeGreaterThan(direct);
  });
});

// ── outlineToSvgPath ──────────────────────────────────────────

describe("outlineToSvgPath", () => {
  it("returns empty for insufficient points", () => {
    expect(outlineToSvgPath([])).toBe("");
    expect(outlineToSvgPath([[0, 0]])).toBe("");
  });

  it("creates closed path with M..L..Z", () => {
    const path = outlineToSvgPath([
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
    ]);
    expect(path).toMatch(/^M /);
    expect(path).toContain("L ");
    expect(path).toMatch(/Z$/);
  });
});

// ── inputPointsToPath ─────────────────────────────────────────

describe("inputPointsToPath", () => {
  it("produces non-empty SVG path from sample points", () => {
    const points = sampleLine(0, 0, 100, 0, 20);
    const path = inputPointsToPath(points);
    expect(path.length).toBeGreaterThan(0);
    expect(path).toMatch(/^M /);
    expect(path).toContain("Z");
  });
});

// ── annotationSeed ────────────────────────────────────────────

describe("annotationSeed", () => {
  it("returns consistent value for same input", () => {
    expect(annotationSeed("eq-1")).toBe(annotationSeed("eq-1"));
  });

  it("returns different values for different inputs", () => {
    expect(annotationSeed("eq-1")).not.toBe(annotationSeed("eq-2"));
  });

  it("returns positive integer", () => {
    const seed = annotationSeed("test");
    expect(seed).toBeGreaterThan(0);
    expect(Number.isInteger(seed)).toBe(true);
  });
});
