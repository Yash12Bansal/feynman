import { describe, it, expect } from "vitest";
import { chemistryLayout } from "../layout/strategies/chemistry-layout";
import { defaultLayoutContext } from "../components/types";

const ctx = { ...defaultLayoutContext(), sceneWidth: 700, sceneHeight: 500 };

// ── Mode detection ──────────────────────────────────────────

describe("chemistryLayout — mode detection", () => {
  it("returns empty geometry for no elements", () => {
    const result = chemistryLayout([], ctx);
    expect(result.paths).toHaveLength(0);
    expect(result.labels).toHaveLength(0);
  });

  it("detects reaction mode for molecules + arrow_label", () => {
    const result = chemistryLayout(
      [
        { id: "r1", kind: "molecule", label: "A" },
        { id: "arr", kind: "arrow_label", label: "→" },
        { id: "p1", kind: "molecule", label: "B" },
      ],
      ctx,
    );
    // Should have molecule badges + arrow paths + "+" labels etc
    expect(result.paths.length).toBeGreaterThan(0);
    // No bench line in reaction mode
    const benchPaths = result.paths.filter((p) => p.id === "bench-line");
    expect(benchPaths.length).toBe(0);
  });

  it("detects apparatus mode when beaker is present", () => {
    const result = chemistryLayout(
      [{ id: "b1", kind: "beaker", label: "Water" }],
      ctx,
    );
    // Should have bench line
    const benchPaths = result.paths.filter((p) => p.id === "bench-line");
    expect(benchPaths.length).toBe(1);
  });
});

// ── Reaction mode ───────────────────────────────────────────

describe("chemistryLayout — reaction mode", () => {
  const reactionElements = [
    {
      id: "r1",
      kind: "molecule",
      label: "H₂",
      extras: { coefficient: 2, state: "g" },
    },
    { id: "r2", kind: "molecule", label: "O₂", extras: { state: "g" } },
    { id: "arr", kind: "arrow_label", label: "Spark" },
    {
      id: "p1",
      kind: "molecule",
      label: "H₂O",
      extras: { coefficient: 2, state: "l" },
    },
  ];

  it("renders all molecules", () => {
    const result = chemistryLayout(reactionElements, ctx);
    const r1Paths = result.paths.filter((p) => p.id.startsWith("r1-"));
    const r2Paths = result.paths.filter((p) => p.id.startsWith("r2-"));
    const p1Paths = result.paths.filter((p) => p.id.startsWith("p1-"));
    expect(r1Paths.length).toBeGreaterThan(0);
    expect(r2Paths.length).toBeGreaterThan(0);
    expect(p1Paths.length).toBeGreaterThan(0);
  });

  it("renders the arrow", () => {
    const result = chemistryLayout(reactionElements, ctx);
    const arrowPaths = result.paths.filter((p) => p.id.startsWith("arr-"));
    expect(arrowPaths.length).toBeGreaterThan(0);
  });

  it("generates plus signs between reactants", () => {
    const result = chemistryLayout(reactionElements, ctx);
    const plusLabels = result.labels.filter((l) => l.text === "+");
    expect(plusLabels.length).toBe(1); // between r1 and r2
  });

  it("formula labels include coefficients and states", () => {
    const result = chemistryLayout(reactionElements, ctx);
    const formulaLabels = result.labels.filter((l) =>
      l.id.includes("-formula"),
    );
    const texts = formulaLabels.map((l) => l.text);
    expect(texts).toContain("2H₂(g)");
    expect(texts).toContain("O₂(g)");
    expect(texts).toContain("2H₂O(l)");
  });

  it("includes arrow condition label", () => {
    const result = chemistryLayout(reactionElements, ctx);
    const sparkLabel = result.labels.find((l) => l.text === "Spark");
    expect(sparkLabel).toBeDefined();
  });

  it("computes non-zero bounds", () => {
    const result = chemistryLayout(reactionElements, ctx);
    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });

  it("works with molecules only (no arrow)", () => {
    const result = chemistryLayout(
      [
        { id: "m1", kind: "molecule", label: "NaCl" },
        { id: "m2", kind: "molecule", label: "AgNO₃" },
      ],
      ctx,
    );
    expect(result.paths.length).toBeGreaterThan(0);
  });
});

// ── Apparatus mode ──────────────────────────────────────────

describe("chemistryLayout — apparatus mode", () => {
  it("renders a bench line", () => {
    const result = chemistryLayout(
      [{ id: "b1", kind: "beaker", label: "H₂O" }],
      ctx,
    );
    const bench = result.paths.find((p) => p.id === "bench-line");
    expect(bench).toBeDefined();
  });

  it("renders beaker above bench", () => {
    const result = chemistryLayout(
      [{ id: "b1", kind: "beaker", label: "H₂O" }],
      ctx,
    );
    const beakerPaths = result.paths.filter((p) => p.id.startsWith("b1-"));
    expect(beakerPaths.length).toBeGreaterThan(0);
  });

  it("renders flask + beaker side by side", () => {
    const result = chemistryLayout(
      [
        { id: "f1", kind: "flask", label: "Flask" },
        { id: "b1", kind: "beaker", label: "Beaker" },
      ],
      ctx,
    );
    const flaskPaths = result.paths.filter((p) => p.id.startsWith("f1-"));
    const beakerPaths = result.paths.filter((p) => p.id.startsWith("b1-"));
    expect(flaskPaths.length).toBeGreaterThan(0);
    expect(beakerPaths.length).toBeGreaterThan(0);
  });

  it("positions burner below adjacent apparatus", () => {
    const result = chemistryLayout(
      [
        { id: "tube", kind: "test_tube" },
        { id: "burner", kind: "bunsen_burner", extras: { flame: true } },
      ],
      ctx,
    );
    // Burner should be rendered
    const burnerPaths = result.paths.filter((p) => p.id.startsWith("burner-"));
    expect(burnerPaths.length).toBeGreaterThan(0);
  });

  it("positions thermometer inside referenced vessel", () => {
    const result = chemistryLayout(
      [
        { id: "tube", kind: "test_tube" },
        { id: "therm", kind: "thermometer", from: "tube" },
      ],
      ctx,
    );
    const thermPaths = result.paths.filter((p) => p.id.startsWith("therm-"));
    expect(thermPaths.length).toBeGreaterThan(0);
  });

  it("full apparatus setup renders all components", () => {
    const result = chemistryLayout(
      [
        {
          id: "rbf",
          kind: "flask",
          label: "Mixture",
          extras: { variant: "round_bottom", side_arm: true, fill_level: 0.4 },
        },
        {
          id: "burner",
          kind: "bunsen_burner",
          extras: { flame: true },
        },
        {
          id: "therm",
          kind: "thermometer",
          from: "rbf",
          label: "78°C",
        },
        { id: "collector", kind: "beaker", label: "Distillate" },
      ],
      ctx,
    );
    expect(result.paths.length).toBeGreaterThan(5);
    expect(result.labels.length).toBeGreaterThan(0);
  });

  it("produces anchors for all components", () => {
    const result = chemistryLayout(
      [
        { id: "b1", kind: "beaker", label: "H₂O" },
        { id: "f1", kind: "flask", label: "Mix" },
      ],
      ctx,
    );
    expect(result.anchors).toBeDefined();
    // Should have anchors prefixed with element IDs
    const anchorKeys = Object.keys(result.anchors!);
    expect(anchorKeys.some((k) => k.startsWith("b1-"))).toBe(true);
    expect(anchorKeys.some((k) => k.startsWith("f1-"))).toBe(true);
  });
});
