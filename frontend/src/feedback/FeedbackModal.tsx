/**
 * Feedback modal. Two variants share one form:
 *   - "exit": the full 5-MCQ survey + liked / disliked / future free-text.
 *   - "manual": a lighter pulse — one quick rating + a free note + a wish.
 *
 * Submits to Firestore via feedbackService, then shows a thank-you regardless
 * of network outcome (never lose the user's goodwill over a failed write).
 */

import { useCallback, useMemo, useState } from "react";
import { useAuth } from "../auth/authContext";
import { EXIT_MCQS, MANUAL_QUICK, type McqQuestion } from "./questions";
import { submitFeedback, type FeedbackPayload } from "./feedbackService";

interface FeedbackModalProps {
  readonly variant: "exit" | "manual";
  readonly onClose: () => void;
  readonly onSubmitted: () => void;
}

export function FeedbackModal({ variant, onClose, onSubmitted }: FeedbackModalProps) {
  const { user, profile } = useAuth();
  const questions = useMemo<readonly McqQuestion[]>(
    () => (variant === "exit" ? EXIT_MCQS : [MANUAL_QUICK]),
    [variant],
  );

  const [ratings, setRatings] = useState<Record<string, number | null>>({});
  const [liked, setLiked] = useState("");
  const [disliked, setDisliked] = useState("");
  const [future, setFuture] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<"form" | "submitting" | "done">("form");

  const select = useCallback((id: string, idx: number) => {
    setRatings((r) => ({ ...r, [id]: idx }));
  }, []);

  const onSubmit = useCallback(async () => {
    setStatus("submitting");
    const ratingLabels: Record<string, string> = {};
    for (const q of questions) {
      const idx = ratings[q.id];
      if (idx != null) ratingLabels[q.id] = q.options[idx];
    }
    const payload: FeedbackPayload = {
      variant,
      ratings: Object.fromEntries(questions.map((q) => [q.id, ratings[q.id] ?? null])),
      ratingLabels,
      liked: liked.trim(),
      disliked: disliked.trim(),
      future: future.trim(),
      note: note.trim(),
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
  }, [questions, ratings, liked, disliked, future, note, variant, user, profile, onSubmitted]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Feedback"
      style={backdropStyle}
      onClick={status === "form" ? onClose : undefined}
    >
      <div style={cardStyle} onClick={(e) => e.stopPropagation()}>
        {status === "done" ? (
          <ThankYou />
        ) : (
          <>
            <h2 style={titleStyle}>
              {variant === "exit" ? "Before you go — got 30 seconds?" : "Share feedback"}
            </h2>
            <p style={subtitleStyle}>
              {variant === "exit"
                ? "Your honest take shapes what we build next."
                : "Tell us anything — good or bad."}
            </p>

            <div style={bodyStyle}>
              {questions.map((q) => (
                <McqRow
                  key={q.id}
                  question={q}
                  selected={ratings[q.id] ?? null}
                  onSelect={select}
                />
              ))}

              {variant === "exit" ? (
                <>
                  <TextField label="One thing you liked" value={liked} onChange={setLiked} placeholder="What worked for you?" />
                  <TextField label="One thing you completely disliked" value={disliked} onChange={setDisliked} placeholder="Be brutal — it helps." />
                  <TextField label="What would you like to see in future versions?" value={future} onChange={setFuture} placeholder="Dream a little." />
                </>
              ) : (
                <>
                  <TextField label="What's on your mind?" value={note} onChange={setNote} placeholder="A bug, a moment that clicked, a wish…" />
                  <TextField label="Anything you'd love to see?" value={future} onChange={setFuture} placeholder="Optional" />
                </>
              )}
            </div>

            <div style={footerStyle}>
              <button
                type="button"
                onClick={onClose}
                style={ghostButtonStyle}
                disabled={status === "submitting"}
              >
                {variant === "exit" ? "No thanks" : "Cancel"}
              </button>
              <button
                type="button"
                onClick={onSubmit}
                style={submitButtonStyle}
                disabled={status === "submitting"}
              >
                {status === "submitting" ? "Sending…" : "Send feedback"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function McqRow({
  question,
  selected,
  onSelect,
}: {
  readonly question: McqQuestion;
  readonly selected: number | null;
  readonly onSelect: (id: string, idx: number) => void;
}) {
  return (
    <div style={rowStyle}>
      <div style={promptStyle}>{question.prompt}</div>
      <div style={optionsStyle}>
        {question.options.map((opt, idx) => (
          <button
            key={opt}
            type="button"
            onClick={() => onSelect(question.id, idx)}
            style={{ ...pillStyle, ...(selected === idx ? pillActiveStyle : null) }}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (v: string) => void;
  readonly placeholder?: string;
}) {
  return (
    <div style={fieldStyle}>
      <label style={fieldLabelStyle}>{label}</label>
      <textarea
        style={textareaStyle}
        value={value}
        rows={2}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onFocus={(e) => (e.currentTarget.style.borderColor = "rgba(127, 212, 255, 0.5)")}
        onBlur={(e) => (e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.10)")}
      />
    </div>
  );
}

function ThankYou() {
  return (
    <div style={thankYouStyle}>
      <div style={checkOrbStyle} aria-hidden>
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
      <div style={thankYouTitleStyle}>Thank you</div>
      <div style={thankYouBodyStyle}>That genuinely helps us build something better.</div>
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────

const backdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 20,
  background: "rgba(6, 6, 10, 0.6)",
  backdropFilter: "blur(8px)",
  WebkitBackdropFilter: "blur(8px)",
};

const cardStyle: React.CSSProperties = {
  width: "min(480px, 94vw)",
  maxHeight: "88vh",
  overflowY: "auto",
  background: "#0f0f14",
  borderRadius: 20,
  border: "1px solid rgba(255, 255, 255, 0.1)",
  padding: "26px 26px 22px",
  boxShadow: "0 30px 80px rgba(0, 0, 0, 0.65)",
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const titleStyle: React.CSSProperties = {
  fontSize: "1.2rem",
  fontWeight: 700,
  color: "#fafafa",
  margin: "0 0 6px",
  letterSpacing: "-0.01em",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "0.88rem",
  color: "rgba(240, 240, 240, 0.5)",
  margin: "0 0 22px",
};

const bodyStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 20,
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 9,
};

const promptStyle: React.CSSProperties = {
  fontSize: "0.92rem",
  fontWeight: 600,
  color: "#e8e8ee",
  lineHeight: 1.4,
};

const optionsStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 7,
};

const pillStyle: React.CSSProperties = {
  flex: "1 1 auto",
  minWidth: 72,
  padding: "8px 10px",
  borderRadius: 10,
  border: "1px solid rgba(255, 255, 255, 0.1)",
  background: "rgba(255, 255, 255, 0.03)",
  color: "rgba(232, 232, 238, 0.72)",
  fontSize: "0.76rem",
  fontWeight: 500,
  fontFamily: "inherit",
  cursor: "pointer",
  transition: "background 140ms ease, border-color 140ms ease, color 140ms ease",
};

const pillActiveStyle: React.CSSProperties = {
  background: "#1b3a4a",
  borderColor: "rgba(127, 212, 255, 0.5)",
  color: "#7fd4ff",
  fontWeight: 600,
};

const fieldStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 7,
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "0.82rem",
  fontWeight: 600,
  color: "#e8e8ee",
};

const textareaStyle: React.CSSProperties = {
  resize: "vertical",
  minHeight: 44,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid rgba(255, 255, 255, 0.10)",
  background: "rgba(255, 255, 255, 0.04)",
  color: "#f0f0f0",
  fontSize: "0.88rem",
  fontFamily: "inherit",
  lineHeight: 1.5,
  outline: "none",
  boxSizing: "border-box",
  transition: "border-color 150ms ease",
};

const footerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: 10,
  marginTop: 22,
};

const ghostButtonStyle: React.CSSProperties = {
  padding: "11px 18px",
  borderRadius: 11,
  border: "1px solid rgba(255, 255, 255, 0.1)",
  background: "transparent",
  color: "rgba(232, 232, 238, 0.7)",
  fontSize: "0.9rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
};

const submitButtonStyle: React.CSSProperties = {
  padding: "11px 20px",
  borderRadius: 11,
  border: "1px solid rgba(127, 212, 255, 0.4)",
  background: "#1b3a4a",
  color: "#7fd4ff",
  fontSize: "0.9rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
};

const thankYouStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  textAlign: "center",
  padding: "22px 8px 14px",
};

const checkOrbStyle: React.CSSProperties = {
  width: 52,
  height: 52,
  borderRadius: "50%",
  display: "grid",
  placeItems: "center",
  background: "linear-gradient(135deg, #4ade80, #7fd4ff)",
  boxShadow: "0 10px 30px rgba(74, 222, 128, 0.35)",
  marginBottom: 16,
};

const thankYouTitleStyle: React.CSSProperties = {
  fontSize: "1.15rem",
  fontWeight: 700,
  color: "#fafafa",
  marginBottom: 6,
};

const thankYouBodyStyle: React.CSSProperties = {
  fontSize: "0.88rem",
  color: "rgba(240, 240, 240, 0.55)",
  lineHeight: 1.5,
};
