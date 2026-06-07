/**
 * Edge-triggered timestamp trigger for in-lecture feedback. Fires `onFire` once
 * the lecture has been watched past a percentage threshold AND a hard minimum
 * elapsed time (so it never fires at the very start). Each threshold fires at
 * most once — seeking backward past an already-fired threshold does NOT re-arm
 * it, so the scrubber can't be used to re-pop the prompt.
 *
 * `onFire` may return `false` to signal "couldn't open right now" (e.g. another
 * surface is open); in that case the threshold is left un-consumed and retried
 * on the next tick, rather than being silently burned.
 */

import { useEffect, useRef } from "react";

const DEFAULT_THRESHOLDS: readonly number[] = [0.45, 0.85];

interface TimestampTriggerOptions {
  readonly currentMs: number;
  readonly durationMs: number;
  readonly enabled: boolean;
  /** Fractions of the lecture (0–1) at which to fire. Default [0.45, 0.85]. */
  readonly thresholdsPct?: readonly number[];
  /** Never fire before this many ms elapsed. Default 90_000. */
  readonly minElapsedMs?: number;
  /** Cap on total fires for the lifetime of the hook. Default 1. */
  readonly maxFires?: number;
  /** Return false to indicate the fire couldn't happen and should be retried. */
  readonly onFire: () => boolean | void;
}

export function useTimestampTrigger({
  currentMs,
  durationMs,
  enabled,
  thresholdsPct = DEFAULT_THRESHOLDS,
  minElapsedMs = 90_000,
  maxFires = 1,
  onFire,
}: TimestampTriggerOptions): void {
  const firedRef = useRef<Set<number>>(new Set());
  const fireCountRef = useRef(0);
  const onFireRef = useRef(onFire);
  useEffect(() => {
    onFireRef.current = onFire;
  }, [onFire]);

  useEffect(() => {
    if (!enabled || durationMs <= 0) return;
    if (currentMs < minElapsedMs) return;
    if (fireCountRef.current >= maxFires) return;

    const pct = currentMs / durationMs;
    for (let i = 0; i < thresholdsPct.length; i++) {
      if (pct >= thresholdsPct[i] && !firedRef.current.has(i)) {
        const result = onFireRef.current();
        if (result !== false) {
          firedRef.current.add(i);
          fireCountRef.current += 1;
        }
        break; // one threshold per tick
      }
    }
  }, [currentMs, durationMs, enabled, minElapsedMs, maxFires, thresholdsPct]);
}
