/**
 * Modal overlay shown at the end of a doubt resolution.
 *
 * Four options — Crystal clear (primary), Counter-doubt, Somewhat cleared,
 * Start over. The parent (LectureViewer) decides when to render this and
 * what to do with the chosen key (publish back to the worker over the
 * `doubt_signal` data channel).
 *
 * Presentational only. Stays out of the way of the SplitBoard underneath
 * via a translucent backdrop with backdrop-filter blur.
 */

import { useCallback } from "react";

export interface SatisfactionOption {
  readonly key: string;
  readonly label: string;
  readonly description: string;
}

interface SatisfactionPromptProps {
  readonly options: readonly SatisfactionOption[];
  readonly onChoose: (key: string) => void;
}

export function SatisfactionPrompt({
  options,
  onChoose,
}: SatisfactionPromptProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="How clear was that?"
      data-testid="satisfaction-prompt"
      style={backdropStyle}
    >
      <div style={cardStyle}>
        <h2 style={titleStyle}>How clear was that?</h2>
        <div style={listStyle}>
          {options.map((opt, index) => (
            <SatisfactionButton
              key={opt.key}
              option={opt}
              variant={index === 0 ? "primary" : "secondary"}
              onChoose={onChoose}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

interface SatisfactionButtonProps {
  readonly option: SatisfactionOption;
  readonly variant: "primary" | "secondary";
  readonly onChoose: (key: string) => void;
}

function SatisfactionButton({
  option,
  variant,
  onChoose,
}: SatisfactionButtonProps) {
  const onClick = useCallback(
    () => onChoose(option.key),
    [option.key, onChoose],
  );
  return (
    <button
      type="button"
      data-testid={`satisfaction-option-${option.key}`}
      data-variant={variant}
      onClick={onClick}
      style={{
        ...buttonBaseStyle,
        ...(variant === "primary" ? primaryButtonStyle : secondaryButtonStyle),
      }}
    >
      <span style={labelStyle}>{option.label}</span>
      <span style={descStyle}>{option.description}</span>
    </button>
  );
}

// ── Styles ──────────────────────────────────────────────────────

const backdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 20,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(10, 10, 12, 0.55)",
  backdropFilter: "blur(6px)",
  WebkitBackdropFilter: "blur(6px)",
};

const cardStyle: React.CSSProperties = {
  background: "#0f0f12",
  borderRadius: 18,
  border: "1px solid rgba(255, 255, 255, 0.08)",
  padding: "28px 28px 24px",
  width: "min(440px, 90vw)",
  boxShadow: "0 20px 60px rgba(0, 0, 0, 0.6)",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const titleStyle: React.CSSProperties = {
  fontSize: "1.1rem",
  fontWeight: 600,
  color: "#fafafa",
  margin: "0 0 18px",
  letterSpacing: "-0.005em",
};

const listStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 10,
};

const buttonBaseStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "14px 18px",
  borderRadius: 12,
  border: "1px solid rgba(255, 255, 255, 0.08)",
  cursor: "pointer",
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontFamily: "inherit",
  transition:
    "background 180ms ease, border-color 180ms ease, transform 180ms ease",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "#1b3a4a",
  color: "#7fd4ff",
  borderColor: "rgba(127, 212, 255, 0.4)",
};

const secondaryButtonStyle: React.CSSProperties = {
  background: "#141417",
  color: "#e8e8ee",
  borderColor: "rgba(255, 255, 255, 0.06)",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.96rem",
  fontWeight: 600,
};

const descStyle: React.CSSProperties = {
  fontSize: "0.82rem",
  color: "rgba(232, 232, 238, 0.55)",
  fontWeight: 400,
};
