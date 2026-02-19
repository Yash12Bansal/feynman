/**
 * Frontend configuration.
 */

export const config = {
  livekitUrl: import.meta.env.VITE_LIVEKIT_URL ?? "ws://localhost:7880",
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api",
} as const;
