import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import type { ReactNode } from "react";

interface RoomProviderProps {
  token: string;
  serverUrl: string;
  children: ReactNode;
}

export function RoomProvider({
  token,
  serverUrl,
  children,
}: RoomProviderProps) {
  return (
    <LiveKitRoom
      serverUrl={serverUrl}
      token={token}
      connect={true}
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
