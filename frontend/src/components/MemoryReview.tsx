/**
 * Shared, presentational rendering for the personalised memory cards. One
 * renderer backs all three surfaces:
 *   - MemoryCardOverlay      — auto-pop on chapter open (prior study-days).
 *   - ChapterWeaknessButton  — "important points of this chapter, just for you".
 *   - GlobalMemoryButton     — recent mistakes across every chapter (home).
 *
 * The look is entirely token-driven (see memory-review.css): pass
 * `variant="notebook"` for the warm Living-Notebook home surface, or
 * `variant="space"` + the lecture `theme` for the in-lecture Deep-Space Glass.
 *
 * `MemoryReviewSections` is the body (questions missed + doubts raised, text
 * only — no diagrams, by design). `MemoryReviewOverlay`/`Drawer` wrap it with
 * loading + empty states. Pure UI; callers own data.
 */

import { useEffect } from "react";
import type { MemoryCard } from "../lib/api";
import "./memory-review.css";

export type MemoryVariant = "notebook" | "space";
type Theme = "light" | "dark";

interface SectionsProps {
  readonly card: MemoryCard;
  /** Tag each item with its chapter_id — used on the global card, which spans
   *  chapters. Off for per-chapter cards where it'd be noise. */
  readonly showChapterTag?: boolean;
}

export function MemoryReviewSections({
  card,
  showChapterTag = false,
}: SectionsProps) {
  return (
    <>
      {card.incorrect_attempts.length > 0 && (
        <section className="mem-section mem-section--missed">
          <div className="mem-section-label">Questions you missed</div>
          <ul className="mem-list">
            {card.incorrect_attempts.map((a, i) => (
              <li
                key={`${a.question_id}-${a.created_at}`}
                className="mem-item"
                style={{ "--i": i } as React.CSSProperties}
              >
                {showChapterTag && (
                  <span className="mem-tag">{a.chapter_id}</span>
                )}
                <div className="mem-item-text">{a.q_text}</div>
                {a.options && a.options.length > 0 && (
                  <details className="mem-disclosure">
                    <summary className="mem-summary">Options</summary>
                    <ul className="mem-opt-list">
                      {a.options.map((opt) => {
                        const isCorrect =
                          opt.trim().charAt(0).toUpperCase() ===
                          (a.solution || "").trim().charAt(0).toUpperCase();
                        return (
                          <li
                            key={opt}
                            className={
                              isCorrect ? "mem-opt mem-opt--correct" : "mem-opt"
                            }
                          >
                            <span>{opt}</span>
                            {isCorrect && (
                              <span className="mem-opt-badge">correct</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                )}
                {a.solution_steps && a.solution_steps.length > 0 && (
                  <details className="mem-disclosure">
                    <summary className="mem-summary">Worked solution</summary>
                    <ol className="mem-step-ol">
                      {a.solution_steps.map((s, j) => (
                        <li key={j}>{s}</li>
                      ))}
                    </ol>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {card.doubts.length > 0 && (
        <section className="mem-section mem-section--doubts">
          <div className="mem-section-label">Doubts you raised</div>
          <ul className="mem-list">
            {card.doubts.map((d, i) => (
              <li
                key={`${d.topic_id}-${d.created_at}-${i}`}
                className="mem-item"
                style={{ "--i": i } as React.CSSProperties}
              >
                {showChapterTag && (
                  <span className="mem-tag">{d.chapter_id}</span>
                )}
                <div className="mem-item-text">{d.doubt_text}</div>
                {d.response && (
                  <details className="mem-disclosure">
                    <summary className="mem-summary">Feynman's answer</summary>
                    <p className="mem-explain">{d.response}</p>
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

/** Close on Escape — small shared affordance for the dialog wrappers. */
function useEscapeToClose(onClose: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
}

function isCardEmpty(card: MemoryCard | null): boolean {
  return (
    !card || (card.incorrect_attempts.length === 0 && card.doubts.length === 0)
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
  readonly variant?: MemoryVariant;
  readonly theme?: Theme;
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
  variant = "space",
  theme = "dark",
}: DrawerProps) {
  useEscapeToClose(onClose);
  const empty = isCardEmpty(card);
  return (
    <div className={`mem-root mem-root--${variant}`} data-theme={theme}>
      <div className="mem-drawer-scrim" onClick={onClose}>
        <aside
          className="mem-drawer"
          role="dialog"
          aria-label={title}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="mem-drawer-head">
            <div>
              <div className="mem-kicker">{kicker}</div>
              <h2 className="mem-drawer-title">{title}</h2>
            </div>
            <button className="mem-close" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
          <div className="mem-drawer-body">
            {loading ? (
              <p className="mem-subtle">Loading…</p>
            ) : empty ? (
              <p className="mem-empty">{emptyText}</p>
            ) : (
              <MemoryReviewSections
                card={card!}
                showChapterTag={showChapterTag}
              />
            )}
          </div>
        </aside>
      </div>
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
  readonly variant?: MemoryVariant;
  readonly theme?: Theme;
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
  variant = "space",
  theme = "dark",
}: OverlayProps) {
  useEscapeToClose(onClose);
  const empty = isCardEmpty(card);
  return (
    <div className={`mem-root mem-root--${variant}`} data-theme={theme}>
      <div className="mem-overlay" onClick={onClose}>
        <div
          className="mem-card"
          role="dialog"
          aria-label={title}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="mem-kicker">{kicker}</div>
          <h2 className="mem-title">{title}</h2>
          {loading ? (
            <p className="mem-subtle">Loading…</p>
          ) : empty ? (
            <p className="mem-empty">{emptyText}</p>
          ) : (
            <MemoryReviewSections
              card={card!}
              showChapterTag={showChapterTag}
            />
          )}
          <button className="mem-btn" onClick={onClose}>
            {closeLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
