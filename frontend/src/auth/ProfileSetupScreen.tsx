/**
 * Profile completion — the one step between Google sign-in and the product.
 *
 * Name (prefilled from Google, editable) + email (from Google, read-only) +
 * phone (required, India-first +91 default). Writes `users/{uid}` with
 * profileComplete:true, which flips the gate open.
 */

import { useCallback, useState } from "react";
import { AuroraBackground } from "./AuroraBackground";
import { useAuth } from "./authContext";
import { DISPLAY_FONT } from "../styles/fonts";

export function ProfileSetupScreen() {
  const { user, saveProfile } = useAuth();
  const [name, setName] = useState(user?.displayName ?? "");
  const [code, setCode] = useState("+91");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const digits = phone.replace(/\D/g, "");
  const canSubmit =
    name.trim().length > 0 && /^\+\d{1,4}$/.test(code) && digits.length >= 7;

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const cleanDigits = phone.replace(/\D/g, "");
      if (
        name.trim().length === 0 ||
        !/^\+\d{1,4}$/.test(code) ||
        cleanDigits.length < 7
      ) {
        setErr("Please enter your name and a valid phone number.");
        return;
      }
      setBusy(true);
      setErr(null);
      try {
        await saveProfile({ name, phone: `${code} ${cleanDigits}` });
        // On success the profile flips profileComplete → the gate unmounts us.
      } catch (saveErr) {
        console.error("[auth] failed to save profile", saveErr);
        setErr("Couldn't save — please try again.");
        setBusy(false);
      }
    },
    [name, code, phone, saveProfile],
  );

  return (
    <AuroraBackground>
      <form onSubmit={onSubmit} style={cardStyle}>
        {user?.photoURL ? (
          <img src={user.photoURL} alt="" referrerPolicy="no-referrer" style={avatarStyle} />
        ) : (
          <div style={avatarFallbackStyle} aria-hidden>
            {(user?.displayName ?? user?.email ?? "?").trim().charAt(0).toUpperCase()}
          </div>
        )}

        <h1 style={titleStyle}>One last step</h1>
        <p style={subtitleStyle}>Set up your learning profile.</p>

        <label style={labelStyle} htmlFor="profile-name">
          Full name
        </label>
        <input
          id="profile-name"
          style={inputStyle}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
          autoComplete="name"
          onFocus={focusRing}
          onBlur={blurRing}
        />

        <label style={labelStyle} htmlFor="profile-phone">
          Phone number
        </label>
        <div style={phoneRowStyle}>
          <input
            aria-label="Country code"
            style={{ ...inputStyle, width: 72, textAlign: "center" }}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            inputMode="tel"
            onFocus={focusRing}
            onBlur={blurRing}
          />
          <input
            id="profile-phone"
            style={{ ...inputStyle, flex: 1 }}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="98765 43210"
            inputMode="numeric"
            autoComplete="tel-national"
            onFocus={focusRing}
            onBlur={blurRing}
          />
        </div>

        <label style={labelStyle} htmlFor="profile-email">
          Email
        </label>
        <input
          id="profile-email"
          style={{ ...inputStyle, ...readonlyInputStyle }}
          value={user?.email ?? ""}
          readOnly
        />

        {err && <p style={errorStyle}>{err}</p>}

        <button
          type="submit"
          disabled={busy || !canSubmit}
          style={{ ...submitStyle, opacity: busy || !canSubmit ? 0.55 : 1 }}
        >
          {busy ? "Saving…" : "Start learning"}
        </button>
      </form>
    </AuroraBackground>
  );
}

function focusRing(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.borderColor = "rgba(127, 212, 255, 0.55)";
  e.currentTarget.style.background = "rgba(127, 212, 255, 0.06)";
  e.currentTarget.style.boxShadow =
    "0 0 0 1px rgba(127,212,255,0.45), 0 6px 26px rgba(127,212,255,0.18)";
}
function blurRing(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.10)";
  e.currentTarget.style.background = "rgba(255, 255, 255, 0.04)";
  e.currentTarget.style.boxShadow = "none";
}

const cardStyle: React.CSSProperties = {
  position: "relative",
  width: "min(420px, 92vw)",
  padding: "34px 34px 30px",
  borderRadius: 20,
  background:
    "linear-gradient(180deg, rgba(20,22,32,0.68), rgba(14,15,23,0.68))",
  backdropFilter: "blur(20px) saturate(1.2)",
  WebkitBackdropFilter: "blur(20px) saturate(1.2)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  boxShadow:
    "0 24px 70px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07), inset 0 0 0 1px rgba(127,212,255,0.06)",
  display: "flex",
  flexDirection: "column",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const avatarStyle: React.CSSProperties = {
  width: 56,
  height: 56,
  borderRadius: "50%",
  alignSelf: "center",
  border: "2px solid rgba(127,212,255,0.28)",
  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
  marginBottom: 16,
  objectFit: "cover",
};

const avatarFallbackStyle: React.CSSProperties = {
  width: 56,
  height: 56,
  borderRadius: "50%",
  alignSelf: "center",
  display: "grid",
  placeItems: "center",
  background: "linear-gradient(135deg, #7fd4ff 0%, #6aa8ff 45%, #a78bfa 100%)",
  boxShadow: "0 8px 24px rgba(127,212,255,0.32)",
  color: "#fff",
  fontSize: "1.4rem",
  fontWeight: 700,
  marginBottom: 16,
};

const titleStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "1.35rem",
  fontWeight: 600,
  color: "#f4f6fb",
  margin: "0 0 6px",
  textAlign: "center",
  letterSpacing: "-0.01em",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "0.9rem",
  color: "rgba(244,246,251,0.58)",
  margin: "0 0 24px",
  textAlign: "center",
};

const labelStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "0.72rem",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "rgba(244,246,251,0.58)",
  margin: "0 0 7px 2px",
};

const inputStyle: React.CSSProperties = {
  padding: "12px 14px",
  borderRadius: 12,
  border: "1px solid rgba(255, 255, 255, 0.10)",
  background: "rgba(255, 255, 255, 0.04)",
  color: "#f4f6fb",
  fontSize: "0.95rem",
  fontFamily: "inherit",
  outline: "none",
  marginBottom: 16,
  boxSizing: "border-box",
  transition:
    "border-color 160ms cubic-bezier(0.22,0.61,0.36,1), background 160ms cubic-bezier(0.22,0.61,0.36,1), box-shadow 200ms cubic-bezier(0.22,0.61,0.36,1)",
};

const readonlyInputStyle: React.CSSProperties = {
  color: "rgba(244,246,251,0.30)",
  cursor: "not-allowed",
};

const phoneRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
};

const submitStyle: React.CSSProperties = {
  marginTop: 6,
  padding: "13px 18px",
  borderRadius: 12,
  border: "1px solid rgba(127, 212, 255, 0.40)",
  background:
    "linear-gradient(180deg, rgba(127,212,255,0.16), rgba(91,157,255,0.12))",
  color: "#7fd4ff",
  fontSize: "0.96rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
  boxShadow:
    "inset 0 1px 0 rgba(255,255,255,0.10), 0 6px 26px rgba(127,212,255,0.18)",
  transition:
    "opacity 160ms cubic-bezier(0.22,0.61,0.36,1), box-shadow 200ms cubic-bezier(0.22,0.61,0.36,1)",
};

const errorStyle: React.CSSProperties = {
  margin: "0 0 14px",
  padding: "8px 12px",
  borderRadius: 10,
  background: "rgba(255,120,140,0.08)",
  border: "1px solid rgba(255,120,140,0.18)",
  fontSize: "0.83rem",
  color: "#ffb4be",
};
