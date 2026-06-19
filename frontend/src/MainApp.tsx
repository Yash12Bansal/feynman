import { useCallback, useEffect, useState } from "react";
import { useSession } from "./hooks/useSession";
import { useAuth } from "./auth/authContext";
import { RoomProvider } from "./livekit/RoomProvider";
import { ClassroomScreen } from "./screens/ClassroomScreen";
import { WaitingScreen } from "./screens/WaitingScreen";
import { useLectureChapterParam } from "./hooks/useLectureChapterParam";
import { MemoryCardOverlay } from "./components/MemoryCardOverlay";
import {
  createStudySession,
  completeStudySession,
  fetchMemoryCard,
  type MemoryCard,
} from "./lib/api";

/**
 * The immersive lecture experience: the whiteboard rendering engine, LiveKit,
 * katex, charts, gsap, roughjs, etc. This is the bulk of the app's JS and is
 * only needed once a student opens a lecture, so App.tsx loads it lazily.
 */
export function MainApp() {
  const lectureChapterParam = useLectureChapterParam();
  const { token, livekitUrl, status, startSession } = useSession();
  const { user } = useAuth();

  // Memory layer. A StudySession is one (student, chapter, day) with a
  // DETERMINISTIC server id, so resolving it is idempotent: a refresh / new tab
  // re-resolves the SAME session — no client storage needed. We then fetch the
  // review card EXCLUDING today's session, so it only ever shows PRIOR study-
  // days, even on a mid-lecture refresh when today's session already exists.
  const [memoryCard, setMemoryCard] = useState<MemoryCard | null>(null);
  const [studySessionId, setStudySessionId] = useState<string | null>(null);
  const uid = user?.uid;
  useEffect(() => {
    if (!uid || !lectureChapterParam) return;
    let cancelled = false;
    (async () => {
      const created = await createStudySession(uid, lectureChapterParam).catch(
        () => null,
      );
      const sid = created?.session_id ?? null;
      if (cancelled) return;
      setStudySessionId(sid);
      const card = await fetchMemoryCard(uid, lectureChapterParam, {
        exclude: sid ?? undefined,
      }).catch(() => null);
      if (cancelled) return;
      setMemoryCard(card);
    })();
    return () => {
      cancelled = true;
    };
  }, [uid, lectureChapterParam]);

  const onLectureComplete = useCallback(() => {
    if (uid && studySessionId) void completeStudySession(uid, studySessionId);
  }, [uid, studySessionId]);

  // LAZY CONNECT: do NOT auto-start a session on lecture open. Watching a
  // precomputed lecture is fully client-side (audio + visuals stream from the
  // preview server); LiveKit's room + agent are only spun up when the student
  // first taps "Ask Feynman". This means passive viewers consume zero LiveKit —
  // the dominant cost saving. Guarded on session status so we don't double-start
  // while a session is in flight, but a failed start can be retried.
  const requestDoubtSession = useCallback(() => {
    if (!lectureChapterParam) return;
    if (status === "connecting" || status === "connected") return;
    void startSession({
      lecture_chapter_id: lectureChapterParam,
      student_id: uid,
      study_session_id: studySessionId ?? undefined,
    });
  }, [lectureChapterParam, status, startSession, uid, studySessionId]);

  // Param removed mid-session (popstate) — fall back to the free-form flow.
  if (!lectureChapterParam) {
    return (
      <WaitingScreen
        onStart={(body) => startSession(body)}
        isLoading={status === "connecting"}
      />
    );
  }

  // Render the lecture immediately. RoomProvider only CONNECTS once a session
  // token exists (after the first doubt request); until then LiveKitRoom mounts
  // disconnected so the viewer's room hooks work without using any LiveKit.
  const connected = status === "connected" && !!token && !!livekitUrl;
  return (
    <RoomProvider
      token={token ?? ""}
      serverUrl={livekitUrl ?? ""}
      connect={connected}
    >
      <MemoryCardOverlay card={memoryCard} />
      <ClassroomScreen
        lectureChapterId={lectureChapterParam}
        studentId={uid}
        studySessionId={studySessionId}
        onRequestDoubtSession={requestDoubtSession}
        onLectureComplete={onLectureComplete}
      />
    </RoomProvider>
  );
}
