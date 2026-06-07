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
    const until = cooldownUntil.get(source);
    return until == null || nowMs() >= until;
  },

  /** Gated claim for automatic triggers. Returns false if not allowed. */
  tryOpen(source: FeedbackSource): boolean {
    if (!this.canOpen(source)) return false;
    openCount += 1;
    return true;
  },

  /** Unconditional claim for explicit user actions (the FAB). */
  markOpened(): void {
    openCount += 1;
  },

  markClosed(): void {
    openCount = Math.max(0, openCount - 1);
  },

  markSubmitted(): void {
    submitted = true;
    openCount = Math.max(0, openCount - 1);
    try {
      sessionStorage.setItem(SUBMITTED_KEY, "1");
    } catch {
      /* ignore */
    }
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
    try {
      sessionStorage.removeItem(SUBMITTED_KEY);
    } catch {
      /* ignore */
    }
  },
};
