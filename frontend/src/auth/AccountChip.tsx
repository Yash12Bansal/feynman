/**
 * Minimal account control, fixed top-right. Collapsed = avatar; click opens a
 * small card with name / email / phone + Sign out. Lets cohort testers switch
 * accounts. Renders nothing when there's no signed-in user (e.g. dev bypass).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "./authContext";

export function AccountChip() {
  const { user, profile, signOut } = useAuth();
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

  return (
    <div ref={wrapRef} style={wrapStyle}>
      <button
        type="button"
        aria-label="Account menu"
        onClick={() => setOpen((o) => !o)}
        style={chipStyle}
      >
        {user.photoURL ? (
          <img src={user.photoURL} alt="" referrerPolicy="no-referrer" style={avatarImgStyle} />
        ) : (
          <span style={avatarFallbackStyle}>{initial}</span>
        )}
      </button>

      {open && (
        <div style={menuStyle}>
          <div style={menuNameStyle}>{name}</div>
          {user.email && <div style={menuMetaStyle}>{user.email}</div>}
          {profile?.phone && <div style={menuMetaStyle}>{profile.phone}</div>}
          <button type="button" onClick={onSignOut} style={signOutStyle}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

const wrapStyle: React.CSSProperties = {
  // Top-left: the one screen corner the lecture player leaves free (Topics is
  // top-right, Pause bottom-left, Ask Feynman bottom-right, scrubber center).
  position: "fixed",
  top: 16,
  left: 16,
  zIndex: 100,
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const chipStyle: React.CSSProperties = {
  width: 36,
  height: 36,
  borderRadius: "50%",
  padding: 0,
  border: "1px solid rgba(255, 255, 255, 0.14)",
  background: "rgba(20, 20, 32, 0.6)",
  backdropFilter: "blur(8px)",
  WebkitBackdropFilter: "blur(8px)",
  cursor: "pointer",
  display: "grid",
  placeItems: "center",
  overflow: "hidden",
  boxShadow: "0 6px 18px rgba(0,0,0,0.4)",
};

const avatarImgStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  objectFit: "cover",
};

const avatarFallbackStyle: React.CSSProperties = {
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
  background: "rgba(15, 15, 18, 0.92)",
  backdropFilter: "blur(14px)",
  WebkitBackdropFilter: "blur(14px)",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  boxShadow: "0 18px 50px rgba(0,0,0,0.6)",
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const menuNameStyle: React.CSSProperties = {
  fontSize: "0.92rem",
  fontWeight: 600,
  color: "#fafafa",
};

const menuMetaStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "rgba(240, 240, 240, 0.5)",
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
