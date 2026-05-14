/**
 * SlideAnnotationLayer — visual rendering tests.
 *
 * Two paths exercised:
 *   1. Dictionary-bounds fallback (no `stageRef` → mathematical assertions
 *      against fixture bounds, no DOM measurement required).
 *   2. Live-DOM resolution (`stageRef` provided + mocked
 *      `getBoundingClientRect`/`getScreenCTM`) — the Phase 1 happy path.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRef } from "react";
import { render } from "@testing-library/react";
import { SlideAnnotationLayer } from "./SlideAnnotationLayer";
import type {
  AnnotationInstruction,
  AnnotationTarget,
  BracketInstruction,
  DrawCalloutInstruction,
  ElementMeta,
  HighlightPulseInstruction,
  PinLabelInstruction,
} from "../../../types/visuals";

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

function renderLayer(
  annotations: readonly AnnotationInstruction[],
  dictionary: Record<string, ElementMeta>,
) {
  return render(
    <SlideAnnotationLayer
      viewBox={VIEW_BOX}
      dictionary={dictionary}
      annotations={annotations}
    />,
  );
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
  it("renders nothing when there are no annotations", () => {
    const { container } = renderLayer([], {});
    expect(container.querySelector(".sb-slide-annotations")).toBeNull();
  });

  it("pin_label renders text above the target bounds with a connector", () => {
    const dictionary: Record<string, ElementMeta> = {
      side_AB: meta([120, 100, 280, 360], { role: "hypotenuse" }),
    };
    const instr: PinLabelInstruction = {
      type: "pin_label",
      target_element_id: "side_AB",
      text: "8m",
      position: "above",
    };
    const { container } = renderLayer([instr], dictionary);

    const pinGroup = container.querySelector(
      '[data-annotation-type="pin_label"]',
    );
    expect(pinGroup).not.toBeNull();
    expect(pinGroup?.getAttribute("data-target-element-id")).toBe("side_AB");

    const text = pinGroup?.querySelector(".sb-annot-pin-text");
    expect(text?.textContent).toBe("8m");
    // Centered horizontally over the bounds: x = 120 + 280/2 = 260.
    expect(text?.getAttribute("x")).toBe("260");
    expect(text?.getAttribute("text-anchor")).toBe("middle");
    // Above the bounds → text y is less than the top edge (y = 100).
    const textY = parseFloat(text?.getAttribute("y") ?? "0");
    expect(textY).toBeLessThan(100);

    // Connector line drops from text down to the top of the bounds.
    const line = pinGroup?.querySelector(".sb-annot-pin-connector");
    expect(line).not.toBeNull();
    expect(line?.getAttribute("x2")).toBe("260");
    expect(line?.getAttribute("y2")).toBe("100");
  });

  it("draw_callout direction places the bubble in the requested quadrant", () => {
    const dictionary: Record<string, ElementMeta> = {
      target: meta([200, 200, 60, 60]),
    };
    const instr: DrawCalloutInstruction = {
      type: "draw_callout",
      target_element_id: "target",
      text: "key insight here!",
      direction: "up-right",
    };
    const { container } = renderLayer([instr], dictionary);

    const calloutGroup = container.querySelector(
      '[data-annotation-type="draw_callout"]',
    );
    expect(calloutGroup).not.toBeNull();

    const bubble = calloutGroup?.querySelector(".sb-annot-callout-bubble");
    const bubbleX = parseFloat(bubble?.getAttribute("x") ?? "0");
    const bubbleY = parseFloat(bubble?.getAttribute("y") ?? "Infinity");
    // up-right → bubble sits to the right of the bounds (x > 260) and above
    // the top edge (y < 200, accounting for bubble height).
    expect(bubbleX).toBeGreaterThanOrEqual(260);
    expect(bubbleY).toBeLessThan(200);

    const tail = calloutGroup?.querySelector(".sb-annot-callout-tail");
    expect(tail).not.toBeNull();
    // Tail path points back to the target's center (230, 230).
    expect(tail?.getAttribute("d")).toContain("L 230 230");

    const text = calloutGroup?.querySelector(".sb-annot-callout-text");
    expect(text?.textContent).toContain("key");
  });

  it("bracket spans both element bounds with a centered label", () => {
    const dictionary: Record<string, ElementMeta> = {
      a: meta([0, 100, 50, 50]),
      b: meta([200, 100, 50, 50]),
    };
    const instr: BracketInstruction = {
      type: "bracket",
      element_a_id: "a",
      element_b_id: "b",
      label: "right triangle",
      side: "above",
    };
    const { container } = renderLayer([instr], dictionary);

    const bracketGroup = container.querySelector(
      '[data-annotation-type="bracket"]',
    );
    expect(bracketGroup).not.toBeNull();
    expect(bracketGroup?.getAttribute("data-side")).toBe("above");

    const path = bracketGroup?.querySelector(".sb-annot-bracket-path");
    const d = path?.getAttribute("d") ?? "";
    // Spans from minX=0 to maxX=250 across both bounds.
    expect(d).toContain("M 0 ");
    expect(d).toContain(" 250 ");

    const label = bracketGroup?.querySelector(".sb-annot-bracket-label");
    expect(label?.textContent).toBe("right triangle");
    // Label centered: x = (0 + 250) / 2 = 125.
    expect(label?.getAttribute("x")).toBe("125");
    expect(label?.getAttribute("text-anchor")).toBe("middle");
  });

  it("highlight_pulse draws a glow rect over bounds with duration + color custom props", () => {
    const dictionary: Record<string, ElementMeta> = {
      apex: meta([100, 100, 80, 80]),
    };
    const instr: HighlightPulseInstruction = {
      type: "highlight_pulse",
      target_element_id: "apex",
      duration_ms: 2000,
      color_token: "--my-color",
    };
    const { container } = renderLayer([instr], dictionary);

    const pulseRect = container.querySelector(
      '[data-annotation-type="highlight_pulse"]',
    );
    expect(pulseRect).not.toBeNull();
    expect(pulseRect?.classList.contains("sb-annot-pulse")).toBe(true);
    expect(pulseRect?.getAttribute("data-target-element-id")).toBe("apex");

    const style = pulseRect?.getAttribute("style") ?? "";
    expect(style).toContain("--sb-pulse-duration: 2000ms");
    expect(style).toContain("--sb-pulse-color: var(--my-color)");

    // Padded rect over bounds: x ≈ 100 - PULSE_PAD, w ≈ 80 + 2*PULSE_PAD.
    const x = parseFloat(pulseRect?.getAttribute("x") ?? "0");
    const w = parseFloat(pulseRect?.getAttribute("width") ?? "0");
    expect(x).toBeLessThan(100);
    expect(w).toBeGreaterThan(80);
  });

  it("prefers-reduced-motion sets data-reduced-motion on the layer", () => {
    setReducedMotion(true);
    const dictionary: Record<string, ElementMeta> = {
      apex: meta([100, 100, 80, 80]),
    };
    const instr: HighlightPulseInstruction = {
      type: "highlight_pulse",
      target_element_id: "apex",
    };
    const { container } = renderLayer([instr], dictionary);

    const layer = container.querySelector(".sb-slide-annotations");
    expect(layer?.getAttribute("data-reduced-motion")).toBe("true");
  });

  it("falls through silently when bounds are missing for a target", () => {
    const dictionary: Record<string, ElementMeta> = {
      // No bounds on this entry — overlay should skip rendering.
      ghost: { role: "x", semantic: "x", position: "center" },
    };
    const instr: PinLabelInstruction = {
      type: "pin_label",
      target_element_id: "ghost",
      text: "should not render",
    };
    const { container } = renderLayer([instr], dictionary);

    // Layer renders (annotations array is non-empty), but no pin group inside.
    const layer = container.querySelector(".sb-slide-annotations");
    expect(layer).not.toBeNull();
    expect(
      layer?.querySelector('[data-annotation-type="pin_label"]'),
    ).toBeNull();
  });
});

// ── Phase 1: multi-kind targets + live-DOM resolution ─────────

describe("SlideAnnotationLayer — multi-kind targets", () => {
  it("legacy target_element_id is treated as kind=id and stamps data-target-kind", () => {
    const dictionary: Record<string, ElementMeta> = {
      side_AB: meta([10, 20, 100, 50], { role: "hypotenuse" }),
    };
    const instr: PinLabelInstruction = {
      type: "pin_label",
      target_element_id: "side_AB",
      text: "10m",
    };
    const { container } = renderLayer([instr], dictionary);
    const pin = container.querySelector('[data-annotation-type="pin_label"]');
    expect(pin?.getAttribute("data-target-kind")).toBe("id");
  });

  it("resolves a role-kind target via the dictionary when DOM lookup misses", () => {
    const dictionary: Record<string, ElementMeta> = {
      side_AB: meta([10, 20, 100, 50], { role: "hypotenuse" }),
    };
    const target: AnnotationTarget = { kind: "role", value: "hypotenuse" };
    const instr: PinLabelInstruction = {
      type: "pin_label",
      target_element_id: "side_AB",
      target,
      text: "10m",
    };
    const { container } = renderLayer([instr], dictionary);
    const pin = container.querySelector('[data-annotation-type="pin_label"]');
    expect(pin).not.toBeNull();
    expect(pin?.getAttribute("data-target-kind")).toBe("role");
    // Falls back to dictionary bounds since no stageRef in this render —
    // position math centers over x=10, w=100 → text x = 60.
    const text = pin?.querySelector(".sb-annot-pin-text");
    expect(text?.getAttribute("x")).toBe("60");
  });

  it("drops the annotation when neither DOM nor dictionary can locate the target", () => {
    const target: AnnotationTarget = {
      kind: "color",
      value: "#ff0000",
    };
    const instr: PinLabelInstruction = {
      type: "pin_label",
      target_element_id: "irrelevant",
      target,
      text: "red line",
    };
    const { container } = renderLayer([instr], {});
    // Layer mounts but nothing inside — no DOM scope to query, no
    // dictionary entry matches.
    expect(
      container.querySelector('[data-annotation-type="pin_label"]'),
    ).toBeNull();
  });
});

describe("SlideAnnotationLayer — live-DOM resolution", () => {
  /**
   * Live-DOM resolution test harness. JSDOM's `getBoundingClientRect`
   * and `SVGSVGElement.getScreenCTM` return degenerate values, so we
   * stub them with a known mapping to assert the conversion path:
   *
   *   screen (200, 100, 50, 30) × identity-CTM = viewBox (200, 100, 50, 30)
   *
   * The point of the test is to confirm: (a) the layer queries the
   * stage subtree for `[data-design-element]`, (b) it converts client
   * rects through `getScreenCTM().inverse()`, (c) the result feeds the
   * annotation positioning math.
   */
  function HarnessWithStage({
    annotations,
    dictionary,
  }: {
    annotations: readonly AnnotationInstruction[];
    dictionary: Record<string, ElementMeta>;
  }) {
    const stageRef = useRef<HTMLDivElement>(null);
    return (
      <div ref={stageRef}>
        {/* Simulated rendered diagram: just the data-design-element nodes. */}
        <svg viewBox={VIEW_BOX} data-testid="diagram-svg">
          <rect
            data-design-element="side_AB"
            x={0}
            y={0}
            width={1}
            height={1}
          />
        </svg>
        <SlideAnnotationLayer
          viewBox={VIEW_BOX}
          dictionary={dictionary}
          annotations={annotations}
          stageRef={stageRef}
        />
      </div>
    );
  }

  function stubLiveBounds(rect: {
    x: number;
    y: number;
    width: number;
    height: number;
  }) {
    // Stub the target element's screen rect.
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(
      function (this: Element) {
        if (this.getAttribute("data-design-element") === "side_AB") {
          return {
            x: rect.x,
            y: rect.y,
            left: rect.x,
            top: rect.y,
            right: rect.x + rect.width,
            bottom: rect.y + rect.height,
            width: rect.width,
            height: rect.height,
            toJSON() {
              return this;
            },
          } as DOMRect;
        }
        return new DOMRect(0, 0, 0, 0);
      },
    );

    // JSDOM lacks SVGGraphicsElement.getScreenCTM / SVGSVGElement.createSVGPoint.
    // Install them directly on the prototype with identity-CTM stubs so the
    // screen → viewBox conversion is a pass-through in tests.
    const identity = {
      a: 1,
      b: 0,
      c: 0,
      d: 1,
      e: 0,
      f: 0,
      inverse() {
        return identity;
      },
    };
    // @ts-expect-error — patching missing JSDOM members
    SVGGraphicsElement.prototype.getScreenCTM = function () {
      return identity as unknown as DOMMatrix;
    };
    // @ts-expect-error — patching missing JSDOM members
    SVGSVGElement.prototype.createSVGPoint = function () {
      const pt = {
        x: 0,
        y: 0,
        matrixTransform() {
          return { x: pt.x, y: pt.y } as DOMPoint;
        },
      };
      return pt as unknown as DOMPoint;
    };
  }

  it("uses live getBoundingClientRect via screenCTM when stageRef finds the element", async () => {
    stubLiveBounds({ x: 200, y: 100, width: 50, height: 30 });
    const dictionary: Record<string, ElementMeta> = {
      // Stale dictionary bounds — should be ignored when live DOM resolves.
      side_AB: meta([0, 0, 1, 1], { role: "hypotenuse" }),
    };
    const instr: PinLabelInstruction = {
      type: "pin_label",
      target_element_id: "side_AB",
      text: "10m",
      position: "below",
    };

    const { container, findByTestId } = render(
      <HarnessWithStage annotations={[instr]} dictionary={dictionary} />,
    );
    await findByTestId("diagram-svg");

    // Wait one effect cycle so `useResolvedBounds` runs.
    await new Promise((r) => setTimeout(r, 0));

    const text = container.querySelector(".sb-annot-pin-text");
    // Live bounds: x=200, y=100, w=50, h=30 → text centered at x=225.
    expect(text?.getAttribute("x")).toBe("225");
  });
});
