/**
 * Slide panel — left ~38% of the split board.
 *
 * Holds exactly one slide at a time. Shows DraftingLoader while generating,
 * stroke-reveals the diagram on arrival. Cross-fades between slides.
 */

import { useMemo } from "react";
import type { VisualInstruction } from "../../../types/visuals";
import type { SlideState, SlideSketch } from "./types";
import { DraftingLoader } from "./DraftingLoader";
import { InstructionSwitch } from "../InstructionSwitch";

interface SlidePanelProps {
  readonly state: SlideState;
}

function liveTitleFor(instr: VisualInstruction): { title: string; subtitle: string } {
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
  const { status, active, pendingTitle, liveInstruction } = state;

  const liveHeader = liveInstruction ? liveTitleFor(liveInstruction) : null;
  const headerTitle =
    liveHeader?.title || active?.title || pendingTitle || "";
  const headerSubtitle =
    liveHeader?.subtitle ||
    active?.subtitle ||
    (status === "loading" ? "loading" : "");

  return (
    <section className="sb-slide" aria-label="Slide panel">
      <div className="sb-slide-header">
        <h2 className="sb-slide-title">
          {headerTitle || "\u00A0"}
        </h2>
        <span className="sb-slide-subtitle">
          {headerSubtitle || "\u00A0"}
        </span>
      </div>

      <div className="sb-slide-stage">
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
