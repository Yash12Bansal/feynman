/**
 * Shared inline-style vocabulary for the feedback surfaces. Lifted out of the
 * old single-dialog FeedbackModal so the wizard and its step renderers consume
 * exactly one set of consts. Inline `CSSProperties` matches the codebase
 * convention (no CSS modules / tailwind).
 *
 * "Premium Deep-Space Glass" redesign: colors/glass only — every geometric
 * value (sizes, padding, radii, gaps, heights) is preserved.
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
  background: "rgba(7, 7, 13, 0.62)",
  backdropFilter: "blur(10px) saturate(1.1)",
  WebkitBackdropFilter: "blur(10px) saturate(1.1)",
};

export const cardStyle: React.CSSProperties = {
  width: "min(480px, 94vw)",
  maxHeight: "88vh",
  overflowY: "auto",
  background:
    "radial-gradient(120% 100% at 50% 0%, rgba(127,212,255,0.05), transparent 55%), rgba(11,12,20,0.92)",
  borderRadius: 20,
  border: "1px solid rgba(255, 255, 255, 0.1)",
  padding: "26px 26px 22px",
  boxShadow: "0 30px 80px rgba(0,0,0,0.65), inset 0 1px 0 rgba(255,255,255,0.06)",
  backdropFilter: "blur(20px) saturate(1.2)",
  WebkitBackdropFilter: "blur(20px) saturate(1.2)",
  fontFamily: DISPLAY_FONT,
};

export const titleStyle: React.CSSProperties = {
  fontSize: "1.2rem",
  fontWeight: 700,
  color: "#f4f6fb",
  margin: "0 0 6px",
  letterSpacing: "-0.01em",
};

export const subtitleStyle: React.CSSProperties = {
  fontSize: "0.88rem",
  color: "rgba(244,246,251,0.55)",
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
  color: "#f4f6fb",
  lineHeight: 1.45,
};

export const helperStyle: React.CSSProperties = {
  fontSize: "0.8rem",
  color: "rgba(127, 212, 255, 0.72)",
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
  border: "1px solid rgba(255, 255, 255, 0.1)",
  background: "rgba(255, 255, 255, 0.03)",
  color: "rgba(244,246,251,0.72)",
  fontSize: "0.8rem",
  fontWeight: 500,
  fontFamily: "inherit",
  cursor: "pointer",
  transition: "background 140ms ease, border-color 140ms ease, color 140ms ease",
};

export const pillActiveStyle: React.CSSProperties = {
  background: "rgba(18,32,48,0.6)",
  borderColor: "rgba(127, 212, 255, 0.5)",
  color: "#9fdcff",
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
  color: "#f4f6fb",
};

export const commentLabelStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  fontWeight: 500,
  color: "rgba(244,246,251,0.55)",
};

export const textareaStyle: React.CSSProperties = {
  resize: "vertical",
  minHeight: 44,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid rgba(255, 255, 255, 0.10)",
  background: "rgba(255, 255, 255, 0.04)",
  color: "#f4f6fb",
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
  border: "1px solid rgba(255, 255, 255, 0.1)",
  background: "transparent",
  color: "rgba(244,246,251,0.7)",
  fontSize: "0.9rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
};

export const submitButtonStyle: React.CSSProperties = {
  padding: "11px 20px",
  borderRadius: 11,
  border: "1px solid rgba(127, 212, 255, 0.4)",
  background: "rgba(18,32,48,0.6)",
  color: "#9fdcff",
  fontSize: "0.9rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)",
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
  background: "rgba(255, 255, 255, 0.1)",
  transition: "background 200ms ease",
};

export const progressSegFilledStyle: React.CSSProperties = {
  background: "linear-gradient(90deg, #7fd4ff, #6aa8ff)",
};

export const progressLabelStyle: React.CSSProperties = {
  fontFamily: MONO_FONT,
  fontSize: "0.72rem",
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "rgba(244,246,251,0.4)",
  marginLeft: 8,
  whiteSpace: "nowrap",
};

// ── Intro splash ─────────────────────────────────────────────────

export const introTitleStyle: React.CSSProperties = {
  fontSize: "1.35rem",
  fontWeight: 700,
  color: "#f4f6fb",
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
  color: "rgba(244,246,251,0.82)",
};

export const bulletDotStyle: React.CSSProperties = {
  flex: "0 0 auto",
  width: 7,
  height: 7,
  marginTop: 7,
  borderRadius: "50%",
  background: "linear-gradient(135deg, #7fd4ff, #6aa8ff)",
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
  background: "linear-gradient(135deg, #7fd4ff, #a78bfa)",
  boxShadow: "0 10px 30px rgba(127,212,255,0.35)",
  marginBottom: 16,
};

export const thankYouTitleStyle: React.CSSProperties = {
  fontSize: "1.15rem",
  fontWeight: 700,
  color: "#f4f6fb",
  marginBottom: 6,
};

export const thankYouBodyStyle: React.CSSProperties = {
  fontSize: "0.88rem",
  color: "rgba(244,246,251,0.55)",
  lineHeight: 1.5,
};
