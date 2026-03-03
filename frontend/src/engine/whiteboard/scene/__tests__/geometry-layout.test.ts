import { describe, it, expect } from "vitest";
import { constructionSequence } from "../layout/strategies/geometry-layout";
import { defaultLayoutContext } from "../components/types";

const ctx = { ...defaultLayoutContext(), sceneWidth: 500, sceneHeight: 400 };

// ── Basic rendering ──────────────────────────────────────────

describe("constructionSequence — basic", () => {
  it("returns empty geometry for no elements", () => {
    const result = constructionSequence([], ctx);
    expect(result.paths).toHaveLength(0);
    expect(result.labels).toHaveLength(0);
    expect(result.bounds).toEqual({ x: 0, y: 0, width: 0, height: 0 });
  });

  it("renders a single point with explicit coords", () => {
    const result = constructionSequence(
      [{ id: "A", kind: "point", label: "A", extras: { x: 100, y: 200 } }],
      ctx,
    );
    expect(result.paths.length).toBeGreaterThan(0);
    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].text).toBe("A");
  });
});

// ── Triangle + altitude ──────────────────────────────────────

describe("constructionSequence — triangle with altitude", () => {
  const elements = [
    { id: "A", kind: "point", label: "A", extras: { x: 250, y: 80 } },
    { id: "B", kind: "point", label: "B", extras: { x: 100, y: 320 } },
    { id: "C", kind: "point", label: "C", extras: { x: 400, y: 320 } },
    { id: "tri", kind: "triangle", extras: { v1: "A", v2: "B", v3: "C" } },
    { id: "H", kind: "point", label: "H", extras: { x: 250, y: 320 } },
    { id: "altitude", kind: "line_segment", from: "A", to: "H" },
    {
      id: "ra",
      kind: "right_angle_mark",
      extras: { vertex: "H", ray1: "A", ray2: "C" },
    },
  ];

  it("renders triangle, altitude, and right-angle mark", () => {
    const result = constructionSequence(elements, ctx);
    const triPaths = result.paths.filter((p) => p.id.startsWith("tri-"));
    const altPaths = result.paths.filter((p) => p.id.startsWith("altitude-"));
    const raPaths = result.paths.filter((p) => p.id.startsWith("ra-"));
    expect(triPaths.length).toBeGreaterThan(0);
    expect(altPaths.length).toBeGreaterThan(0);
    expect(raPaths.length).toBeGreaterThan(0);
  });

  it("right-angle mark path is open (no Z)", () => {
    const result = constructionSequence(elements, ctx);
    const raPath = result.paths.find((p) => p.id.startsWith("ra-"));
    expect(raPath?.d).not.toContain("Z");
  });

  it("non-zero bounds for complex scene", () => {
    const result = constructionSequence(elements, ctx);
    expect(result.bounds.width).toBeGreaterThan(0);
    expect(result.bounds.height).toBeGreaterThan(0);
  });
});

// ── Auto-placement ───────────────────────────────────────────

describe("constructionSequence — auto-placement", () => {
  it("auto-places triangle vertices when no explicit coords", () => {
    const result = constructionSequence(
      [
        { id: "A", kind: "point", label: "A" },
        { id: "B", kind: "point", label: "B" },
        { id: "C", kind: "point", label: "C" },
        { id: "tri", kind: "triangle", extras: { v1: "A", v2: "B", v3: "C" } },
      ],
      ctx,
    );
    // Should still render — auto-placement kicks in
    expect(result.paths.length).toBeGreaterThan(0);
    // Triangle path + 3 point dots = at least 4 paths
    expect(result.paths.length).toBeGreaterThanOrEqual(4);
  });
});

// ── Kind normalization ───────────────────────────────────────

describe("constructionSequence — kind normalization", () => {
  it("handles underscore kinds from LLM (line_segment → line-segment)", () => {
    const result = constructionSequence(
      [
        { id: "A", kind: "point", extras: { x: 50, y: 50 } },
        { id: "B", kind: "point", extras: { x: 200, y: 50 } },
        { id: "seg", kind: "line_segment", from: "A", to: "B" },
      ],
      ctx,
    );
    const segPaths = result.paths.filter((p) => p.id.startsWith("seg-"));
    expect(segPaths.length).toBeGreaterThan(0);
  });

  it("handles angle_arc underscore normalization", () => {
    const result = constructionSequence(
      [
        { id: "V", kind: "point", extras: { x: 100, y: 100 } },
        { id: "P", kind: "point", extras: { x: 200, y: 100 } },
        { id: "Q", kind: "point", extras: { x: 100, y: 200 } },
        {
          id: "ang",
          kind: "angle_arc",
          extras: { vertex: "V", ray1: "P", ray2: "Q" },
        },
      ],
      ctx,
    );
    const arcPaths = result.paths.filter((p) => p.id.startsWith("ang-"));
    expect(arcPaths.length).toBeGreaterThan(0);
  });
});

// ── Circle with center reference ─────────────────────────────

describe("constructionSequence — circle", () => {
  it("renders circle with center point reference", () => {
    const result = constructionSequence(
      [
        { id: "O", kind: "point", label: "O", extras: { x: 250, y: 200 } },
        {
          id: "circ",
          kind: "circle_shape",
          extras: { center: "O", radius: 100 },
        },
      ],
      ctx,
    );
    const circPaths = result.paths.filter((p) => p.id.startsWith("circ-"));
    expect(circPaths.length).toBeGreaterThan(0);
  });

  it("auto-places circle center when unplaced", () => {
    const result = constructionSequence(
      [
        { id: "O", kind: "point", label: "O" },
        {
          id: "circ",
          kind: "circle_shape",
          extras: { center: "O", radius: 80 },
        },
      ],
      ctx,
    );
    expect(result.paths.length).toBeGreaterThan(0);
  });
});

// ── Anchor namespacing ───────────────────────────────────────

describe("constructionSequence — anchors", () => {
  it("namespaces anchors with element id prefix", () => {
    const result = constructionSequence(
      [
        { id: "A", kind: "point", extras: { x: 0, y: 0 } },
        { id: "B", kind: "point", extras: { x: 100, y: 0 } },
        { id: "C", kind: "point", extras: { x: 50, y: 80 } },
        { id: "tri", kind: "triangle", extras: { v1: "A", v2: "B", v3: "C" } },
      ],
      ctx,
    );
    expect(result.anchors!["tri-A"]).toBeDefined();
    expect(result.anchors!["tri-B"]).toBeDefined();
    expect(result.anchors!["tri-C"]).toBeDefined();
    expect(result.anchors!["tri-BC_mid"]).toBeDefined();
    expect(result.anchors!["tri-centroid"]).toBeDefined();
  });

  it("element can reference anchors from previously rendered element", () => {
    const result = constructionSequence(
      [
        { id: "A", kind: "point", extras: { x: 0, y: 0 } },
        { id: "B", kind: "point", extras: { x: 100, y: 0 } },
        { id: "C", kind: "point", extras: { x: 50, y: 80 } },
        { id: "tri", kind: "triangle", extras: { v1: "A", v2: "B", v3: "C" } },
        // Line from A to the BC midpoint (referencing triangle anchor)
        { id: "median", kind: "line_segment", from: "A", to: "tri-BC_mid" },
      ],
      ctx,
    );
    const medianPaths = result.paths.filter((p) => p.id.startsWith("median-"));
    expect(medianPaths.length).toBeGreaterThan(0);
  });
});

// ── Unknown kind ─────────────────────────────────────────────

describe("constructionSequence — unknown kind", () => {
  it("gracefully skips unknown component kinds", () => {
    const result = constructionSequence(
      [
        { id: "A", kind: "point", extras: { x: 100, y: 100 } },
        { id: "mystery", kind: "nonexistent_widget" },
      ],
      ctx,
    );
    // Should render the point, skip the unknown kind
    expect(result.paths.length).toBe(1);
  });
});

// ── Congruence + parallel marks via strategy ─────────────────

describe("constructionSequence — marks", () => {
  it("renders congruence marks on a segment", () => {
    const result = constructionSequence(
      [
        { id: "A", kind: "point", extras: { x: 0, y: 0 } },
        { id: "B", kind: "point", extras: { x: 100, y: 0 } },
        {
          id: "cm",
          kind: "congruence_mark",
          from: "A",
          to: "B",
          extras: { count: 2 },
        },
      ],
      ctx,
    );
    const cmPaths = result.paths.filter((p) => p.id.startsWith("cm-"));
    expect(cmPaths).toHaveLength(2); // count=2 → 2 tick paths
  });
});
