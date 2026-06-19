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
import { MarketingLanding } from "../marketing/MarketingLanding";
import { ProfileSetupScreen } from "./ProfileSetupScreen";
import { DISPLAY_FONT } from "../styles/fonts";

export function AuthGate({ children }: { readonly children: ReactNode }) {
  const { configured, initializing, profileLoading, user, profileComplete } =
    useAuth();

  // Local-dev escape hatch — render the product directly.
  if (config.authDisabled) return <>{children}</>;

  if (!configured) return <NotConfiguredNotice />;
  if (initializing) return <AuthSplash />;
  // Logged-out visitors land on the public marketing page; its "Try now" CTAs
  // open the Google sign-in popup, after which the gate advances past `!user`.
  if (!user) return <MarketingLanding />;
  // A signed-in user's profile is still loading — wait on the splash rather than
  // flashing the setup form at a returning user whose profile just hasn't
  // arrived yet.
  if (profileLoading) return <AuthSplash />;
  if (!profileComplete) return <ProfileSetupScreen />;
  return <>{children}</>;
}

function AuthSplash() {
  // Light "Living Notebook" boot splash — warm paper + the Fraunces brand
  // wordmark, matching the home picker / marketing landing so first paint and
  // the hand-off into the product read as one continuous light surface. (The
  // dark aurora is the old neon theme; it stays only on the dev-only
  // NotConfiguredNotice below.)
  return (
    <div style={splashRootStyle}>
      <div style={splashStyle}>
        <span style={splashSpinnerStyle} aria-hidden />
        <span style={splashTextStyle}>
          Feynman<span style={splashDotStyle}>.</span>
        </span>
      </div>
    </div>
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

const splashRootStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "#faf6ee", // --paper (Living Notebook)
};

const splashStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 18,
};

const splashSpinnerStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: "50%",
  border: "2px solid rgba(39, 64, 221, 0.16)", // --blue @ low alpha
  borderTopColor: "#2740dd", // --blue
  animation: "auth-spin 0.9s linear infinite",
};

const splashTextStyle: React.CSSProperties = {
  fontFamily: '"Fraunces", Georgia, "Times New Roman", serif', // --display
  fontSize: "1.3rem",
  fontWeight: 600,
  letterSpacing: "-0.02em",
  color: "#1b1916", // --ink
};

const splashDotStyle: React.CSSProperties = {
  color: "#2740dd", // --blue
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
