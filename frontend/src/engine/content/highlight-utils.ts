/**
 * Shared SVG-aware highlight effects for sub-elements within diagram cards.
 *
 * Used by both HighlightOverlay (direct highlights) and HighlightWalkOverlay
 * (speech-synced highlights).
 */

import gsap from "gsap";

const DEFAULT_GLOW_COLOR = "#fbbf24";

/**
 * Find all DOM elements within a parent card that match a sub-element ID.
 *
 * Searches across all known attribute conventions:
 * - Diagram nodes: data-node, data-rough-node, data-node-label
 * - Scene components: data-scene-path, data-scene-label (exact + prefix)
 * - Design diagram elements: data-design-element (exact + prefix)
 */
export function findSubElements(
  parent: HTMLElement,
  subId: string,
): (SVGElement | HTMLElement)[] {
  const selectors = [
    `[data-node="${subId}"]`,
    `[data-rough-node="${subId}"]`,
    `[data-node-label="${subId}"]`,
    `[data-scene-path="${subId}"]`,
    `[data-scene-label="${subId}"]`,
    `[data-scene-path^="${subId}-"]`,
    `[data-scene-label^="${subId}-"]`,
    `[data-design-element="${subId}"]`,
    `[data-design-element^="${subId}-"]`,
  ];

  const results: (SVGElement | HTMLElement)[] = [];
  const seen = new Set<Node>();

  for (const sel of selectors) {
    const els = parent.querySelectorAll<SVGElement | HTMLElement>(sel);
    for (const el of els) {
      if (!seen.has(el)) {
        seen.add(el);
        results.push(el);
      }
    }
  }

  return results;
}

/** Apply a glow/pulse highlight effect to an SVG or HTML element. */
export function applySubHighlight(
  el: SVGElement | HTMLElement,
  style: string,
  color: string,
): void {
  const glowColor = color || DEFAULT_GLOW_COLOR;
  el.setAttribute("data-walk-highlight", style);

  if (el instanceof SVGElement) {
    gsap.killTweensOf(el);

    switch (style) {
      case "pulse":
        el.style.filter = `drop-shadow(0 0 6px ${glowColor})`;
        gsap.to(el, {
          scale: 1.06,
          transformOrigin: "center center",
          duration: 0.4,
          ease: "power2.inOut",
          yoyo: true,
          repeat: -1,
        });
        break;
      case "glow":
      default:
        gsap.fromTo(
          el,
          { css: { filter: "drop-shadow(0 0 0px transparent)" } },
          {
            css: {
              filter: `drop-shadow(0 0 8px ${glowColor}) drop-shadow(0 0 16px ${glowColor})`,
            },
            duration: 0.3,
            ease: "power2.out",
          },
        );
        break;
    }
  } else {
    el.setAttribute("data-highlight", style);
    if (color) el.style.setProperty("--highlight-color", color);
  }
}

/** Remove highlight effect from an SVG or HTML element. */
export function removeSubHighlight(el: SVGElement | HTMLElement): void {
  el.removeAttribute("data-walk-highlight");

  if (el instanceof SVGElement) {
    gsap.killTweensOf(el);
    gsap.to(el, {
      css: { filter: "none" },
      scale: 1,
      duration: 0.25,
      ease: "power2.in",
      onComplete: () => {
        el.style.removeProperty("filter");
        el.style.removeProperty("transform");
      },
    });
  } else {
    el.removeAttribute("data-highlight");
    el.style.removeProperty("--highlight-color");
  }
}
