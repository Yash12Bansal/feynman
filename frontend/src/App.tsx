import { useState, useEffect, useCallback } from "react";
import { useSession } from "./hooks/useSession";
import { useLectureParams } from "./hooks/useLectureParams";
import { RoomProvider } from "./livekit/RoomProvider";
import { ClassroomScreen } from "./screens/ClassroomScreen";
import { LectureHomeScreen } from "./screens/LectureHomeScreen";
import { WaitingScreen } from "./screens/WaitingScreen";
import { AuthProvider } from "./auth/AuthProvider";
import { AuthGate } from "./auth/AuthGate";
import { AccountChip } from "./auth/AccountChip";
import { FeedbackFab } from "./feedback/FeedbackFab";
import { ExitIntentFeedback } from "./feedback/ExitIntentFeedback";

function useLectureChapterParam(): string | null {
  return useLectureParams().chapterId;
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
  const { chapterId: lectureChapterParam, personaId } = useLectureParams();
  const { token, livekitUrl, status, startSession } = useSession();

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
      persona_id: personaId,
    });
  }, [lectureChapterParam, personaId, status, startSession]);

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
      <ClassroomScreen
        lectureChapterId={lectureChapterParam}
        personaId={personaId}
        onRequestDoubtSession={requestDoubtSession}
      />
    </RoomProvider>
  );
}
