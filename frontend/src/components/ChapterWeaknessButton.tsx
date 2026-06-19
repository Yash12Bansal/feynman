/**
 * "Memory" — an always-available, unobtrusive review surface inside the lecture.
 * A small glass pill in the top-right control cluster (left of the Topics
 * button, clear of the slide title); tapping it slides in a right-side drawer
 * with the student's full history on THIS chapter (including today), so even a
 * first-time visitor gets a meaningful "what's tripped me up so far" view.
 * Fetches lazily on open.
 *
 * Skinned in the "Deep-Space Glass" language: the pill matches the AskFeynman /
 * theme-toggle chrome (glass, `--lv-*` tokens, so it re-themes with the viewer),
 * and the drawer follows the current lecture theme.
 */

import { useCallback, useState } from "react";
import { fetchChapterMemory, type MemoryCard } from "../lib/api";
import { useTheme } from "../theme/themeContext";
import { DISPLAY_FONT } from "../styles/fonts";
import { MemoryReviewDrawer } from "./MemoryReview";

interface ChapterWeaknessButtonProps {
  readonly studentId: string | null | undefined;
  readonly chapterId: string;
}

export function ChapterWeaknessButton({
  studentId,
  chapterId,
}: ChapterWeaknessButtonProps) {
  const { theme } = useTheme();
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
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "translateY(-1px)";
          e.currentTarget.style.borderColor = "var(--lv-accent-glow)";
          e.currentTarget.style.boxShadow =
            "var(--lv-shadow), var(--lv-inset), 0 0 0 1px var(--lv-accent-glow-soft), 0 6px 22px var(--lv-accent-glow-soft)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "translateY(0)";
          e.currentTarget.style.borderColor = "var(--lv-border)";
          e.currentTarget.style.boxShadow = "var(--lv-shadow), var(--lv-inset)";
        }}
      >
        <span aria-hidden style={GLYPH}>
          <Spark />
        </span>
        <span style={{ whiteSpace: "nowrap" }}>Memory</span>
      </button>
      {open && (
        <MemoryReviewDrawer
          variant="space"
          theme={theme}
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

/** The shared "just for you" four-point spark (mirrors the home weak-points
 *  pill), in the lecture accent colour. */
function Spark() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3c.4 4.2 1.8 5.6 6 6-4.2.4-5.6 1.8-6 6-.4-4.2-1.8-5.6-6-6 4.2-.4 5.6-1.8 6-6Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const PILL: React.CSSProperties = {
  position: "fixed",
  // Top-right cluster, tucked LEFT of the "☰ Topics" button (right:84) and the
  // theme toggle (right:32) — out of the centre where the slide title sits.
  top: 32,
  right: 148,
  zIndex: 100,
  display: "flex",
  alignItems: "center",
  gap: 9,
  padding: "10px 17px",
  borderRadius: 999,
  background: "var(--lv-panel)",
  border: "1px solid var(--lv-border)",
  color: "var(--lv-accent-text)",
  fontFamily: DISPLAY_FONT,
  fontSize: "0.82rem",
  fontWeight: 600,
  letterSpacing: "0.01em",
  cursor: "pointer",
  backdropFilter: "blur(18px) saturate(1.2)",
  WebkitBackdropFilter: "blur(18px) saturate(1.2)",
  boxShadow: "var(--lv-shadow), var(--lv-inset)",
  transition:
    "transform 220ms cubic-bezier(0.22,0.61,0.36,1), border-color 220ms ease, box-shadow 220ms ease",
};

const GLYPH: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  color: "var(--lv-accent)",
};
