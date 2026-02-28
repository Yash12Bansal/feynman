import { useCallback, useState } from "react";
import { createSession, type CreateSessionResponse } from "../lib/api";

type SessionStatus = "idle" | "connecting" | "connected" | "error";

export function useSession() {
  const [session, setSession] = useState<CreateSessionResponse | null>(null);
  const [status, setStatus] = useState<SessionStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const startSession = useCallback(async () => {
    setStatus("connecting");
    setError(null);
    try {
      const response = await createSession();
      setSession(response);
      setStatus("connected");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  }, []);

  return {
    sessionId: session?.session_id ?? null,
    token: session?.token ?? null,
    livekitUrl: session?.livekit_url ?? null,
    status,
    error,
    startSession,
  };
}
