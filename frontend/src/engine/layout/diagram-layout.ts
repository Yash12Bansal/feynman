/**
 * Pure diagram layout engine — no React, no SVG, no GSAP.
 *
 * Computes positioned nodes and routed edges for a given diagram,
 * ready for SVG rendering. Layout strategy varies by diagram type.
 */

import dagre from "@dagrejs/dagre";
import type {
  DiagramNode,
  DiagramEdge,
  DiagramType,
  NodeShape,
} from "../../types/visuals";

// ── Output types ──────────────────────────────────────────────

export interface LayoutNode {
  id: string;
  label: string;
  shape: NodeShape;
  color: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LayoutEdge {
  fromId: string;
  toId: string;
  label: string;
  style: "solid" | "dashed" | "dotted";
  directed: boolean;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  labelX: number;
  labelY: number;
}

export interface DiagramLayout {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
  width: number;
  height: number;
}

// ── Node sizing ───────────────────────────────────────────────

const CHAR_WIDTH = 9;
const NODE_PADDING_X = 32;
const MIN_NODE_WIDTH = 60;
const MIN_NODE_HEIGHT = 40;

function computeNodeSize(
  label: string,
  shape: NodeShape,
): { width: number; height: number } {
  const textWidth = label.length * CHAR_WIDTH;
  let width = Math.max(textWidth + NODE_PADDING_X, MIN_NODE_WIDTH);
  let height = MIN_NODE_HEIGHT;

  switch (shape) {
    case "circle": {
      const diameter = Math.max(width, height);
      width = diameter;
      height = diameter;
      break;
    }
    case "diamond": {
      // Diamond needs extra space because text sits in the inscribed rect
      width = Math.max(width * 1.5, MIN_NODE_WIDTH * 1.5);
      height = Math.max(height * 1.5, MIN_NODE_HEIGHT * 1.5);
      break;
    }
    case "ellipse": {
      width = Math.max(textWidth + NODE_PADDING_X * 1.5, MIN_NODE_WIDTH);
      height = Math.max(MIN_NODE_HEIGHT, height);
      break;
    }
    // rectangle, rounded — default sizing is fine
  }

  return { width, height };
}

// ── Boundary intersection ─────────────────────────────────────

/**
 * Compute the point where a line from (targetX, targetY) to the node center
 * intersects the node boundary. Used for edge endpoints.
 */
export function intersectNodeBoundary(
  node: LayoutNode,
  targetX: number,
  targetY: number,
): { x: number; y: number } {
  const cx = node.x;
  const cy = node.y;
  const dx = targetX - cx;
  const dy = targetY - cy;

  if (dx === 0 && dy === 0) return { x: cx, y: cy };

  switch (node.shape) {
    case "circle": {
      const r = node.width / 2;
      const dist = Math.sqrt(dx * dx + dy * dy);
      return {
        x: cx + (dx / dist) * r,
        y: cy + (dy / dist) * r,
      };
    }

    case "ellipse": {
      const rx = node.width / 2;
      const ry = node.height / 2;
      const angle = Math.atan2(dy, dx);
      return {
        x: cx + rx * Math.cos(angle),
        y: cy + ry * Math.sin(angle),
      };
    }

    case "diamond": {
      const hw = node.width / 2;
      const hh = node.height / 2;
      // Diamond has 4 edges; find intersection with the edge towards target
      const adx = Math.abs(dx);
      const ady = Math.abs(dy);
      const sx = dx > 0 ? 1 : -1;
      const sy = dy > 0 ? 1 : -1;
      // Line from center to diamond boundary: |x/hw| + |y/hh| = 1
      if (adx * hh + ady * hw === 0) return { x: cx, y: cy };
      const t = (hw * hh) / (adx * hh + ady * hw);
      return {
        x: cx + sx * adx * t,
        y: cy + sy * ady * t,
      };
    }

    // rectangle, rounded — axis-aligned bounding box
    default: {
      const hw = node.width / 2;
      const hh = node.height / 2;
      // Parametric intersection with rect edges
      const adx = Math.abs(dx);
      const ady = Math.abs(dy);
      // Scale to hit the edge
      let t: number;
      if (adx * hh > ady * hw) {
        // Hits left/right edge
        t = hw / adx;
      } else {
        // Hits top/bottom edge
        t = hh / ady;
      }
      return {
        x: cx + dx * t,
        y: cy + dy * t,
      };
    }
  }
}

// ── Layout strategies ─────────────────────────────────────────

function layoutWithDagre(
  nodes: DiagramNode[],
  edges: DiagramEdge[],
): DiagramLayout {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "TB",
    nodesep: 60,
    ranksep: 70,
    marginx: 30,
    marginy: 30,
  });
  g.setDefaultEdgeLabel(() => ({}));

  const layoutNodes: Map<string, LayoutNode> = new Map();

  for (const node of nodes) {
    const shape = node.shape ?? "rounded";
    const size = computeNodeSize(node.label, shape);
    g.setNode(node.id, { width: size.width, height: size.height });
    layoutNodes.set(node.id, {
      id: node.id,
      label: node.label,
      shape,
      color: node.color ?? "",
      x: 0,
      y: 0,
      width: size.width,
      height: size.height,
    });
  }

  for (const edge of edges) {
    g.setEdge(edge.from_id, edge.to_id);
  }

  dagre.layout(g);

  // Read back positions
  for (const nodeId of g.nodes()) {
    const gNode = g.node(nodeId);
    const ln = layoutNodes.get(nodeId);
    if (ln && gNode) {
      ln.x = gNode.x;
      ln.y = gNode.y;
    }
  }

  const resultNodes = Array.from(layoutNodes.values());
  const resultEdges = routeEdges(edges, layoutNodes);
  const { width, height } = computeViewBox(resultNodes);

  return { nodes: resultNodes, edges: resultEdges, width, height };
}

function layoutCircular(
  nodes: DiagramNode[],
  edges: DiagramEdge[],
): DiagramLayout {
  const n = nodes.length;
  const radius = Math.max(80, n * 40);
  const centerX = radius + 60;
  const centerY = radius + 60;

  const layoutNodes: Map<string, LayoutNode> = new Map();

  nodes.forEach((node, i) => {
    const shape = node.shape ?? "rounded";
    const size = computeNodeSize(node.label, shape);
    const angle = (2 * Math.PI * i) / n - Math.PI / 2; // Start from top
    layoutNodes.set(node.id, {
      id: node.id,
      label: node.label,
      shape,
      color: node.color ?? "",
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
      width: size.width,
      height: size.height,
    });
  });

  const resultNodes = Array.from(layoutNodes.values());
  const resultEdges = routeEdges(edges, layoutNodes);
  const { width, height } = computeViewBox(resultNodes);

  return { nodes: resultNodes, edges: resultEdges, width, height };
}

function layoutRadial(
  nodes: DiagramNode[],
  edges: DiagramEdge[],
): DiagramLayout {
  if (nodes.length === 0) {
    return { nodes: [], edges: [], width: 0, height: 0 };
  }

  // Find the most-connected node
  const connectionCount = new Map<string, number>();
  for (const node of nodes) {
    connectionCount.set(node.id, 0);
  }
  for (const edge of edges) {
    connectionCount.set(
      edge.from_id,
      (connectionCount.get(edge.from_id) ?? 0) + 1,
    );
    connectionCount.set(edge.to_id, (connectionCount.get(edge.to_id) ?? 0) + 1);
  }

  let centralId = nodes[0].id;
  let maxConn = 0;
  for (const [id, count] of connectionCount) {
    if (count > maxConn) {
      maxConn = count;
      centralId = id;
    }
  }

  const orbitNodes = nodes.filter((n) => n.id !== centralId);
  const radius = Math.max(100, orbitNodes.length * 45);
  const centerX = radius + 80;
  const centerY = radius + 80;

  const layoutNodes: Map<string, LayoutNode> = new Map();

  // Place central node
  const centralNode = nodes.find((n) => n.id === centralId)!;
  const centralShape = centralNode.shape ?? "rounded";
  const centralSize = computeNodeSize(centralNode.label, centralShape);
  layoutNodes.set(centralId, {
    id: centralId,
    label: centralNode.label,
    shape: centralShape,
    color: centralNode.color ?? "",
    x: centerX,
    y: centerY,
    width: centralSize.width,
    height: centralSize.height,
  });

  // Place orbit nodes
  orbitNodes.forEach((node, i) => {
    const shape = node.shape ?? "rounded";
    const size = computeNodeSize(node.label, shape);
    const angle = (2 * Math.PI * i) / orbitNodes.length - Math.PI / 2;
    layoutNodes.set(node.id, {
      id: node.id,
      label: node.label,
      shape,
      color: node.color ?? "",
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
      width: size.width,
      height: size.height,
    });
  });

  const resultNodes = Array.from(layoutNodes.values());
  const resultEdges = routeEdges(edges, layoutNodes);
  const { width, height } = computeViewBox(resultNodes);

  return { nodes: resultNodes, edges: resultEdges, width, height };
}

function layoutComparison(
  nodes: DiagramNode[],
  edges: DiagramEdge[],
): DiagramLayout {
  const half = Math.ceil(nodes.length / 2);
  const leftGroup = nodes.slice(0, half);
  const rightGroup = nodes.slice(half);

  const layoutNodes: Map<string, LayoutNode> = new Map();
  const colGap = 300;
  const rowGap = 80;

  const placeColumn = (group: DiagramNode[], xBase: number) => {
    group.forEach((node, i) => {
      const shape = node.shape ?? "rounded";
      const size = computeNodeSize(node.label, shape);
      layoutNodes.set(node.id, {
        id: node.id,
        label: node.label,
        shape,
        color: node.color ?? "",
        x: xBase,
        y: 60 + i * (size.height + rowGap),
        width: size.width,
        height: size.height,
      });
    });
  };

  placeColumn(leftGroup, 120);
  placeColumn(rightGroup, 120 + colGap);

  const resultNodes = Array.from(layoutNodes.values());
  const resultEdges = routeEdges(edges, layoutNodes);
  const { width, height } = computeViewBox(resultNodes);

  return { nodes: resultNodes, edges: resultEdges, width, height };
}

// ── Edge routing ──────────────────────────────────────────────

function routeEdges(
  edges: DiagramEdge[],
  nodeMap: Map<string, LayoutNode>,
): LayoutEdge[] {
  return edges
    .map((edge) => {
      const fromNode = nodeMap.get(edge.from_id);
      const toNode = nodeMap.get(edge.to_id);
      if (!fromNode || !toNode) return null;

      const start = intersectNodeBoundary(fromNode, toNode.x, toNode.y);
      const end = intersectNodeBoundary(toNode, fromNode.x, fromNode.y);

      return {
        fromId: edge.from_id,
        toId: edge.to_id,
        label: edge.label ?? "",
        style: edge.style ?? "solid",
        directed: edge.directed ?? true,
        x1: start.x,
        y1: start.y,
        x2: end.x,
        y2: end.y,
        labelX: (start.x + end.x) / 2,
        labelY: (start.y + end.y) / 2,
      } satisfies LayoutEdge;
    })
    .filter((e): e is LayoutEdge => e !== null);
}

// ── ViewBox computation ───────────────────────────────────────

const VIEWBOX_PADDING = 40;

function computeViewBox(nodes: LayoutNode[]): {
  width: number;
  height: number;
} {
  if (nodes.length === 0) return { width: 200, height: 200 };

  let maxX = 0;
  let maxY = 0;

  for (const n of nodes) {
    maxX = Math.max(maxX, n.x + n.width / 2);
    maxY = Math.max(maxY, n.y + n.height / 2);
  }

  return {
    width: maxX + VIEWBOX_PADDING,
    height: maxY + VIEWBOX_PADDING,
  };
}

// ── Public API ────────────────────────────────────────────────

const DAGRE_TYPES: DiagramType[] = [
  "flowchart",
  "tree",
  "concept_map",
  "free_form",
];

export function computeDiagramLayout(
  nodes: DiagramNode[],
  edges: DiagramEdge[],
  diagramType: DiagramType = "free_form",
): DiagramLayout {
  if (nodes.length === 0) {
    return { nodes: [], edges: [], width: 0, height: 0 };
  }

  if (nodes.length === 1) {
    // Single node — center it
    const node = nodes[0];
    const shape = node.shape ?? "rounded";
    const size = computeNodeSize(node.label, shape);
    const layoutNode: LayoutNode = {
      id: node.id,
      label: node.label,
      shape,
      color: node.color ?? "",
      x: size.width / 2 + VIEWBOX_PADDING,
      y: size.height / 2 + VIEWBOX_PADDING,
      width: size.width,
      height: size.height,
    };
    return {
      nodes: [layoutNode],
      edges: [],
      width: size.width + VIEWBOX_PADDING * 2,
      height: size.height + VIEWBOX_PADDING * 2,
    };
  }

  if (DAGRE_TYPES.includes(diagramType)) {
    return layoutWithDagre(nodes, edges);
  }

  switch (diagramType) {
    case "cycle":
      return layoutCircular(nodes, edges);
    case "force_diagram":
      return layoutRadial(nodes, edges);
    case "comparison":
      return layoutComparison(nodes, edges);
    default:
      return layoutWithDagre(nodes, edges);
  }
}
