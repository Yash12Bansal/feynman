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

export type AskFeynmanState = "idle" | "listening" | "thinking";

interface AskFeynmanButtonProps {
  readonly state: AskFeynmanState;
  readonly onActivate: () => void;
}

export function AskFeynmanButton({ state, onActivate }: AskFeynmanButtonProps) {
  const disabled = state !== "idle";

  const onClick = useCallback(() => {
    if (!disabled) onActivate();
  }, [disabled, onActivate]);

  return (
    <button
      type="button"
      aria-label="Ask Feynman a question"
      data-testid="ask-feynman-button"
      data-state={state}
      disabled={disabled}
      onClick={onClick}
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
        border: "2px solid rgba(232, 232, 238, 0.25)",
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
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontSize: "0.95rem",
  fontWeight: 600,
  letterSpacing: "0.01em",
  cursor: "pointer",
  transition:
    "background 220ms ease, border-color 220ms ease, transform 220ms ease",
  zIndex: 10,
  boxShadow: "0 10px 30px rgba(0, 0, 0, 0.5)",
};

const buttonStateStyle: Record<AskFeynmanState, React.CSSProperties> = {
  idle: {
    background: "#1b3a4a",
    color: "#7fd4ff",
    borderColor: "rgba(127, 212, 255, 0.35)",
  },
  listening: {
    background: "#3a1b1f",
    color: "#ff7a8a",
    borderColor: "rgba(255, 122, 138, 0.35)",
    cursor: "default",
  },
  thinking: {
    background: "#1a1c20",
    color: "rgba(232, 232, 238, 0.65)",
    borderColor: "rgba(232, 232, 238, 0.12)",
    cursor: "default",
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
