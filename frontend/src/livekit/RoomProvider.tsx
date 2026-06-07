import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import type { ReactNode } from "react";

interface RoomProviderProps {
  token: string;
  serverUrl: string;
  /**
   * Whether to actually connect to LiveKit. Defaults true. Lazy-connect callers
   * pass false until a session exists (token/serverUrl empty) so the lecture
   * renders + plays WITHOUT spinning up a room/agent — watching is fully
   * client-side. Flip to true (with a real token) on the first doubt.
   */
  connect?: boolean;
  children: ReactNode;
}

export function RoomProvider({
  token,
  serverUrl,
  connect = true,
  children,
}: RoomProviderProps) {
  return (
    <LiveKitRoom
      serverUrl={serverUrl}
      token={token}
      connect={connect}
      audio={true}
      video={false}
      onConnected={() => console.log("[LiveKit] Connected to room")}
      onDisconnected={(reason) =>
        console.log("[LiveKit] Disconnected:", reason)
      }
      onError={(error) => console.error("[LiveKit] Error:", error)}
      style={{ width: "100%", height: "100%" }}
    >
      <RoomAudioRenderer />
      {children}
    </LiveKitRoom>
  );
}
