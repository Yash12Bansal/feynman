/**
 * Always-available feedback button, fixed bottom-left (Ask Feynman owns
 * bottom-right). Opens the full feedback wizard. Made deliberately visible (a
 * real accent-bordered CTA, not faint chrome) and given a PERIODIC attention
 * pulse — a short glow every ~35s, then rest — so it gently asks to be noticed
 * without nagging. The pulse is suppressed while any feedback wizard is open,
 * disabled under prefers-reduced-motion, held off for the first 30s, and stops
 * for good once the user has submitted feedback this session.
 */

import { useEffect, useRef, useState } from "react";
import { FeedbackModal } from "./FeedbackModal";
import { feedbackSession } from "./feedbackSession";
import { DISPLAY_FONT } from "../styles/fonts";

const KEYFRAMES_ID = "fb-fab-keyframes";
const FIRST_PULSE_DELAY_MS = 30_000;
const PULSE_PERIOD_MS = 35_000;
const PULSE_DURATION_MS = 1_800;

/** Inject the attention keyframe once (mirrors AskFeynmanButton's pattern). */
function ensureKeyframes(): void {
  if (typeof document === "undefined" || document.getElementById(KEYFRAMES_ID)) return;
  const el = document.createElement("style");
  el.id = KEYFRAMES_ID;
  el.textContent = `
@keyframes fb-fab-attention {
  0%   { box-shadow: 0 0 0 0 rgba(127, 212, 255, 0.55), 0 10px 34px rgba(0, 0, 0, 0.5); }
  70%  { box-shadow: 0 0 0 14px rgba(127, 212, 255, 0), 0 10px 34px rgba(0, 0, 0, 0.5); }
  100% { box-shadow: 0 0 0 0 rgba(127, 212, 255, 0), 0 10px 34px rgba(0, 0, 0, 0.5); }
}`;
  document.head.appendChild(el);
}

export function FeedbackFab() {
  const [open, setOpen] = useState(false);
  const [pulsing, setPulsing] = useState(false);
  const openRef = useRef(false);
  useEffect(() => {
    openRef.current = open;
  }, [open]);

  useEffect(() => {
    ensureKeyframes();
    if (typeof window === "undefined") return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reduce) return;

    let offTimer: number | undefined;
    const tick = () => {
      // Don't pulse while a wizard is open (anywhere) or after a submission.
      if (openRef.current || feedbackSession.isOpen() || feedbackSession.hasSubmitted()) return;
      setPulsing(true);
      offTimer = window.setTimeout(() => setPulsing(false), PULSE_DURATION_MS);
    };
    const first = window.setTimeout(tick, FIRST_PULSE_DELAY_MS);
    const interval = window.setInterval(tick, PULSE_PERIOD_MS);
    return () => {
      window.clearTimeout(first);
      window.clearTimeout(offTimer);
      window.clearInterval(interval);
    };
  }, []);

  const onActivate = () => {
    if (feedbackSession.isOpen()) return;
    setPulsing(false);
    feedbackSession.markOpened();
    setOpen(true);
  };

  return (
    <>
      <button
        type="button"
        aria-label="Send feedback"
        onClick={onActivate}
        style={{
          ...fabStyle,
          ...(pulsing ? { animation: "fb-fab-attention 1.6s ease-out" } : null),
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "translateY(-1px)";
          e.currentTarget.style.opacity = "1";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "translateY(0)";
          e.currentTarget.style.opacity = "0.95";
        }}
      >
        <ChatGlyph />
        <span style={labelStyle}>Feedback</span>
      </button>
      {open && (
        <FeedbackModal
          variant="manual"
          onClose={() => {
            setOpen(false);
            feedbackSession.markClosed();
          }}
          onSubmitted={() => {
            setOpen(false);
            feedbackSession.markSubmitted();
          }}
        />
      )}
    </>
  );
}

function ChatGlyph() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 0 1-.9-3.8A8.38 8.38 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const fabStyle: React.CSSProperties = {
  // Bottom-left, lifted above the lecture's Pause button (bottom:32, 52px tall)
  // so it never overlaps. Ask Feynman owns bottom-right.
  position: "fixed",
  bottom: 100,
  left: 32,
  display: "flex",
  alignItems: "center",
  gap: 9,
  padding: "11px 18px",
  borderRadius: 999,
  border: "1px solid rgba(127, 212, 255, 0.40)",
  background: "rgba(18, 32, 48, 0.62)",
  backdropFilter: "blur(18px) saturate(1.2)",
  WebkitBackdropFilter: "blur(18px) saturate(1.2)",
  color: "#cdeeff",
  fontFamily: DISPLAY_FONT,
  fontSize: "0.88rem",
  fontWeight: 600,
  cursor: "pointer",
  opacity: 0.95,
  transition: "transform 200ms ease, opacity 200ms ease",
  zIndex: 100,
  boxShadow:
    "0 10px 34px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07), 0 0 0 1px rgba(127,212,255,0.16)",
};

const labelStyle: React.CSSProperties = {
  whiteSpace: "nowrap",
};
