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

    const rect = container.querySelector(
      'rect[data-design-element="frame-earth"], g[data-design-element="frame-earth"] rect',
    );
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

describe("DesignDiagramContent — expression coordinates (safe evaluator)", () => {
  it("resolves expression-string coords from parameter defaults", () => {
    const spec: DesignDiagramSpec = {
      parameters: [{ name: "a", min: 0, max: 100, default: 50 }],
      elements: [{ type: "svg_circle", id: "c", cx: "a", cy: "a + 10", r: 5 }],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    const circle = container.querySelector('circle[data-design-element="c"]');
    expect(circle?.getAttribute("cx")).toBe("50");
    expect(circle?.getAttribute("cy")).toBe("60");
  });

  it("renders a graph curve as a non-empty path", () => {
    const spec: DesignDiagramSpec = {
      elements: [
        {
          type: "graph",
          id: "g",
          x: 0,
          y: 0,
          width: 300,
          height: 200,
          curves: [{ expression: "sin(x)" }],
        },
      ],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    const paths = Array.from(container.querySelectorAll("path")).filter(
      (p) => (p.getAttribute("d") ?? "").length > 0,
    );
    expect(paths.length).toBeGreaterThan(0);
  });

  it("falls back to 0 for a dangerous/invalid coord (no eval, no throw)", () => {
    const spec: DesignDiagramSpec = {
      elements: [
        // `x = 5` is an assignment — disabled in the sandbox → NaN → fallback 0.
        { type: "svg_circle", id: "bad", cx: "x = 5", cy: 20, r: 5 },
      ],
    };
    const { container } = render(
      <DesignDiagramContent instruction={wrap(spec)} />,
    );
    const circle = container.querySelector('circle[data-design-element="bad"]');
    expect(circle?.getAttribute("cx")).toBe("0");
  });
});

describe("DesignDiagramContent — staged reveal (Workstream B)", () => {
  const twoCircles: DesignDiagramSpec = {
    elements: [
      { type: "svg_circle", id: "a", cx: 100, cy: 100, r: 10 },
      { type: "svg_circle", id: "b", cx: 200, cy: 200, r: 10 },
    ],
  };

  it("no revealedElementIds → no dd-staging, no data-revealed (INV-7)", () => {
    const { container } = render(
      <DesignDiagramContent instruction={wrap(twoCircles)} />,
    );
    expect(
      container.querySelector(".design-diagram-content.dd-staging"),
    ).toBeNull();
    expect(container.querySelector("[data-revealed]")).toBeNull();
  });

  it("a revealed-set adds dd-staging and per-element data-revealed", () => {
    const { container } = render(
      <DesignDiagramContent
        instruction={wrap(twoCircles)}
        revealedElementIds={new Set(["a"])}
      />,
    );
    expect(
      container.querySelector(".design-diagram-content.dd-staging"),
    ).not.toBeNull();
    expect(
      container
        .querySelector('[data-design-element="a"]')
        ?.getAttribute("data-revealed"),
    ).toBe("true");
    expect(
      container
        .querySelector('[data-design-element="b"]')
        ?.getAttribute("data-revealed"),
    ).toBe("false");
  });
});

describe("DesignDiagramContent — teaching-mode gate (Workstream A4)", () => {
  const withParam: DesignDiagramSpec = {
    parameters: [{ name: "a", min: 0, max: 10, default: 5 }],
    elements: [{ type: "svg_circle", id: "c", cx: "a * 10", cy: 50, r: 5 }],
  };

  it("hides sliders by default (lecture/doubt playback)", () => {
    const { container } = render(
      <DesignDiagramContent instruction={wrap(withParam)} />,
    );
    expect(container.querySelector('input[type="range"]')).toBeNull();
    // The geometry still resolves from the parameter default.
    expect(
      container.querySelector('[data-design-element="c"]')?.getAttribute("cx"),
    ).toBe("50");
  });

  it("shows sliders when interactive", () => {
    const { container } = render(
      <DesignDiagramContent instruction={wrap(withParam)} interactive />,
    );
    expect(container.querySelector('input[type="range"]')).not.toBeNull();
  });
});

describe("DesignDiagramContent — narration-driven parameters (Workstream A5)", () => {
  it("paramOverrides win over spec defaults, even without sliders", () => {
    const spec: DesignDiagramSpec = {
      parameters: [{ name: "a", min: 0, max: 100, default: 50 }],
      elements: [{ type: "svg_circle", id: "c", cx: "a", cy: 50, r: 5 }],
    };
    const { container } = render(
      <DesignDiagramContent
        instruction={wrap(spec)}
        paramOverrides={{ a: 80 }}
      />,
    );
    // default is 50; the event-driven override (80) drives the geometry.
    expect(
      container.querySelector('[data-design-element="c"]')?.getAttribute("cx"),
    ).toBe("80");
  });
});
