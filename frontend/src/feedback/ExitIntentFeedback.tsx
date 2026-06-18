/**
 * Exit survey for the non-lecture surfaces (home screen, between lectures).
 *
 * Handshake (see `useExitIntent`): the FIRST time the cursor heads for the tab
 * bar / close, the survey opens; if the user makes the leave gesture AGAIN while
 * it's up, it closes and lets them go. `feedbackSession.tryOpen("exit")` is the
 * once-per-session gate so a dismissed survey never re-pops on later gestures.
 * Stands down entirely while a lecture is on screen — the in-lecture surface
 * owns exit-intent there because only it can pause playback.
 */

import { useState } from "react";
import { useExitIntent } from "./useExitIntent";
import { useLeaveSignals } from "./useLeaveSignals";
import { FeedbackModal } from "./FeedbackModal";
import { feedbackSession } from "./feedbackSession";

export function ExitIntentFeedback() {
  const [open, setOpen] = useState(false);

  // Best-effort logging of real leaves (independent of whether the form opened).
  useLeaveSignals();

  useExitIntent({
    enabled: true,
    isOpen: open,
    onOpen: () => {
      if (feedbackSession.isLectureActive()) return;
      if (feedbackSession.tryOpen("exit")) setOpen(true);
    },
    onClose: () => {
      setOpen(false);
      feedbackSession.markClosed();
    },
  });

  if (!open) return null;
  return (
    <FeedbackModal
      variant="exit"
      theme="light"
      onClose={() => {
        setOpen(false);
        feedbackSession.markClosed();
      }}
      onSubmitted={() => {
        setOpen(false);
        feedbackSession.markSubmitted();
      }}
    />
  );
}
