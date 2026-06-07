/**
 * In-lecture feedback trigger. Rendered INSIDE LectureViewer (the only place
 * that owns playback time + pause/play). It opens the full feedback wizard when
 * either (a) the lecture passes ~45% and is at least 90s in, or (b) the user
 * makes a leave gesture (cursor to the tab bar) mid-lecture. Either way it
 * PAUSES the lecture first and resumes on close — so audio never plays behind
 * the modal. Fires at most once per threshold, respects the shared
 * feedbackSession lock, and (while mounted) claims exit-intent so the global
 * exit survey stands down during a lecture.
 */

import { useCallback, useEffect, useState } from "react";
import { FeedbackWizard } from "./FeedbackWizard";
import { WIZARD_STEPS } from "./steps";
import { feedbackSession } from "./feedbackSession";
import { useTimestampTrigger } from "./useTimestampTrigger";
import { useExitIntent } from "./useExitIntent";

const DISMISS_COOLDOWN_MS = 60_000;

interface InLectureFeedbackProps {
  readonly currentMs: number;
  readonly durationMs: number;
  /** Gate from the viewer (e.g. no active doubt / satisfaction prompt). */
  readonly enabled: boolean;
  /** Only fire while the lecture is actually playing — so we never auto-resume a
   *  lecture the user deliberately paused (matters for the exit-intent path). */
  readonly isPlaying: boolean;
  readonly pause: () => void;
  readonly play: () => void;
  /** Lets the viewer hide its chrome while the wizard is up. */
  readonly onOpenChange?: (open: boolean) => void;
}

export function InLectureFeedback({
  currentMs,
  durationMs,
  enabled,
  isPlaying,
  pause,
  play,
  onOpenChange,
}: InLectureFeedbackProps) {
  const [open, setOpen] = useState(false);

  // Mark a lecture on screen so the global exit survey stands down (it can't
  // pause playback; we can).
  useEffect(() => {
    feedbackSession.setLectureActive(true);
    return () => feedbackSession.setLectureActive(false);
  }, []);

  const fire = useCallback((): boolean => {
    if (!feedbackSession.tryOpen("in_lecture")) return false;
    pause();
    setOpen(true);
    onOpenChange?.(true);
    return true;
  }, [pause, onOpenChange]);

  useTimestampTrigger({
    currentMs,
    durationMs,
    enabled: enabled && isPlaying && !open && !feedbackSession.hasSubmitted(),
    onFire: fire,
  });

  // A leave gesture mid-lecture also opens the survey (and pauses) — but only
  // while playing, so we never resume a lecture the user paused themselves.
  useExitIntent({ enabled: enabled && isPlaying && !open, onTrigger: fire });

  const close = useCallback(
    (submitted: boolean) => {
      setOpen(false);
      onOpenChange?.(false);
      if (submitted) {
        feedbackSession.markSubmitted();
      } else {
        feedbackSession.markClosed();
        feedbackSession.startCooldown("in_lecture", DISMISS_COOLDOWN_MS);
      }
      play();
    },
    [onOpenChange, play],
  );

  if (!open) return null;
  return (
    <FeedbackWizard
      steps={WIZARD_STEPS}
      source="in_lecture"
      onClose={() => close(false)}
      onSubmitted={() => close(true)}
    />
  );
}
