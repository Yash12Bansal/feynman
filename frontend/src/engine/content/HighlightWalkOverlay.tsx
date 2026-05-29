// TODO(DEADCODE): file unused in active pipelines (lecture-playback / ask-feynman) — interactive live-agent rendering (parked). See docs/engineering/13-redundant-code-audit.md Group 1/2. Safe to delete.
// import { useEffect } from "react";
// import type { HighlightWalkInstruction } from "../../types/visuals";
// import { useElementRegistry } from "../elements";
// import { useSyncManager } from "../useSyncManager";
// import {
//   findSubElements,
//   applySubHighlight,
//   removeSubHighlight,
// } from "./highlight-utils";

// /**
//  * Headless component — renders no DOM.
//  *
//  * Two modes:
//  * 1. **Design diagrams** (target has data-design-element children):
//  *    Immediate sequential highlighting — steps fire on a timer without
//  *    waiting for speech. More reliable than speech sync.
//  * 2. **Other diagrams** (rough diagrams, scenes):
//  *    Speech-synced via SyncManager — steps fire when trigger words are spoken.
//  *
//  * Spotlight semantics: only one sub-element highlighted at a time.
//  * Auto-cleanup on timeout.
//  */
// export function HighlightWalkOverlay({
//   instruction,
// }: {
//   instruction: HighlightWalkInstruction;
// }) {
//   const registry = useElementRegistry();
//   const syncManager = useSyncManager();
//   const { target_id, steps, term_hints, duration_ms } = instruction;

//   useEffect(() => {
//     if (steps.length === 0) return;

//     function trySetup(): (() => void) | null {
//       const entry = registry.get(target_id);
//       if (!entry) return null;

//       const parentEl = entry.ref;

//       // Check if this is a design diagram by looking for data-design-element
//       const isDesignDiagram =
//         parentEl.querySelector("[data-design-element]") !== null;

//       if (isDesignDiagram) {
//         return setupImmediateWalk(parentEl);
//       }

//       // Fall back to SyncManager for non-design diagrams
//       if (!syncManager || !term_hints) return null;
//       return setupSyncedWalk(parentEl);
//     }

//     // ── Immediate sequential walk (design diagrams) ──────────
//     function setupImmediateWalk(parentEl: HTMLElement): (() => void) | null {
//       const timers: ReturnType<typeof setTimeout>[] = [];
//       let prevEls: (SVGElement | HTMLElement)[] = [];
//       const perStepMs = duration_ms
//         ? duration_ms / steps.length
//         : 3000;

//       // Immediately highlight first step, then schedule the rest
//       for (let i = 0; i < steps.length; i++) {
//         const step = steps[i];
//         const delay = i * perStepMs;

//         const timer = setTimeout(() => {
//           // Dim previous
//           for (const el of prevEls) removeSubHighlight(el);

//           // Light up current
//           const subEls = findSubElements(parentEl, step.sub_element_id);
//           for (const el of subEls) {
//             applySubHighlight(el, step.style ?? "glow", step.color ?? "");
//           }
//           prevEls = subEls;
//         }, delay);

//         timers.push(timer);
//       }

//       // Final cleanup: dim the last step after it's had its time
//       const cleanupTimer = setTimeout(() => {
//         for (const el of prevEls) removeSubHighlight(el);
//         prevEls = [];
//       }, steps.length * perStepMs);
//       timers.push(cleanupTimer);

//       return () => {
//         for (const t of timers) clearTimeout(t);
//         for (const el of prevEls) removeSubHighlight(el);
//         // Clean up any remaining highlights
//         for (const step of steps) {
//           const subEls = findSubElements(parentEl, step.sub_element_id);
//           for (const el of subEls) removeSubHighlight(el);
//         }
//       };
//     }

//     // ── Speech-synced walk (rough diagrams, scenes) ──────────
//     function setupSyncedWalk(parentEl: HTMLElement): (() => void) | null {
//       const walkId = `walk-${target_id}-${Date.now()}`;
//       const callbacks = new Map<string, (active: boolean) => void>();

//       for (const step of steps) {
//         const subEls = findSubElements(parentEl, step.sub_element_id);
//         if (subEls.length === 0) continue;

//         const highlightStyle = step.style ?? "glow";
//         const color = step.color ?? "";

//         callbacks.set(step.sub_element_id, (active: boolean) => {
//           for (const el of subEls) {
//             if (active) {
//               applySubHighlight(el, highlightStyle, color);
//             } else {
//               removeSubHighlight(el);
//             }
//           }
//         });
//       }

//       if (callbacks.size === 0) return null;

//       const unregister = syncManager!.registerWalk(
//         walkId,
//         term_hints!,
//         callbacks,
//       );

//       const fallbackMs = duration_ms ?? steps.length * 5000;
//       const fallbackTimer = window.setTimeout(() => unregister(), fallbackMs);

//       return () => {
//         unregister();
//         clearTimeout(fallbackTimer);
//         for (const step of steps) {
//           const subEls = findSubElements(parentEl, step.sub_element_id);
//           for (const el of subEls) removeSubHighlight(el);
//         }
//       };
//     }

//     // Try immediately, retry once on next frame if card not mounted yet
//     let cleanup = trySetup();
//     let rafId: number | undefined;

//     if (!cleanup) {
//       rafId = requestAnimationFrame(() => {
//         cleanup = trySetup();
//         if (!cleanup) {
//           console.warn(
//             `[HighlightWalkOverlay] Target "${target_id}" not found after retry`,
//           );
//         }
//       });
//     }

//     return () => {
//       if (rafId !== undefined) cancelAnimationFrame(rafId);
//       cleanup?.();
//     };
//   }, [registry, syncManager, target_id, steps, term_hints, duration_ms]);

//   return null;
// }
