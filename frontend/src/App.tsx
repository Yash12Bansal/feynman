import { useState, useEffect, useRef } from "react";
import { useSession } from "./hooks/useSession";
import { RoomProvider } from "./livekit/RoomProvider";
import { ClassroomScreen } from "./screens/ClassroomScreen";
import { DevHarness } from "./screens/DevHarness";
import { DiagramGenerationTestScreen } from "./screens/DiagramGenerationTestScreen";
import { LectureHomeScreen } from "./screens/LectureHomeScreen";
import { LecturePreviewScreen } from "./screens/LecturePreviewScreen";
import { SplitBoardPrototype } from "./screens/SplitBoardPrototype";
import { WaitingScreen } from "./screens/WaitingScreen";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return hash;
}

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
  const hash = useHash();

  if (hash === "#/dev") {
    return <DevHarness />;
  }

  if (hash === "#/dev/split-board") {
    return <SplitBoardPrototype />;
  }

  // Diagram-generation experimental testbed (strategy/model/options plugin lab).
  if (hash.startsWith("#/diagram_generation_test")) {
    return <DiagramGenerationTestScreen />;
  }

  // v2 precompute classroom playback playground. Optional ?chapter=<id>:
  //   #/lecture-preview                                  → chapter list
  //   #/lecture-preview?chapter=chapter:physics:...      → player
  if (hash.startsWith("#/lecture-preview")) {
    return <LecturePreviewScreen />;
  }

  // Legacy live-agent flow ("type a topic, start a class"). Parked behind a
  // dev hash route — the consumer product entrypoint is LectureHomeScreen.
  if (hash.startsWith("#/dev/live-teacher")) {
    return <MainApp />;
  }

  return <MainEntry />;
}

function MainEntry() {
  // ?lecture=<id> in the URL → MainApp auto-starts a lecture session and
  // routes into ClassroomScreen → LectureViewer. No param → show the
  // product front door (LectureHomeScreen).
  const params = new URLSearchParams(window.location.search);
  if (params.get("lecture")) {
    return <MainApp />;
  }
  return <LectureHomeScreen />;
}

function MainApp() {
  const lectureChapterParam = useLectureChapterParam();
  const { token, livekitUrl, lectureChapterId, status, error, startSession } =
    useSession();

  // Auto-start a lecture session when ?lecture=<id> is in the URL.
  // The ref guard short-circuits React strict-mode's double-effect in dev,
  // which otherwise fires startSession twice before status flips off "idle"
  // and creates two LiveKit rooms per chapter click.
  const autoStartFiredRef = useRef(false);
  useEffect(() => {
    if (autoStartFiredRef.current) return;
    if (lectureChapterParam && status === "idle") {
      autoStartFiredRef.current = true;
      void startSession({ lecture_chapter_id: lectureChapterParam });
    }
  }, [lectureChapterParam, status, startSession]);

  if (status === "connected" && token && livekitUrl) {
    return (
      <RoomProvider token={token} serverUrl={livekitUrl}>
        <ClassroomScreen lectureChapterId={lectureChapterId} />
      </RoomProvider>
    );
  }

  if (status === "error") {
    return (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: "1rem",
          background: "#0a0a0a",
          color: "#fafafa",
        }}
      >
        <p style={{ color: "#ef4444" }}>Failed to start session: {error}</p>
        <button
          onClick={startSession}
          style={{
            padding: "0.5rem 1.5rem",
            fontSize: "1rem",
            background: "#3b82f6",
            color: "#fff",
            border: "none",
            borderRadius: "0.5rem",
            cursor: "pointer",
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  // While auto-starting a lecture session, show a minimal "preparing" splash
  // instead of WaitingScreen (which expects a topic).
  if (lectureChapterParam) {
    return (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0a0a",
          color: "#6b7280",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          fontSize: "0.95rem",
          letterSpacing: "0.05em",
        }}
      >
        Preparing lecture…
      </div>
    );
  }

  return (
    <WaitingScreen
      onStart={(body) => startSession(body)}
      isLoading={status === "connecting"}
    />
  );
}
