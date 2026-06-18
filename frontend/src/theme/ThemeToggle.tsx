/**
 * Small sun/moon control that flips the lecture theme. Lives in the lecture
 * viewer's top-right cluster; styled from the `--lv-*` tokens so it themes with
 * everything else. Shows the destination icon (sun while dark, moon while light).
 */

import { useTheme } from "./themeContext";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Light" : "Dark"}
      style={{
        position: "fixed",
        top: 32,
        right: 32,
        zIndex: 100,
        width: 44,
        height: 44,
        borderRadius: 22,
        background: "var(--lv-panel)",
        border: "1px solid var(--lv-border)",
        color: "var(--lv-ink)",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backdropFilter: "blur(18px) saturate(1.2)",
        WebkitBackdropFilter: "blur(18px) saturate(1.2)",
        boxShadow: "var(--lv-shadow), var(--lv-inset)",
        transition:
          "transform 0.18s cubic-bezier(0.22,0.61,0.36,1), box-shadow 0.18s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-1px)";
        e.currentTarget.style.boxShadow =
          "var(--lv-shadow), var(--lv-inset), 0 0 0 1px var(--lv-accent-glow), 0 6px 24px var(--lv-accent-glow-soft)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "var(--lv-shadow), var(--lv-inset)";
      }}
    >
      {dark ? <SunGlyph /> : <MoonGlyph />}
    </button>
  );
}

function SunGlyph() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 2.5v2.2M12 19.3v2.2M21.5 12h-2.2M4.7 12H2.5M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6M18.7 18.7l-1.6-1.6M6.9 6.9 5.3 5.3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonGlyph() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
