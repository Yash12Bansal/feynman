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
  e.currentTarget.style.borderColor = "rgba(127, 212, 255, 0.6)";
  e.currentTarget.style.background = "rgba(127, 212, 255, 0.06)";
}
function blurRing(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.12)";
  e.currentTarget.style.background = "rgba(255, 255, 255, 0.04)";
}

const cardStyle: React.CSSProperties = {
  position: "relative",
  width: "min(420px, 92vw)",
  padding: "34px 34px 30px",
  borderRadius: 22,
  background: "rgba(17, 17, 24, 0.74)",
  backdropFilter: "blur(18px)",
  WebkitBackdropFilter: "blur(18px)",
  border: "1px solid rgba(255, 255, 255, 0.10)",
  boxShadow: "0 30px 80px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255,255,255,0.06)",
  display: "flex",
  flexDirection: "column",
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const avatarStyle: React.CSSProperties = {
  width: 56,
  height: 56,
  borderRadius: "50%",
  alignSelf: "center",
  border: "2px solid rgba(255,255,255,0.12)",
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
  background: "linear-gradient(135deg, #60a5fa, #a78bfa)",
  color: "#fff",
  fontSize: "1.4rem",
  fontWeight: 700,
  marginBottom: 16,
};

const titleStyle: React.CSSProperties = {
  fontSize: "1.35rem",
  fontWeight: 700,
  color: "#fafafa",
  margin: "0 0 6px",
  textAlign: "center",
  letterSpacing: "-0.02em",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "0.9rem",
  color: "rgba(240, 240, 240, 0.5)",
  margin: "0 0 24px",
  textAlign: "center",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.72rem",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "rgba(240, 240, 240, 0.5)",
  margin: "0 0 7px 2px",
};

const inputStyle: React.CSSProperties = {
  padding: "12px 14px",
  borderRadius: 12,
  border: "1px solid rgba(255, 255, 255, 0.12)",
  background: "rgba(255, 255, 255, 0.04)",
  color: "#f0f0f0",
  fontSize: "0.95rem",
  fontFamily: "inherit",
  outline: "none",
  marginBottom: 16,
  boxSizing: "border-box",
  transition: "border-color 150ms ease, background 150ms ease",
};

const readonlyInputStyle: React.CSSProperties = {
  color: "rgba(240, 240, 240, 0.5)",
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
  border: "1px solid rgba(127, 212, 255, 0.4)",
  background: "#1b3a4a",
  color: "#7fd4ff",
  fontSize: "0.96rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
  transition: "opacity 160ms ease",
};

const errorStyle: React.CSSProperties = {
  margin: "0 0 14px",
  fontSize: "0.83rem",
  color: "#ffb4be",
};
