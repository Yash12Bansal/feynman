/**
 * Full-viewport animated aurora backdrop for the auth surfaces.
 *
 * Pure CSS / GPU — three large blurred gradient blobs drift behind a faint
 * grid and a vignette. Deliberately NO 3D engine: depth comes from blur,
 * layering, and (in the cards above) a mouse-parallax tilt, so first paint
 * stays instant. Matches the product's dark-neon palette.
 */

import type { ReactNode } from "react";

export function AuroraBackground({ children }: { readonly children: ReactNode }) {
  return (
    <div style={rootStyle}>
      <div style={blobOneStyle} />
      <div style={blobTwoStyle} />
      <div style={blobThreeStyle} />
      <div style={gridStyle} />
      <div style={vignetteStyle} />
      <div style={sheenStyle} />
      <div style={contentStyle}>{children}</div>
    </div>
  );
}

const rootStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  overflow: "hidden",
  background:
    "radial-gradient(120% 120% at 50% 30%, #0b0c14 0%, #07070d 60%, #05050a 100%)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const blobBase: React.CSSProperties = {
  position: "absolute",
  width: "62vmax",
  height: "62vmax",
  borderRadius: "50%",
  filter: "blur(80px)",
  willChange: "transform",
  pointerEvents: "none",
};

const blobOneStyle: React.CSSProperties = {
  ...blobBase,
  top: "-18vmax",
  left: "-10vmax",
  background:
    "radial-gradient(circle at 50% 50%, rgba(127,212,255,0.34), rgba(127,212,255,0) 62%)",
  animation: "auth-aurora-1 26s ease-in-out infinite",
};

const blobTwoStyle: React.CSSProperties = {
  ...blobBase,
  bottom: "-22vmax",
  right: "-12vmax",
  background:
    "radial-gradient(circle at 50% 50%, rgba(167,139,250,0.32), rgba(167,139,250,0) 62%)",
  animation: "auth-aurora-2 32s ease-in-out infinite",
};

const blobThreeStyle: React.CSSProperties = {
  ...blobBase,
  top: "20vmax",
  right: "16vmax",
  width: "44vmax",
  height: "44vmax",
  background:
    "radial-gradient(circle at 50% 50%, rgba(91,157,255,0.26), rgba(91,157,255,0) 62%)",
  animation: "auth-aurora-3 38s ease-in-out infinite",
};

const gridStyle: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  backgroundImage:
    "radial-gradient(rgba(127,212,255,0.05) 1px, transparent 1.4px)",
  backgroundSize: "30px 30px",
  maskImage:
    "radial-gradient(ellipse 78% 66% at 50% 44%, #000 24%, transparent 78%)",
  WebkitMaskImage:
    "radial-gradient(ellipse 78% 66% at 50% 44%, #000 24%, transparent 78%)",
  pointerEvents: "none",
};

const vignetteStyle: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  background:
    "radial-gradient(ellipse 100% 100% at 50% 48%, transparent 38%, rgba(0,0,0,0.66) 100%)",
  pointerEvents: "none",
};

// Slow rotating overhead "light" — a very faint conic sheen for depth.
const sheenStyle: React.CSSProperties = {
  position: "absolute",
  inset: "-20%",
  background:
    "conic-gradient(from 210deg at 50% 30%, transparent 0deg, rgba(127,212,255,0.05) 40deg, transparent 110deg, rgba(167,139,250,0.045) 200deg, transparent 300deg)",
  filter: "blur(40px)",
  mixBlendMode: "screen",
  willChange: "transform",
  animation: "auth-sheen 60s linear infinite",
  pointerEvents: "none",
};

const contentStyle: React.CSSProperties = {
  position: "relative",
  zIndex: 1,
  width: "100%",
  height: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 24,
  boxSizing: "border-box",
};

// Inject drift keyframes once (inline styles can't carry @keyframes).
if (typeof document !== "undefined") {
  const KEY = "auth-aurora-keyframes";
  if (!document.getElementById(KEY)) {
    const style = document.createElement("style");
    style.id = KEY;
    style.textContent = `
@keyframes auth-aurora-1 {
  0%,100% { transform: translate(0,0) scale(1); }
  50%     { transform: translate(8vmax,6vmax) scale(1.12); }
}
@keyframes auth-aurora-2 {
  0%,100% { transform: translate(0,0) scale(1.05); }
  50%     { transform: translate(-7vmax,-5vmax) scale(0.92); }
}
@keyframes auth-aurora-3 {
  0%,100% { transform: translate(0,0) scale(0.95); }
  50%     { transform: translate(-5vmax,7vmax) scale(1.15); }
}
@keyframes auth-spin { to { transform: rotate(360deg); } }
@keyframes auth-sheen { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  [style*="auth-aurora-1"],
  [style*="auth-aurora-2"],
  [style*="auth-aurora-3"],
  [style*="auth-sheen"] { animation: none !important; }
}`;
    document.head.appendChild(style);
  }
}
