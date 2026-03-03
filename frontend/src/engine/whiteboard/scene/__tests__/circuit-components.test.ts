import { describe, it, expect } from "vitest";
import { battery } from "../components/circuits/battery";
import { resistor } from "../components/circuits/resistor";
import { capacitor } from "../components/circuits/capacitor";
import { inductor } from "../components/circuits/inductor";
import { switchComponent } from "../components/circuits/switch-component";
import { bulb } from "../components/circuits/bulb";
import { ammeter } from "../components/circuits/ammeter";
import { voltmeter } from "../components/circuits/voltmeter";
import { wire } from "../components/circuits/wire";
import { junction } from "../components/circuits/junction";
import { ground } from "../components/circuits/ground";
import { computeBasis, toWorld } from "../components/circuits/utils";
import { COLORS } from "../../../theme";

// ── Utils ────────────────────────────────────────────────────

describe("computeBasis", () => {
  it("returns null for zero-length (coincident points)", () => {
    expect(computeBasis(50, 50, 50, 50)).toBeNull();
  });

  it("computes correct midpoint", () => {
    const b = computeBasis(0, 0, 100, 0)!;
    expect(b.mx).toBe(50);
    expect(b.my).toBe(0);
  });

  it("computes unit vectors for horizontal axis", () => {
    const b = computeBasis(0, 0, 100, 0)!;
    expect(b.ux).toBeCloseTo(1);
    expect(b.uy).toBeCloseTo(0);
    expect(b.px).toBeCloseTo(0);
    expect(b.py).toBeCloseTo(1);
    expect(b.len).toBe(100);
  });

  it("computes unit vectors for vertical axis", () => {
    const b = computeBasis(0, 0, 0, 100)!;
    expect(b.ux).toBeCloseTo(0);
    expect(b.uy).toBeCloseTo(1);
    expect(b.px).toBeCloseTo(-1);
    expect(b.py).toBeCloseTo(0);
  });

  it("computes correct length for diagonal", () => {
    const b = computeBasis(0, 0, 30, 40)!;
    expect(b.len).toBeCloseTo(50);
  });
});

describe("toWorld", () => {
  it("returns midpoint when along=0, perp=0", () => {
    const b = computeBasis(0, 0, 100, 0)!;
    const pt = toWorld(b, 0, 0);
    expect(pt.x).toBeCloseTo(50);
    expect(pt.y).toBeCloseTo(0);
  });

  it("moves along the axis", () => {
    const b = computeBasis(0, 0, 100, 0)!;
    const pt = toWorld(b, 20, 0);
    expect(pt.x).toBeCloseTo(70);
    expect(pt.y).toBeCloseTo(0);
  });

  it("moves perpendicular to axis", () => {
    const b = computeBasis(0, 0, 100, 0)!;
    const pt = toWorld(b, 0, 15);
    expect(pt.x).toBeCloseTo(50);
    expect(pt.y).toBeCloseTo(15);
  });
});

// ── Battery ──────────────────────────────────────────────────

describe("battery", () => {
  it("returns paths for plates + leads", () => {
    const result = battery({ x1: 0, y1: 0, x2: 80, y2: 0, id: "b1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(4);
  });

  it("zero-length returns empty paths", () => {
    const result = battery({ x1: 50, y1: 50, x2: 50, y2: 50, id: "b0" });
    expect(result.paths).toHaveLength(0);
  });

  it("returns start, end, center anchors", () => {
    const result = battery({ x1: 0, y1: 0, x2: 80, y2: 0, id: "b1" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 80, y: 0 });
    expect(result.anchors!.center).toEqual({ x: 40, y: 0 });
  });

  it("default color is textPrimary", () => {
    const result = battery({ x1: 0, y1: 0, x2: 80, y2: 0, id: "b1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("includes label when provided", () => {
    const result = battery({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "12V",
      id: "b1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("12V");
  });

  it("omits label when not provided", () => {
    const result = battery({ x1: 0, y1: 0, x2: 80, y2: 0, id: "b1" });
    expect(result.labels).toHaveLength(0);
  });
});

// ── Resistor ─────────────────────────────────────────────────

describe("resistor", () => {
  it("returns a single zigzag path", () => {
    const result = resistor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "r1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("r1-zigzag");
  });

  it("zigzag path contains line segments", () => {
    const result = resistor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "r1" });
    expect(result.paths[0].d).toContain("L");
  });

  it("zero-length returns empty paths", () => {
    const result = resistor({ x1: 50, y1: 50, x2: 50, y2: 50, id: "r0" });
    expect(result.paths).toHaveLength(0);
  });

  it("returns start, end, center anchors", () => {
    const result = resistor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "r1" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 80, y: 0 });
    expect(result.anchors!.center).toEqual({ x: 40, y: 0 });
  });

  it("default color is textPrimary", () => {
    const result = resistor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "r1" });
    expect(result.paths[0].roughOptions?.stroke).toBe(COLORS.textPrimary);
  });

  it("includes label when provided", () => {
    const result = resistor({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "100Ω",
      id: "r1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("100Ω");
  });

  it("omits label when not provided", () => {
    const result = resistor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "r1" });
    expect(result.labels).toHaveLength(0);
  });
});

// ── Capacitor ────────────────────────────────────────────────

describe("capacitor", () => {
  it("returns plates + leads paths", () => {
    const result = capacitor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "c1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(4);
  });

  it("zero-length returns empty paths", () => {
    const result = capacitor({ x1: 50, y1: 50, x2: 50, y2: 50, id: "c0" });
    expect(result.paths).toHaveLength(0);
  });

  it("electrolytic uses curved second plate (cubic bezier)", () => {
    const result = capacitor({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      electrolytic: true,
      id: "c1",
    });
    const plate2 = result.paths.find((p) => p.id === "c1-plate2");
    expect(plate2?.d).toContain("C");
  });

  it("non-electrolytic uses straight second plate", () => {
    const result = capacitor({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      electrolytic: false,
      id: "c1",
    });
    const plate2 = result.paths.find((p) => p.id === "c1-plate2");
    expect(plate2?.d).not.toContain("C");
  });

  it("returns start, end, center anchors", () => {
    const result = capacitor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "c1" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 80, y: 0 });
    expect(result.anchors!.center).toEqual({ x: 40, y: 0 });
  });

  it("includes label when provided", () => {
    const result = capacitor({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "10µF",
      id: "c1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("10µF");
  });
});

// ── Inductor ─────────────────────────────────────────────────

describe("inductor", () => {
  it("returns a single coil path with cubic beziers", () => {
    const result = inductor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "i1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("i1-coil");
    expect(result.paths[0].d).toContain("C");
  });

  it("zero-length returns empty paths", () => {
    const result = inductor({ x1: 50, y1: 50, x2: 50, y2: 50, id: "i0" });
    expect(result.paths).toHaveLength(0);
  });

  it("returns start, end, center anchors", () => {
    const result = inductor({ x1: 0, y1: 0, x2: 80, y2: 0, id: "i1" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 80, y: 0 });
    expect(result.anchors!.center).toEqual({ x: 40, y: 0 });
  });

  it("includes label when provided", () => {
    const result = inductor({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "10mH",
      id: "i1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("10mH");
  });
});

// ── Switch ───────────────────────────────────────────────────

describe("switchComponent", () => {
  it("returns leads + pivot + contact + arm paths", () => {
    const result = switchComponent({ x1: 0, y1: 0, x2: 80, y2: 0, id: "s1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(5);
  });

  it("zero-length returns empty paths", () => {
    const result = switchComponent({
      x1: 50,
      y1: 50,
      x2: 50,
      y2: 50,
      id: "s0",
    });
    expect(result.paths).toHaveLength(0);
  });

  it("closed switch has arm connecting pivot to contact", () => {
    const result = switchComponent({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      closed: true,
      id: "s1",
    });
    const arm = result.paths.find((p) => p.id === "s1-arm");
    expect(arm).toBeDefined();
  });

  it("open switch has lifted arm", () => {
    const result = switchComponent({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      closed: false,
      id: "s1",
    });
    const arm = result.paths.find((p) => p.id === "s1-arm");
    expect(arm).toBeDefined();
  });

  it("default is open", () => {
    const open = switchComponent({ x1: 0, y1: 0, x2: 80, y2: 0, id: "s1" });
    const closed = switchComponent({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      closed: true,
      id: "s2",
    });
    const openArm = open.paths.find((p) => p.id === "s1-arm")!;
    const closedArm = closed.paths.find((p) => p.id === "s2-arm")!;
    expect(openArm.d).not.toBe(closedArm.d);
  });

  it("includes label when provided", () => {
    const result = switchComponent({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "S₁",
      id: "s1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("S₁");
  });
});

// ── Bulb ─────────────────────────────────────────────────────

describe("bulb", () => {
  it("returns circle + X + leads paths", () => {
    const result = bulb({ x1: 0, y1: 0, x2: 80, y2: 0, id: "lb1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(5);
    expect(result.paths.find((p) => p.id === "lb1-circle")).toBeDefined();
    expect(result.paths.find((p) => p.id === "lb1-x1")).toBeDefined();
    expect(result.paths.find((p) => p.id === "lb1-x2")).toBeDefined();
  });

  it("zero-length returns empty paths", () => {
    const result = bulb({ x1: 50, y1: 50, x2: 50, y2: 50, id: "lb0" });
    expect(result.paths).toHaveLength(0);
  });

  it("circle path uses arcs", () => {
    const result = bulb({ x1: 0, y1: 0, x2: 80, y2: 0, id: "lb1" });
    const circle = result.paths.find((p) => p.id === "lb1-circle")!;
    expect(circle.d).toContain("A");
  });

  it("includes label when provided", () => {
    const result = bulb({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "Bulb",
      id: "lb1",
    });
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("Bulb");
  });
});

// ── Ammeter ──────────────────────────────────────────────────

describe("ammeter", () => {
  it("returns circle + leads paths", () => {
    const result = ammeter({ x1: 0, y1: 0, x2: 80, y2: 0, id: "am1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(3);
    expect(result.paths.find((p) => p.id === "am1-circle")).toBeDefined();
  });

  it("zero-length returns empty paths", () => {
    const result = ammeter({ x1: 50, y1: 50, x2: 50, y2: 50, id: "am0" });
    expect(result.paths).toHaveLength(0);
  });

  it("always shows 'A' symbol label inside", () => {
    const result = ammeter({ x1: 0, y1: 0, x2: 80, y2: 0, id: "am1" });
    const symbolLabel = result.labels.find((l) => l.id === "am1-symbol");
    expect(symbolLabel).toBeDefined();
    expect(symbolLabel!.text).toBe("A");
  });

  it("shows external label when provided", () => {
    const result = ammeter({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "I₁",
      id: "am1",
    });
    expect(result.labels).toHaveLength(2); // "A" + external label
    expect(result.labels.find((l) => l.id === "am1-label")!.text).toBe("I₁");
  });
});

// ── Voltmeter ────────────────────────────────────────────────

describe("voltmeter", () => {
  it("returns circle + leads paths", () => {
    const result = voltmeter({ x1: 0, y1: 0, x2: 80, y2: 0, id: "vm1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(3);
  });

  it("always shows 'V' symbol label inside", () => {
    const result = voltmeter({ x1: 0, y1: 0, x2: 80, y2: 0, id: "vm1" });
    const symbolLabel = result.labels.find((l) => l.id === "vm1-symbol");
    expect(symbolLabel).toBeDefined();
    expect(symbolLabel!.text).toBe("V");
  });

  it("shows external label when provided", () => {
    const result = voltmeter({
      x1: 0,
      y1: 0,
      x2: 80,
      y2: 0,
      label: "V₁",
      id: "vm1",
    });
    expect(result.labels).toHaveLength(2);
  });
});

// ── Wire ─────────────────────────────────────────────────────

describe("wire", () => {
  it("returns a single line path", () => {
    const result = wire({ x1: 0, y1: 0, x2: 100, y2: 0, id: "w1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("w1-line");
  });

  it("zero-length returns empty paths", () => {
    const result = wire({ x1: 50, y1: 50, x2: 50, y2: 50, id: "w0" });
    expect(result.paths).toHaveLength(0);
  });

  it("returns start and end anchors only", () => {
    const result = wire({ x1: 0, y1: 0, x2: 100, y2: 0, id: "w1" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 100, y: 0 });
    expect(result.anchors!["center"]).toBeUndefined();
  });

  it("custom color is applied", () => {
    const result = wire({
      x1: 0,
      y1: 0,
      x2: 100,
      y2: 0,
      color: "#ff0000",
      id: "w1",
    });
    expect(result.paths[0].roughOptions?.stroke).toBe("#ff0000");
  });

  it("no labels", () => {
    const result = wire({ x1: 0, y1: 0, x2: 100, y2: 0, id: "w1" });
    expect(result.labels).toHaveLength(0);
  });
});

// ── Junction ─────────────────────────────────────────────────

describe("junction", () => {
  it("returns a single filled dot path", () => {
    const result = junction({ x1: 100, y1: 200, id: "j1" });
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0].id).toBe("j1-dot");
  });

  it("dot is filled solid", () => {
    const result = junction({ x1: 100, y1: 200, id: "j1" });
    expect(result.paths[0].roughOptions?.fillStyle).toBe("solid");
    expect(result.paths[0].roughOptions?.fill).toBe(COLORS.textPrimary);
  });

  it("returns center anchor", () => {
    const result = junction({ x1: 100, y1: 200, id: "j1" });
    expect(result.anchors!.center).toEqual({ x: 100, y: 200 });
  });

  it("custom radius affects bounds", () => {
    const result = junction({ x1: 100, y1: 200, radius: 8, id: "j1" });
    expect(result.bounds).toEqual({ x: 92, y: 192, width: 16, height: 16 });
  });
});

// ── Ground ───────────────────────────────────────────────────

describe("ground", () => {
  it("returns stem + 3 horizontal lines", () => {
    const result = ground({ x1: 100, y1: 200, id: "g1" });
    expect(result.paths).toHaveLength(4);
    expect(result.paths[0].id).toBe("g1-stem");
    expect(result.paths[1].id).toBe("g1-line0");
    expect(result.paths[2].id).toBe("g1-line1");
    expect(result.paths[3].id).toBe("g1-line2");
  });

  it("returns top and center anchors", () => {
    const result = ground({ x1: 100, y1: 200, id: "g1" });
    expect(result.anchors!.top).toEqual({ x: 100, y: 200 });
    expect(result.anchors!.center).toBeDefined();
  });

  it("stem is vertical from top", () => {
    const result = ground({ x1: 100, y1: 200, id: "g1" });
    const stem = result.paths[0];
    expect(stem.d).toContain("M 100 200");
    expect(stem.d).toContain("L 100");
  });

  it("horizontal lines get progressively shorter", () => {
    const result = ground({ x1: 100, y1: 200, height: 20, id: "g1" });
    // All 3 lines should be at different widths
    const lineWidths = result.paths.slice(1).map((p) => {
      const nums = p.d.match(/-?\d+\.?\d*/g)!.map(Number);
      return Math.abs(nums[2] - nums[0]); // x2 - x1
    });
    expect(lineWidths[0]).toBeGreaterThan(lineWidths[1]);
    expect(lineWidths[1]).toBeGreaterThan(lineWidths[2]);
  });
});
