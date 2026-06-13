/**
 * Shared, presentational rendering for the personalised memory cards. One
 * renderer backs all three surfaces:
 *   - MemoryCardOverlay      — auto-pop on chapter open (prior study-days).
 *   - ChapterWeaknessButton  — "important points of this chapter, just for you".
 *   - the home-screen global card (recent mistakes across every chapter).
 *
 * `MemoryReviewSections` is the body (questions missed + doubts raised, text
 * only — no diagrams, by design). `MemoryReviewOverlay` is a generic modal
 * wrapper around it with a loading + empty state. Pure UI; callers own data.
 */

import type { MemoryCard } from "../lib/api";
import {
  BUTTON,
  CARD,
  CLOSE_X,
  DISCLOSURE,
  DRAWER,
  DRAWER_BODY,
  DRAWER_HEAD,
  DRAWER_SCRIM,
  DRAWER_TITLE,
  EMPTY,
  EXPLAIN,
  ITEM,
  KICKER,
  LIST,
  OPT_BADGE,
  OPT_CORRECT,
  OPT_ITEM,
  OPT_LIST,
  OVERLAY,
  SECTION,
  SECTION_LABEL,
  SUBTLE,
  SUMMARY,
  TAG,
  TITLE,
} from "./memoryReviewStyles";

interface SectionsProps {
  readonly card: MemoryCard;
  /** Tag each item with its chapter_id — used on the global card, which spans
   *  chapters. Off for per-chapter cards where it'd be noise. */
  readonly showChapterTag?: boolean;
}

export function MemoryReviewSections({ card, showChapterTag = false }: SectionsProps) {
  return (
    <>
      {card.incorrect_attempts.length > 0 && (
        <section style={SECTION}>
          <div style={SECTION_LABEL}>Questions you missed</div>
          <ul style={LIST}>
            {card.incorrect_attempts.map((a) => (
              <li key={`${a.question_id}-${a.created_at}`} style={ITEM}>
                {showChapterTag && <span style={TAG}>{a.chapter_id}</span>}
                <div>{a.q_text}</div>
                {a.options && a.options.length > 0 && (
                  <details style={DISCLOSURE}>
                    <summary style={SUMMARY}>Options</summary>
                    <ul style={OPT_LIST}>
                      {a.options.map((opt) => {
                        const isCorrect =
                          opt.trim().charAt(0).toUpperCase() ===
                          (a.solution || "").trim().charAt(0).toUpperCase();
                        return (
                          <li
                            key={opt}
                            style={isCorrect ? OPT_CORRECT : OPT_ITEM}
                          >
                            {opt}
                            {isCorrect && <span style={OPT_BADGE}>correct</span>}
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                )}
                {a.explanation && (
                  <details style={DISCLOSURE}>
                    <summary style={SUMMARY}>Why</summary>
                    <p style={EXPLAIN}>{a.explanation}</p>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {card.doubts.length > 0 && (
        <section style={SECTION}>
          <div style={SECTION_LABEL}>Doubts you raised</div>
          <ul style={LIST}>
            {card.doubts.map((d, i) => (
              <li key={`${d.topic_id}-${d.created_at}-${i}`} style={ITEM}>
                {showChapterTag && <span style={TAG}>{d.chapter_id}</span>}
                <div>{d.doubt_text}</div>
                {d.response && (
                  <details style={DISCLOSURE}>
                    <summary style={SUMMARY}>Feynman's answer</summary>
                    <p style={EXPLAIN}>{d.response}</p>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

interface DrawerProps {
  readonly kicker: string;
  readonly title: string;
  readonly card: MemoryCard | null;
  readonly loading?: boolean;
  readonly showChapterTag?: boolean;
  readonly emptyText: string;
  readonly onClose: () => void;
}

/** Side panel that slides in from the right. Used in-lecture so the board stays
 *  visible — the review sits beside the content, not on top of it. */
export function MemoryReviewDrawer({
  kicker,
  title,
  card,
  loading = false,
  showChapterTag = false,
  emptyText,
  onClose,
}: DrawerProps) {
  const isEmpty =
    !card || (card.incorrect_attempts.length === 0 && card.doubts.length === 0);
  return (
    <div style={DRAWER_SCRIM} onClick={onClose}>
      <aside style={DRAWER} onClick={(e) => e.stopPropagation()}>
        <div style={DRAWER_HEAD}>
          <div>
            <div style={KICKER}>{kicker}</div>
            <h2 style={DRAWER_TITLE}>{title}</h2>
          </div>
          <button style={CLOSE_X} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div style={DRAWER_BODY}>
          {loading ? (
            <p style={SUBTLE}>Loading…</p>
          ) : isEmpty ? (
            <p style={EMPTY}>{emptyText}</p>
          ) : (
            <MemoryReviewSections card={card} showChapterTag={showChapterTag} />
          )}
        </div>
      </aside>
    </div>
  );
}

interface OverlayProps {
  readonly kicker: string;
  readonly title: string;
  readonly card: MemoryCard | null;
  readonly loading?: boolean;
  readonly showChapterTag?: boolean;
  readonly emptyText: string;
  readonly closeLabel?: string;
  readonly onClose: () => void;
}

export function MemoryReviewOverlay({
  kicker,
  title,
  card,
  loading = false,
  showChapterTag = false,
  emptyText,
  closeLabel = "Close",
  onClose,
}: OverlayProps) {
  const isEmpty =
    !card || (card.incorrect_attempts.length === 0 && card.doubts.length === 0);
  return (
    <div style={OVERLAY} onClick={onClose}>
      <div style={CARD} onClick={(e) => e.stopPropagation()}>
        <div style={KICKER}>{kicker}</div>
        <h2 style={TITLE}>{title}</h2>
        {loading ? (
          <p style={SUBTLE}>Loading…</p>
        ) : isEmpty ? (
          <p style={EMPTY}>{emptyText}</p>
        ) : (
          <MemoryReviewSections card={card} showChapterTag={showChapterTag} />
        )}
        <button style={BUTTON} onClick={onClose}>
          {closeLabel}
        </button>
      </div>
    </div>
  );
}
