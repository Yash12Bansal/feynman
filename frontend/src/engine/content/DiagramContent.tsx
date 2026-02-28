import { useEffect, useRef } from "react";
import gsap from "gsap";
import type { DrawDiagramInstruction } from "../../types/visuals";
import { COLORS } from "../theme";
import {
  computeDiagramLayout,
  type LayoutNode,
  type LayoutEdge,
} from "../layout/diagram-layout";

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

const EDGE_COLOR = COLORS.accentGreen;
const STROKE_WIDTH = 2;
const ARROWHEAD_SIZE = 8;

// ── Node shape renderer ───────────────────────────────────────

function NodeShapeSvg({ node }: { node: LayoutNode }) {
  const fill = node.color
    ? `${node.color}1F` // 12% opacity
    : `${COLORS.accentGreen}14`; // 8% opacity
  const stroke = node.color || COLORS.accentGreen;
  const hw = node.width / 2;
  const hh = node.height / 2;

  switch (node.shape) {
    case "rectangle":
      return (
        <rect
          x={-hw}
          y={-hh}
          width={node.width}
          height={node.height}
          fill={fill}
          stroke={stroke}
          strokeWidth={STROKE_WIDTH}
        />
      );

    case "rounded":
      return (
        <rect
          x={-hw}
          y={-hh}
          width={node.width}
          height={node.height}
          rx={8}
          ry={8}
          fill={fill}
          stroke={stroke}
          strokeWidth={STROKE_WIDTH}
        />
      );

    case "circle":
      return (
        <circle
          cx={0}
          cy={0}
          r={hw}
          fill={fill}
          stroke={stroke}
          strokeWidth={STROKE_WIDTH}
        />
      );

    case "ellipse":
      return (
        <ellipse
          cx={0}
          cy={0}
          rx={hw}
          ry={hh}
          fill={fill}
          stroke={stroke}
          strokeWidth={STROKE_WIDTH}
        />
      );

    case "diamond": {
      const points = `0,${-hh} ${hw},0 0,${hh} ${-hw},0`;
      return (
        <polygon
          points={points}
          fill={fill}
          stroke={stroke}
          strokeWidth={STROKE_WIDTH}
        />
      );
    }

    default:
      return (
        <rect
          x={-hw}
          y={-hh}
          width={node.width}
          height={node.height}
          rx={8}
          ry={8}
          fill={fill}
          stroke={stroke}
          strokeWidth={STROKE_WIDTH}
        />
      );
  }
}

// ── Arrowhead ─────────────────────────────────────────────────

function computeArrowheadPoints(
  x2: number,
  y2: number,
  x1: number,
  y1: number,
): string {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return "";

  const ux = dx / len;
  const uy = dy / len;
  // Perpendicular
  const px = -uy;
  const py = ux;

  const tipX = x2;
  const tipY = y2;
  const baseX = x2 - ux * ARROWHEAD_SIZE;
  const baseY = y2 - uy * ARROWHEAD_SIZE;
  const leftX = baseX + px * (ARROWHEAD_SIZE / 2.5);
  const leftY = baseY + py * (ARROWHEAD_SIZE / 2.5);
  const rightX = baseX - px * (ARROWHEAD_SIZE / 2.5);
  const rightY = baseY - py * (ARROWHEAD_SIZE / 2.5);

  return `${tipX},${tipY} ${leftX},${leftY} ${rightX},${rightY}`;
}

// ── Edge dash patterns ────────────────────────────────────────

function getDashArray(style: LayoutEdge["style"]): string | undefined {
  switch (style) {
    case "dashed":
      return "8,4";
    case "dotted":
      return "3,3";
    default:
      return undefined;
  }
}

// ── Structured SVG diagram ────────────────────────────────────

function StructuredDiagram({
  instruction,
}: {
  instruction: DrawDiagramInstruction;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  const nodes = instruction.nodes ?? [];
  const edges = instruction.edges ?? [];
  const diagramType = instruction.diagram_type ?? "free_form";
  const progressive = instruction.progressive !== false;

  const layout = computeDiagramLayout(nodes, edges, diagramType);

  // Progressive animation
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !progressive) return;

    timelineRef.current?.kill();

    const nodeEls = svg.querySelectorAll<SVGGElement>("[data-node]");
    const edgeEls = svg.querySelectorAll<SVGLineElement>("[data-edge]");
    const arrowEls =
      svg.querySelectorAll<SVGPolygonElement>("[data-arrowhead]");
    const edgeLabelEls = svg.querySelectorAll<SVGGElement>("[data-edge-label]");

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

    // Phase 2: Edges draw in (overlapping with end of phase 1)
    if (edgeEls.length > 0) {
      edgeEls.forEach((line) => {
        const length = getLineLength(line);
        gsap.set(line, {
          strokeDasharray: length,
          strokeDashoffset: length,
        });
      });

      const edgeStart = Math.max(0, (nodeEls.length - 1) * 0.1);
      tl.to(
        edgeEls,
        {
          strokeDashoffset: 0,
          duration: 0.4,
          stagger: 0.08,
          ease: "power2.out",
        },
        edgeStart,
      );
    }

    // Phase 3: Arrowheads + edge labels fade in
    const fadeTargets = [...Array.from(arrowEls), ...Array.from(edgeLabelEls)];
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
        {/* Edges (behind nodes) */}
        {layout.edges.map((edge, i) => (
          <g key={`edge-${i}`}>
            <line
              data-edge={i}
              x1={edge.x1}
              y1={edge.y1}
              x2={edge.x2}
              y2={edge.y2}
              stroke={EDGE_COLOR}
              strokeWidth={STROKE_WIDTH}
              strokeDasharray={getDashArray(edge.style)}
            />
            {edge.directed && (
              <polygon
                data-arrowhead={i}
                points={computeArrowheadPoints(
                  edge.x2,
                  edge.y2,
                  edge.x1,
                  edge.y1,
                )}
                fill={EDGE_COLOR}
              />
            )}
            {edge.label && (
              <g data-edge-label={i}>
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
            )}
          </g>
        ))}

        {/* Nodes (on top) */}
        {layout.nodes.map((node) => (
          <g
            key={node.id}
            data-node={node.id}
            transform={`translate(${node.x},${node.y})`}
          >
            <NodeShapeSvg node={node} />
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

function getLineLength(line: SVGLineElement): number {
  const x1 = parseFloat(line.getAttribute("x1") ?? "0");
  const y1 = parseFloat(line.getAttribute("y1") ?? "0");
  const x2 = parseFloat(line.getAttribute("x2") ?? "0");
  const y2 = parseFloat(line.getAttribute("y2") ?? "0");
  return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
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

export function DiagramContent({
  instruction,
}: {
  instruction: DrawDiagramInstruction;
}) {
  const hasNodes = (instruction.nodes?.length ?? 0) > 0;

  if (hasNodes) {
    return <StructuredDiagram instruction={instruction} />;
  }

  return <FallbackDiagram instruction={instruction} />;
}
