/**
 * Tests for the `svg_frame` primitive added in Phase B of the design-agent
 * styling bridge. Frames enable comparison / before-after / labeled-scene
 * layouts (e.g. the prototype's Earth-vs-Space panels).
 */

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { DesignDiagramContent } from "./DesignDiagramContent";
import type {
  DrawDesignDiagramInstruction,
  DesignDiagramSpec,
} from "../../../types/visuals";

function wrap(spec: DesignDiagramSpec): DrawDesignDiagramInstruction {
  return {
    type: "draw_design_diagram",
    title: spec.title ?? "",
    spec,
  };
}

describe("DesignDiagramContent — svg_frame", () => {
  it("renders a frame with title and caption", () => {
    const spec: DesignDiagramSpec = {
      width: 900,
      height: 650,
      elements: [
        {
          type: "svg_frame",
          id: "frame-earth",
          x: 40,
          y: 60,
          width: 380,
          height: 540,
          title: "Earth's Surface (Frame 1)",
          caption: "Book appears AT REST",
          background: "var(--sb-panel-earth)",
          accent: "#1f2430",
        },
      ],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );

    const rect = container.querySelector('rect[data-design-element="frame-earth"], g[data-design-element="frame-earth"] rect');
    expect(rect).not.toBeNull();
    // Background flows through via fill attribute.
    expect(rect?.getAttribute("fill")).toBe("var(--sb-panel-earth)");
    expect(rect?.getAttribute("stroke")).toBe("#1f2430");

    const titleEl = container.querySelector(".dd-frame-title");
    expect(titleEl?.textContent).toBe("Earth's Surface (Frame 1)");

    const captionEl = container.querySelector(".dd-frame-caption");
    expect(captionEl?.textContent).toBe("Book appears AT REST");
  });

  it("renders two side-by-side frames for comparison layouts", () => {
    const spec: DesignDiagramSpec = {
      width: 900,
      height: 650,
      elements: [
        {
          type: "svg_frame",
          id: "earth",
          x: 40,
          y: 60,
          width: 380,
          height: 540,
          title: "Earth's Surface",
          background: "var(--sb-panel-earth)",
        },
        {
          type: "svg_frame",
          id: "space",
          x: 480,
          y: 60,
          width: 380,
          height: 540,
          title: "Space / Moon",
          background: "var(--sb-panel-space)",
        },
      ],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    const frames = container.querySelectorAll(".dd-frame-title");
    expect(frames).toHaveLength(2);
    expect(frames[0].textContent).toBe("Earth's Surface");
    expect(frames[1].textContent).toBe("Space / Moon");
  });

  it("omits caption when not provided", () => {
    const spec: DesignDiagramSpec = {
      elements: [
        {
          type: "svg_frame",
          id: "solo",
          x: 0,
          y: 0,
          width: 100,
          height: 100,
          title: "Only a title",
        },
      ],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    expect(container.querySelector(".dd-frame-title")).not.toBeNull();
    expect(container.querySelector(".dd-frame-caption")).toBeNull();
  });

  it("falls back to cream background and solid dark ink accent when unspecified", () => {
    const spec: DesignDiagramSpec = {
      elements: [
        {
          type: "svg_frame",
          id: "bare",
          x: 0,
          y: 0,
          width: 200,
          height: 150,
        },
      ],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    const rect = container.querySelector("rect");
    expect(rect?.getAttribute("fill")).toContain("--sb-panel-cream");
    // Solid `--sb-panel-ink`, not the muted variant — so titles read cleanly.
    expect(rect?.getAttribute("stroke")).toContain("--sb-panel-ink");
    expect(rect?.getAttribute("stroke")).not.toContain("--sb-panel-ink-muted");
  });

  it("defaults primitive stroke to ink palette var when unspecified", () => {
    // Phase A regression guard: previously defaulted to #000 which is
    // invisible on dark split-board panels.
    const spec: DesignDiagramSpec = {
      elements: [
        {
          type: "svg_line",
          id: "l",
          x1: 0,
          y1: 0,
          x2: 100,
          y2: 100,
        },
      ],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    const line = container.querySelector("line");
    expect(line?.getAttribute("stroke")).toContain("--sb-ink");
  });

  it("defaults the svg stage background to transparent", () => {
    // Phase A: previously defaulted to #ffffff which painted a white box
    // inside the dark split-board slide panel.
    const spec: DesignDiagramSpec = { elements: [] };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("style")).toContain("transparent");
  });
});
