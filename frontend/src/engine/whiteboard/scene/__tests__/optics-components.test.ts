import { describe, it, expect } from "vitest";
import { pointSource } from "../components/optics/point-source";
import { ray } from "../components/optics/ray";
import { screen } from "../components/optics/screen";
import { barrier } from "../components/optics/barrier";
import { wavefrontArc } from "../components/optics/wavefront-arc";
import { convexLens } from "../components/optics/convex-lens";
import { concaveLens } from "../components/optics/concave-lens";
import { prism } from "../components/optics/prism";
import { COLORS } from "../../../theme";

// ── Point Source ─────────────────────────────────────────────

describe("pointSource", () => {
  it("returns a circle path with correct id", () => {
    const result = pointSource({ cx: 100, cy: 200, id: "s1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("s1-circle");
  });

  it("circle path uses two arcs (closed shape)", () => {
    const result = pointSource({ cx: 100, cy: 200, id: "s1" });
    expect(result.paths[0].d).toContain("A");
    expect(result.paths[0].d).toContain("Z");
  });

  it("default color is accentBlue", () => {
    const result = pointSource({ cx: 100, cy: 200, id: "s1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.accentBlue);
    expect(result.paths[0].roughOptions?.fill).toBe(COLORS.accentBlue);
  });

  it("returns 5 anchors at correct positions", () => {
    const result = pointSource({ cx: 100, cy: 200, radius: 6, id: "s1" });
    const a = result.anchors!;
    expect(a.center).toEqual({ x: 100, y: 200 });
    expect(a.right).toEqual({ x: 106, y: 200 });
    expect(a.left).toEqual({ x: 94, y: 200 });
    expect(a.top).toEqual({ x: 100, y: 194 });
    expect(a.bottom).toEqual({ x: 100, y: 206 });
  });

  it("includes label when provided", () => {
    const result = pointSource({ cx: 100, cy: 200, label: "S", id: "s1" });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("S");
  });

  it("omits label when not provided", () => {
    const result = pointSource({ cx: 100, cy: 200, id: "s1" });
    expect(result.labels).toHaveLength(0);
  });

  it("custom radius affects bounds", () => {
    const result = pointSource({ cx: 100, cy: 200, radius: 10, id: "s1" });
    expect(result.bounds).toEqual({ x: 90, y: 190, width: 20, height: 20 });
  });
});

// ── Ray ──────────────────────────────────────────────────────

describe("ray", () => {
  it("returns shaft + head paths by default", () => {
    const result = ray({ x1: 0, y1: 0, x2: 100, y2: 0, id: "r1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(2);
    expect(result.paths[0].id).toBe("r1-shaft");
    expect(result.paths[1].id).toBe("r1-head");
  });

  it("zero-length ray returns empty paths", () => {
    const result = ray({ x1: 50, y1: 50, x2: 50, y2: 50, id: "r0" });
    expect(result.paths).toHaveLength(0);
  });

  it("dashed ray has strokeLineDash", () => {
    const result = ray({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      dashed: true,
      id: "r1",
    });
    expect(result.paths[0].roughOptions?.strokeLineDash).toEqual([8, 6]);
  });

  it("showArrow=false omits arrowhead", () => {
    const result = ray({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      showArrow: false,
      id: "r1",
    });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("r1-shaft");
  });

  it("returns start, end, mid anchors", () => {
    const result = ray({ x1: 0, y1: 0, x2: 100, y2: 0, id: "r1" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 100, y: 0 });
    expect(result.anchors!.mid).toEqual({ x: 50, y: 0 });
  });

  it("includes label when provided", () => {
    const result = ray({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      label: "Ray 1",
      id: "r1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("Ray 1");
  });

  it("custom color is applied", () => {
    const result = ray({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      color: "#ff0000",
      id: "r1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe("#ff0000");
  });
});

// ── Screen ───────────────────────────────────────────────────

describe("screen", () => {
  it("returns a single vertical line path", () => {
    const result = screen({ x: 300, yTop: 50, yBottom: 350, id: "scr1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("scr1-line");
    expect(result.paths[0].d).toContain("M 300 50");
    expect(result.paths[0].d).toContain("L 300 350");
  });

  it("returns top, bottom, center anchors", () => {
    const result = screen({ x: 300, yTop: 50, yBottom: 350, id: "scr1" });
    expect(result.anchors!.top).toEqual({ x: 300, y: 50 });
    expect(result.anchors!.bottom).toEqual({ x: 300, y: 350 });
    expect(result.anchors!.center).toEqual({ x: 300, y: 200 });
  });

  it("includes label when provided", () => {
    const result = screen({
      x: 300,
      yTop: 50,
      yBottom: 350,
      label: "Screen",
      id: "scr1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("Screen");
  });

  it("default color is textSecondary", () => {
    const result = screen({ x: 300, yTop: 50, yBottom: 350, id: "scr1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textSecondary);
  });
});

// ── Barrier ──────────────────────────────────────────────────

describe("barrier", () => {
  it("no slits: single filled rectangle", () => {
    const result = barrier({ x: 200, yTop: 50, yBottom: 350, id: "b1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].d).toContain("Z");
  });

  it("two slits: three filled sections", () => {
    const result = barrier({
      x: 200,
      yTop: 50,
      yBottom: 350,
      slits: [
        { y: 175, halfWidth: 6 },
        { y: 225, halfWidth: 6 },
      ],
      id: "b1",
    });
    // Top section + middle section + bottom section
    expect(result.paths).toHaveLength(3);
  });

  it("slit anchors at exit side", () => {
    const result = barrier({
      x: 200,
      yTop: 50,
      yBottom: 350,
      width: 20,
      slits: [{ y: 175 }, { y: 225 }],
      id: "b1",
    });
    // Exit side = x + width = 220
    expect(result.anchors!["slit-0"]).toEqual({ x: 220, y: 175 });
    expect(result.anchors!["slit-1"]).toEqual({ x: 220, y: 225 });
  });

  it("default color is textSecondary", () => {
    const result = barrier({ x: 200, yTop: 50, yBottom: 350, id: "b1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textSecondary);
  });

  it("single slit: two sections", () => {
    const result = barrier({
      x: 200,
      yTop: 50,
      yBottom: 350,
      slits: [{ y: 200, halfWidth: 6 }],
      id: "b1",
    });
    expect(result.paths).toHaveLength(2);
  });
});

// ── Wavefront Arc ────────────────────────────────────────────

describe("wavefrontArc", () => {
  it("returns a single arc path", () => {
    const result = wavefrontArc({ cx: 100, cy: 200, radius: 50, id: "wf1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].d).toContain("A");
  });

  it("default color is accentBlue with transparency", () => {
    const result = wavefrontArc({ cx: 100, cy: 200, radius: 50, id: "wf1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(`${COLORS.accentBlue}99`);
  });

  it("returns center, arcTop, arcBottom anchors", () => {
    const result = wavefrontArc({ cx: 100, cy: 200, radius: 50, id: "wf1" });
    expect(result.anchors!.center).toEqual({ x: 100, y: 200 });
    expect(result.anchors!.arcTop).toBeDefined();
    expect(result.anchors!.arcBottom).toBeDefined();
  });

  it("bounds cover the full arc radius", () => {
    const result = wavefrontArc({ cx: 100, cy: 200, radius: 50, id: "wf1" });
    expect(result.bounds).toEqual({ x: 50, y: 150, width: 100, height: 100 });
  });
});

// ── Convex Lens ──────────────────────────────────────────────

describe("convexLens", () => {
  it("returns 4 paths: left surface, right surface, 2 arrowheads", () => {
    const result = convexLens({ cx: 250, cy: 200, id: "cl1" });
    expect(result.paths).toHaveLength(4);
  });

  it("left and right surfaces use cubic bezier (C command)", () => {
    const result = convexLens({ cx: 250, cy: 200, id: "cl1" });
    expect(result.paths[0].d).toContain("C");
    expect(result.paths[1].d).toContain("C");
  });

  it("arrowheads point inward (converging lens)", () => {
    const result = convexLens({ cx: 250, cy: 200, id: "cl1" });
    // Top arrowhead points down toward center
    expect(result.paths[2].id).toBe("cl1-arrow-top");
    // Bottom arrowhead points up toward center
    expect(result.paths[3].id).toBe("cl1-arrow-bottom");
  });

  it("returns center, top, bottom anchors", () => {
    const result = convexLens({ cx: 250, cy: 200, height: 120, id: "cl1" });
    expect(result.anchors!.center).toEqual({ x: 250, y: 200 });
    expect(result.anchors!.top).toEqual({ x: 250, y: 140 });
    expect(result.anchors!.bottom).toEqual({ x: 250, y: 260 });
  });

  it("default color is textPrimary", () => {
    const result = convexLens({ cx: 250, cy: 200, id: "cl1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("includes label when provided", () => {
    const result = convexLens({ cx: 250, cy: 200, label: "L", id: "cl1" });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("L");
  });
});

// ── Concave Lens ─────────────────────────────────────────────

describe("concaveLens", () => {
  it("returns 4 paths: left surface, right surface, 2 arrowheads", () => {
    const result = concaveLens({ cx: 250, cy: 200, id: "cl1" });
    expect(result.paths).toHaveLength(4);
  });

  it("surfaces use cubic bezier (C command)", () => {
    const result = concaveLens({ cx: 250, cy: 200, id: "cl1" });
    expect(result.paths[0].d).toContain("C");
    expect(result.paths[1].d).toContain("C");
  });

  it("arrowheads point outward (diverging lens)", () => {
    const result = concaveLens({ cx: 250, cy: 200, height: 120, id: "cl1" });
    const topArrow = result.paths[2];
    // Top arrowhead: middle point is at top (cy - 60), wings extend further up
    expect(topArrow.d).toContain(`250 140`); // apex point at cy - halfH
  });

  it("returns center, top, bottom anchors", () => {
    const result = concaveLens({ cx: 250, cy: 200, height: 120, id: "cl1" });
    expect(result.anchors!.center).toEqual({ x: 250, y: 200 });
    expect(result.anchors!.top).toEqual({ x: 250, y: 140 });
    expect(result.anchors!.bottom).toEqual({ x: 250, y: 260 });
  });

  it("default color is textPrimary", () => {
    const result = concaveLens({ cx: 250, cy: 200, id: "cl1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });
});

// ── Prism ────────────────────────────────────────────────────

describe("prism", () => {
  it("returns a single closed triangle path", () => {
    const result = prism({ cx: 200, cy: 200, id: "p1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].d).toContain("Z");
  });

  it("returns 6 anchors", () => {
    const result = prism({ cx: 200, cy: 200, id: "p1" });
    const a = result.anchors!;
    expect(a.center).toEqual({ x: 200, y: 200 });
    expect(a.apex).toBeDefined();
    expect(a.baseLeft).toBeDefined();
    expect(a.baseRight).toBeDefined();
    expect(a.leftFace).toBeDefined();
    expect(a.rightFace).toBeDefined();
  });

  it("apex is above center (no rotation)", () => {
    const result = prism({ cx: 200, cy: 200, id: "p1" });
    expect(result.anchors!.apex.y).toBeLessThan(200);
  });

  it("base vertices are symmetric around center x", () => {
    const result = prism({ cx: 200, cy: 200, sideLength: 80, id: "p1" });
    const bl = result.anchors!.baseLeft;
    const br = result.anchors!.baseRight;
    expect(bl.x).toBeLessThan(200);
    expect(br.x).toBeGreaterThan(200);
    expect(bl.y).toBeCloseTo(br.y, 5);
  });

  it("rotation moves apex", () => {
    const noRotation = prism({ cx: 200, cy: 200, id: "p1" });
    const rotated = prism({ cx: 200, cy: 200, rotation: 90, id: "p2" });
    expect(rotated.anchors!.apex.x).not.toBeCloseTo(
      noRotation.anchors!.apex.x,
      1,
    );
  });

  it("default color is textSecondary", () => {
    const result = prism({ cx: 200, cy: 200, id: "p1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textSecondary);
  });

  it("includes label when provided", () => {
    const result = prism({ cx: 200, cy: 200, label: "Prism", id: "p1" });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("Prism");
  });

  it("outline only (no fill)", () => {
    const result = prism({ cx: 200, cy: 200, id: "p1" });
    expect(result.paths[0].roughOptions?.fill).toBe("none");
  });
});
