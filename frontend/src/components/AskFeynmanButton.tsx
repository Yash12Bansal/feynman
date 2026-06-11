/**
 * Floating "Ask Feynman" button overlaid on the LectureViewer.
 *
 * Three visual states drive the affordance:
 *   - idle:      blue pill, "Ask Feynman" label, mic glyph, tap-to-activate
 *   - listening: pulsing red dot, "I'm listening…" label, inert (the worker
 *                ends the capture on VAD silence, the student doesn't have
 *                to tap again)
 *   - thinking:  spinner, "Feynman is thinking…" label, inert
 *
 * The button is presentational. The parent (LectureViewer) drives state
 * transitions: tap → frontend pauses playback + sends a doubt_intent over
 * the LiveKit data channel; worker emits doubt_captured → parent flips us
 * to "thinking"; Phase 4+ resolution finishes → parent flips back to idle.
 */

import { useCallback } from "react";
import { DISPLAY_FONT } from "../styles/fonts";

export type AskFeynmanState = "idle" | "listening" | "thinking" | "error";

interface AskFeynmanButtonProps {
  readonly state: AskFeynmanState;
  readonly onActivate: () => void;
  /** Required when state==="error". The parent passes a retry handler. */
  readonly onRetry?: () => void;
  /** Required when state==="error". Shown alongside the "Try again" button. */
  readonly errorMessage?: string;
}

export function AskFeynmanButton({
  state,
  onActivate,
  onRetry,
  errorMessage,
}: AskFeynmanButtonProps) {
  const disabled = state !== "idle";

  const onClick = useCallback(() => {
    if (!disabled) onActivate();
  }, [disabled, onActivate]);

  const onRetryClick = useCallback(() => {
    onRetry?.();
  }, [onRetry]);

  if (state === "error") {
    return (
      <div
        data-testid="ask-feynman-button"
        data-state="error"
        style={{ ...buttonBaseStyle, ...buttonStateStyle.error }}
      >
        <span aria-hidden style={glyphStyle}>
          <WarningGlyph />
        </span>
        <span style={errorMessageStyle}>
          {errorMessage ?? "Something went wrong."}
        </span>
        <button
          type="button"
          data-testid="ask-feynman-retry"
          onClick={onRetryClick}
          style={retryButtonStyle}
        >
          ↻ Try again
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      aria-label="Ask Feynman a question"
      data-testid="ask-feynman-button"
      data-state={state}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={(e) => {
        if (state !== "idle") return;
        e.currentTarget.style.transform = "translateY(-1px)";
        e.currentTarget.style.boxShadow =
          "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07), 0 0 0 1px rgba(127,212,255,0.4), 0 6px 24px rgba(127,212,255,0.16)";
      }}
      onMouseLeave={(e) => {
        if (state !== "idle") return;
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow =
          "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07), 0 0 0 1px rgba(127,212,255,0.18), 0 6px 24px rgba(127,212,255,0.14)";
      }}
      style={{
        ...buttonBaseStyle,
        ...buttonStateStyle[state],
      }}
    >
      <span aria-hidden style={glyphStyle}>
        {state === "thinking" ? (
          <Spinner />
        ) : state === "listening" ? (
          <PulsingDot />
        ) : (
          <MicGlyph />
        )}
      </span>
      <span style={labelStyle}>{LABELS[state]}</span>
    </button>
  );
}

const LABELS: Record<AskFeynmanState, string> = {
  idle: "Ask Feynman",
  listening: "I'm listening…",
  thinking: "Feynman is thinking…",
  error: "Something went wrong",
};

// ── Sub-glyphs ─────────────────────────────────────────────────

function MicGlyph() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 14a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v4a3 3 0 0 0 3 3Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M5 11a7 7 0 0 0 14 0M12 18v3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function PulsingDot() {
  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: "#ff7a8a",
        boxShadow: "0 0 0 0 rgba(255, 122, 138, 0.7)",
        animation: "afb-pulse 1.6s ease-out infinite",
      }}
    />
  );
}

function Spinner() {
  return (
    <span
      style={{
        display: "inline-block",
        width: 14,
        height: 14,
        borderRadius: "50%",
        border: "2px solid rgba(244,246,251,0.18)",
        borderTopColor: "#7fd4ff",
        animation: "afb-spin 0.9s linear infinite",
      }}
    />
  );
}

// ── Styles ─────────────────────────────────────────────────────

const buttonBaseStyle: React.CSSProperties = {
  position: "fixed",
  bottom: 32,
  right: 32,
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "14px 22px",
  borderRadius: 999,
  border: "1px solid rgba(255, 255, 255, 0.08)",
  fontFamily: DISPLAY_FONT,
  fontSize: "0.95rem",
  fontWeight: 600,
  letterSpacing: "0.01em",
  cursor: "pointer",
  backdropFilter: "blur(18px) saturate(1.2)",
  WebkitBackdropFilter: "blur(18px) saturate(1.2)",
  transition:
    "background 220ms cubic-bezier(0.22,0.61,0.36,1), border-color 220ms ease, box-shadow 220ms ease, transform 220ms cubic-bezier(0.22,0.61,0.36,1)",
  zIndex: 10,
  boxShadow: "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07)",
};

const buttonStateStyle: Record<AskFeynmanState, React.CSSProperties> = {
  idle: {
    background: "rgba(18,32,48,0.6)",
    color: "#9fdcff",
    borderColor: "rgba(127, 212, 255, 0.4)",
    boxShadow:
      "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07), 0 0 0 1px rgba(127,212,255,0.18), 0 6px 24px rgba(127,212,255,0.14)",
  },
  listening: {
    background: "rgba(44,22,28,0.6)",
    color: "#ff9aa6",
    borderColor: "rgba(255, 122, 138, 0.4)",
    boxShadow:
      "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07), 0 0 0 1px rgba(255,122,138,0.22), 0 6px 26px rgba(255,122,138,0.18)",
    cursor: "default",
  },
  thinking: {
    background: "rgba(16,18,26,0.66)",
    color: "rgba(244,246,251,0.68)",
    borderColor: "rgba(255, 255, 255, 0.1)",
    cursor: "default",
  },
  error: {
    background: "rgba(42,22,28,0.62)",
    color: "#ffb4be",
    borderColor: "rgba(255, 180, 190, 0.32)",
    cursor: "default",
    // Slightly wider so the inline retry button fits without wrapping.
    maxWidth: 420,
  },
};

const glyphStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 20,
  height: 20,
};

const labelStyle: React.CSSProperties = {
  fontVariantLigatures: "none",
  whiteSpace: "nowrap",
};

const errorMessageStyle: React.CSSProperties = {
  fontVariantLigatures: "none",
  fontSize: "0.85rem",
  fontWeight: 500,
  lineHeight: 1.35,
  flex: 1,
  whiteSpace: "normal",
};

const retryButtonStyle: React.CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(255, 180, 190, 0.5)",
  color: "#ffb4be",
  fontFamily: "inherit",
  fontSize: "0.8rem",
  fontWeight: 600,
  padding: "6px 12px",
  borderRadius: 999,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

function WarningGlyph() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 3 22 21H2L12 3Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M12 10v5M12 18v.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

// Inject keyframes once on module load (inline styles can't carry @keyframes).
if (typeof document !== "undefined") {
  const KEY = "ask-feynman-button-keyframes";
  if (!document.getElementById(KEY)) {
    const style = document.createElement("style");
    style.id = KEY;
    style.textContent = `
@keyframes afb-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(255, 122, 138, 0.7); }
  70%  { box-shadow: 0 0 0 10px rgba(255, 122, 138, 0); }
  100% { box-shadow: 0 0 0 0 rgba(255, 122, 138, 0); }
}
@keyframes afb-spin { to { transform: rotate(360deg); } }
`;
    document.head.appendChild(style);
  }
}
