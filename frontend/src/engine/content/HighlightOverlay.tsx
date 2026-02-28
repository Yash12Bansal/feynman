import { useEffect } from "react";
import type { HighlightInstruction } from "../../types/visuals";
import { useElementRegistry } from "../elements";

/**
 * Headless component — renders no DOM.
 *
 * Looks up the target element in the registry, applies a CSS highlight
 * class (data-highlight attribute), and auto-removes after duration_ms.
 */
export function HighlightOverlay({
  instruction,
}: {
  instruction: HighlightInstruction;
}) {
  const registry = useElementRegistry();
  const { target_id, style = "glow", color, duration_ms = 2000 } = instruction;

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let highlightedEl: HTMLDivElement | undefined;

    function applyHighlight(el: HTMLDivElement) {
      highlightedEl = el;
      if (color) {
        el.style.setProperty("--highlight-color", color);
      }
      el.setAttribute("data-highlight", style);

      timer = setTimeout(() => {
        removeHighlight();
      }, duration_ms);
    }

    function removeHighlight() {
      if (!highlightedEl) return;
      highlightedEl.removeAttribute("data-highlight");
      if (color) {
        highlightedEl.style.removeProperty("--highlight-color");
      }
      highlightedEl = undefined;
    }

    const entry = registry.get(target_id);
    if (entry) {
      applyHighlight(entry.ref);
    } else {
      // Target may not be mounted yet — retry once on next frame
      requestAnimationFrame(() => {
        const retryEntry = registry.get(target_id);
        if (!retryEntry) {
          console.warn(`[HighlightOverlay] Target "${target_id}" not found`);
          return;
        }
        applyHighlight(retryEntry.ref);
      });
    }

    return () => {
      if (timer) clearTimeout(timer);
      removeHighlight();
    };
  }, [registry, target_id, style, color, duration_ms]);

  return null;
}
