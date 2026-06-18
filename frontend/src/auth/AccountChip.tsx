/**
 * Minimal account control, fixed top-right. Collapsed = avatar; click opens a
 * small card with name / email / phone + Sign out. Lets cohort testers switch
 * accounts. Renders nothing when there's no signed-in user (e.g. dev bypass).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "./authContext";
import { useTheme } from "../theme/themeContext";
import { DISPLAY_FONT } from "../styles/fonts";

export function AccountChip({ inLecture = false }: { inLecture?: boolean }) {
  const { user, profile, signOut } = useAuth();
  const { theme } = useTheme();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const onSignOut = useCallback(() => {
    setOpen(false);
    void signOut();
  }, [signOut]);

  if (!user) return null;

  const name = profile?.name || user.displayName || "Account";
  const initial = (name.trim().charAt(0) || "?").toUpperCase();
  // Dark chip only inside a DARK lecture; the home screen and a light lecture
  // both use the light variant. Position still keys off `inLecture`.
  const useDark = inLecture && theme === "dark";

  return (
    <div ref={wrapRef} style={inLecture ? wrapStyleLecture : wrapStyle}>
      <button
        type="button"
        aria-label="Account menu"
        onClick={() => setOpen((o) => !o)}
        style={useDark ? chipStyle : chipLightStyle}
      >
        {user.photoURL ? (
          <img src={user.photoURL} alt="" referrerPolicy="no-referrer" style={avatarImgStyle} />
        ) : (
          <span style={useDark ? avatarFallbackStyle : avatarFallbackLightStyle}>
            {initial}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            ...(useDark ? menuStyle : menuLightStyle),
            // In a lecture the chip sits low → open the card upward.
            ...(inLecture ? { top: undefined, bottom: 44 } : null),
          }}
        >
          <div style={useDark ? menuNameStyle : menuNameLightStyle}>{name}</div>
          {user.email && (
            <div style={useDark ? menuMetaStyle : menuMetaLightStyle}>
              {user.email}
            </div>
          )}
          {profile?.phone && (
            <div style={useDark ? menuMetaStyle : menuMetaLightStyle}>
              {profile.phone}
            </div>
          )}
          <button
            type="button"
            onClick={onSignOut}
            style={useDark ? signOutStyle : signOutLightStyle}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

const wrapStyle: React.CSSProperties = {
  // Home / default position: top-left.
  position: "fixed",
  top: 16,
  left: 16,
  zIndex: 100,
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

// In a lecture the top-left holds the slide title, so the chip drops to the
// bottom-left, stacked just above the Feedback button (bottom:100) — still one
// tap from sign-out, but clear of all the title text. Its menu opens upward.
const wrapStyleLecture: React.CSSProperties = {
  ...wrapStyle,
  top: undefined,
  bottom: 160,
  left: 32,
};

const chipStyle: React.CSSProperties = {
  width: 36,
  height: 36,
  borderRadius: "50%",
  padding: 0,
  border: "1px solid rgba(255, 255, 255, 0.10)",
  background: "rgba(16, 18, 26, 0.62)",
  backdropFilter: "blur(16px) saturate(1.2)",
  WebkitBackdropFilter: "blur(16px) saturate(1.2)",
  cursor: "pointer",
  display: "grid",
  placeItems: "center",
  overflow: "hidden",
  boxShadow: "0 6px 18px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06)",
};

const avatarImgStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  objectFit: "cover",
};

const avatarFallbackStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "0.85rem",
  fontWeight: 700,
  color: "#7fd4ff",
};

const menuStyle: React.CSSProperties = {
  position: "absolute",
  top: 44,
  left: 0,
  width: 220,
  padding: "14px 16px",
  borderRadius: 14,
  background: "linear-gradient(180deg, rgba(20,22,32,0.86), rgba(14,15,23,0.86))",
  backdropFilter: "blur(18px) saturate(1.2)",
  WebkitBackdropFilter: "blur(18px) saturate(1.2)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  boxShadow: "0 24px 70px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.06)",
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const menuNameStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "0.92rem",
  fontWeight: 600,
  color: "#f4f6fb",
};

const menuMetaStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "rgba(244,246,251,0.50)",
  wordBreak: "break-all",
};

const signOutStyle: React.CSSProperties = {
  marginTop: 10,
  padding: "9px 12px",
  borderRadius: 10,
  border: "1px solid rgba(255, 180, 190, 0.3)",
  background: "transparent",
  color: "#ffb4be",
  fontSize: "0.85rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
  textAlign: "center",
};

// ── Light variants (home / "Living Notebook" surface) ────────────────────────
// The chip overlays the dark teaching board in a lecture (dark styles above) but
// the light paper home screen otherwise. These mirror the marketing palette
// (paper / ink / fountain-pen blue / coral) so the chip reads on light paper.
const LIGHT_FONT = "'Hanken Grotesk', -apple-system, BlinkMacSystemFont, sans-serif";

const chipLightStyle: React.CSSProperties = {
  ...chipStyle,
  border: "1px solid rgba(27, 25, 22, 0.14)",
  background: "#fffdf8",
  backdropFilter: "none",
  WebkitBackdropFilter: "none",
  boxShadow:
    "0 4px 14px -6px rgba(27,25,22,0.4), inset 0 1px 0 rgba(255,255,255,0.9)",
};

const avatarFallbackLightStyle: React.CSSProperties = {
  fontFamily: LIGHT_FONT,
  fontSize: "0.85rem",
  fontWeight: 700,
  color: "#2740dd",
};

const menuLightStyle: React.CSSProperties = {
  ...menuStyle,
  background: "#fffdf8",
  backdropFilter: "none",
  WebkitBackdropFilter: "none",
  border: "1px solid rgba(27, 25, 22, 0.12)",
  boxShadow:
    "0 20px 50px -28px rgba(27,25,22,0.5), inset 0 1px 0 rgba(255,255,255,0.9)",
};

const menuNameLightStyle: React.CSSProperties = {
  fontFamily: LIGHT_FONT,
  fontSize: "0.92rem",
  fontWeight: 600,
  color: "#1b1916",
};

const menuMetaLightStyle: React.CSSProperties = {
  fontFamily: LIGHT_FONT,
  fontSize: "0.78rem",
  color: "rgba(27,25,22,0.55)",
  wordBreak: "break-all",
};

const signOutLightStyle: React.CSSProperties = {
  marginTop: 10,
  padding: "9px 12px",
  borderRadius: 10,
  border: "1px solid rgba(226, 86, 59, 0.35)",
  background: "transparent",
  color: "#c0452c",
  fontFamily: LIGHT_FONT,
  fontSize: "0.85rem",
  fontWeight: 600,
  cursor: "pointer",
  textAlign: "center",
};
