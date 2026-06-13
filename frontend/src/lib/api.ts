/**
 * API client for the Feynman backend.
 */

const BASE_URL = "/api";

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

// ── In-lecture interaction (question checkpoints) ───────────────────────────

export interface CheckpointQuestion {
  question_id: string;
  topic_id: string;
  kind: "mcq" | "subjective";
  q_text: string;
  options: string[];
  // The question's own setup figure (e.g. a circuit it refers to), generated
  // during the topic + cached. Most MCQs have none.
  diagram_needed: boolean;
  diagram_spec: Record<string, unknown> | null;
}

export interface Solution {
  diagram_needed: boolean;
  // DesignDiagramSpec — opaque to the API layer; rendered by DesignDiagramContent.
  diagram_spec: Record<string, unknown> | null;
  answer: string; // raw stored answer (an MCQ letter) — client resolves to the option
  explanation: string; // why the correct answer is correct (student-facing)
  answer_audio_url: string | null;
}

export interface AttemptOutcome {
  correct: boolean;
  answer: string;
  answer_audio_url: string | null;
}

/** The question to pose after a topic, or null when the topic has none. */
export async function fetchCheckpoint(
  topicId: string,
): Promise<CheckpointQuestion | null> {
  const res = await fetch(
    `${BASE_URL}/interaction/checkpoint?topic_id=${encodeURIComponent(topicId)}`,
  );
  if (!res.ok) throw new Error(`checkpoint fetch failed: ${res.status}`);
  const data = await res.json();
  return data ?? null;
}

/** The worked solution (text + audio + optional diagram). Built+cached on the
 *  backend on first demand; called during think-time so the diagram is ready. */
export async function fetchSolution(questionId: string): Promise<Solution> {
  const res = await fetch(
    `${BASE_URL}/interaction/solution?question_id=${encodeURIComponent(questionId)}`,
  );
  if (!res.ok) throw new Error(`solution fetch failed: ${res.status}`);
  return res.json();
}

// ── Checkpoint narration (TTS) ──────────────────────────────────────────────
// The checkpoint reads its prompt + explanation aloud in the lecture's own
// Kokoro voice, via the preview server. Same text → cached audio (instant).

/** The spoken intro + question shown when the checkpoint pops. */
export function promptNarration(qText: string): string {
  return `Let's test your understanding, genius. ${qText}`;
}

/** The spoken intro + explanation read out on reveal. */
export function explanationNarration(explanation: string): string {
  return `Let me help you understand. ${explanation}`;
}

/** URL the browser can play directly; the server synthesizes + caches by text. */
export function checkpointTtsUrl(text: string): string {
  return `/lecture-api/tts?text=${encodeURIComponent(text)}`;
}

/** Submit an answer — server checks correctness, records the attempt, reveals
 *  the solution. */
export async function submitAttempt(
  sessionId: string,
  questionId: string,
  selectedOption: string,
): Promise<AttemptOutcome> {
  const res = await fetch(`${BASE_URL}/interaction/attempts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      question_id: questionId,
      selected_option: selectedOption,
    }),
  });
  if (!res.ok) throw new Error(`attempt submit failed: ${res.status}`);
  return res.json();
}

// ── Personalised memory card ────────────────────────────────────────────────

export interface AttemptMemory {
  question_id: string;
  topic_id: string;
  chapter_id: string; // denormalised — labels items on the global card
  q_text: string;
  options: string[]; // collapsible on the card
  solution: string; // correct answer (an MCQ letter)
  explanation: string; // why it's correct — collapsible on the card
  correct: boolean;
  mode: "mcq" | "subjective";
  created_at: number;
}

export interface DoubtMemory {
  topic_id: string;
  chapter_id: string; // denormalised — labels items on the global card
  doubt_text: string;
  response: string;
  created_at: number;
}

export interface MemoryCard {
  student_id: string;
  chapter_id: string; // "" on the user-level global card (spans chapters)
  incorrect_attempts: AttemptMemory[];
  doubts: DoubtMemory[];
  sessions_covered: number;
}

/** Local calendar date (YYYY-MM-DD) in the student's timezone — the session's
 *  day boundary, so "new day = new session" matches their midnight. */
function localDateString(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Resolve today's study session for a chapter. The backend keys it by
 *  (student, chapter, local_date) and MERGEs, so this is idempotent: a refresh /
 *  new tab returns the SAME session_id. That id is threaded to the doubt worker
 *  + attempt writes so the whole day shares one session. */
export async function createStudySession(
  studentId: string,
  chapterId: string,
  subject = "",
): Promise<{ session_id: string; started_at: number }> {
  const res = await fetch(
    `${BASE_URL}/students/${encodeURIComponent(studentId)}/sessions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chapter_id: chapterId,
        subject,
        local_date: localDateString(),
      }),
    },
  );
  if (!res.ok) throw new Error(`Failed to start study session: ${res.status}`);
  return res.json();
}

/** Mark a study session finished (player reached the chapter end). Best-effort
 *  metadata — failures are swallowed by the caller. */
export async function completeStudySession(
  studentId: string,
  sessionId: string,
): Promise<void> {
  await fetch(
    `${BASE_URL}/students/${encodeURIComponent(studentId)}/sessions/${encodeURIComponent(sessionId)}/complete`,
    { method: "POST" },
  );
}

/** Last-N-sessions review card for a student on one chapter. `lookback`
 *  omitted → backend default (memory_lookback_sessions, 2). */
export async function fetchMemoryCard(
  studentId: string,
  chapterId: string,
  opts?: { lookback?: number; exclude?: string },
): Promise<MemoryCard> {
  const params = new URLSearchParams({ chapter_id: chapterId });
  if (opts?.lookback != null) params.set("lookback", String(opts.lookback));
  if (opts?.exclude) params.set("exclude", opts.exclude);
  const res = await fetch(
    `${BASE_URL}/students/${encodeURIComponent(studentId)}/memory-card?${params}`,
  );
  if (!res.ok) throw new Error(`Failed to fetch memory card: ${res.status}`);
  return res.json();
}

/** Full-chapter "weakness" card — every study-day on this chapter incl. today.
 *  Backs the "important points of this chapter, just for you" button. */
export async function fetchChapterMemory(
  studentId: string,
  chapterId: string,
): Promise<MemoryCard> {
  const params = new URLSearchParams({ chapter_id: chapterId });
  const res = await fetch(
    `${BASE_URL}/students/${encodeURIComponent(studentId)}/chapter-memory?${params}`,
  );
  if (!res.ok) throw new Error(`Failed to fetch chapter memory: ${res.status}`);
  return res.json();
}

/** User-level card — recent mistakes + doubts across every chapter, newest
 *  first. Backs the home-screen / on-login review. */
export async function fetchGlobalMemory(
  studentId: string,
  limit?: number,
): Promise<MemoryCard> {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", String(limit));
  const qs = params.toString();
  const res = await fetch(
    `${BASE_URL}/students/${encodeURIComponent(studentId)}/global-memory${qs ? `?${qs}` : ""}`,
  );
  if (!res.ok) throw new Error(`Failed to fetch global memory: ${res.status}`);
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
  // Firebase uid of the signed-in student — powers the personalised memory
  // layer (doubts + question attempts attributed to this student).
  student_id?: string;
  // The StudySession opened on lecture-open; threaded to the worker so doubts
  // attach to the same session as the student's question attempts.
  study_session_id?: string;
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
