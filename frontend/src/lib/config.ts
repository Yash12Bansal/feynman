/**
 * Frontend configuration.
 */

export const config = {
  livekitUrl: import.meta.env.VITE_LIVEKIT_URL ?? "ws://localhost:7880",
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api",
  // Default ON. Opt out with `VITE_SPLIT_BOARD=false` when testing the
  // legacy card-list renderer.
  splitBoardEnabled: (import.meta.env.VITE_SPLIT_BOARD ?? "true") !== "false",
} as const;
