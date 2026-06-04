/**
 * Slide panel — left ~38% of the split board.
 *
 * Holds exactly one slide at a time. Shows DraftingLoader while generating,
 * stroke-reveals the diagram on arrival. Cross-fades between slides.
 */

import { useMemo, useRef } from "react";
import type { VisualInstruction } from "../../../types/visuals";
import type { SlideState, SlideSketch } from "./types";
import { DraftingLoader } from "./DraftingLoader";
import { InstructionSwitch } from "../InstructionSwitch";
import { SlideAnnotationLayer } from "./SlideAnnotationLayer";

interface SlidePanelProps {
  readonly state: SlideState;
  /**
   * Workstream A4: when true, design diagrams render draggable parameter
   * sliders. Lecture/doubt playback leaves this false (parameters are
   * event-driven); an interactive playground surface sets it true.
   */
  readonly interactive?: boolean;
}

function liveTitleFor(instr: VisualInstruction): {
  title: string;
  subtitle: string;
} {
  switch (instr.type) {
    case "draw_design_diagram":
      return { title: instr.title ?? "", subtitle: "diagram" };
    case "draw_diagram":
      return { title: instr.title ?? "", subtitle: "diagram" };
    case "draw_scene":
      return { title: instr.title ?? "", subtitle: "scene" };
    default:
      return { title: "", subtitle: "" };
  }
}

export function SlidePanel({ state, interactive }: SlidePanelProps) {
  const {
    status,
    active,
    pendingTitle,
    liveInstruction,
    traces,
    markPoints,
    marginNotes,
    pointers,
    focusedElementId,
    focusedElementIds,
    focusedRole,
    revealedElementIds,
    paramOverrides,
  } = state;

  // Live-DOM bounds anchor: the annotation layer queries this subtree for
  // `[data-design-element]` and reads `getBoundingClientRect()`.
  const stageRef = useRef<HTMLDivElement>(null);

  // Only design diagrams carry the semantic dictionary; the annotation layer
  // is a no-op for legacy diagram types since it has nothing to anchor against.
  const designDiagram =
    status === "ready" && liveInstruction?.type === "draw_design_diagram"
      ? liveInstruction
      : null;
  // Mount the annotation layer whenever there's a design diagram with a
  // dictionary, so trace/mark/margin annotations can anchor to its elements.
  const showAnnotations =
    designDiagram !== null && !!designDiagram.spec?.dictionary;

  const liveHeader = liveInstruction ? liveTitleFor(liveInstruction) : null;
  const headerTitle = liveHeader?.title || active?.title || pendingTitle || "";
  const headerSubtitle =
    liveHeader?.subtitle ||
    active?.subtitle ||
    (status === "loading" ? "loading" : "");

  return (
    <section className="sb-slide" aria-label="Slide panel">
      <div className="sb-slide-header">
        <h2 className="sb-slide-title">{headerTitle || "\u00A0"}</h2>
        <span className="sb-slide-subtitle">{headerSubtitle || "\u00A0"}</span>
      </div>

      <div className="sb-slide-stage" ref={stageRef}>
        {status === "loading" && (
          <DraftingLoader
            caption={
              pendingTitle ? `Sketching — ${pendingTitle}` : "Sketching…"
            }
          />
        )}
        {status === "ready" && liveInstruction && (
          <div
            className="sb-slide-live sb-slide-active"
            key={liveInstruction.element_id ?? `${liveInstruction.type}-live`}
          >
            <InstructionSwitch
              instruction={liveInstruction}
              focusedElementId={focusedElementId}
              focusedElementIds={focusedElementIds}
              focusedRole={focusedRole}
              revealedElementIds={revealedElementIds}
              interactive={interactive}
              paramOverrides={paramOverrides}
            />
          </div>
        )}
        {showAnnotations && designDiagram && (
          <SlideAnnotationLayer
            viewBox={`0 0 ${designDiagram.spec?.width ?? 900} ${designDiagram.spec?.height ?? 650}`}
            dictionary={designDiagram.spec?.dictionary}
            stageRef={stageRef}
            traces={traces}
            markPoints={markPoints}
            marginNotes={marginNotes}
            pointers={pointers}
          />
        )}
        {status === "ready" && !liveInstruction && active && (
          <SlideSketchView key={active.id} sketch={active.sketch} />
        )}
        {status === "empty" && (
          <span className="sb-slide-empty">slide — empty</span>
        )}
      </div>
    </section>
  );
}

function SlideSketchView({ sketch }: { readonly sketch: SlideSketch }) {
  // Memoize the rendered paths — recomputing transforms on every parent render
  // would retrigger the draw animation.
  const rendered = useMemo(() => {
    return sketch.paths.map((p, i) => {
      const strokeOrder = i;
      const hasFill = p.fill && p.fill !== "none";
      return (
        <g key={i} style={{ ["--sb-stroke-order" as string]: strokeOrder }}>
          <path
            className="sb-slide-stroke"
            d={p.d}
            stroke={p.stroke ?? "#e8e8ee"}
            strokeWidth={p.strokeWidth ?? 1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
            fill={hasFill ? p.fill : "none"}
            style={hasFill ? { fill: "transparent" } : undefined}
          />
          {hasFill && (
            <path
              className="sb-slide-fill"
              d={p.d}
              fill={p.fill}
              stroke="none"
            />
          )}
          {p.label && p.labelX !== undefined && p.labelY !== undefined && (
            <text
              className="sb-slide-label sb-slide-label-anim"
              x={p.labelX}
              y={p.labelY}
              textAnchor="middle"
            >
              {p.label}
            </text>
          )}
        </g>
      );
    });
  }, [sketch]);

  return (
    <svg
      className="sb-slide-svg sb-slide-active"
      viewBox={sketch.viewBox}
      preserveAspectRatio="xMidYMid meet"
    >
      {rendered}
    </svg>
  );
}
