/**
 * User-level memory entry point for the home screen. One tap surfaces the
 * student's most recent mistakes + doubts across EVERY chapter, newest first
 * ("yesterday in Friction you missed…; in Optics you asked…"). Self-contained:
 * reads the signed-in uid from auth and fetches lazily on click, so the home
 * grid stays a pure catalogue.
 *
 * Skinned in the "Living Notebook" language (the home screen's world): a warm
 * paper pill with a hand-drawn spark, and a paper-modal review.
 */

import { useCallback, useContext, useState } from "react";
import { AuthContext } from "../auth/authContext";
import { fetchGlobalMemory, type MemoryCard } from "../lib/api";
import { MemoryReviewOverlay } from "./MemoryReview";

export function GlobalMemoryButton() {
  // Read auth directly (not useAuth) so this optional widget degrades to
  // nothing when rendered outside a provider, instead of crashing its host.
  const auth = useContext(AuthContext);
  const uid = auth?.user?.uid;
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [card, setCard] = useState<MemoryCard | null>(null);

  const onOpen = useCallback(() => {
    if (!uid) return;
    setOpen(true);
    setLoading(true);
    fetchGlobalMemory(uid)
      .then(setCard)
      .catch(() => setCard(null))
      .finally(() => setLoading(false));
  }, [uid]);

  if (!uid) return null;

  return (
    <>
      <button type="button" onClick={onOpen} className="mem-home-pill">
        <Spark />
        <span>Your weak points</span>
        <span className="mem-home-pill__arrow" aria-hidden>
          →
        </span>
      </button>
      {open && (
        <MemoryReviewOverlay
          variant="notebook"
          kicker="Personalised for you"
          title="What to revisit"
          card={card}
          loading={loading}
          showChapterTag
          emptyText="Nothing yet — once you study a chapter and answer its questions, the things you got wrong show up here for quick revision."
          closeLabel="Got it"
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

/** A small hand-drawn four-point spark — the shared "just for you" motif (it
 *  also fronts the in-lecture Memory pill). Strokes draw on mount via CSS. */
function Spark() {
  return (
    <svg
      className="mem-home-pill__spark"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path d="M12 3c.4 4.2 1.8 5.6 6 6-4.2.4-5.6 1.8-6 6-.4-4.2-1.8-5.6-6-6 4.2-.4 5.6-1.8 6-6Z" />
    </svg>
  );
}
