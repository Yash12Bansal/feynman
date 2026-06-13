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
 */

import { useState } from "react";
import type { MemoryCard } from "../lib/api";
import { MemoryReviewSections } from "./MemoryReview";
import { BUTTON, CARD, KICKER, OVERLAY, TITLE } from "./memoryReviewStyles";

interface MemoryCardOverlayProps {
  readonly card: MemoryCard | null;
}

export function MemoryCardOverlay({ card }: MemoryCardOverlayProps) {
  const [dismissed, setDismissed] = useState(false);

  const isEmpty =
    !card || (card.incorrect_attempts.length === 0 && card.doubts.length === 0);
  if (dismissed || isEmpty || !card) return null;

  return (
    <div style={OVERLAY}>
      <div style={CARD}>
        <div style={KICKER}>From your last session</div>
        <h2 style={TITLE}>Worth a second look</h2>
        <MemoryReviewSections card={card} />
        <button style={BUTTON} onClick={() => setDismissed(true)}>
          Got it — start the lecture
        </button>
      </div>
    </div>
  );
}
