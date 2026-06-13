/**
 * "Memory" — an always-available, unobtrusive review surface inside the lecture.
 * A small pill in the top-right corner (out of the way of the slide title and
 * narration); tapping it slides in a right-side drawer with the student's full
 * history on THIS chapter (including today), so even a first-time visitor gets a
 * meaningful "what's tripped me up so far" view. Fetches lazily on open.
 */

import { useCallback, useState } from "react";
import { fetchChapterMemory, type MemoryCard } from "../lib/api";
import { MemoryReviewDrawer } from "./MemoryReview";

interface ChapterWeaknessButtonProps {
  readonly studentId: string | null | undefined;
  readonly chapterId: string;
}

export function ChapterWeaknessButton({
  studentId,
  chapterId,
}: ChapterWeaknessButtonProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [card, setCard] = useState<MemoryCard | null>(null);

  const onOpen = useCallback(() => {
    if (!studentId) return;
    setOpen(true);
    setLoading(true);
    fetchChapterMemory(studentId, chapterId)
      .then(setCard)
      .catch(() => setCard(null))
      .finally(() => setLoading(false));
  }, [studentId, chapterId]);

  if (!studentId) return null;

  return (
    <>
      <button
        type="button"
        onClick={onOpen}
        aria-label="Memory — your personalised review for this chapter"
        title="Memory — what you've gotten wrong / asked, just for you"
        style={PILL}
      >
        🧠 Memory
      </button>
      {open && (
        <MemoryReviewDrawer
          kicker="Personalised for you"
          title="Your memory · this chapter"
          card={card}
          loading={loading}
          emptyText="Nothing to review yet — answer a few checkpoint questions or raise a doubt, and what trips you up shows up here so you can revise it."
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

const PILL: React.CSSProperties = {
  position: "fixed",
  // Top-right corner, tucked LEFT of the "☰ Topics" button (which sits at
  // right:32) — out of the center where it used to collide with the title.
  top: 32,
  right: 148,
  zIndex: 100,
  padding: "10px 16px",
  borderRadius: 999,
  background: "rgba(16, 18, 26, 0.66)",
  border: "1px solid rgba(127, 212, 255, 0.28)",
  color: "#f4f6fb",
  fontSize: "0.85rem",
  letterSpacing: "0.01em",
  cursor: "pointer",
  backdropFilter: "blur(18px) saturate(1.2)",
  WebkitBackdropFilter: "blur(18px) saturate(1.2)",
  boxShadow: "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07)",
};
