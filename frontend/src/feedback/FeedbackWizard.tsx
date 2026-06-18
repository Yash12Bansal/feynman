/**
 * The feedback wizard — one question per slide, Back / Next, a progress bar, and
 * an intro splash first. Data-driven from a `FeedbackStep[]` (see steps.ts), so
 * the FAB, exit-intent and in-lecture triggers all reuse it with the same list;
 * they differ only by the `source` tag stamped on the payload.
 *
 * MCQ steps render option pills plus an optional free-text comment. On the last
 * step "Next" becomes "Send feedback" → submits to Firestore, then shows a
 * thank-you regardless of network outcome (never lose the user's goodwill).
 *
 * Session bookkeeping (open/close/submit coordination) is owned by the TRIGGER
 * that renders this wizard, not the wizard itself — keeping it pure + testable.
 */

import { useCallback, useMemo, useState } from "react";
import { useAuth } from "../auth/authContext";
import {
  COMMENT_SUFFIX,
  LEGACY_MIRROR_IDS,
  type FeedbackStep,
  type IntroStep,
  type McqStep,
  type TextStep,
} from "./steps";
import {
  submitFeedback,
  type FeedbackPayload,
  type FeedbackSource,
} from "./feedbackService";
import * as fs from "./feedbackStyles";
import "./feedback.css";

interface FeedbackWizardProps {
  readonly steps: readonly FeedbackStep[];
  readonly source: FeedbackSource;
  readonly onClose: () => void;
  readonly onSubmitted: () => void;
  /** Light on the home / a light lecture; dark only inside a dark lecture. */
  readonly theme?: "light" | "dark";
}

export function FeedbackWizard({
  steps,
  source,
  onClose,
  onSubmitted,
  theme = "light",
}: FeedbackWizardProps) {
  const { user, profile } = useAuth();
  const [index, setIndex] = useState(0);
  const [ratings, setRatings] = useState<Record<string, number | null>>({});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"form" | "submitting" | "done">("form");

  const step = steps[index];
  const isLast = index === steps.length - 1;

  const totalQuestions = useMemo(
    () => steps.filter((s) => s.kind !== "intro").length,
    [steps],
  );
  const questionsPassed = useMemo(
    () => steps.slice(0, index + 1).filter((s) => s.kind !== "intro").length,
    [steps, index],
  );

  const isAnswered = useCallback(
    (s: FeedbackStep): boolean => {
      if (s.kind === "mcq") return ratings[s.id] != null;
      if (s.kind === "text") return (answers[s.id] ?? "").trim().length > 0;
      return true; // intro
    },
    [ratings, answers],
  );

  const setRating = useCallback(
    (id: string, idx: number) => setRatings((r) => ({ ...r, [id]: idx })),
    [],
  );
  const setAnswer = useCallback(
    (id: string, v: string) => setAnswers((a) => ({ ...a, [id]: v })),
    [],
  );

  const onSubmit = useCallback(async () => {
    setStatus("submitting");
    const finalRatings: Record<string, number | null> = {};
    const ratingLabels: Record<string, string> = {};
    const finalAnswers: Record<string, string> = {};
    for (const s of steps) {
      if (s.kind === "mcq") {
        const idx = ratings[s.id] ?? null;
        finalRatings[s.id] = idx;
        if (idx != null) ratingLabels[s.id] = s.options[idx];
        if (s.withComment !== false) {
          finalAnswers[s.id + COMMENT_SUFFIX] = (answers[s.id + COMMENT_SUFFIX] ?? "").trim();
        }
      } else if (s.kind === "text") {
        finalAnswers[s.id] = (answers[s.id] ?? "").trim();
      }
    }
    const mirror = (id: string) => finalAnswers[id] ?? "";
    const payload: FeedbackPayload = {
      source,
      variant: source === "exit" ? "exit" : "manual",
      ratings: finalRatings,
      ratingLabels,
      answers: finalAnswers,
      liked: mirror(LEGACY_MIRROR_IDS.liked),
      disliked: mirror(LEGACY_MIRROR_IDS.disliked),
      future: mirror(LEGACY_MIRROR_IDS.future),
      note: mirror(LEGACY_MIRROR_IDS.note),
    };
    try {
      await submitFeedback(payload, {
        uid: user?.uid ?? null,
        email: user?.email ?? null,
        name: profile?.name ?? user?.displayName ?? null,
        lectureChapterId: new URLSearchParams(window.location.search).get("lecture"),
      });
    } catch (err) {
      console.error("[feedback] submit failed", err);
    }
    setStatus("done");
    window.setTimeout(onSubmitted, 1100);
  }, [steps, ratings, answers, source, user, profile, onSubmitted]);

  const canAdvance = !step.required || isAnswered(step);

  const goNext = useCallback(() => {
    if (step.required && !isAnswered(step)) return;
    if (isLast) void onSubmit();
    else setIndex((i) => Math.min(i + 1, steps.length - 1));
  }, [step, isAnswered, isLast, onSubmit, steps.length]);

  const goBack = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (status !== "form") return;
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Enter") {
        const inTextarea = (e.target as HTMLElement).tagName === "TEXTAREA";
        // In a textarea, plain Enter inserts a newline; Cmd/Ctrl+Enter advances.
        if (inTextarea && !(e.metaKey || e.ctrlKey)) return;
        e.preventDefault();
        goNext();
      }
    },
    [status, onClose, goNext],
  );

  const nextLabel =
    step.kind === "intro"
      ? (step.cta ?? "Next →")
      : isLast
        ? status === "submitting"
          ? "Sending…"
          : "Send feedback"
        : "Next →";

  return (
    <div
      className="fb-shell"
      data-theme={theme}
      role="dialog"
      aria-modal="true"
      aria-label="Feedback"
      style={fs.backdropStyle}
      onClick={status === "form" ? onClose : undefined}
    >
      <div
        style={{ ...fs.cardStyle, position: "relative" }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        {status === "done" ? (
          <ThankYou />
        ) : (
          <>
            {status === "form" && <CloseButton onClick={onClose} />}
            {step.kind !== "intro" && (
              <ProgressBar total={totalQuestions} passed={questionsPassed} />
            )}

            <div key={step.id} style={fs.bodyStyle}>
              {step.kind === "intro" && <IntroView step={step} />}
              {step.kind === "mcq" && (
                <McqView
                  step={step}
                  selected={ratings[step.id] ?? null}
                  comment={answers[step.id + COMMENT_SUFFIX] ?? ""}
                  onSelect={(idx) => setRating(step.id, idx)}
                  onComment={(v) => setAnswer(step.id + COMMENT_SUFFIX, v)}
                />
              )}
              {step.kind === "text" && (
                <TextView
                  step={step}
                  value={answers[step.id] ?? ""}
                  onChange={(v) => setAnswer(step.id, v)}
                />
              )}
            </div>

            <div style={fs.footerStyle}>
              {index > 0 ? (
                <button type="button" onClick={goBack} style={fs.ghostButtonStyle}>
                  ← Back
                </button>
              ) : (
                <span />
              )}
              <button
                type="button"
                onClick={goNext}
                disabled={!canAdvance || status === "submitting"}
                style={{
                  ...fs.submitButtonStyle,
                  ...(canAdvance ? null : nextDisabledStyle),
                }}
              >
                {nextLabel}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Step renderers ───────────────────────────────────────────────

function IntroView({ step }: { readonly step: IntroStep }) {
  return (
    <div>
      <h2 style={fs.introTitleStyle}>{step.title}</h2>
      <ul style={fs.bulletListStyle}>
        {step.bullets.map((b, i) => (
          <li key={i} style={fs.bulletItemStyle}>
            <span style={fs.bulletDotStyle} aria-hidden />
            <span>{b}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function McqView({
  step,
  selected,
  comment,
  onSelect,
  onComment,
}: {
  readonly step: McqStep;
  readonly selected: number | null;
  readonly comment: string;
  readonly onSelect: (idx: number) => void;
  readonly onComment: (v: string) => void;
}) {
  return (
    <div style={fs.fieldStyle}>
      <div style={fs.promptStyle}>{step.prompt}</div>
      <div style={{ ...fs.optionsStyle, marginTop: 4 }}>
        {step.options.map((opt, idx) => (
          <button
            key={opt}
            type="button"
            onClick={() => onSelect(idx)}
            style={{ ...fs.pillStyle, ...(selected === idx ? fs.pillActiveStyle : null) }}
          >
            {opt}
          </button>
        ))}
      </div>
      {step.withComment !== false && (
        <textarea
          style={{ ...fs.textareaStyle, marginTop: 10 }}
          rows={2}
          value={comment}
          placeholder={step.commentPlaceholder ?? "Want to add why? (optional)"}
          onChange={(e) => onComment(e.target.value)}
          onFocus={focusBorder}
          onBlur={blurBorder}
        />
      )}
    </div>
  );
}

function TextView({
  step,
  value,
  onChange,
}: {
  readonly step: TextStep;
  readonly value: string;
  readonly onChange: (v: string) => void;
}) {
  return (
    <div style={fs.fieldStyle}>
      <div style={fs.promptStyle}>
        {step.prompt}
        {step.required && <span style={requiredStarStyle}> *</span>}
      </div>
      {step.helper && <p style={fs.helperStyle}>{step.helper}</p>}
      <textarea
        style={{ ...fs.textareaStyle, minHeight: 90, marginTop: 4 }}
        rows={4}
        value={value}
        placeholder={step.placeholder}
        autoFocus
        onChange={(e) => onChange(e.target.value)}
        onFocus={focusBorder}
        onBlur={blurBorder}
      />
    </div>
  );
}

function ProgressBar({ total, passed }: { readonly total: number; readonly passed: number }) {
  return (
    <div style={fs.progressRowStyle}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          style={{ ...fs.progressSegStyle, ...(i < passed ? fs.progressSegFilledStyle : null) }}
        />
      ))}
      <span style={fs.progressLabelStyle}>
        {passed}/{total}
      </span>
    </div>
  );
}

function CloseButton({ onClick }: { readonly onClick: () => void }) {
  return (
    <button type="button" aria-label="Close feedback" onClick={onClick} style={closeBtnStyle}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </button>
  );
}

function ThankYou() {
  return (
    <div style={fs.thankYouStyle}>
      <div style={fs.checkOrbStyle} aria-hidden>
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
          <path
            d="M5 12.5 10 17.5 19 7"
            stroke="#0a0a0a"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <div style={fs.thankYouTitleStyle}>Thank you</div>
      <div style={fs.thankYouBodyStyle}>That genuinely helps us build something better.</div>
    </div>
  );
}

// ── Local style helpers ──────────────────────────────────────────

function focusBorder(e: React.FocusEvent<HTMLTextAreaElement>) {
  e.currentTarget.style.borderColor = "var(--fb-accent-border)";
}
function blurBorder(e: React.FocusEvent<HTMLTextAreaElement>) {
  e.currentTarget.style.borderColor = "var(--fb-border)";
}

const nextDisabledStyle: React.CSSProperties = {
  opacity: 0.45,
  cursor: "not-allowed",
};

const requiredStarStyle: React.CSSProperties = {
  color: "var(--fb-accent)",
};

const closeBtnStyle: React.CSSProperties = {
  position: "absolute",
  top: 14,
  right: 14,
  width: 30,
  height: 30,
  display: "grid",
  placeItems: "center",
  borderRadius: 8,
  border: "1px solid var(--fb-border)",
  background: "var(--fb-pill-bg)",
  color: "var(--fb-ink-muted)",
  cursor: "pointer",
  padding: 0,
  zIndex: 1,
};
