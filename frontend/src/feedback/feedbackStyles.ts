/**
 * Shared inline-style vocabulary for the feedback surfaces. Lifted out of the
 * old single-dialog FeedbackModal so the wizard and its step renderers consume
 * exactly one set of consts. Inline `CSSProperties` matches the codebase
 * convention (no CSS modules / tailwind).
 *
 * Theme-aware: every colour reads a `--fb-*` variable defined per theme in
 * feedback.css (`.fb-shell[data-theme]`). The FeedbackWizard root carries that
 * class + data-theme, so the modal is light on the home / a light lecture and
 * dark inside a dark lecture. Geometry (sizes, padding, radii) is unchanged.
 */

import { DISPLAY_FONT, MONO_FONT } from "../styles/fonts";

export const backdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 20,
  background: "var(--fb-scrim)",
  backdropFilter: "blur(10px) saturate(1.1)",
  WebkitBackdropFilter: "blur(10px) saturate(1.1)",
};

export const cardStyle: React.CSSProperties = {
  width: "min(480px, 94vw)",
  maxHeight: "88vh",
  overflowY: "auto",
  background: "var(--fb-card-bg)",
  borderRadius: 20,
  border: "1px solid var(--fb-border)",
  padding: "26px 26px 22px",
  boxShadow: "var(--fb-shadow)",
  backdropFilter: "blur(20px) saturate(1.2)",
  WebkitBackdropFilter: "blur(20px) saturate(1.2)",
  fontFamily: DISPLAY_FONT,
};

export const titleStyle: React.CSSProperties = {
  fontSize: "1.2rem",
  fontWeight: 700,
  color: "var(--fb-ink)",
  margin: "0 0 6px",
  letterSpacing: "-0.01em",
};

export const subtitleStyle: React.CSSProperties = {
  fontSize: "0.88rem",
  color: "var(--fb-ink-muted)",
  margin: "0 0 22px",
};

export const bodyStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 20,
};

export const promptStyle: React.CSSProperties = {
  fontSize: "0.98rem",
  fontWeight: 600,
  color: "var(--fb-ink)",
  lineHeight: 1.45,
};

export const helperStyle: React.CSSProperties = {
  fontSize: "0.8rem",
  color: "var(--fb-accent)",
  lineHeight: 1.45,
  margin: "6px 0 0",
};

export const optionsStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 7,
};

export const pillStyle: React.CSSProperties = {
  flex: "1 1 auto",
  minWidth: 72,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid var(--fb-border)",
  background: "var(--fb-pill-bg)",
  color: "var(--fb-ink-muted)",
  fontSize: "0.8rem",
  fontWeight: 500,
  fontFamily: "inherit",
  cursor: "pointer",
  transition: "background 140ms ease, border-color 140ms ease, color 140ms ease",
};

export const pillActiveStyle: React.CSSProperties = {
  background: "var(--fb-accent-bg)",
  borderColor: "var(--fb-accent-border)",
  color: "var(--fb-accent-text)",
  fontWeight: 600,
};

export const fieldStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 7,
};

export const fieldLabelStyle: React.CSSProperties = {
  fontSize: "0.82rem",
  fontWeight: 600,
  color: "var(--fb-ink)",
};

export const commentLabelStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  fontWeight: 500,
  color: "var(--fb-ink-muted)",
};

export const textareaStyle: React.CSSProperties = {
  resize: "vertical",
  minHeight: 44,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid var(--fb-border)",
  background: "var(--fb-field-bg)",
  color: "var(--fb-ink)",
  fontSize: "0.88rem",
  fontFamily: "inherit",
  lineHeight: 1.5,
  outline: "none",
  boxSizing: "border-box",
  transition: "border-color 150ms ease, box-shadow 150ms ease",
};

export const footerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 10,
  marginTop: 24,
};

export const ghostButtonStyle: React.CSSProperties = {
  padding: "11px 18px",
  borderRadius: 11,
  border: "1px solid var(--fb-border)",
  background: "transparent",
  color: "var(--fb-ink-muted)",
  fontSize: "0.9rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
};

export const submitButtonStyle: React.CSSProperties = {
  padding: "11px 20px",
  borderRadius: 11,
  border: "1px solid var(--fb-accent-border)",
  background: "var(--fb-accent-bg)",
  color: "var(--fb-accent-text)",
  fontSize: "0.9rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
  boxShadow: "var(--fb-inset)",
};

// ── Wizard chrome ────────────────────────────────────────────────

export const progressRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  marginBottom: 18,
};

export const progressSegStyle: React.CSSProperties = {
  flex: 1,
  height: 3,
  borderRadius: 999,
  background: "var(--fb-track)",
  transition: "background 200ms ease",
};

export const progressSegFilledStyle: React.CSSProperties = {
  background: "var(--fb-accent)",
};

export const progressLabelStyle: React.CSSProperties = {
  fontFamily: MONO_FONT,
  fontSize: "0.72rem",
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--fb-ink-faint)",
  marginLeft: 8,
  whiteSpace: "nowrap",
};

// ── Intro splash ─────────────────────────────────────────────────

export const introTitleStyle: React.CSSProperties = {
  fontSize: "1.35rem",
  fontWeight: 700,
  color: "var(--fb-ink)",
  margin: "0 0 18px",
  letterSpacing: "-0.01em",
  lineHeight: 1.3,
};

export const bulletListStyle: React.CSSProperties = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  display: "flex",
  flexDirection: "column",
  gap: 14,
};

export const bulletItemStyle: React.CSSProperties = {
  display: "flex",
  gap: 11,
  fontSize: "0.92rem",
  lineHeight: 1.5,
  color: "var(--fb-ink)",
};

export const bulletDotStyle: React.CSSProperties = {
  flex: "0 0 auto",
  width: 7,
  height: 7,
  marginTop: 7,
  borderRadius: "50%",
  background: "var(--fb-accent)",
};

// ── Thank-you ────────────────────────────────────────────────────

export const thankYouStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  textAlign: "center",
  padding: "22px 8px 14px",
};

export const checkOrbStyle: React.CSSProperties = {
  width: 52,
  height: 52,
  borderRadius: "50%",
  display: "grid",
  placeItems: "center",
  background: "var(--fb-accent)",
  boxShadow: "0 10px 30px var(--fb-accent-glow)",
  marginBottom: 16,
};

export const thankYouTitleStyle: React.CSSProperties = {
  fontSize: "1.15rem",
  fontWeight: 700,
  color: "var(--fb-ink)",
  marginBottom: 6,
};

export const thankYouBodyStyle: React.CSSProperties = {
  fontSize: "0.88rem",
  color: "var(--fb-ink-muted)",
  lineHeight: 1.5,
};
