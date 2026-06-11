/**
 * The gate. Nothing in the product renders until the user is signed in AND
 * their profile (name + phone) is complete.
 *
 * Order: dev-bypass → not-configured notice → loading splash → sign-in →
 * profile setup → children. `useAuth` is called unconditionally (rules of
 * hooks); the dev-bypass branch comes after.
 */

import type { ReactNode } from "react";
import { config } from "../lib/config";
import { AuroraBackground } from "./AuroraBackground";
import { useAuth } from "./authContext";
import { SignInScreen } from "./SignInScreen";
import { ProfileSetupScreen } from "./ProfileSetupScreen";
import { DISPLAY_FONT } from "../styles/fonts";

export function AuthGate({ children }: { readonly children: ReactNode }) {
  const { configured, initializing, profileLoading, user, profileComplete } = useAuth();

  // Local-dev escape hatch — render the product directly.
  if (config.authDisabled) return <>{children}</>;

  if (!configured) return <NotConfiguredNotice />;
  if (initializing) return <AuthSplash />;
  if (!user) return <SignInScreen />;
  // A signed-in user's profile is still loading — wait on the splash rather than
  // flashing the setup form at a returning user whose profile just hasn't
  // arrived yet.
  if (profileLoading) return <AuthSplash />;
  if (!profileComplete) return <ProfileSetupScreen />;
  return <>{children}</>;
}

function AuthSplash() {
  return (
    <AuroraBackground>
      <div style={splashStyle}>
        <span style={splashSpinnerStyle} aria-hidden />
        <span style={splashTextStyle}>Feynman</span>
      </div>
    </AuroraBackground>
  );
}

function NotConfiguredNotice() {
  return (
    <AuroraBackground>
      <div style={noticeCardStyle}>
        <h1 style={noticeTitleStyle}>Sign-in isn't configured yet</h1>
        <p style={noticeBodyStyle}>
          This build gates the product behind Google sign-in, but no Firebase
          project is wired up. Add your Firebase web config to{" "}
          <code style={codeStyle}>frontend/.env.local</code> (see{" "}
          <code style={codeStyle}>frontend/AUTH_FEEDBACK_SETUP.md</code>).
        </p>
        <p style={noticeBodyStyle}>
          To skip the gate during local development, set{" "}
          <code style={codeStyle}>VITE_AUTH_DISABLED=true</code> and restart the
          dev server.
        </p>
      </div>
    </AuroraBackground>
  );
}

const splashStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 18,
  fontFamily: DISPLAY_FONT,
};

const splashSpinnerStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: "50%",
  border: "2px solid rgba(127,212,255,0.14)",
  borderTopColor: "#7fd4ff",
  boxShadow: "0 0 18px rgba(127,212,255,0.35)",
  animation: "auth-spin 0.9s linear infinite",
};

const splashTextStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "0.95rem",
  fontWeight: 600,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  color: "rgba(244,246,251,0.58)",
};

const noticeCardStyle: React.CSSProperties = {
  width: "min(460px, 92vw)",
  padding: "34px 34px 28px",
  borderRadius: 20,
  background:
    "linear-gradient(180deg, rgba(20,22,32,0.68), rgba(14,15,23,0.68))",
  backdropFilter: "blur(20px) saturate(1.2)",
  WebkitBackdropFilter: "blur(20px) saturate(1.2)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  boxShadow:
    "0 24px 70px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07)",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const noticeTitleStyle: React.CSSProperties = {
  fontFamily: DISPLAY_FONT,
  fontSize: "1.25rem",
  fontWeight: 600,
  color: "#f4f6fb",
  margin: "0 0 14px",
  letterSpacing: "-0.01em",
};

const noticeBodyStyle: React.CSSProperties = {
  fontSize: "0.9rem",
  color: "rgba(244,246,251,0.58)",
  lineHeight: 1.6,
  margin: "0 0 12px",
};

const codeStyle: React.CSSProperties = {
  fontFamily: "'SF Mono', ui-monospace, monospace",
  fontSize: "0.82rem",
  background: "rgba(127,212,255,0.10)",
  padding: "1px 6px",
  borderRadius: 6,
  color: "#7fd4ff",
};
