/**
 * Frontend configuration.
 */

export const config = {
  livekitUrl: import.meta.env.VITE_LIVEKIT_URL ?? "ws://localhost:7880",
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api",
  // Default ON. Opt out with `VITE_SPLIT_BOARD=false` when testing the
  // legacy card-list renderer.
  splitBoardEnabled: (import.meta.env.VITE_SPLIT_BOARD ?? "true") !== "false",
  // Local-dev escape hatch: bypass the Google sign-in gate entirely. Default
  // OFF — the cohort build must gate. Set VITE_AUTH_DISABLED=true to run the
  // app without configuring Firebase.
  authDisabled: (import.meta.env.VITE_AUTH_DISABLED ?? "false") === "true",
} as const;
