import { useState, useEffect, useCallback } from "react";
import { useSession } from "./hooks/useSession";
import { RoomProvider } from "./livekit/RoomProvider";
import { ClassroomScreen } from "./screens/ClassroomScreen";
import { LectureHomeScreen } from "./screens/LectureHomeScreen";
import { WaitingScreen } from "./screens/WaitingScreen";
import { AuthProvider } from "./auth/AuthProvider";
import { AuthGate } from "./auth/AuthGate";
import { AccountChip } from "./auth/AccountChip";
import { useAuth } from "./auth/authContext";
import { FeedbackFab } from "./feedback/FeedbackFab";
import { ExitIntentFeedback } from "./feedback/ExitIntentFeedback";
import { MemoryCardOverlay } from "./components/MemoryCardOverlay";
import {
  createStudySession,
  completeStudySession,
  fetchMemoryCard,
  type MemoryCard,
} from "./lib/api";

function useLectureChapterParam(): string | null {
  // ?lecture=<chapter_id> on the main app path binds the session to a
  // precomputed lecture and lands the student in the immersive viewer.
  const [value, setValue] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("lecture");
  });
  useEffect(() => {
    const onPop = () => {
      const params = new URLSearchParams(window.location.search);
      setValue(params.get("lecture"));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return value;
}

export function App() {
  // Gate the entire product behind Google sign-in + profile completion. The
  // feedback surfaces mount inside the gate so only signed-in users see them.
  return (
    <AuthProvider>
      <AuthGate>
        <AppShell />
      </AuthGate>
    </AuthProvider>
  );
}

function AppShell() {
  // The account chip stays available everywhere (sign-out must always be
  // reachable), but it MOVES during a lecture: the immersive viewer puts the
  // slide title in the top-left, so a top-left avatar would cover it. In a
  // lecture the chip drops to the bottom-left control cluster instead. The hook
  // is popstate-aware so the position toggles on navigation.
  const lecture = useLectureChapterParam();
  return (
    <>
      <MainEntry />
      <AccountChip inLecture={!!lecture} />
      <FeedbackFab />
      <ExitIntentFeedback />
    </>
  );
}

function MainEntry() {
  // ?lecture=<id> in the URL → MainApp renders the precomputed lecture (LiveKit
  // is connected lazily, only on the first doubt). No param → product front
  // door (LectureHomeScreen).
  const params = new URLSearchParams(window.location.search);
  if (params.get("lecture")) {
    return <MainApp />;
  }
  return <LectureHomeScreen />;
}

function MainApp() {
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
