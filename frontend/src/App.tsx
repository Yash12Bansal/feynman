import { useSession } from "./hooks/useSession";
import { RoomProvider } from "./livekit/RoomProvider";
import { ClassroomScreen } from "./screens/ClassroomScreen";
import { WaitingScreen } from "./screens/WaitingScreen";

export function App() {
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
    <WaitingScreen onStart={startSession} isLoading={status === "connecting"} />
  );
}
