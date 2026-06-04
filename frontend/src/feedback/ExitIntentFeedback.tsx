/**
 * Shows the full feedback survey when the user looks like they're leaving
 * (cursor exits via the top edge). Once submitted, it stays quiet for the rest
 * of the session; after a dismiss it waits out a 60s cooldown so it doesn't
 * re-pop on every stray mouse movement toward the tab bar.
 */

import { useCallback, useRef, useState } from "react";
import { useExitIntent } from "./useExitIntent";
import { FeedbackModal } from "./FeedbackModal";

const DISMISS_COOLDOWN_MS = 60_000;

export function ExitIntentFeedback() {
  const [open, setOpen] = useState(false);
  const submittedRef = useRef(false);
  const lastShownRef = useRef(0);

  const onTrigger = useCallback(() => {
    if (submittedRef.current) return;
    const now = performance.now();
    if (lastShownRef.current !== 0 && now - lastShownRef.current < DISMISS_COOLDOWN_MS) {
      return;
    }
    lastShownRef.current = now;
    setOpen(true);
  }, []);

  // Detector is inert while the modal is open.
  useExitIntent({ enabled: !open, onTrigger });

  if (!open) return null;
  return (
    <FeedbackModal
      variant="exit"
      onClose={() => setOpen(false)}
      onSubmitted={() => {
        submittedRef.current = true;
        setOpen(false);
      }}
    />
  );
}
