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

export function AuthGate({ children }: { readonly children: ReactNode }) {
  const { configured, initializing, user, profileComplete } = useAuth();

  // Local-dev escape hatch — render the product directly.
  if (config.authDisabled) return <>{children}</>;

  if (!configured) return <NotConfiguredNotice />;
  if (initializing) return <AuthSplash />;
  if (!user) return <SignInScreen />;
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
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const splashSpinnerStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: "50%",
  border: "2px solid rgba(255,255,255,0.18)",
  borderTopColor: "#7fd4ff",
  animation: "auth-spin 0.9s linear infinite",
};

const splashTextStyle: React.CSSProperties = {
  fontSize: "0.95rem",
  fontWeight: 600,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  color: "rgba(240,240,240,0.4)",
};

const noticeCardStyle: React.CSSProperties = {
  width: "min(460px, 92vw)",
  padding: "34px 34px 28px",
  borderRadius: 22,
  background: "rgba(17, 17, 24, 0.74)",
  backdropFilter: "blur(18px)",
  WebkitBackdropFilter: "blur(18px)",
  border: "1px solid rgba(255, 255, 255, 0.10)",
  boxShadow: "0 30px 80px rgba(0, 0, 0, 0.6)",
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const noticeTitleStyle: React.CSSProperties = {
  fontSize: "1.25rem",
  fontWeight: 700,
  color: "#fafafa",
  margin: "0 0 14px",
  letterSpacing: "-0.01em",
};

const noticeBodyStyle: React.CSSProperties = {
  fontSize: "0.9rem",
  color: "rgba(240, 240, 240, 0.6)",
  lineHeight: 1.6,
  margin: "0 0 12px",
};

const codeStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
  fontSize: "0.82rem",
  background: "rgba(255,255,255,0.07)",
  padding: "1px 6px",
  borderRadius: 6,
  color: "#7fd4ff",
};
