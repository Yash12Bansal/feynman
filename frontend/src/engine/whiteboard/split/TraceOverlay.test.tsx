/**
 * TraceOverlay — doc 19 §12 stroke-draw primitive tests.
 *
 * The component queries the live DOM to clone the original element's leaf
 * shape into the annotation overlay. Tests cover the cloning fidelity per
 * leaf type, the bounds-rect fallback when the DOM has nothing to clone,
 * and the animation kickoff (CSS variable + class are wired up correctly).
 */

import { useRef, type RefObject } from "react";
import { describe, expect, it } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { TraceOverlay } from "./TraceOverlay";
import type { ElementMeta } from "../../../types/visuals";

interface HarnessProps {
  readonly stageContent: React.ReactNode;
  readonly elementId: string;
  readonly durationMs: number;
  readonly dictionary?: Record<string, ElementMeta>;
}

/**
 * Wraps a stage div + an overlay SVG so the component can query the stage
 * for the matching `[data-design-element]` and render inside the overlay.
 */
function Harness({
  stageContent,
  elementId,
  durationMs,
  dictionary,
}: HarnessProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  return (
    <div>
      <div ref={stageRef} data-testid="stage">
        <svg viewBox="0 0 900 650">{stageContent}</svg>
      </div>
      <svg viewBox="0 0 900 650" data-testid="overlay">
        <TraceOverlay
          elementId={elementId}
          durationMs={durationMs}
          dictionary={dictionary}
          stageRef={stageRef as unknown as RefObject<HTMLElement | null>}
        />
      </svg>
    </div>
  );
}

describe("TraceOverlay", () => {
  it("clones a <path> leaf into the overlay with the same `d`", async () => {
    const { container } = render(
      <Harness
        elementId="parabola-1"
        durationMs={2000}
        stageContent={
          <g data-design-element="parabola-1">
            <path d="M 10 10 Q 100 50 200 10" stroke="#ff8888" />
          </g>
        }
      />,
    );

    await waitFor(() => {
      const traced = container.querySelector(
        ".sb-trace path.sb-trace-stroke",
      ) as SVGPathElement | null;
      expect(traced).not.toBeNull();
      expect(traced?.getAttribute("d")).toBe("M 10 10 Q 100 50 200 10");
      // Stroke comes from the original element.
      expect(traced?.getAttribute("stroke")).toBe("#ff8888");
    });
  });

  it("clones a <line> leaf with x1/y1/x2/y2", async () => {
    const { container } = render(
      <Harness
        elementId="vertical-1"
        durationMs={1000}
        stageContent={
          <g data-design-element="vertical-1">
            <line x1={50} y1={10} x2={50} y2={200} stroke="#ffffff" />
          </g>
        }
      />,
    );

    await waitFor(() => {
      const line = container.querySelector(
        ".sb-trace line.sb-trace-stroke",
      ) as SVGLineElement | null;
      expect(line).not.toBeNull();
      expect(line?.getAttribute("x1")).toBe("50");
      expect(line?.getAttribute("y1")).toBe("10");
      expect(line?.getAttribute("x2")).toBe("50");
      expect(line?.getAttribute("y2")).toBe("200");
    });
  });

  it("clones a <circle> leaf with cx/cy/r", async () => {
    const { container } = render(
      <Harness
        elementId="ball-1"
        durationMs={1500}
        stageContent={
          <g data-design-element="ball-1">
            <circle cx={100} cy={100} r={20} stroke="#00ff00" />
          </g>
        }
      />,
    );

    await waitFor(() => {
      const c = container.querySelector(
        ".sb-trace circle.sb-trace-stroke",
      ) as SVGCircleElement | null;
      expect(c).not.toBeNull();
      expect(c?.getAttribute("cx")).toBe("100");
      expect(c?.getAttribute("cy")).toBe("100");
      expect(c?.getAttribute("r")).toBe("20");
    });
  });

  it("clones a <polyline> leaf with points", async () => {
    const { container } = render(
      <Harness
        elementId="poly-1"
        durationMs={1200}
        stageContent={
          <g data-design-element="poly-1">
            <polyline points="0,0 50,50 100,0" stroke="#ff0000" />
          </g>
        }
      />,
    );

    await waitFor(() => {
      const pl = container.querySelector(
        ".sb-trace polyline.sb-trace-stroke",
      ) as SVGPolylineElement | null;
      expect(pl).not.toBeNull();
      expect(pl?.getAttribute("points")).toBe("0,0 50,50 100,0");
    });
  });

  it("uses the bounds fallback when no DOM element matches", async () => {
    const dictionary: Record<string, ElementMeta> = {
      "missing-thing": {
        role: "ghost",
        semantic: "not in DOM",
        position: "center",
        bounds: [100, 100, 80, 60],
      },
    };
    const { container } = render(
      <Harness
        elementId="missing-thing"
        durationMs={1500}
        dictionary={dictionary}
        stageContent={null}
      />,
    );

    await waitFor(() => {
      const rect = container.querySelector(
        ".sb-trace rect.sb-trace-stroke-fallback",
      ) as SVGRectElement | null;
      expect(rect).not.toBeNull();
      expect(rect?.getAttribute("x")).toBe("100");
      expect(rect?.getAttribute("y")).toBe("100");
      expect(rect?.getAttribute("width")).toBe("80");
      expect(rect?.getAttribute("height")).toBe("60");
    });
  });

  it("renders nothing when neither DOM nor bounds can resolve", async () => {
    const { container } = render(
      <Harness elementId="nowhere" durationMs={1500} stageContent={null} />,
    );

    // Give the useEffect a tick.
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector(".sb-trace")).toBeNull();
  });

  it("writes durationMs as a CSS custom property for the animation timing", async () => {
    const { container } = render(
      <Harness
        elementId="path-2"
        durationMs={3200}
        stageContent={
          <g data-design-element="path-2">
            <path d="M 0 0 L 100 100" stroke="#ffffff" />
          </g>
        }
      />,
    );

    await waitFor(() => {
      const traced = container.querySelector(
        ".sb-trace path.sb-trace-stroke",
      ) as SVGPathElement | null;
      expect(traced).not.toBeNull();
      const style = traced!.getAttribute("style") ?? "";
      // React serializes inline CSS custom props using the camelCase →
      // kebab-case mapping; assert the duration is present in either form.
      expect(style).toContain("3200ms");
    });
  });

  it("tags the rendered group with the element_id for debugging", async () => {
    const { container } = render(
      <Harness
        elementId="my-element"
        durationMs={1500}
        stageContent={
          <g data-design-element="my-element">
            <line x1={0} y1={0} x2={10} y2={10} stroke="#fff" />
          </g>
        }
      />,
    );

    await waitFor(() => {
      const group = container.querySelector(".sb-trace");
      expect(group?.getAttribute("data-element-id")).toBe("my-element");
      expect(group?.getAttribute("data-shape-kind")).toBe("line");
    });
  });
});
