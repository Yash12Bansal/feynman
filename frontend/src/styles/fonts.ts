/**
 * Shared font stacks for the app UI ("Premium Deep-Space Glass" redesign).
 *
 * DISPLAY_FONT — geometric display face for wordmarks, screen titles, and HUD
 * labels (loaded in index.html). MONO_FONT — technical micro-labels.
 *
 * IMPORTANT: these are for the app chrome / login ONLY. The teaching board
 * (SplitBoard.css) renders in its own "Inter"/system fallback on purpose — do
 * NOT apply these there, and do NOT load Inter/JetBrains Mono/Crimson Pro in
 * index.html, or the board would re-flow already-paginated lectures.
 */

export const DISPLAY_FONT =
  "'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

export const MONO_FONT = "'JetBrains Mono', 'SF Mono', ui-monospace, monospace";
