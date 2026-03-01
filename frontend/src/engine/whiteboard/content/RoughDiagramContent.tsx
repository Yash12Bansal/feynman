/**
 * Hand-drawn diagram renderer using Rough.js.
 *
 * Two-layer SVG architecture:
 * 1. Rough layer (imperative) — Rough.js shapes and edges via useEffect
 * 2. Label layer (declarative React) — clean SVG text for readability
 *
 * Same data contract as DiagramContent. Same layout engine. Different feel.
 */

import { useEffect, useRef } from "react";
import gsap from "gsap";
import rough from "roughjs";
import type { RoughSVG } from "roughjs/bin/svg";
import type { DrawDiagramInstruction } from "../../../types/visuals";
import { COLORS } from "../../theme";
import {
  computeDiagramLayout,
  type DiagramLayout,
  type LayoutNode,
  type LayoutEdge,
} from "../../layout/diagram-layout";
import {
  hashSeed,
  nodeRoughOptions,
  computeArrowheadVertices,
  EDGE_DEFAULTS,
  ARROWHEAD_DEFAULTS,
} from "./rough-helpers";
import { ALIVE_FILTER_ID } from "../AliveFilter";

// ── Constants ─────────────────────────────────────────────────

const DIAGRAM_TYPE_LABELS: Record<string, string> = {
  flowchart: "FLOWCHART",
  concept_map: "CONCEPT MAP",
  force_diagram: "FORCE DIAGRAM",
  tree: "TREE",
  cycle: "CYCLE",
  comparison: "COMPARISON",
  free_form: "DIAGRAM",
};

// ── Edge dash patterns ────────────────────────────────────────

function getStrokeLineDash(style: LayoutEdge["style"]): number[] | undefined {
  switch (style) {
    case "dashed":
      return [8, 4];
    case "dotted":
      return [3, 3];
    default:
      return undefined;
  }
}

// ── Shape dispatch ────────────────────────────────────────────

function drawNodeShape(rc: RoughSVG, node: LayoutNode): SVGGElement {
  const opts = nodeRoughOptions(node.color, hashSeed(node.id));
  const hw = node.width / 2;
  const hh = node.height / 2;

  let el: SVGGElement;

  switch (node.shape) {
    case "circle":
      el = rc.circle(0, 0, node.width, opts) as unknown as SVGGElement;
      break;

    case "ellipse":
      el = rc.ellipse(
        0,
        0,
        node.width,
        node.height,
        opts,
      ) as unknown as SVGGElement;
      break;

    case "diamond": {
      const vertices: [number, number][] = [
        [0, -hh],
        [hw, 0],
        [0, hh],
        [-hw, 0],
      ];
      el = rc.polygon(vertices, opts) as unknown as SVGGElement;
      break;
    }

    // rectangle, rounded, and default all get rc.rectangle
    // Rough.js has no native rounded rect, but at roughness 1.5
    // the organic wobble makes them visually indistinguishable.
    default:
      el = rc.rectangle(
        -hw,
        -hh,
        node.width,
        node.height,
        opts,
      ) as unknown as SVGGElement;
      break;
  }

  return el;
}

// ── Structured rough diagram ──────────────────────────────────

function StructuredRoughDiagram({
  instruction,
}: {
  instruction: DrawDiagramInstruction;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const roughLayerRef = useRef<SVGGElement>(null);
  const labelLayerRef = useRef<SVGGElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  const nodes = instruction.nodes ?? [];
  const edges = instruction.edges ?? [];
  const diagramType = instruction.diagram_type ?? "free_form";
  const progressive = instruction.progressive !== false;

  const layout: DiagramLayout = computeDiagramLayout(nodes, edges, diagramType);

  // Render rough shapes imperatively
  useEffect(() => {
    const svg = svgRef.current;
    const roughLayer = roughLayerRef.current;
    if (!svg || !roughLayer) return;

    // Clear previous
    while (roughLayer.firstChild) {
      roughLayer.removeChild(roughLayer.firstChild);
    }

    if (layout.nodes.length === 0) return;

    const rc = rough.svg(svg);

    // Edges first (behind nodes in z-order)
    for (let i = 0; i < layout.edges.length; i++) {
      const edge = layout.edges[i];
      const dashOpts = getStrokeLineDash(edge.style);
      const edgeOpts = dashOpts
        ? { ...EDGE_DEFAULTS, strokeLineDash: dashOpts }
        : { ...EDGE_DEFAULTS };

      const edgeGroup = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "g",
      );
      edgeGroup.setAttribute("data-rough-edge", String(i));

      const lineEl = rc.line(edge.x1, edge.y1, edge.x2, edge.y2, edgeOpts);
      edgeGroup.appendChild(lineEl);

      // Arrowhead
      if (edge.directed) {
        const vertices = computeArrowheadVertices(
          edge.x2,
          edge.y2,
          edge.x1,
          edge.y1,
        );
        if (vertices.length > 0) {
          const arrowEl = rc.polygon(vertices, ARROWHEAD_DEFAULTS);
          arrowEl.setAttribute("data-rough-arrowhead", String(i));
          edgeGroup.appendChild(arrowEl);
        }
      }

      roughLayer.appendChild(edgeGroup);
    }

    // Nodes on top
    for (const node of layout.nodes) {
      const nodeGroup = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "g",
      );
      nodeGroup.setAttribute("data-rough-node", node.id);
      nodeGroup.setAttribute("transform", `translate(${node.x},${node.y})`);

      const shapeEl = drawNodeShape(rc, node);
      nodeGroup.appendChild(shapeEl);

      roughLayer.appendChild(nodeGroup);
    }
  }, [layout]);

  // Progressive animation
  useEffect(() => {
    const svg = svgRef.current;
    const labelLayer = labelLayerRef.current;
    if (!svg || !labelLayer || !progressive) return;

    timelineRef.current?.kill();

    const nodeEls = svg.querySelectorAll<SVGGElement>("[data-rough-node]");
    const edgeEls = svg.querySelectorAll<SVGGElement>("[data-rough-edge]");
    const arrowEls = svg.querySelectorAll<SVGElement>("[data-rough-arrowhead]");
    const nodeLabelEls =
      labelLayer.querySelectorAll<SVGGElement>("[data-node-label]");
    const edgeLabelEls =
      labelLayer.querySelectorAll<SVGGElement>("[data-edge-label]");

    if (nodeEls.length === 0) return;

    const tl = gsap.timeline();
    timelineRef.current = tl;

    // Phase 1: Nodes pop in
    gsap.set(nodeEls, { scale: 0, opacity: 0, transformOrigin: "center" });
    tl.to(nodeEls, {
      scale: 1,
      opacity: 1,
      duration: 0.35,
      stagger: 0.1,
      ease: "back.out(1.4)",
    });

    // Phase 2: Edges draw in via stroke-dash animation on inner paths
    if (edgeEls.length > 0) {
      const edgePaths: SVGPathElement[] = [];
      edgeEls.forEach((g) => {
        const path = g.querySelector<SVGPathElement>("path");
        if (path) edgePaths.push(path);
      });

      edgePaths.forEach((path) => {
        const length = path.getTotalLength();
        gsap.set(path, {
          strokeDasharray: length,
          strokeDashoffset: length,
        });
      });

      const edgeStart = Math.max(0, (nodeEls.length - 1) * 0.1);
      if (edgePaths.length > 0) {
        tl.to(
          edgePaths,
          {
            strokeDashoffset: 0,
            duration: 0.4,
            stagger: 0.08,
            ease: "power2.out",
          },
          edgeStart,
        );
      }
    }

    // Phase 3: Labels + arrowheads fade in
    const fadeTargets = [
      ...Array.from(nodeLabelEls),
      ...Array.from(edgeLabelEls),
      ...Array.from(arrowEls),
    ];

    if (fadeTargets.length > 0) {
      gsap.set(fadeTargets, { opacity: 0 });
      const fadeStart =
        Math.max(0, (nodeEls.length - 1) * 0.1) +
        Math.max(0, (edgeEls.length - 1) * 0.08) +
        0.2;
      tl.to(
        fadeTargets,
        {
          opacity: 1,
          duration: 0.25,
          stagger: 0.05,
          ease: "power2.out",
        },
        fadeStart,
      );
    }

    return () => {
      tl.kill();
    };
  }, [layout, progressive]);

  const description = instruction.description || instruction.title || "";

  return (
    <div>
      {instruction.title && (
        <div
          style={{
            fontSize: 20,
            fontStyle: "italic",
            lineHeight: "28px",
            color: COLORS.accentPurple,
            marginBottom: 12,
          }}
        >
          {instruction.title}
        </div>
      )}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={description || `${diagramType} diagram`}
        style={{ display: "block" }}
      >
        {/* Layer 1: Rough.js shapes (imperative) — alive filter for organic wobble */}
        <g ref={roughLayerRef} style={{ filter: `url(#${ALIVE_FILTER_ID})` }} />

        {/* Layer 2: Clean labels (declarative) */}
        <g ref={labelLayerRef}>
          {/* Node labels */}
          {layout.nodes.map((node) => (
            <g
              key={`label-${node.id}`}
              data-node-label={node.id}
              transform={`translate(${node.x},${node.y})`}
            >
              <text
                x={0}
                y={4}
                textAnchor="middle"
                fill={COLORS.textPrimary}
                fontSize={14}
                fontFamily="Inter, system-ui, sans-serif"
                fontWeight={500}
              >
                {node.label}
              </text>
            </g>
          ))}

          {/* Edge labels */}
          {layout.edges.map((edge, i) =>
            edge.label ? (
              <g key={`edge-label-${i}`} data-edge-label={i}>
                <rect
                  x={edge.labelX - (edge.label.length * 4 + 6)}
                  y={edge.labelY - 10}
                  width={edge.label.length * 8 + 12}
                  height={20}
                  rx={4}
                  fill={COLORS.cardBg}
                  stroke={COLORS.cardBorder}
                  strokeWidth={1}
                />
                <text
                  x={edge.labelX}
                  y={edge.labelY + 4}
                  textAnchor="middle"
                  fill={COLORS.textSecondary}
                  fontSize={12}
                  fontFamily="Inter, system-ui, sans-serif"
                >
                  {edge.label}
                </text>
              </g>
            ) : null,
          )}
        </g>
      </svg>
      {instruction.description && (
        <p
          style={{
            margin: 0,
            marginTop: 12,
            fontSize: 16,
            lineHeight: "24px",
            color: COLORS.textSecondary,
          }}
        >
          {instruction.description}
        </p>
      )}
    </div>
  );
}

// ── Fallback (description only) ───────────────────────────────

function FallbackDiagram({
  instruction,
}: {
  instruction: DrawDiagramInstruction;
}) {
  const description = instruction.description ?? instruction.title ?? "";
  const badge =
    DIAGRAM_TYPE_LABELS[instruction.diagram_type ?? "free_form"] ?? "DIAGRAM";

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: description ? 12 : 0,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.05em",
            color: COLORS.diagramBg,
            background: `${COLORS.accentGreen}99`,
            padding: "3px 8px",
            borderRadius: 4,
          }}
        >
          {badge}
        </span>
      </div>
      {description && (
        <p
          style={{
            margin: 0,
            fontSize: 20,
            lineHeight: "32px",
            color: COLORS.textSecondary,
          }}
        >
          {description}
        </p>
      )}
    </div>
  );
}

// ── Public component ──────────────────────────────────────────

export function RoughDiagramContent({
  instruction,
}: {
  instruction: DrawDiagramInstruction;
}) {
  const hasNodes = (instruction.nodes?.length ?? 0) > 0;

  if (hasNodes) {
    return <StructuredRoughDiagram instruction={instruction} />;
  }

  return <FallbackDiagram instruction={instruction} />;
}
