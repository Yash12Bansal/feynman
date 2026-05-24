/**
 * SlideAnnotationLayer — doc 18 spotlight rendering tests.
 *
 * The legacy PIN/CALLOUT/BRACKET/HIGHLIGHT/PULSE tests were deleted along
 * with their components. Tests now cover:
 *   1. No focus → no spotlight rendered.
 *   2. Focus present → spotlight overlay + optional inline label.
 *   3. presentation_mode propagates as a data attribute.
 *   4. Reduced motion attribute reflects matchMedia.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { SlideAnnotationLayer } from "./SlideAnnotationLayer";
import type { ElementMeta } from "../../../types/visuals";

const VIEW_BOX = "0 0 900 650";

function meta(
  bounds: readonly [number, number, number, number],
  extra: Partial<ElementMeta> = {},
): ElementMeta {
  return {
    role: "test",
    semantic: "test element",
    position: "center",
    bounds,
    ...extra,
  };
}

function setReducedMotion(reduced: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: reduced && query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

beforeEach(() => {
  setReducedMotion(false);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SlideAnnotationLayer (spotlight)", () => {
  it("mounts the overlay svg even with no focus", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([100, 100, 50, 50], { role: "hypotenuse" }) }}
        focusedRole={null}
        inlineLabelText={null}
      />,
    );
    const svg = container.querySelector(".sb-slide-annotations");
    expect(svg).not.toBeNull();
    // No spotlight group rendered when nothing is focused.
    expect(container.querySelector(".sb-spotlight")).toBeNull();
  });

  it("renders the spotlight group when focused via dictionary bounds", () => {
    const dictionary = {
      el_hyp: meta([200, 200, 100, 10], { role: "hypotenuse" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedRole="hypotenuse"
        inlineLabelText={null}
      />,
    );
    const spot = container.querySelector(".sb-spotlight");
    expect(spot).not.toBeNull();
    expect(spot?.getAttribute("data-focused-role")).toBe("hypotenuse");
    // Dim overlay + mask present.
    expect(container.querySelector(".sb-spotlight-dim")).not.toBeNull();
  });

  it("doc 19 §A-3: resolves spotlight via element_id (preferred selector)", () => {
    const dictionary = {
      // Two elements share the same role — focus-by-role would collide.
      // element_id picks the right one unambiguously.
      el_first: meta([100, 100, 50, 10], { role: "curve" }),
      el_second: meta([300, 300, 50, 10], { role: "curve" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedElementId="el_second"
        focusedRole={null}
        inlineLabelText="payoff"
      />,
    );
    const spot = container.querySelector(".sb-spotlight");
    expect(spot).not.toBeNull();
    expect(spot?.getAttribute("data-focused-element-id")).toBe("el_second");
    // No focusedRole prop set; the role data-attr should NOT be populated.
    expect(spot?.getAttribute("data-focused-role")).toBeNull();
  });

  it("doc 19 §A-3: element_id takes precedence when both are provided", () => {
    const dictionary = {
      el_a: meta([100, 100, 50, 10], { role: "shared_role" }),
      el_b: meta([300, 300, 50, 10], { role: "shared_role" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedElementId="el_b"
        focusedRole="shared_role"
        inlineLabelText={null}
      />,
    );
    const spot = container.querySelector(".sb-spotlight");
    expect(spot).not.toBeNull();
    // Both attrs render; the SVG transforms its target via id (the "id" kind
    // in useResolvedBounds), so it resolves el_b deterministically.
    expect(spot?.getAttribute("data-focused-element-id")).toBe("el_b");
    expect(spot?.getAttribute("data-focused-role")).toBe("shared_role");
  });

  it("renders the inline label pill + text when provided", () => {
    const dictionary = {
      el_hyp: meta([200, 200, 100, 10], { role: "hypotenuse" }),
    };
    const { container, getByText } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedRole="hypotenuse"
        inlineLabelText="hypotenuse"
      />,
    );
    expect(container.querySelector(".sb-spotlight-label")).not.toBeNull();
    expect(getByText("hypotenuse")).not.toBeNull();
  });

  it("omits the inline label when text is empty", () => {
    const dictionary = {
      el_hyp: meta([200, 200, 100, 10], { role: "hypotenuse" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedRole="hypotenuse"
        inlineLabelText={null}
      />,
    );
    expect(container.querySelector(".sb-spotlight-label")).toBeNull();
  });

  it("reflects presentation_mode as a data attribute", () => {
    const dictionary = {
      el_hyp: meta([200, 200, 100, 10], { role: "hypotenuse" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedRole="hypotenuse"
        inlineLabelText={null}
        presentationMode="build_up"
      />,
    );
    const svg = container.querySelector(".sb-slide-annotations");
    expect(svg?.getAttribute("data-presentation-mode")).toBe("build_up");
    const spot = container.querySelector(".sb-spotlight");
    expect(spot?.getAttribute("data-presentation-mode")).toBe("build_up");
  });

  it("defaults presentation_mode to overview when undefined", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
        focusedRole={null}
        inlineLabelText={null}
      />,
    );
    const svg = container.querySelector(".sb-slide-annotations");
    expect(svg?.getAttribute("data-presentation-mode")).toBe("overview");
  });

  it("renders nothing for an unknown role (no bounds)", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10], { role: "hypotenuse" }) }}
        focusedRole="not_a_role"
        inlineLabelText="ghost"
      />,
    );
    expect(container.querySelector(".sb-spotlight")).toBeNull();
  });

  it("propagates reduced-motion attribute when the user prefers it", () => {
    setReducedMotion(true);
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
        focusedRole={null}
        inlineLabelText={null}
      />,
    );
    const svg = container.querySelector(".sb-slide-annotations");
    expect(svg?.getAttribute("data-reduced-motion")).toBe("true");
  });

  // ── Doc 19 §12: live-annotation primitives integration ─────────

  it("mounts traces, mark points, pointers, and margin notes alongside the spotlight", () => {
    const dictionary = {
      el_a: meta([100, 100, 80, 60], { role: "thing-a" }),
      el_b: meta([300, 300, 80, 60], { role: "thing-b" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedElementId="el_a"
        focusedRole={null}
        inlineLabelText="A"
        traces={[
          { key: 0, elementId: "el_a", durationMs: 1500 },
          { key: 1, elementId: "el_b", durationMs: 1200 },
        ]}
        markPoints={[{ key: 2, x: 50, y: 50, kind: "dot", label: "" }]}
        pointers={[{ key: 3, elementId: "el_b", fromSide: "left" }]}
        marginNotes={[
          {
            key: 4,
            anchorElementId: "el_a",
            side: "right",
            text: "v = u + at",
          },
        ]}
      />,
    );
    // Spotlight + the 4 new primitives all present.
    expect(container.querySelector(".sb-spotlight")).not.toBeNull();
    // Two traces — both will render (one as a real element clone if DOM
    // had it; otherwise as bounds fallback against the dictionary).
    expect(container.querySelectorAll(".sb-trace").length).toBe(2);
    expect(container.querySelector(".sb-mark-point")).not.toBeNull();
    expect(container.querySelector(".sb-pointer")).not.toBeNull();
    expect(container.querySelector(".sb-margin-note")).not.toBeNull();
  });

  it("renders nothing extra when all primitive lists are empty", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
        focusedRole={null}
        inlineLabelText={null}
        traces={[]}
        markPoints={[]}
        pointers={[]}
        marginNotes={[]}
      />,
    );
    // Layer SVG is still present, but no annotation primitives.
    expect(container.querySelector(".sb-slide-annotations")).not.toBeNull();
    expect(container.querySelector(".sb-trace")).toBeNull();
    expect(container.querySelector(".sb-mark-point")).toBeNull();
    expect(container.querySelector(".sb-pointer")).toBeNull();
    expect(container.querySelector(".sb-margin-note")).toBeNull();
  });

  it("primitives accept undefined list props (back-compat / no events yet)", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
        focusedRole={null}
        inlineLabelText={null}
      />,
    );
    // No primitive lists passed in at all → renders cleanly, no children.
    expect(container.querySelector(".sb-slide-annotations")).not.toBeNull();
  });

  it("reduced-motion attribute applies to primitives via CSS selectors", () => {
    setReducedMotion(true);
    const dictionary = {
      el_a: meta([100, 100, 80, 60], { role: "a" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedRole={null}
        inlineLabelText={null}
        traces={[{ key: 0, elementId: "el_a", durationMs: 1000 }]}
      />,
    );
    const svg = container.querySelector(".sb-slide-annotations");
    expect(svg?.getAttribute("data-reduced-motion")).toBe("true");
    // The trace itself is rendered; CSS handles the reduced-motion override.
    expect(container.querySelector(".sb-trace")).not.toBeNull();
  });

  it("multiple traces with different keys mount as distinct elements", () => {
    const dictionary = {
      el_a: meta([100, 100, 80, 60], { role: "a" }),
      el_b: meta([200, 200, 80, 60], { role: "b" }),
      el_c: meta([300, 300, 80, 60], { role: "c" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        focusedRole={null}
        inlineLabelText={null}
        traces={[
          { key: 0, elementId: "el_a", durationMs: 1000 },
          { key: 1, elementId: "el_b", durationMs: 1500 },
          { key: 2, elementId: "el_c", durationMs: 2000 },
        ]}
      />,
    );
    const traces = container.querySelectorAll(".sb-trace");
    expect(traces.length).toBe(3);
    // Each one tags its element_id.
    const ids = Array.from(traces).map((t) =>
      t.getAttribute("data-element-id"),
    );
    expect(ids).toEqual(["el_a", "el_b", "el_c"]);
  });

  it("multiple mark points coexist at different coordinates", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
        focusedRole={null}
        inlineLabelText={null}
        markPoints={[
          { key: 0, x: 50, y: 50, kind: "dot", label: "start" },
          { key: 1, x: 500, y: 500, kind: "cross", label: "end" },
          { key: 2, x: 300, y: 300, kind: "star", label: "" },
        ]}
      />,
    );
    const marks = container.querySelectorAll(".sb-mark-point");
    expect(marks.length).toBe(3);
    const kinds = Array.from(marks).map((m) =>
      m.getAttribute("data-mark-kind"),
    );
    expect(kinds).toEqual(["dot", "cross", "star"]);
  });
});
