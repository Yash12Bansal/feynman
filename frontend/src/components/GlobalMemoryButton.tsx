/**
 * User-level memory entry point for the home screen. One tap surfaces the
 * student's most recent mistakes + doubts across EVERY chapter, newest first
 * ("yesterday in Friction you missed…; in Optics you asked…"). Self-contained:
 * reads the signed-in uid from auth and fetches lazily on click, so the home
 * grid stays a pure catalogue.
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
      <button type="button" onClick={onOpen} style={PILL}>
        ✨ Your recent weak points
      </button>
      {open && (
        <MemoryReviewOverlay
          kicker="Personalised for you"
          title="What to revisit"
          card={card}
          loading={loading}
          showChapterTag
          emptyText="Nothing yet — once you study a chapter and answer its questions, the things you got wrong show up here for quick revision."
          closeLabel="Close"
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

const PILL: React.CSSProperties = {
  marginTop: 14,
  padding: "9px 18px",
  borderRadius: 999,
  background: "rgba(16, 18, 26, 0.55)",
  border: "1px solid rgba(127, 212, 255, 0.28)",
  color: "#f4f6fb",
  fontSize: "0.85rem",
  letterSpacing: "0.01em",
  cursor: "pointer",
  backdropFilter: "blur(18px) saturate(1.2)",
  WebkitBackdropFilter: "blur(18px) saturate(1.2)",
};
