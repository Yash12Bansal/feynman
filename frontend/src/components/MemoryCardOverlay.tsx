/**
 * "Pick up where you left off" card, shown once when a signed-in student
 * opens a lecture they've studied on a PRIOR day. Surfaces the questions they
 * got wrong and the doubts they raised in their last N study-days on this
 * chapter (today excluded by the caller).
 *
 * Pure presentation — the parent fetches the card EXCLUDING today's session (so
 * the current day never pollutes it) and passes it in. Renders nothing when the
 * card is null/empty/dismissed, so a first-timer never sees an empty box. (The
 * explicit "weak points" button is the surface that DOES show for first-timers.)
 *
 * Reuses the shared Deep-Space Glass review modal, themed to the viewer.
 */

import { useState } from "react";
import type { MemoryCard } from "../lib/api";
import { useTheme } from "../theme/themeContext";
import { MemoryReviewOverlay } from "./MemoryReview";

interface MemoryCardOverlayProps {
  readonly card: MemoryCard | null;
}

export function MemoryCardOverlay({ card }: MemoryCardOverlayProps) {
  const { theme } = useTheme();
  const [dismissed, setDismissed] = useState(false);

  const isEmpty =
    !card || (card.incorrect_attempts.length === 0 && card.doubts.length === 0);
  if (dismissed || isEmpty || !card) return null;

  return (
    <MemoryReviewOverlay
      variant="space"
      theme={theme}
      kicker="From your last session"
      title="Worth a second look"
      card={card}
      emptyText=""
      closeLabel="Got it — start the lecture"
      onClose={() => setDismissed(true)}
    />
  );
}
