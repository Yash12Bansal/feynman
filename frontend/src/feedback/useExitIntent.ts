/**
 * Exit-intent detector with a two-step "leave" handshake.
 *
 * Fires when the cursor leaves the viewport through the TOP edge (heading for
 * the tab bar / address bar / close button) — the only signal available *before*
 * the page actually unloads. Browsers do not let a site show its own UI in the
 * native close/leave flow, so a real tab-close (Cmd+W, clicking the ✕) can't be
 * intercepted with our form; this catches the "about to leave" mouse gesture,
 * which is the standard exit-intent technique.
 *
 * The handshake the product wants:
 *   1. FIRST leave gesture  → `onOpen()`  (show the feedback survey).
 *   2. SECOND leave gesture while it's open → `onClose()` (let them go).
 * A short guard stops the SAME gesture that opened the survey from also closing
 * it. Keep `enabled` true while the survey is open so the second gesture is
 * actually heard (the old code disabled the listener once open, which is why the
 * "leave again to dismiss" step never worked).
 */

import { useEffect, useRef } from "react";

const REOPEN_GUARD_MS = 600;

interface UseExitIntentOptions {
  readonly enabled: boolean;
  /** Whether OUR feedback surface is currently open. */
  readonly isOpen: boolean;
  /** First leave gesture → open the survey. */
  readonly onOpen: () => void;
  /** A later leave gesture while open → close it and let the user leave. */
  readonly onClose: () => void;
}

function nowMs(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export function useExitIntent({
  enabled,
  isOpen,
  onOpen,
  onClose,
}: UseExitIntentOptions): void {
  const isOpenRef = useRef(isOpen);
  const openedAtRef = useRef(0);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);

  // Keep refs current without re-binding the document listener each render.
  // Stamp openedAt on the false→true transition so the guard measures from when
  // the survey actually appeared.
  useEffect(() => {
    if (isOpen && !isOpenRef.current) openedAtRef.current = nowMs();
    isOpenRef.current = isOpen;
    onOpenRef.current = onOpen;
    onCloseRef.current = onClose;
  }, [isOpen, onOpen, onClose]);

  useEffect(() => {
    if (!enabled) return;
    const handler = (e: MouseEvent) => {
      // relatedTarget null + clientY <= 0 ⇒ cursor left the document upward.
      if (e.clientY > 0 || e.relatedTarget != null) return;
      if (isOpenRef.current) {
        if (nowMs() - openedAtRef.current < REOPEN_GUARD_MS) return;
        onCloseRef.current();
      } else {
        onOpenRef.current();
      }
    };
    document.addEventListener("mouseout", handler);
    return () => document.removeEventListener("mouseout", handler);
  }, [enabled]);
}
