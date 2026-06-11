/**
 * Module-level coordination for the feedback surfaces (FAB, exit-intent,
 * in-lecture). They live in different parts of the React tree with no common
 * provider, so a small shared singleton is the simplest correct way to enforce:
 *   - only ONE wizard open at a time (no stacking),
 *   - stay quiet for the rest of the session once the user submits,
 *   - per-source cooldowns so a dismissed prompt doesn't immediately re-pop.
 *
 * `tryOpen(source)` is the GATED entry for automatic triggers (exit-intent,
 * in-lecture): it refuses if something is already open, the user already
 * submitted, or the source is cooling down. Explicit user actions (clicking the
 * FAB) use `markOpened()` directly so the button always responds.
 *
 * The "submitted" flag is mirrored to sessionStorage so a reload within the same
 * tab session stays quiet too.
 */

import type { FeedbackSource } from "./feedbackService";

const SUBMITTED_KEY = "feynman.feedback.submitted";

let openCount = 0;
let submitted = readSubmitted();
let lectureActive = false;
const cooldownUntil = new Map<FeedbackSource, number>();
// Each AUTOMATIC source (in_lecture, exit) may auto-open AT MOST ONCE per
// session. This is the hard stop on "feedback again and again": once a prompt
// has auto-fired, the next mouse-to-top gesture or timestamp threshold won't
// re-pop it (the post-dismiss cooldown alone let it return every 60s). The
// manual FAB uses markOpened() and is exempt.
const autoFired = new Set<FeedbackSource>();
// Open/close subscribers. The lecture viewer subscribes so it can pause
// playback whenever ANY feedback surface (in-lecture, exit, or the FAB) opens.
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function readSubmitted(): boolean {
  try {
    return sessionStorage.getItem(SUBMITTED_KEY) === "1";
  } catch {
    return false;
  }
}

function nowMs(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export const feedbackSession = {
  isOpen(): boolean {
    return openCount > 0;
  },

  hasSubmitted(): boolean {
    return submitted;
  },

  /** Whether an automatic trigger may open right now. */
  canOpen(source: FeedbackSource): boolean {
    if (submitted || openCount > 0) return false;
    if (autoFired.has(source)) return false; // one auto-open per source/session
    const until = cooldownUntil.get(source);
    return until == null || nowMs() >= until;
  },

  /** Gated claim for automatic triggers. Returns false if not allowed. */
  tryOpen(source: FeedbackSource): boolean {
    if (!this.canOpen(source)) return false;
    openCount += 1;
    autoFired.add(source); // never auto-open this source again this session
    emit();
    return true;
  },

  /** Unconditional claim for explicit user actions (the FAB). */
  markOpened(): void {
    openCount += 1;
    emit();
  },

  markClosed(): void {
    openCount = Math.max(0, openCount - 1);
    emit();
  },

  markSubmitted(): void {
    submitted = true;
    openCount = Math.max(0, openCount - 1);
    try {
      sessionStorage.setItem(SUBMITTED_KEY, "1");
    } catch {
      /* ignore */
    }
    emit();
  },

  /**
   * Subscribe to open/close transitions; returns an unsubscribe fn. Used by the
   * lecture viewer to pause playback while any feedback surface is open.
   */
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },

  startCooldown(source: FeedbackSource, ms: number): void {
    cooldownUntil.set(source, nowMs() + ms);
  },

  /**
   * Whether a lecture is currently on screen. When true the in-lecture surface
   * owns exit-intent (it can pause playback); the global exit survey stands
   * down so audio never plays behind a modal.
   */
  isLectureActive(): boolean {
    return lectureActive;
  },
  setLectureActive(active: boolean): void {
    lectureActive = active;
  },

  /** Test hook — reset all module state. */
  _reset(): void {
    openCount = 0;
    submitted = false;
    lectureActive = false;
    cooldownUntil.clear();
    autoFired.clear();
    listeners.clear();
    try {
      sessionStorage.removeItem(SUBMITTED_KEY);
    } catch {
      /* ignore */
    }
  },
};
