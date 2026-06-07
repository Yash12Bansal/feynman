/**
 * Opens the full feedback survey when the user looks like they're leaving
 * (cursor exits via the top edge, heading for the tab bar / close). Also wires
 * the leave-signal bounce beacon. Coordinated through `feedbackSession`: it
 * won't pop if the user already submitted, if another wizard is open, or during
 * its 60s post-dismiss cooldown — and it stands down entirely while a lecture is
 * on screen (the in-lecture surface owns exit-intent there, because only it can
 * pause playback).
 */

import { useCallback, useState } from "react";
import { useExitIntent } from "./useExitIntent";
import { useLeaveSignals } from "./useLeaveSignals";
import { FeedbackModal } from "./FeedbackModal";
import { feedbackSession } from "./feedbackSession";

const DISMISS_COOLDOWN_MS = 60_000;

export function ExitIntentFeedback() {
  const [open, setOpen] = useState(false);

  // Best-effort logging of real leaves (independent of whether the form opened).
  useLeaveSignals();

  const onTrigger = useCallback(() => {
    // Read live (feedbackSession isn't reactive): during a lecture the
    // in-lecture surface owns exit-intent because only it can pause playback.
    if (feedbackSession.isLectureActive()) return;
    if (!feedbackSession.tryOpen("exit")) return;
    setOpen(true);
  }, []);

  // Listener stays attached whenever our own modal is closed; the live guards in
  // onTrigger (lecture-active, tryOpen) are the real gates.
  useExitIntent({ enabled: !open, onTrigger });

  if (!open) return null;
  return (
    <FeedbackModal
      variant="exit"
      onClose={() => {
        setOpen(false);
        feedbackSession.markClosed();
        feedbackSession.startCooldown("exit", DISMISS_COOLDOWN_MS);
      }}
      onSubmitted={() => {
        setOpen(false);
        feedbackSession.markSubmitted();
      }}
    />
  );
}
