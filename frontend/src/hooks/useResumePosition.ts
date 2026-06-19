/**
 * Lecture resume — Phase 1 (client-only, the Netflix/Hotstar "fast path").
 *
 * Persists playback position to localStorage keyed by (student, chapter) so a
 * refresh OR a return next day lands the student where they left off. Position
 * is per-CHAPTER (durable), deliberately the opposite lifetime of the memory
 * session id (per-sitting, sessionStorage).
 *
 * Lifecycle baked in:
 *   - SAVE: throttled (every 5s) while playing, plus an immediate flush on
 *     visibilitychange/pagehide so a refresh captures the latest spot.
 *   - RESTORE: once, when the chapter is ready, seek to the saved ms.
 *   - CLEANUP: clear() on lecture-complete; TTL-prune (30d) of all stale keys
 *     on mount. localStorage is per-device/per-user, so this is all it needs —
 *     no server, no cron (that's only for the backend graph).
 *
 * Cross-device durability (Phase 2) layers a debounced backend sync on top of
 * this without rework.
 */

import { useCallback, useEffect, useRef } from "react";

const PREFIX = "lecture_pos:";
const SAVE_INTERVAL_MS = 5_000;
const MIN_RESUME_MS = 5_000; // don't bother resuming a barely-started lecture
const TTL_MS = 30 * 24 * 60 * 60 * 1000;

interface StoredPosition {
  ms: number;
  updatedAt: number;
}

interface UseResumePositionOpts {
  readonly studentId: string | null | undefined;
  readonly chapterId: string;
  readonly ready: boolean; // chapter loaded
  readonly currentMs: number;
  readonly isPlaying: boolean;
  readonly seekToTimeMs: (ms: number) => void;
}

function keyFor(studentId: string, chapterId: string): string {
  return `${PREFIX}${studentId}:${chapterId}`;
}

function read(key: string): StoredPosition | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredPosition;
    if (typeof parsed?.ms !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

/** Drop our keys older than the TTL. Runs opportunistically on mount — no
 *  background job needed since localStorage is per-device. */
function pruneStale(): void {
  try {
    const cutoff = Date.now() - TTL_MS;
    const doomed: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith(PREFIX)) continue;
      const pos = read(key);
      if (!pos || pos.updatedAt < cutoff) doomed.push(key);
    }
    doomed.forEach((k) => localStorage.removeItem(k));
  } catch {
    /* best-effort */
  }
}

export function useResumePosition({
  studentId,
  chapterId,
  ready,
  currentMs,
  isPlaying,
  seekToTimeMs,
}: UseResumePositionOpts): { clear: () => void } {
  const key = studentId ? keyFor(studentId, chapterId) : null;
  // Latest position in a ref so the save interval + unload handler read fresh
  // values without re-subscribing every frame.
  const msRef = useRef(currentMs);
  useEffect(() => {
    msRef.current = currentMs;
  }, [currentMs]);
  const restoredRef = useRef(false);

  const save = useCallback(() => {
    if (!key) return;
    const ms = msRef.current;
    if (ms < MIN_RESUME_MS) return;
    try {
      const payload: StoredPosition = { ms, updatedAt: Date.now() };
      localStorage.setItem(key, JSON.stringify(payload));
    } catch {
      /* quota / private mode — resume is best-effort */
    }
  }, [key]);

  const clear = useCallback(() => {
    if (!key) return;
    try {
      localStorage.removeItem(key);
    } catch {
      /* best-effort */
    }
  }, [key]);

  // TTL prune once on mount.
  useEffect(() => {
    pruneStale();
  }, []);

  // Restore once, when the chapter is ready.
  useEffect(() => {
    if (!key || !ready || restoredRef.current) return;
    restoredRef.current = true;
    const pos = read(key);
    if (
      pos &&
      pos.ms >= MIN_RESUME_MS &&
      pos.updatedAt >= Date.now() - TTL_MS
    ) {
      seekToTimeMs(pos.ms);
    }
  }, [key, ready, seekToTimeMs]);

  // Throttled save while playing.
  useEffect(() => {
    if (!key || !isPlaying) return;
    const id = window.setInterval(save, SAVE_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [key, isPlaying, save]);

  // Flush on tab-hide / unload so a refresh captures the latest spot.
  useEffect(() => {
    if (!key) return;
    const flush = () => {
      if (document.visibilityState === "hidden") save();
    };
    window.addEventListener("visibilitychange", flush);
    window.addEventListener("pagehide", save);
    return () => {
      window.removeEventListener("visibilitychange", flush);
      window.removeEventListener("pagehide", save);
    };
  }, [key, save]);

  return { clear };
}
