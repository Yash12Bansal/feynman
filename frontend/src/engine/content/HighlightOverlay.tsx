import { useEffect } from "react";
import type { HighlightInstruction } from "../../types/visuals";
import { useElementRegistry } from "../elements";
import {
  findSubElements,
  applySubHighlight,
  removeSubHighlight,
} from "./highlight-utils";

/**
 * Headless component — renders no DOM.
 *
 * Two modes:
 * 1. Card-level highlight (no sub_element_ids): applies CSS data-highlight
 *    to the target card. Original behavior.
 * 2. Sub-element highlight (sub_element_ids set): finds SVG elements within
 *    the target card and applies GSAP glow/pulse effects. Used for design
 *    diagram parts — like a teacher's laser pointer.
 */
export function HighlightOverlay({
  instruction,
}: {
  instruction: HighlightInstruction;
}) {
  const registry = useElementRegistry();
  const {
    target_id,
    style = "glow",
    color,
    duration_ms = 2000,
    sub_element_ids,
  } = instruction;

  const hasSubElements = sub_element_ids && sub_element_ids.length > 0;

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;

    // ── Sub-element mode (design diagram parts) ──
    if (hasSubElements) {
      let highlightedEls: (SVGElement | HTMLElement)[] = [];

      function applyToSubElements(parentEl: HTMLElement) {
        // Clear any previous sub-highlights on this parent
        const prevHighlighted = parentEl.querySelectorAll<
          SVGElement | HTMLElement
        >("[data-walk-highlight]");
        for (const el of prevHighlighted) {
          removeSubHighlight(el);
        }

        for (const subId of sub_element_ids!) {
          const subEls = findSubElements(parentEl, subId);
          for (const el of subEls) {
            applySubHighlight(el, style, color ?? "");
            highlightedEls.push(el);
          }
        }

        timer = setTimeout(() => {
          for (const el of highlightedEls) removeSubHighlight(el);
          highlightedEls = [];
        }, duration_ms);
      }

      const entry = registry.get(target_id);
      if (entry) {
        applyToSubElements(entry.ref);
      } else {
        requestAnimationFrame(() => {
          const retryEntry = registry.get(target_id);
          if (retryEntry) applyToSubElements(retryEntry.ref);
        });
      }

      return () => {
        if (timer) clearTimeout(timer);
        for (const el of highlightedEls) removeSubHighlight(el);
      };
    }

    // ── Card-level mode (original behavior) ──
    let highlightedEl: HTMLDivElement | undefined;

    function applyHighlight(el: HTMLDivElement) {
      highlightedEl = el;
      if (color) {
        el.style.setProperty("--highlight-color", color);
      }
      el.setAttribute("data-highlight", style);

      timer = setTimeout(() => {
        removeCardHighlight();
      }, duration_ms);
    }

    function removeCardHighlight() {
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
      removeCardHighlight();
    };
  }, [registry, target_id, style, color, duration_ms, hasSubElements, sub_element_ids]);

  return null;
}
