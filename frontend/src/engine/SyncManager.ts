import type { TermSyncHint } from "../types/visuals";

interface PendingSync {
  hints: TermSyncHint[];
  callbacks: Map<string, () => void>;
  revealedTerms: Set<string>;
}

/**
 * Word-to-term matching engine for voice-visual synchronization.
 *
 * Bridges transcription events (spoken words) to GSAP animation callbacks
 * (equation term reveals). Plain class — not a React component — to avoid
 * re-renders on every spoken word.
 */
export class SyncManager {
  private pendingSyncs = new Map<string, PendingSync>();

  /** Register an instruction for term-level sync. Returns unregister fn. */
  register(
    id: string,
    hints: TermSyncHint[],
    callbacks: Map<string, () => void>,
  ): () => void {
    this.pendingSyncs.set(id, { hints, callbacks, revealedTerms: new Set() });
    return () => {
      this.pendingSyncs.delete(id);
    };
  }

  /**
   * Register a highlight walk with spotlight semantics.
   *
   * Unlike `register` (reveal-once), each step callback receives an `active`
   * boolean. When a new step triggers, the previous step is deactivated
   * (only one highlighted at a time). Returns unregister fn that also
   * deactivates the currently active step.
   */
  registerWalk(
    id: string,
    hints: TermSyncHint[],
    callbacks: Map<string, (active: boolean) => void>,
  ): () => void {
    let activeTermId: string | null = null;

    // Wrap spotlight callbacks into the PendingSync shape (void callbacks).
    const wrappedCallbacks = new Map<string, () => void>();
    for (const [termId, cb] of callbacks) {
      wrappedCallbacks.set(termId, () => {
        // Deactivate previous
        if (activeTermId && activeTermId !== termId) {
          callbacks.get(activeTermId)?.(false);
        }
        // Activate current
        cb(true);
        activeTermId = termId;
      });
    }

    this.pendingSyncs.set(id, {
      hints,
      callbacks: wrappedCallbacks,
      revealedTerms: new Set(),
    });

    return () => {
      // Deactivate current on cleanup
      if (activeTermId) {
        callbacks.get(activeTermId)?.(false);
        activeTermId = null;
      }
      this.pendingSyncs.delete(id);
    };
  }

  /** Called on each transcription word. Matches against pending sync hints. */
  onWord(word: string): void {
    const normalized = word.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (!normalized) return;

    for (const [, sync] of this.pendingSyncs) {
      for (const hint of sync.hints) {
        if (sync.revealedTerms.has(hint.term_id)) continue;
        const matched = hint.trigger_words.some(
          (tw) => tw.toLowerCase().replace(/[^a-z0-9]/g, "") === normalized,
        );
        if (matched) {
          sync.revealedTerms.add(hint.term_id);
          sync.callbacks.get(hint.term_id)?.();
        }
      }
    }
  }

  /** Force-reveal all unrevealed terms (fallback when sync fails or times out). */
  revealAll(id: string): void {
    const sync = this.pendingSyncs.get(id);
    if (!sync) return;
    for (const [termId, cb] of sync.callbacks) {
      if (!sync.revealedTerms.has(termId)) {
        sync.revealedTerms.add(termId);
        cb();
      }
    }
  }

  clear(): void {
    this.pendingSyncs.clear();
  }
}
