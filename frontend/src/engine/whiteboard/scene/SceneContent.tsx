/**
 * Scientific scene renderer using Rough.js rough.path().
 *
 * Two-layer SVG architecture (mirrors RoughDiagramContent):
 * 1. Rough layer (imperative) — rough.path() for each ScenePath, alive filter
 * 2. Label layer (declarative React) — clean SVG text for readability
 *
 * Template dispatch: looks up template_id → function, calls with params,
 * gets SceneGeometry, renders it.
 */

import { useEffect, useRef } from "react";
import gsap from "gsap";
import rough from "roughjs";
import type { DrawSceneInstruction } from "../../../types/visuals";
import type { SceneGeometry } from "./scene-types";
import { COLORS } from "../../theme";
import { ALIVE_FILTER_ID } from "../AliveFilter";
import { freeBodyDiagram } from "./templates/free-body";
import type { FreeBodyParams } from "./templates/free-body";
import { doubleSlit } from "./templates/double-slit";
import type { DoubleSlitParams } from "./templates/double-slit";

// ── Template registry ─────────────────────────────────────────

const TEMPLATES: Record<
  string,
  (params: Record<string, string | number | boolean>) => SceneGeometry
> = {
  free_body: (params) => freeBodyDiagram(params as unknown as FreeBodyParams),
  double_slit: (params) => doubleSlit(params as unknown as DoubleSlitParams),
};

// ── Fallback ──────────────────────────────────────────────────

function FallbackScene({ instruction }: { instruction: DrawSceneInstruction }) {
  const description = instruction.description ?? instruction.title ?? "";

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
            background: `${COLORS.accentBlue}99`,
            padding: "3px 8px",
            borderRadius: 4,
          }}
        >
          SCENE
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

// ── Structured scene ──────────────────────────────────────────

function StructuredScene({
  instruction,
  geometry,
}: {
  instruction: DrawSceneInstruction;
  geometry: SceneGeometry;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const roughLayerRef = useRef<SVGGElement>(null);
  const labelLayerRef = useRef<SVGGElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  const progressive = instruction.progressive !== false;
  const { bounds } = geometry;

  // Render rough paths imperatively
  useEffect(() => {
    const svg = svgRef.current;
    const roughLayer = roughLayerRef.current;
    if (!svg || !roughLayer) return;

    // Clear previous
    while (roughLayer.firstChild) {
      roughLayer.removeChild(roughLayer.firstChild);
    }

    if (geometry.paths.length === 0) return;

    const rc = rough.svg(svg);

    for (const scenePath of geometry.paths) {
      const el = rc.path(scenePath.d, scenePath.roughOptions ?? {});
      el.setAttribute("data-scene-path", scenePath.id);
      roughLayer.appendChild(el);
    }
  }, [geometry]);

  // Progressive draw-in animation
  useEffect(() => {
    const svg = svgRef.current;
    const labelLayer = labelLayerRef.current;
    if (!svg || !labelLayer || !progressive) return;

    timelineRef.current?.kill();

    const pathEls = svg.querySelectorAll<SVGGElement>("[data-scene-path]");
    const labelEls =
      labelLayer.querySelectorAll<SVGGElement>("[data-scene-label]");

    if (pathEls.length === 0) return;

    const tl = gsap.timeline();
    timelineRef.current = tl;

    // Phase 1: Paths draw in via strokeDashoffset
    const innerPaths: SVGPathElement[] = [];
    pathEls.forEach((g) => {
      // rough.path() wraps the actual <path> elements in a <g>
      const paths = g.querySelectorAll<SVGPathElement>("path");
      paths.forEach((p) => innerPaths.push(p));
    });

    innerPaths.forEach((path) => {
      const length = path.getTotalLength();
      gsap.set(path, {
        strokeDasharray: length,
        strokeDashoffset: length,
      });
    });

    if (innerPaths.length > 0) {
      tl.to(innerPaths, {
        strokeDashoffset: 0,
        duration: 0.4,
        stagger: 0.06,
        ease: "power2.out",
      });
    }

    // Phase 2: Labels fade in
    if (labelEls.length > 0) {
      gsap.set(labelEls, { opacity: 0 });
      const fadeStart = Math.max(0, (innerPaths.length - 1) * 0.06) + 0.2;
      tl.to(
        labelEls,
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
  }, [geometry, progressive]);

  const description = instruction.description || instruction.title || "";

  return (
    <div>
      {instruction.title && (
        <div
          style={{
            fontSize: 20,
            fontStyle: "italic",
            lineHeight: "28px",
            color: COLORS.accentBlue,
            marginBottom: 12,
          }}
        >
          {instruction.title}
        </div>
      )}
      <svg
        ref={svgRef}
        viewBox={`${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={description || "scientific diagram"}
        style={{ display: "block" }}
      >
        {/* Layer 1: Rough.js paths (imperative) — alive filter for organic wobble */}
        <g ref={roughLayerRef} style={{ filter: `url(#${ALIVE_FILTER_ID})` }} />

        {/* Layer 2: Clean labels (declarative) */}
        <g ref={labelLayerRef}>
          {geometry.labels.map((label) => (
            <g key={label.id} data-scene-label={label.id}>
              <text
                x={label.x}
                y={label.y}
                textAnchor={label.anchor ?? "middle"}
                fill={label.color ?? COLORS.textPrimary}
                fontSize={label.fontSize ?? 14}
                fontFamily="Inter, system-ui, sans-serif"
                fontWeight={600}
              >
                {label.text}
              </text>
            </g>
          ))}
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

// ── Public component ──────────────────────────────────────────

export function SceneContent({
  instruction,
}: {
  instruction: DrawSceneInstruction;
}) {
  const templateId = instruction.template?.template_id;
  const templateFn = templateId ? TEMPLATES[templateId] : undefined;

  if (templateFn) {
    const geometry = templateFn(instruction.template?.params ?? {});
    return <StructuredScene instruction={instruction} geometry={geometry} />;
  }

  return <FallbackScene instruction={instruction} />;
}
