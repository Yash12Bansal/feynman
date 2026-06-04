/**
 * Always-available manual feedback button, fixed bottom-left (Ask Feynman owns
 * bottom-right). Opens the lighter "manual" feedback form. Kept subtle so it
 * doesn't compete with the lecture — fades up to full opacity on hover.
 */

import { useState } from "react";
import { FeedbackModal } from "./FeedbackModal";

export function FeedbackFab() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-label="Send feedback"
        onClick={() => setOpen(true)}
        style={fabStyle}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "translateY(-1px)";
          e.currentTarget.style.opacity = "1";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "translateY(0)";
          e.currentTarget.style.opacity = "0.82";
        }}
      >
        <ChatGlyph />
        <span style={labelStyle}>Feedback</span>
      </button>
      {open && (
        <FeedbackModal
          variant="manual"
          onClose={() => setOpen(false)}
          onSubmitted={() => setOpen(false)}
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
  border: "1px solid rgba(255, 255, 255, 0.1)",
  background: "rgba(20, 20, 32, 0.62)",
  backdropFilter: "blur(8px)",
  WebkitBackdropFilter: "blur(8px)",
  color: "rgba(232, 232, 238, 0.85)",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontSize: "0.88rem",
  fontWeight: 600,
  cursor: "pointer",
  opacity: 0.82,
  transition: "transform 200ms ease, opacity 200ms ease",
  zIndex: 100,
  boxShadow: "0 10px 30px rgba(0, 0, 0, 0.45)",
};

const labelStyle: React.CSSProperties = {
  whiteSpace: "nowrap",
};
