import { describe, it, expect } from "vitest";
import {
  computeDiagramLayout,
  intersectNodeBoundary,
  type LayoutNode,
} from "../layout/diagram-layout";
import type { DiagramNode, DiagramEdge } from "../../types/visuals";

// ── Helpers ───────────────────────────────────────────────────

function makeNodes(count: number): DiagramNode[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `n${i}`,
    label: `Node ${i}`,
  }));
}

function makeEdge(from: string, to: string): DiagramEdge {
  return { from_id: from, to_id: to };
}

// ── Layout output ─────────────────────────────────────────────

describe("computeDiagramLayout", () => {
  it("returns positioned nodes for a 2-node graph", () => {
    const nodes = makeNodes(2);
    const edges = [makeEdge("n0", "n1")];
    const layout = computeDiagramLayout(nodes, edges, "flowchart");

    expect(layout.nodes).toHaveLength(2);
    expect(layout.edges).toHaveLength(1);
    // Both nodes should have finite positions
    for (const n of layout.nodes) {
      expect(Number.isFinite(n.x)).toBe(true);
      expect(Number.isFinite(n.y)).toBe(true);
      expect(n.width).toBeGreaterThan(0);
      expect(n.height).toBeGreaterThan(0);
    }
  });

  it("returns empty layout for zero nodes", () => {
    const layout = computeDiagramLayout([], [], "flowchart");
    expect(layout.nodes).toHaveLength(0);
    expect(layout.edges).toHaveLength(0);
    expect(layout.width).toBe(0);
    expect(layout.height).toBe(0);
  });

  it("handles single node with no edges", () => {
    const layout = computeDiagramLayout(
      [{ id: "solo", label: "Alone" }],
      [],
      "flowchart",
    );
    expect(layout.nodes).toHaveLength(1);
    expect(layout.edges).toHaveLength(0);
    expect(layout.nodes[0].x).toBeGreaterThan(0);
    expect(layout.nodes[0].y).toBeGreaterThan(0);
  });

  it("viewBox contains all nodes", () => {
    const nodes = makeNodes(5);
    const edges = [
      makeEdge("n0", "n1"),
      makeEdge("n1", "n2"),
      makeEdge("n2", "n3"),
      makeEdge("n3", "n4"),
    ];
    const layout = computeDiagramLayout(nodes, edges, "flowchart");

    for (const n of layout.nodes) {
      expect(n.x + n.width / 2).toBeLessThanOrEqual(layout.width);
      expect(n.y + n.height / 2).toBeLessThanOrEqual(layout.height);
    }
  });

  it("cycle layout places nodes in a circle", () => {
    const nodes = makeNodes(4);
    const edges = [
      makeEdge("n0", "n1"),
      makeEdge("n1", "n2"),
      makeEdge("n2", "n3"),
      makeEdge("n3", "n0"),
    ];
    const layout = computeDiagramLayout(nodes, edges, "cycle");

    expect(layout.nodes).toHaveLength(4);
    // All nodes should be at roughly the same distance from center
    const xs = layout.nodes.map((n) => n.x);
    const ys = layout.nodes.map((n) => n.y);
    const cx = xs.reduce((a, b) => a + b, 0) / xs.length;
    const cy = ys.reduce((a, b) => a + b, 0) / ys.length;
    const distances = layout.nodes.map((n) =>
      Math.sqrt((n.x - cx) ** 2 + (n.y - cy) ** 2),
    );
    // All distances should be approximately equal (within 1% of each other)
    const avgDist = distances.reduce((a, b) => a + b, 0) / distances.length;
    for (const d of distances) {
      expect(Math.abs(d - avgDist) / avgDist).toBeLessThan(0.01);
    }
  });

  it("force diagram places central node at center", () => {
    const nodes: DiagramNode[] = [
      { id: "center", label: "Hub" },
      { id: "a", label: "A" },
      { id: "b", label: "B" },
      { id: "c", label: "C" },
    ];
    const edges: DiagramEdge[] = [
      makeEdge("center", "a"),
      makeEdge("center", "b"),
      makeEdge("center", "c"),
    ];
    const layout = computeDiagramLayout(nodes, edges, "force_diagram");

    // "center" has most connections, should be placed centrally
    const centerNode = layout.nodes.find((n) => n.id === "center")!;
    const others = layout.nodes.filter((n) => n.id !== "center");

    // Center node should be closer to the geometric center than orbit nodes
    const avgX =
      layout.nodes.reduce((s, n) => s + n.x, 0) / layout.nodes.length;
    const avgY =
      layout.nodes.reduce((s, n) => s + n.y, 0) / layout.nodes.length;
    const centerDist = Math.sqrt(
      (centerNode.x - avgX) ** 2 + (centerNode.y - avgY) ** 2,
    );
    for (const n of others) {
      const dist = Math.sqrt((n.x - avgX) ** 2 + (n.y - avgY) ** 2);
      expect(dist).toBeGreaterThan(centerDist);
    }
  });

  it("preserves node shapes and colors", () => {
    const nodes: DiagramNode[] = [
      { id: "a", label: "A", shape: "diamond", color: "#ff0000" },
      { id: "b", label: "B", shape: "circle" },
    ];
    const layout = computeDiagramLayout(
      nodes,
      [makeEdge("a", "b")],
      "free_form",
    );

    expect(layout.nodes[0].shape).toBe("diamond");
    expect(layout.nodes[0].color).toBe("#ff0000");
    expect(layout.nodes[1].shape).toBe("circle");
  });

  it("edges reference valid boundary-intersection coordinates", () => {
    const nodes = makeNodes(2);
    const edges = [makeEdge("n0", "n1")];
    const layout = computeDiagramLayout(nodes, edges, "flowchart");

    const edge = layout.edges[0];
    expect(Number.isFinite(edge.x1)).toBe(true);
    expect(Number.isFinite(edge.y1)).toBe(true);
    expect(Number.isFinite(edge.x2)).toBe(true);
    expect(Number.isFinite(edge.y2)).toBe(true);
    // Edge endpoints should not be at exact node centers
    const from = layout.nodes.find((n) => n.id === edge.fromId)!;
    const to = layout.nodes.find((n) => n.id === edge.toId)!;
    // At least one coordinate should differ from center
    expect(edge.x1 !== from.x || edge.y1 !== from.y).toBe(true);
    expect(edge.x2 !== to.x || edge.y2 !== to.y).toBe(true);
  });

  it("skips edges referencing non-existent nodes", () => {
    const nodes = makeNodes(2);
    const edges = [makeEdge("n0", "n1"), makeEdge("n0", "ghost")];
    const layout = computeDiagramLayout(nodes, edges, "flowchart");
    expect(layout.edges).toHaveLength(1);
  });
});

// ── Boundary intersection ─────────────────────────────────────

describe("intersectNodeBoundary", () => {
  const rectNode: LayoutNode = {
    id: "r",
    label: "R",
    shape: "rectangle",
    color: "",
    x: 100,
    y: 100,
    width: 80,
    height: 40,
  };

  const circleNode: LayoutNode = {
    id: "c",
    label: "C",
    shape: "circle",
    color: "",
    x: 100,
    y: 100,
    width: 60,
    height: 60,
  };

  const diamondNode: LayoutNode = {
    id: "d",
    label: "D",
    shape: "diamond",
    color: "",
    x: 100,
    y: 100,
    width: 80,
    height: 60,
  };

  it("intersects rectangle from the right", () => {
    const pt = intersectNodeBoundary(rectNode, 200, 100);
    expect(pt.x).toBeCloseTo(140); // x + width/2
    expect(pt.y).toBeCloseTo(100);
  });

  it("intersects rectangle from below", () => {
    const pt = intersectNodeBoundary(rectNode, 100, 200);
    expect(pt.x).toBeCloseTo(100);
    expect(pt.y).toBeCloseTo(120); // y + height/2
  });

  it("intersects circle from any direction", () => {
    const r = 30; // radius = width/2
    // From the right
    const pt = intersectNodeBoundary(circleNode, 200, 100);
    expect(pt.x).toBeCloseTo(100 + r);
    expect(pt.y).toBeCloseTo(100);
    // From below
    const pt2 = intersectNodeBoundary(circleNode, 100, 200);
    expect(pt2.x).toBeCloseTo(100);
    expect(pt2.y).toBeCloseTo(100 + r);
  });

  it("intersects diamond boundary", () => {
    // From directly right — diamond edge at (hw, 0) relative
    const pt = intersectNodeBoundary(diamondNode, 200, 100);
    expect(pt.x).toBeCloseTo(140); // x + hw
    expect(pt.y).toBeCloseTo(100);
    // From directly below — diamond edge at (0, hh) relative
    const pt2 = intersectNodeBoundary(diamondNode, 100, 200);
    expect(pt2.x).toBeCloseTo(100);
    expect(pt2.y).toBeCloseTo(130); // y + hh
  });

  it("returns center when target is at center", () => {
    const pt = intersectNodeBoundary(rectNode, 100, 100);
    expect(pt.x).toBe(100);
    expect(pt.y).toBe(100);
  });
});
