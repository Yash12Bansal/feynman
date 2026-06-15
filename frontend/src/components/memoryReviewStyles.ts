/** Shared styles for the memory-card surfaces (auto-pop, chapter weakness,
 *  global). Kept in a non-component module so the component files can export
 *  only components (Vite fast-refresh requirement). */

export const OVERLAY: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 120,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(8, 9, 12, 0.72)",
  backdropFilter: "blur(6px)",
};
export const CARD: React.CSSProperties = {
  width: "min(92vw, 520px)",
  maxHeight: "80vh",
  overflowY: "auto",
  padding: "28px 30px",
  background: "#14151a",
  border: "1px solid rgba(232, 232, 238, 0.12)",
  borderRadius: 18,
  color: "rgba(232, 232, 238, 0.92)",
  boxShadow: "0 24px 60px rgba(0,0,0,0.5)",
};
export const KICKER: React.CSSProperties = {
  fontSize: "0.72rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "#7fd4ff",
};
export const TITLE: React.CSSProperties = {
  margin: "6px 0 18px",
  fontSize: "1.4rem",
  fontWeight: 600,
};
export const SECTION: React.CSSProperties = { marginBottom: 18 };
export const SECTION_LABEL: React.CSSProperties = {
  fontSize: "0.8rem",
  color: "rgba(232, 232, 238, 0.6)",
  marginBottom: 8,
};
export const LIST: React.CSSProperties = {
  margin: 0,
  paddingLeft: 18,
  display: "flex",
  flexDirection: "column",
  gap: 6,
};
export const ITEM: React.CSSProperties = { fontSize: "0.95rem", lineHeight: 1.45 };
export const SUBTLE: React.CSSProperties = {
  marginTop: 4,
  fontSize: "0.85rem",
  color: "rgba(232, 232, 238, 0.6)",
};
export const EMPTY: React.CSSProperties = {
  fontSize: "0.95rem",
  lineHeight: 1.5,
  color: "rgba(232, 232, 238, 0.7)",
  marginBottom: 18,
};
// ── Collapsible disclosures (options / explanation / doubt answer) ──────────
export const DISCLOSURE: React.CSSProperties = { marginTop: 6 };
export const SUMMARY: React.CSSProperties = {
  cursor: "pointer",
  fontSize: "0.8rem",
  color: "#7fd4ff",
  listStyle: "none",
  userSelect: "none",
  padding: "2px 0",
};
export const OPT_LIST: React.CSSProperties = {
  margin: "6px 0 0",
  paddingLeft: 0,
  listStyle: "none",
  display: "flex",
  flexDirection: "column",
  gap: 4,
};
export const OPT_ITEM: React.CSSProperties = {
  fontSize: "0.88rem",
  lineHeight: 1.4,
  color: "rgba(232, 232, 238, 0.78)",
  padding: "4px 8px",
  borderRadius: 6,
};
export const OPT_CORRECT: React.CSSProperties = {
  ...OPT_ITEM,
  color: "#cfffe4",
  background: "rgba(124, 255, 178, 0.10)",
  border: "1px solid rgba(124, 255, 178, 0.22)",
};
export const OPT_BADGE: React.CSSProperties = {
  marginLeft: 8,
  fontSize: "0.64rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#7CFFB2",
};
export const EXPLAIN: React.CSSProperties = {
  margin: "6px 0 0",
  fontSize: "0.88rem",
  lineHeight: 1.5,
  color: "rgba(232, 232, 238, 0.78)",
};
export const STEP_OL: React.CSSProperties = {
  margin: "6px 0 0",
  paddingLeft: 20,
  display: "flex",
  flexDirection: "column",
  gap: 6,
};
export const TAG: React.CSSProperties = {
  display: "inline-block",
  marginRight: 8,
  padding: "1px 7px",
  fontSize: "0.68rem",
  borderRadius: 6,
  background: "rgba(127, 212, 255, 0.12)",
  color: "#7fd4ff",
  verticalAlign: "middle",
};
// ── Side drawer (in-lecture) ────────────────────────────────────────────────
export const DRAWER_SCRIM: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 120,
  // Very light scrim — the board stays readable behind it (the whole point:
  // the review sits beside the lecture, "not right in front").
  background: "rgba(6, 7, 11, 0.28)",
};
export const DRAWER: React.CSSProperties = {
  position: "fixed",
  top: 0,
  right: 0,
  height: "100vh",
  width: "min(94vw, 400px)",
  display: "flex",
  flexDirection: "column",
  background: "#14151a",
  borderLeft: "1px solid rgba(232, 232, 238, 0.12)",
  boxShadow: "-24px 0 60px rgba(0,0,0,0.5)",
  color: "rgba(232, 232, 238, 0.92)",
};
export const DRAWER_HEAD: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: 12,
  padding: "22px 22px 14px",
  borderBottom: "1px solid rgba(232, 232, 238, 0.08)",
};
export const DRAWER_TITLE: React.CSSProperties = {
  margin: "6px 0 0",
  fontSize: "1.15rem",
  fontWeight: 600,
};
export const DRAWER_BODY: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
  padding: "18px 22px 28px",
};
export const CLOSE_X: React.CSSProperties = {
  flexShrink: 0,
  width: 32,
  height: 32,
  borderRadius: 8,
  background: "transparent",
  border: "1px solid rgba(232, 232, 238, 0.14)",
  color: "rgba(232, 232, 238, 0.7)",
  fontSize: "0.9rem",
  cursor: "pointer",
};
export const BUTTON: React.CSSProperties = {
  marginTop: 8,
  width: "100%",
  padding: "12px 0",
  background: "#7fd4ff",
  color: "#0a0a0a",
  border: "none",
  borderRadius: 10,
  fontSize: "0.95rem",
  fontWeight: 600,
  cursor: "pointer",
};
