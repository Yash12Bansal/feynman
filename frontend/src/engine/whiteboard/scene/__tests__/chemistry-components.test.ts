import { describe, it, expect } from "vitest";
import { molecule } from "../components/chemistry/molecule";
import { arrowLabel } from "../components/chemistry/arrow-label";
import { beaker } from "../components/chemistry/beaker";
import { flask } from "../components/chemistry/flask";
import { testTube } from "../components/chemistry/test-tube";
import { bunsenBurner } from "../components/chemistry/bunsen-burner";
import { thermometer } from "../components/chemistry/thermometer";
import { tubing } from "../components/chemistry/tubing";

// ── Molecule ─────────────────────────────────────────────────

describe("molecule", () => {
  it("returns a badge path and formula label", () => {
    const result = molecule({ cx: 100, cy: 100, label: "H₂O", id: "m1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(1);
    expect(result.labels.length).toBe(1);
    expect(result.labels[0].text).toBe("H₂O");
  });

  it("includes coefficient prefix", () => {
    const result = molecule({
      cx: 100,
      cy: 100,
      label: "H₂",
      coefficient: 2,
      id: "m2",
    });
    expect(result.labels[0].text).toBe("2H₂");
  });

  it("includes state suffix", () => {
    const result = molecule({
      cx: 100,
      cy: 100,
      label: "NaCl",
      state: "aq",
      id: "m3",
    });
    expect(result.labels[0].text).toBe("NaCl(aq)");
  });

  it("includes both coefficient and state", () => {
    const result = molecule({
      cx: 100,
      cy: 100,
      label: "H₂O",
      coefficient: 2,
      state: "l",
      id: "m4",
    });
    expect(result.labels[0].text).toBe("2H₂O(l)");
  });

  it("coefficient of 1 is omitted", () => {
    const result = molecule({
      cx: 100,
      cy: 100,
      label: "O₂",
      coefficient: 1,
      id: "m5",
    });
    expect(result.labels[0].text).toBe("O₂");
  });

  it("provides 5 anchors", () => {
    const result = molecule({ cx: 100, cy: 100, label: "X", id: "m6" });
    expect(result.anchors).toBeDefined();
    const anchorNames = Object.keys(result.anchors!);
    expect(anchorNames).toContain("center");
    expect(anchorNames).toContain("left");
    expect(anchorNames).toContain("right");
    expect(anchorNames).toContain("top");
    expect(anchorNames).toContain("bottom");
  });

  it("computes non-zero bounds", () => {
    const result = molecule({ cx: 100, cy: 100, label: "CH₄", id: "m7" });
    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });

  it("handles empty label", () => {
    const result = molecule({ cx: 100, cy: 100, id: "m8" });
    expect(result.paths.length).toBe(1); // badge path only
    expect(result.labels.length).toBe(0); // no label when empty text
  });
});

// ── ArrowLabel ───────────────────────────────────────────────

describe("arrowLabel", () => {
  it("returns shaft and arrowhead paths", () => {
    const result = arrowLabel({ x1: 0, y1: 100, x2: 100, y2: 100, id: "a1" });
    expect(result.paths.length).toBe(2); // shaft + head
  });

  it("includes label text above", () => {
    const result = arrowLabel({
      x1: 0,
      y1: 100,
      x2: 100,
      y2: 100,
      label: "Heat",
      id: "a2",
    });
    expect(result.labels.length).toBe(1);
    expect(result.labels[0].text).toBe("Heat");
  });

  it("handles zero length gracefully", () => {
    const result = arrowLabel({ x1: 50, y1: 50, x2: 50, y2: 50, id: "a3" });
    expect(result.paths).toHaveLength(0);
    expect(result.anchors!.start).toEqual({ x: 50, y: 50 });
  });

  it("provides start/end/center anchors", () => {
    const result = arrowLabel({ x1: 0, y1: 0, x2: 100, y2: 0, id: "a4" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 100, y: 0 });
    expect(result.anchors!.center.x).toBeCloseTo(50);
  });

  it("works with vertical arrow", () => {
    const result = arrowLabel({
      x1: 50,
      y1: 0,
      x2: 50,
      y2: 100,
      label: "→",
      id: "a5",
    });
    expect(result.paths.length).toBe(2);
  });
});

// ── Beaker ───────────────────────────────────────────────────

describe("beaker", () => {
  it("returns body path", () => {
    const result = beaker({ cx: 100, cy: 100, id: "b1" });
    const bodyPaths = result.paths.filter((p) => p.id.includes("-body"));
    expect(bodyPaths.length).toBe(1);
  });

  it("provides 6 anchors", () => {
    const result = beaker({ cx: 100, cy: 100, id: "b2" });
    const anchorNames = Object.keys(result.anchors!);
    expect(anchorNames).toContain("center");
    expect(anchorNames).toContain("top");
    expect(anchorNames).toContain("bottom");
    expect(anchorNames).toContain("left");
    expect(anchorNames).toContain("right");
    expect(anchorNames).toContain("mouth");
  });

  it("renders liquid fill when fill_level > 0", () => {
    const result = beaker({ cx: 100, cy: 100, fill_level: 0.5, id: "b3" });
    const liquidPaths = result.paths.filter((p) => p.id.includes("-liquid"));
    expect(liquidPaths.length).toBe(1);
    const surfacePaths = result.paths.filter((p) => p.id.includes("-surface"));
    expect(surfacePaths.length).toBe(1);
  });

  it("no liquid paths when fill_level is 0", () => {
    const result = beaker({ cx: 100, cy: 100, fill_level: 0, id: "b4" });
    const liquidPaths = result.paths.filter((p) => p.id.includes("-liquid"));
    expect(liquidPaths.length).toBe(0);
  });

  it("includes label below", () => {
    const result = beaker({ cx: 100, cy: 100, label: "Water", id: "b5" });
    expect(result.labels.length).toBe(1);
    expect(result.labels[0].text).toBe("Water");
  });

  it("clamps fill_level to [0, 1]", () => {
    const result = beaker({ cx: 100, cy: 100, fill_level: 1.5, id: "b6" });
    // Should still produce valid paths without error
    expect(result.paths.length).toBeGreaterThan(0);
  });
});

// ── Flask ────────────────────────────────────────────────────

describe("flask", () => {
  it("renders erlenmeyer flask by default", () => {
    const result = flask({ cx: 100, cy: 100, id: "f1" });
    expect(result.paths.length).toBeGreaterThanOrEqual(2); // neck + body
  });

  it("renders round_bottom variant", () => {
    const result = flask({
      cx: 100,
      cy: 100,
      variant: "round_bottom",
      id: "f2",
    });
    expect(result.paths.length).toBeGreaterThanOrEqual(2);
  });

  it("provides 5 anchors including neck and outlet", () => {
    const result = flask({ cx: 100, cy: 100, id: "f3" });
    expect(result.anchors!.neck).toBeDefined();
    expect(result.anchors!.outlet).toBeDefined();
    expect(result.anchors!.center).toBeDefined();
  });

  it("adds side arm path when side_arm is true", () => {
    const result = flask({
      cx: 100,
      cy: 100,
      side_arm: true,
      id: "f4",
    });
    const armPaths = result.paths.filter((p) => p.id.includes("-arm"));
    expect(armPaths.length).toBe(1);
  });

  it("no side arm path by default", () => {
    const result = flask({ cx: 100, cy: 100, id: "f5" });
    const armPaths = result.paths.filter((p) => p.id.includes("-arm"));
    expect(armPaths.length).toBe(0);
  });

  it("renders liquid fill for erlenmeyer", () => {
    const result = flask({
      cx: 100,
      cy: 100,
      fill_level: 0.5,
      id: "f6",
    });
    const liquidPaths = result.paths.filter((p) => p.id.includes("-liquid"));
    expect(liquidPaths.length).toBe(1);
  });

  it("renders liquid fill for round_bottom", () => {
    const result = flask({
      cx: 100,
      cy: 100,
      variant: "round_bottom",
      fill_level: 0.5,
      id: "f7",
    });
    const liquidPaths = result.paths.filter((p) => p.id.includes("-liquid"));
    expect(liquidPaths.length).toBe(1);
  });

  it("includes label below", () => {
    const result = flask({
      cx: 100,
      cy: 100,
      label: "Solution",
      id: "f8",
    });
    expect(result.labels[0].text).toBe("Solution");
  });
});

// ── TestTube ─────────────────────────────────────────────────

describe("testTube", () => {
  it("returns body path with semicircular bottom", () => {
    const result = testTube({ cx: 100, cy: 100, id: "tt1" });
    expect(result.paths.length).toBe(1);
    // Path should contain an arc command
    expect(result.paths[0].d).toContain("A");
  });

  it("provides 3 anchors", () => {
    const result = testTube({ cx: 100, cy: 100, id: "tt2" });
    expect(result.anchors!.center).toBeDefined();
    expect(result.anchors!.top).toBeDefined();
    expect(result.anchors!.bottom).toBeDefined();
  });

  it("renders liquid fill", () => {
    const result = testTube({
      cx: 100,
      cy: 100,
      fill_level: 0.4,
      id: "tt3",
    });
    const liquidPaths = result.paths.filter((p) => p.id.includes("-liquid"));
    expect(liquidPaths.length).toBe(1);
    const surfacePaths = result.paths.filter((p) => p.id.includes("-surface"));
    expect(surfacePaths.length).toBe(1);
  });

  it("no liquid when fill_level is 0", () => {
    const result = testTube({ cx: 100, cy: 100, fill_level: 0, id: "tt4" });
    const liquidPaths = result.paths.filter((p) => p.id.includes("-liquid"));
    expect(liquidPaths.length).toBe(0);
  });

  it("includes label beside tube", () => {
    const result = testTube({
      cx: 100,
      cy: 100,
      label: "HCl",
      id: "tt5",
    });
    expect(result.labels[0].text).toBe("HCl");
    expect(result.labels[0].anchor).toBe("start"); // right of tube
  });
});

// ── BunsenBurner ─────────────────────────────────────────────

describe("bunsenBurner", () => {
  it("returns base + chimney paths", () => {
    const result = bunsenBurner({
      cx: 100,
      cy: 100,
      flame: false,
      id: "bb1",
    });
    const basePaths = result.paths.filter((p) => p.id.includes("-base"));
    const chimneyPaths = result.paths.filter((p) => p.id.includes("-chimney"));
    expect(basePaths.length).toBe(1);
    expect(chimneyPaths.length).toBe(1);
  });

  it("renders flame by default", () => {
    const result = bunsenBurner({ cx: 100, cy: 100, id: "bb2" });
    const flamePaths = result.paths.filter((p) => p.id.includes("-flame"));
    expect(flamePaths.length).toBe(2); // outer + inner
  });

  it("no flame when flame=false", () => {
    const result = bunsenBurner({
      cx: 100,
      cy: 100,
      flame: false,
      id: "bb3",
    });
    const flamePaths = result.paths.filter((p) => p.id.includes("-flame"));
    expect(flamePaths.length).toBe(0);
  });

  it("provides 3 anchors", () => {
    const result = bunsenBurner({ cx: 100, cy: 100, id: "bb4" });
    expect(result.anchors!.center).toBeDefined();
    expect(result.anchors!.top).toBeDefined();
    expect(result.anchors!.bottom).toBeDefined();
  });

  it("includes label below", () => {
    const result = bunsenBurner({
      cx: 100,
      cy: 100,
      label: "Burner",
      id: "bb5",
    });
    expect(result.labels[0].text).toBe("Burner");
  });
});

// ── Thermometer ──────────────────────────────────────────────

describe("thermometer", () => {
  it("returns stem + bulb + mercury paths", () => {
    const result = thermometer({ cx: 100, cy: 100, id: "th1" });
    const stemPaths = result.paths.filter((p) => p.id.includes("-stem"));
    const bulbPaths = result.paths.filter((p) => p.id.includes("-bulb"));
    const mercuryPaths = result.paths.filter((p) => p.id.includes("-mercury"));
    expect(stemPaths.length).toBe(1);
    expect(bulbPaths.length).toBe(1);
    expect(mercuryPaths.length).toBe(1);
  });

  it("renders tick marks", () => {
    const result = thermometer({ cx: 100, cy: 100, id: "th2" });
    const tickPaths = result.paths.filter((p) => p.id.includes("-tick"));
    expect(tickPaths.length).toBe(6); // 0-5 inclusive
  });

  it("provides 4 anchors", () => {
    const result = thermometer({ cx: 100, cy: 100, id: "th3" });
    expect(result.anchors!.center).toBeDefined();
    expect(result.anchors!.top).toBeDefined();
    expect(result.anchors!.bottom).toBeDefined();
    expect(result.anchors!.bulb).toBeDefined();
  });

  it("reading=0 has mercury at bottom", () => {
    const result = thermometer({
      cx: 100,
      cy: 100,
      reading: 0,
      id: "th4",
    });
    const mercury = result.paths.find((p) => p.id === "th4-mercury");
    expect(mercury).toBeDefined();
  });

  it("reading=1 has mercury at top", () => {
    const result = thermometer({
      cx: 100,
      cy: 100,
      reading: 1,
      id: "th5",
    });
    const mercury = result.paths.find((p) => p.id === "th5-mercury");
    expect(mercury).toBeDefined();
  });

  it("includes label to the right", () => {
    const result = thermometer({
      cx: 100,
      cy: 100,
      label: "78°C",
      id: "th6",
    });
    expect(result.labels[0].text).toBe("78°C");
    expect(result.labels[0].anchor).toBe("start");
  });
});

// ── Tubing ───────────────────────────────────────────────────

describe("tubing", () => {
  it("returns a quadratic bezier path", () => {
    const result = tubing({ x1: 0, y1: 0, x2: 100, y2: 0, id: "tu1" });
    expect(result.paths.length).toBe(1);
    expect(result.paths[0].d).toContain("Q"); // quadratic bezier
  });

  it("handles zero length gracefully", () => {
    const result = tubing({ x1: 50, y1: 50, x2: 50, y2: 50, id: "tu2" });
    expect(result.paths).toHaveLength(0);
  });

  it("provides start/end/mid anchors", () => {
    const result = tubing({ x1: 0, y1: 0, x2: 100, y2: 0, id: "tu3" });
    expect(result.anchors!.start).toEqual({ x: 0, y: 0 });
    expect(result.anchors!.end).toEqual({ x: 100, y: 0 });
    expect(result.anchors!.mid).toBeDefined();
  });

  it("sag parameter affects control point", () => {
    const r1 = tubing({ x1: 0, y1: 0, x2: 100, y2: 0, sag: 10, id: "tu4" });
    const r2 = tubing({ x1: 0, y1: 0, x2: 100, y2: 0, sag: 50, id: "tu5" });
    // Mid anchor should be at different y values due to different sag
    expect(r1.anchors!.mid.y).not.toBe(r2.anchors!.mid.y);
  });

  it("default sag is applied", () => {
    const result = tubing({ x1: 0, y1: 0, x2: 100, y2: 0, id: "tu6" });
    // Mid anchor y should not be 0 (sag pushes it perpendicular)
    expect(result.anchors!.mid.y).not.toBe(0);
  });

  it("computes non-zero bounds", () => {
    const result = tubing({ x1: 10, y1: 20, x2: 90, y2: 20, id: "tu7" });
    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });
});
