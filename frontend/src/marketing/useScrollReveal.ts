import { useEffect } from "react";
import type { RefObject } from "react";

/**
 * Drives the landing page's "the board draws itself as you scroll" effect.
 *
 * One IntersectionObserver, rooted on the marketing scroll container (the page
 * is an inner scroller — #root is `overflow:hidden` — so the viewport is NOT
 * the right root). When a `.reveal` block scrolls into view we:
 *   1. add `.is-visible` (CSS fades/slides it in, fires highlighter + wipe), and
 *   2. animate every `.pen` stroke inside it from "fully dashed/hidden" to
 *      drawn, with a stagger so strokes appear in pen order.
 *
 * Pen strokes are prepared up-front: we measure each path's length and set
 * `stroke-dasharray` + `stroke-dashoffset` to it (inline, so it survives before
 * the observer fires). Drawing = setting `stroke-dashoffset: 0`, which the CSS
 * `transition` on `.pen` animates. Per-stroke timing comes from `data-draw`
 * (ms delay) with a sensible index-based fallback.
 *
 * Honors `prefers-reduced-motion`: snaps everything to its final state.
 */
export function useScrollReveal(containerRef: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    const pens = Array.from(
      root.querySelectorAll<SVGGeometryElement>(".pen"),
    );
    // Prime every stroke to its hidden (fully-dashed) state.
    for (const pen of pens) {
      const len = typeof pen.getTotalLength === "function" ? pen.getTotalLength() : 0;
      pen.style.strokeDasharray = `${len}`;
      pen.style.strokeDashoffset = `${len}`;
    }

    const drawPen = (pen: SVGGeometryElement, fallbackDelay: number) => {
      const delay = Number(pen.dataset.draw ?? fallbackDelay);
      window.setTimeout(() => {
        pen.style.strokeDashoffset = "0";
      }, delay);
    };

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const blocks = Array.from(root.querySelectorAll<HTMLElement>(".reveal"));

    if (reduce) {
      for (const el of blocks) el.classList.add("is-visible");
      for (const pen of pens) {
        pen.style.transition = "none";
        pen.style.strokeDashoffset = "0";
      }
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const el = entry.target as HTMLElement;
          el.classList.add("is-visible");
          const innerPens = Array.from(
            el.querySelectorAll<SVGGeometryElement>(".pen"),
          );
          innerPens.forEach((pen, i) => drawPen(pen, i * 140));
          observer.unobserve(el);
        }
      },
      { root, threshold: 0.22, rootMargin: "0px 0px -7% 0px" },
    );

    for (const el of blocks) observer.observe(el);
    return () => observer.disconnect();
  }, [containerRef]);
}

/**
 * Toggles `.is-stuck` on the sticky nav once the page has scrolled a little, so
 * the nav gains its hairline border + stronger backdrop only when it's actually
 * floating over content.
 */
export function useStuckNav(
  containerRef: RefObject<HTMLElement | null>,
  navRef: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    const root = containerRef.current;
    const nav = navRef.current;
    if (!root || !nav) return;
    const onScroll = () => {
      nav.classList.toggle("is-stuck", root.scrollTop > 12);
    };
    onScroll();
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, [containerRef, navRef]);
}
