/**
 * SlideAnnotationLayer — live-annotation rendering tests.
 *
 * The FOCUS spotlight (dimming overlay) and POINT_AT pointer arrow were
 * removed — they rendered broken (a full-board gray wash and stray blue
 * arrows). Their tests went with them. Coverage now:
 *   1. Overlay svg mounts (with and without annotation lists).
 *   2. TRACE / MARK_POINT / WRITE_MARGIN primitives render.
 *   3. Reduced-motion attribute reflects matchMedia.
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

describe("SlideAnnotationLayer", () => {
  it("mounts the overlay svg with no annotation lists", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([100, 100, 50, 50], { role: "hypotenuse" }) }}
      />,
    );
    expect(container.querySelector(".sb-slide-annotations")).not.toBeNull();
    // No primitives when no lists are passed.
    expect(container.querySelector(".sb-trace")).toBeNull();
    expect(container.querySelector(".sb-mark-point")).toBeNull();
    expect(container.querySelector(".sb-margin-note")).toBeNull();
  });

  it("propagates reduced-motion attribute when the user prefers it", () => {
    setReducedMotion(true);
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
      />,
    );
    const svg = container.querySelector(".sb-slide-annotations");
    expect(svg?.getAttribute("data-reduced-motion")).toBe("true");
  });

  // ── Doc 19 §12: live-annotation primitives ─────────────────────

  it("mounts traces, mark points, and margin notes", () => {
    const dictionary = {
      el_a: meta([100, 100, 80, 60], { role: "thing-a" }),
      el_b: meta([300, 300, 80, 60], { role: "thing-b" }),
    };
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={dictionary}
        traces={[
          { key: 0, elementId: "el_a", durationMs: 1500 },
          { key: 1, elementId: "el_b", durationMs: 1200 },
        ]}
        markPoints={[{ key: 2, x: 50, y: 50, kind: "dot", label: "" }]}
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
    // Two traces — both render (dictionary-bounds fallback when no live DOM).
    expect(container.querySelectorAll(".sb-trace").length).toBe(2);
    expect(container.querySelector(".sb-mark-point")).not.toBeNull();
    expect(container.querySelector(".sb-margin-note")).not.toBeNull();
  });

  it("renders nothing extra when all primitive lists are empty", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
        traces={[]}
        markPoints={[]}
        marginNotes={[]}
      />,
    );
    expect(container.querySelector(".sb-slide-annotations")).not.toBeNull();
    expect(container.querySelector(".sb-trace")).toBeNull();
    expect(container.querySelector(".sb-mark-point")).toBeNull();
    expect(container.querySelector(".sb-margin-note")).toBeNull();
  });

  it("accepts undefined list props (no events yet)", () => {
    const { container } = render(
      <SlideAnnotationLayer
        viewBox={VIEW_BOX}
        dictionary={{ el_a: meta([10, 10, 10, 10]) }}
      />,
    );
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
