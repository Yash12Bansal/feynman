import { useEffect } from "react";
import gsap from "gsap";
import type { HighlightWalkInstruction } from "../../types/visuals";
import { useElementRegistry } from "../elements";
import { useSyncManager } from "../useSyncManager";

/**
 * Headless component — renders no DOM.
 *
 * Looks up the parent card via ElementRegistry, queries sub-elements
 * within it (data-node, data-rough-node, data-scene-path, etc.), and
 * registers a walk with SyncManager.
 *
 * Spotlight semantics: only one sub-element highlighted at a time.
 * Auto-cleanup on timeout.
 */
export function HighlightWalkOverlay({
  instruction,
}: {
  instruction: HighlightWalkInstruction;
}) {
  const registry = useElementRegistry();
  const syncManager = useSyncManager();
  const { target_id, steps, term_hints, duration_ms } = instruction;

  useEffect(() => {
    if (!syncManager || !term_hints || steps.length === 0) return;

    // Retry logic: the parent card may not be mounted yet.
    function tryRegister(): (() => void) | null {
      const entry = registry.get(target_id);
      if (!entry) return null;

      const parentEl = entry.ref;
      const walkId = `walk-${target_id}-${Date.now()}`;

      const callbacks = new Map<string, (active: boolean) => void>();

      for (const step of steps) {
        const subEls = findSubElements(parentEl, step.sub_element_id);
        if (subEls.length === 0) {
          console.warn(
            `[HighlightWalkOverlay] Sub-element "${step.sub_element_id}" not found in "${target_id}"`,
          );
          continue;
        }

        const highlightStyle = step.style ?? "glow";
        const color = step.color ?? "";

        callbacks.set(step.sub_element_id, (active: boolean) => {
          for (const el of subEls) {
            if (active) {
              applySubHighlight(el, highlightStyle, color);
            } else {
              removeSubHighlight(el);
            }
          }
        });
      }

      if (callbacks.size === 0) return null;

      const unregister = syncManager.registerWalk(walkId, term_hints, callbacks);

      // Fallback timeout: clean up if speech doesn't trigger all steps.
      const fallbackMs = duration_ms ?? steps.length * 5000;
      const fallbackTimer = window.setTimeout(() => {
        unregister();
      }, fallbackMs);

      return () => {
        unregister();
        clearTimeout(fallbackTimer);
        // Remove all sub-element highlights on cleanup
        for (const step of steps) {
          const subEls = findSubElements(parentEl, step.sub_element_id);
          for (const el of subEls) removeSubHighlight(el);
        }
      };
    }

    // Try immediately, then retry once on next frame if needed.
    let cleanup = tryRegister();
    let rafId: number | undefined;

    if (!cleanup) {
      rafId = requestAnimationFrame(() => {
        cleanup = tryRegister();
        if (!cleanup) {
          console.warn(
            `[HighlightWalkOverlay] Target "${target_id}" not found after retry`,
          );
        }
      });
    }

    return () => {
      if (rafId !== undefined) cancelAnimationFrame(rafId);
      cleanup?.();
    };
  }, [registry, syncManager, target_id, steps, term_hints, duration_ms]);

  return null;
}

// ── Sub-element lookup ──────────────────────────────────────────

/**
 * Find all DOM elements within a parent card that match a sub-element ID.
 *
 * Searches across all known attribute conventions:
 * - Diagram nodes: data-node, data-rough-node, data-node-label
 * - Scene components: data-scene-path (prefix match), data-scene-label (prefix match)
 * - Direct ID match and prefix match
 */
function findSubElements(
  parent: HTMLElement,
  subId: string,
): (SVGElement | HTMLElement)[] {
  const selectors = [
    // Diagram nodes (exact match)
    `[data-node="${subId}"]`,
    `[data-rough-node="${subId}"]`,
    `[data-node-label="${subId}"]`,
    // Scene components (exact match on path/label)
    `[data-scene-path="${subId}"]`,
    `[data-scene-label="${subId}"]`,
    // Scene sub-paths (prefix match: "block" matches "block-body", "block-top", etc.)
    `[data-scene-path^="${subId}-"]`,
    `[data-scene-label^="${subId}-"]`,
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

// ── SVG-aware highlight effects ──────────────────────────────────

const DEFAULT_GLOW_COLOR = "#fbbf24";

function applySubHighlight(
  el: SVGElement | HTMLElement,
  style: string,
  color: string,
): void {
  const glowColor = color || DEFAULT_GLOW_COLOR;
  el.setAttribute("data-walk-highlight", style);

  if (el instanceof SVGElement) {
    gsap.killTweensOf(el);

    // Use inline style for CSS filter — SVG `filter` attribute expects url(),
    // not CSS filter functions like drop-shadow().
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
    // HTML elements: reuse existing data-highlight CSS
    el.setAttribute("data-highlight", style);
    if (color) el.style.setProperty("--highlight-color", color);
  }
}

function removeSubHighlight(el: SVGElement | HTMLElement): void {
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
