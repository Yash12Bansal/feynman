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

export function SlidePanel({ state }: SlidePanelProps) {
  const {
    status,
    active,
    pendingTitle,
    liveInstruction,
    focusedElementId,
    focusedRole,
    inlineLabelText,
    presentationMode,
    traces,
    markPoints,
    pointers,
    marginNotes,
  } = state;

  // Live-DOM bounds anchor: the spotlight layer queries this subtree for
  // `[data-design-element]` and reads `getBoundingClientRect()`.
  const stageRef = useRef<HTMLDivElement>(null);

  // Only design diagrams carry the semantic dictionary; the spotlight is a
  // no-op for legacy diagram types since it has nothing to anchor against.
  const designDiagram =
    status === "ready" && liveInstruction?.type === "draw_design_diagram"
      ? liveInstruction
      : null;
  // Mount the spotlight whenever there's a design diagram with a dictionary,
  // even if nothing is focused yet — keeps transitions clean when focus
  // arrives mid-narration.
  const showSpotlight =
    designDiagram !== null && !!designDiagram.spec?.dictionary;

  // Doc 18 §4.3: presentation mode comes from the SlideState (set by the
  // event dispatcher) OR the spec's declared mode OR "overview".
  const effectivePresentationMode =
    presentationMode ?? designDiagram?.spec?.presentation_mode ?? "overview";

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
            <InstructionSwitch instruction={liveInstruction} />
          </div>
        )}
        {showSpotlight && designDiagram && (
          <SlideAnnotationLayer
            viewBox={`0 0 ${designDiagram.spec?.width ?? 900} ${designDiagram.spec?.height ?? 650}`}
            dictionary={designDiagram.spec?.dictionary}
            focusedElementId={focusedElementId}
            focusedRole={focusedRole}
            inlineLabelText={inlineLabelText}
            presentationMode={effectivePresentationMode}
            stageRef={stageRef}
            traces={traces}
            markPoints={markPoints}
            pointers={pointers}
            marginNotes={marginNotes}
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
