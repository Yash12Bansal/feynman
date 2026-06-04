/**
 * Sign-in screen — the product's front door.
 *
 * Aurora backdrop + a glassmorphic card with a subtle mouse-parallax 3D tilt.
 * One action: Continue with Google. After sign-in the gate routes to the
 * profile step (name + phone) before any product surface is reachable.
 */

import { useCallback, useRef, useState } from "react";
import { AuroraBackground } from "./AuroraBackground";
import { useAuth } from "./authContext";

export function SignInScreen() {
  const { signInWithGoogle, authError } = useAuth();
  const [busy, setBusy] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const onSignIn = useCallback(async () => {
    setBusy(true);
    await signInWithGoogle();
    setBusy(false);
  }, [signInWithGoogle]);

  const onMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = cardRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(1100px) rotateX(${(-py * 5).toFixed(2)}deg) rotateY(${(px * 5).toFixed(2)}deg)`;
  }, []);

  const onLeave = useCallback(() => {
    const el = cardRef.current;
    if (el) el.style.transform = "perspective(1100px) rotateX(0deg) rotateY(0deg)";
  }, []);

  return (
    <AuroraBackground>
      <div ref={cardRef} onMouseMove={onMove} onMouseLeave={onLeave} style={cardStyle}>
        <BrandMark />
        <h1 style={titleStyle}>Welcome to Feynman</h1>
        <p style={subtitleStyle}>Your personal AI teacher. Sign in to begin.</p>

        <button
          type="button"
          onClick={onSignIn}
          disabled={busy}
          style={googleButtonStyle}
          onMouseEnter={(e) => (e.currentTarget.style.transform = "translateY(-1px)")}
          onMouseLeave={(e) => (e.currentTarget.style.transform = "translateY(0)")}
        >
          {busy ? <Spinner /> : <GoogleGlyph />}
          <span>{busy ? "Signing you in…" : "Continue with Google"}</span>
        </button>

        {authError && <p style={errorStyle}>{authError}</p>}

        <p style={fineprintStyle}>
          We'll ask for your name and number next — just to set up your profile.
          Nothing is shared.
        </p>
      </div>
    </AuroraBackground>
  );
}

function BrandMark() {
  return (
    <div style={brandOrbStyle} aria-hidden>
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2 L13.9 10.1 L22 12 L13.9 13.9 L12 22 L10.1 13.9 L2 12 L10.1 10.1 Z"
          fill="#ffffff"
          fillOpacity="0.95"
        />
      </svg>
    </div>
  );
}

function GoogleGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

function Spinner() {
  return <span style={spinnerStyle} aria-hidden />;
}

const cardStyle: React.CSSProperties = {
  position: "relative",
  width: "min(420px, 92vw)",
  padding: "40px 36px 28px",
  borderRadius: 22,
  background: "rgba(17, 17, 24, 0.72)",
  backdropFilter: "blur(18px)",
  WebkitBackdropFilter: "blur(18px)",
  border: "1px solid rgba(255, 255, 255, 0.10)",
  boxShadow: "0 30px 80px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255,255,255,0.06)",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  textAlign: "center",
  transition: "transform 240ms ease",
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const brandOrbStyle: React.CSSProperties = {
  width: 52,
  height: 52,
  borderRadius: 16,
  display: "grid",
  placeItems: "center",
  background: "linear-gradient(135deg, #60a5fa, #a78bfa)",
  boxShadow: "0 10px 34px rgba(96, 165, 250, 0.45)",
  marginBottom: 20,
};

const titleStyle: React.CSSProperties = {
  fontSize: "1.5rem",
  fontWeight: 700,
  color: "#fafafa",
  margin: "0 0 8px",
  letterSpacing: "-0.02em",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "0.95rem",
  color: "rgba(240, 240, 240, 0.55)",
  margin: "0 0 28px",
  lineHeight: 1.5,
};

const googleButtonStyle: React.CSSProperties = {
  width: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 12,
  padding: "13px 18px",
  borderRadius: 12,
  border: "1px solid rgba(255, 255, 255, 0.14)",
  background: "#ffffff",
  color: "#1f2227",
  fontSize: "0.96rem",
  fontWeight: 600,
  fontFamily: "inherit",
  cursor: "pointer",
  transition: "transform 160ms ease, box-shadow 160ms ease",
  boxShadow: "0 8px 24px rgba(0, 0, 0, 0.35)",
};

const errorStyle: React.CSSProperties = {
  marginTop: 16,
  fontSize: "0.85rem",
  color: "#ffb4be",
  lineHeight: 1.4,
};

const fineprintStyle: React.CSSProperties = {
  marginTop: 22,
  marginBottom: 0,
  fontSize: "0.76rem",
  color: "rgba(240, 240, 240, 0.38)",
  lineHeight: 1.5,
};

const spinnerStyle: React.CSSProperties = {
  display: "inline-block",
  width: 16,
  height: 16,
  borderRadius: "50%",
  border: "2px solid rgba(31, 34, 39, 0.25)",
  borderTopColor: "#1f2227",
  animation: "auth-spin 0.8s linear infinite",
};
