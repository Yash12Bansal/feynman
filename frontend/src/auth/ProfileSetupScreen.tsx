/**
 * Profile completion — the one step between Google sign-in and the product.
 *
 * Name (prefilled from Google, editable) + email (from Google, read-only) +
 * phone (required, India-first +91 default). Writes `users/{uid}` with
 * profileComplete:true, which flips the gate open.
 *
 * Light "Living Notebook" skin — warm paper, ink + a single blue accent,
 * Fraunces/Hanken — matching the home picker, marketing landing, and the
 * loading splashes so sign-up reads as one continuous light product.
 */

import { useCallback, useState, type FormEvent } from "react";
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
    async (e: FormEvent) => {
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
    <div style={pageStyle}>
      <form onSubmit={onSubmit} style={cardStyle}>
        {user?.photoURL ? (
          <img
            src={user.photoURL}
            alt=""
            referrerPolicy="no-referrer"
            style={avatarStyle}
          />
        ) : (
          <div style={avatarFallbackStyle} aria-hidden>
            {(user?.displayName ?? user?.email ?? "?")
              .trim()
              .charAt(0)
              .toUpperCase()}
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
          style={{ ...submitStyle, opacity: busy || !canSubmit ? 0.5 : 1 }}
        >
          {busy ? "Saving…" : "Start learning"}
        </button>
      </form>
    </div>
  );
}

const BODY_FONT =
  '"Hanken Grotesk", -apple-system, BlinkMacSystemFont, sans-serif';
const DISPLAY_SERIF = '"Fraunces", Georgia, "Times New Roman", serif';
const INPUT_BG = "#fbf8f1";
const LINE = "rgba(27, 25, 22, 0.14)";

function focusRing(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.borderColor = "#2740dd"; // --blue
  e.currentTarget.style.background = "#fffdf8";
  e.currentTarget.style.boxShadow =
    "0 0 0 1px rgba(39,64,221,0.30), 0 4px 16px -6px rgba(39,64,221,0.30)";
}
function blurRing(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.borderColor = LINE;
  e.currentTarget.style.background = INPUT_BG;
  e.currentTarget.style.boxShadow = "none";
}

const pageStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 24,
  background: "#faf6ee", // --paper
};

const cardStyle: React.CSSProperties = {
  position: "relative",
  width: "min(420px, 92vw)",
  padding: "34px 34px 30px",
  borderRadius: 20,
  background: "#fffdf8", // --panel
  border: `1px solid ${LINE}`,
  boxShadow:
    "0 1px 0 rgba(255,255,255,0.8) inset, 0 30px 60px -34px rgba(27,25,22,0.45)",
  display: "flex",
  flexDirection: "column",
  fontFamily: BODY_FONT,
};

const avatarStyle: React.CSSProperties = {
  width: 56,
  height: 56,
  borderRadius: "50%",
  alignSelf: "center",
  border: "2px solid rgba(39,64,221,0.22)",
  boxShadow: "0 8px 22px -10px rgba(27,25,22,0.4)",
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
  background: "#2740dd", // --blue
  boxShadow: "0 8px 22px -8px rgba(39,64,221,0.5)",
  color: "#fff",
  fontFamily: DISPLAY_SERIF,
  fontSize: "1.4rem",
  fontWeight: 600,
  marginBottom: 16,
};

const titleStyle: React.CSSProperties = {
  fontFamily: DISPLAY_SERIF,
  fontSize: "1.5rem",
  fontWeight: 600,
  color: "#1b1916", // --ink
  margin: "0 0 6px",
  textAlign: "center",
  letterSpacing: "-0.02em",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "0.92rem",
  color: "#565049", // --ink-soft
  margin: "0 0 24px",
  textAlign: "center",
};

const labelStyle: React.CSSProperties = {
  fontFamily: BODY_FONT,
  fontSize: "0.7rem",
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.1em",
  color: "#938b7c", // --ink-faint
  margin: "0 0 7px 2px",
};

const inputStyle: React.CSSProperties = {
  padding: "12px 14px",
  borderRadius: 12,
  border: `1px solid ${LINE}`,
  background: INPUT_BG,
  color: "#1b1916", // --ink
  fontSize: "0.95rem",
  fontFamily: BODY_FONT,
  outline: "none",
  marginBottom: 16,
  boxSizing: "border-box",
  transition:
    "border-color 160ms cubic-bezier(0.22,0.61,0.36,1), background 160ms cubic-bezier(0.22,0.61,0.36,1), box-shadow 200ms cubic-bezier(0.22,0.61,0.36,1)",
};

const readonlyInputStyle: React.CSSProperties = {
  color: "#938b7c", // --ink-faint
  background: "#f1ead9", // --paper-deep
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
  border: "none",
  background: "#2740dd", // --blue
  color: "#fff",
  fontSize: "0.96rem",
  fontWeight: 600,
  fontFamily: BODY_FONT,
  cursor: "pointer",
  boxShadow: "0 10px 24px -10px rgba(39,64,221,0.6)",
  transition:
    "opacity 160ms cubic-bezier(0.22,0.61,0.36,1), box-shadow 200ms cubic-bezier(0.22,0.61,0.36,1)",
};

const errorStyle: React.CSSProperties = {
  margin: "0 0 14px",
  padding: "8px 12px",
  borderRadius: 10,
  background: "rgba(226,86,59,0.08)", // --coral
  border: "1px solid rgba(226,86,59,0.22)",
  fontSize: "0.83rem",
  color: "#b23a22",
};
