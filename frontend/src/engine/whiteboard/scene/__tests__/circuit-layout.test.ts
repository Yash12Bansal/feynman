import { describe, it, expect } from "vitest";
import { schematicCircuit } from "../layout/strategies/circuit-layout";
import { defaultLayoutContext } from "../components/types";

const ctx = { ...defaultLayoutContext(), sceneWidth: 700, sceneHeight: 500 };

// ── Basic rendering ──────────────────────────────────────────

describe("schematicCircuit — basic", () => {
  it("returns empty geometry for no elements", () => {
    const result = schematicCircuit([], ctx);
    expect(result.paths).toHaveLength(0);
    expect(result.labels).toHaveLength(0);
  });

  it("renders a simple battery + resistor circuit", () => {
    const result = schematicCircuit(
      [
        { id: "V", kind: "battery", label: "12V" },
        { id: "R1", kind: "resistor", label: "100Ω" },
      ],
      ctx,
    );
    expect(result.paths.length).toBeGreaterThan(0);
    expect(result.labels.length).toBeGreaterThan(0);
  });

  it("computes non-zero tight bounds", () => {
    const result = schematicCircuit(
      [
        { id: "V", kind: "battery", label: "12V" },
        { id: "R1", kind: "resistor", label: "100Ω" },
      ],
      ctx,
    );
    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });
});

// ── Series resistors ────────────────────────────────────────

describe("schematicCircuit — series resistors", () => {
  const elements = [
    { id: "V", kind: "battery", label: "12V" },
    { id: "R1", kind: "resistor", label: "100Ω" },
    { id: "R2", kind: "resistor", label: "200Ω" },
  ];

  it("renders battery and both resistors", () => {
    const result = schematicCircuit(elements, ctx);
    // Battery paths (pos, neg, leads)
    const batteryPaths = result.paths.filter((p) => p.id.startsWith("V-"));
    expect(batteryPaths.length).toBeGreaterThan(0);
    // Resistor paths
    const r1Paths = result.paths.filter((p) => p.id.startsWith("R1-"));
    const r2Paths = result.paths.filter((p) => p.id.startsWith("R2-"));
    expect(r1Paths.length).toBeGreaterThan(0);
    expect(r2Paths.length).toBeGreaterThan(0);
  });

  it("includes labels for all components", () => {
    const result = schematicCircuit(elements, ctx);
    const labelTexts = result.labels.map((l) => l.text);
    expect(labelTexts).toContain("12V");
    expect(labelTexts).toContain("100Ω");
    expect(labelTexts).toContain("200Ω");
  });

  it("generates wire paths for connections", () => {
    const result = schematicCircuit(elements, ctx);
    const wirePaths = result.paths.filter((p) => p.id.startsWith("wire-"));
    expect(wirePaths.length).toBeGreaterThan(0);
  });
});

// ── Battery + switch + bulb ─────────────────────────────────

describe("schematicCircuit — switch + bulb", () => {
  const elements = [
    { id: "V", kind: "battery", label: "9V" },
    { id: "S", kind: "switch", label: "S₁", extras: { closed: true } },
    { id: "L", kind: "bulb", label: "Bulb" },
  ];

  it("renders all three components", () => {
    const result = schematicCircuit(elements, ctx);
    const switchPaths = result.paths.filter((p) => p.id.startsWith("S-"));
    const bulbPaths = result.paths.filter((p) => p.id.startsWith("L-"));
    expect(switchPaths.length).toBeGreaterThan(0);
    expect(bulbPaths.length).toBeGreaterThan(0);
  });

  it("includes labels", () => {
    const result = schematicCircuit(elements, ctx);
    const labelTexts = result.labels.map((l) => l.text);
    expect(labelTexts).toContain("9V");
    expect(labelTexts).toContain("S₁");
    expect(labelTexts).toContain("Bulb");
  });
});

// ── Underscore normalization ────────────────────────────────

describe("schematicCircuit — kind normalization", () => {
  it("handles underscore kinds from LLM", () => {
    const result = schematicCircuit(
      [
        { id: "V", kind: "battery", label: "5V" },
        { id: "R", kind: "resistor", label: "R" },
      ],
      ctx,
    );
    expect(result.paths.length).toBeGreaterThan(0);
  });
});

// ── Ground element ──────────────────────────────────────────

describe("schematicCircuit — ground", () => {
  it("renders ground symbol below the loop", () => {
    const result = schematicCircuit(
      [
        { id: "V", kind: "battery", label: "12V" },
        { id: "R1", kind: "resistor", label: "100Ω" },
        { id: "GND", kind: "ground" },
      ],
      ctx,
    );
    const groundPaths = result.paths.filter((p) => p.id.startsWith("GND-"));
    expect(groundPaths.length).toBeGreaterThan(0);
    // Ground stem wire
    const stemWire = result.paths.find((p) =>
      p.id.startsWith("wire-ground-stem"),
    );
    expect(stemWire).toBeDefined();
  });
});

// ── Many components ─────────────────────────────────────────

describe("schematicCircuit — overflow", () => {
  it("handles more components than fit on one side", () => {
    const elements = [
      { id: "V", kind: "battery", label: "12V" },
      { id: "R1", kind: "resistor", label: "R1" },
      { id: "R2", kind: "resistor", label: "R2" },
      { id: "R3", kind: "resistor", label: "R3" },
      { id: "R4", kind: "resistor", label: "R4" },
      { id: "R5", kind: "resistor", label: "R5" },
      { id: "R6", kind: "resistor", label: "R6" },
      { id: "R7", kind: "resistor", label: "R7" },
    ];
    const result = schematicCircuit(elements, ctx);
    // Should not throw, and should produce geometry
    expect(result.paths.length).toBeGreaterThan(0);
    expect(result.bounds.width).toBeGreaterThan(0);
  });
});

// ── Anchors ─────────────────────────────────────────────────

describe("schematicCircuit — anchors", () => {
  it("includes component anchors with element id prefix", () => {
    const result = schematicCircuit(
      [
        { id: "V", kind: "battery", label: "12V" },
        { id: "R1", kind: "resistor", label: "100Ω" },
      ],
      ctx,
    );
    expect(result.anchors).toBeDefined();
    // Battery anchors should be prefixed
    expect(result.anchors!["V-center"]).toBeDefined();
    expect(result.anchors!["R1-center"]).toBeDefined();
  });
});
