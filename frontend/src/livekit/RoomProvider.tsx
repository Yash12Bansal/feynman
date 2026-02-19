/**
 * LiveKit room provider for the classroom.
 *
 * Wraps the LiveKit components-react provider to manage the
 * WebRTC connection between the classroom screen and the backend agent.
 */

import type { ReactNode } from "react";

interface RoomProviderProps {
  token: string;
  serverUrl: string;
  children: ReactNode;
}

export function RoomProvider({ children }: RoomProviderProps) {
  // Placeholder — will integrate @livekit/components-react
  return <>{children}</>;
}
