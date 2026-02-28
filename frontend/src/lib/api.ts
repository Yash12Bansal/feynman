/**
 * API client for the Feynman backend.
 */

const BASE_URL = "/api";

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export interface CreateSessionResponse {
  session_id: string;
  token: string;
  livekit_url: string;
}

export async function createSession(): Promise<CreateSessionResponse> {
  const res = await fetch(`${BASE_URL}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
  return res.json();
}
