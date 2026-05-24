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
  room_name: string;
  lecture_chapter_id?: string | null;
}

export interface CreateSessionRequest {
  topic?: string;
  subject?: string;
  grade_level?: string;
  lecture_chapter_id?: string;
}

export async function createSession(
  body?: CreateSessionRequest,
): Promise<CreateSessionResponse> {
  const res = await fetch(`${BASE_URL}/sessions`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
  return res.json();
}
