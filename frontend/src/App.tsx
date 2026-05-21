import { useState, useEffect } from "react";
import { useSession } from "./hooks/useSession";
import { RoomProvider } from "./livekit/RoomProvider";
import { ClassroomScreen } from "./screens/ClassroomScreen";
import { DevHarness } from "./screens/DevHarness";
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

export function App() {
  const hash = useHash();

  if (hash === "#/dev") {
    return <DevHarness />;
  }

  if (hash === "#/dev/split-board") {
    return <SplitBoardPrototype />;
  }

  // v2 precompute classroom playback. Optional ?chapter=<id> in the hash:
  //   #/lecture-preview                                  → chapter list
  //   #/lecture-preview?chapter=chapter:physics:...      → player
  if (hash.startsWith("#/lecture-preview")) {
    return <LecturePreviewScreen />;
  }

  return <MainApp />;
}

function MainApp() {
  const { token, livekitUrl, status, error, startSession } = useSession();

  if (status === "connected" && token && livekitUrl) {
    return (
      <RoomProvider token={token} serverUrl={livekitUrl}>
        <ClassroomScreen />
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

  return (
    <WaitingScreen onStart={(body) => startSession(body)} isLoading={status === "connecting"} />
  );
}
