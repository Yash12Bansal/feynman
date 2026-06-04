/**
 * Exit-intent detector. Fires when the cursor leaves the viewport through the
 * top edge (heading for the tab bar / close button) — the only reliable signal
 * available *before* the page actually unloads. (Browsers do not allow custom
 * UI in the native close/leave dialog, so true tab-close can't be intercepted
 * with our own form; this catches the common "about to leave" gesture.)
 */

import { useEffect } from "react";

export function useExitIntent({
  enabled,
  onTrigger,
}: {
  readonly enabled: boolean;
  readonly onTrigger: () => void;
}): void {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: MouseEvent) => {
      // relatedTarget null + leaving via the top = cursor left the document
      // upward (toward tabs / address bar / close).
      if (e.clientY <= 0 && e.relatedTarget == null) {
        onTrigger();
      }
    };
    document.addEventListener("mouseout", handler);
    return () => document.removeEventListener("mouseout", handler);
  }, [enabled, onTrigger]);
}
