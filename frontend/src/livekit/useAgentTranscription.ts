// TODO(DEADCODE): file unused in active pipelines (lecture-playback / ask-feynman) — interactive live-agent rendering (parked). See docs/engineering/13-redundant-code-audit.md Group 1/2. Safe to delete.
// import { useEffect, useCallback } from "react";
// import { useRoomContext } from "@livekit/components-react";
// import type { TranscriptionSegment, Participant } from "livekit-client";
// import { RoomEvent } from "livekit-client";

// /**
//  * Listens for agent (non-local) transcription events and calls `onWord`
//  * for each word in finalized segments.
//  */
// export function useAgentTranscription(onWord: (word: string) => void): void {
//   const room = useRoomContext();

//   const handleTranscription = useCallback(
//     (segments: TranscriptionSegment[], participant?: Participant) => {
//       // Only process agent transcription (not user STT)
//       if (participant?.isLocal) return;

//       for (const segment of segments) {
//         if (!segment.final) continue;
//         const words = segment.text.trim().split(/\s+/);
//         for (const word of words) {
//           if (word) onWord(word);
//         }
//       }
//     },
//     [onWord],
//   );

//   useEffect(() => {
//     if (!room) return;
//     room.on(RoomEvent.TranscriptionReceived, handleTranscription);
//     return () => {
//       room.off(RoomEvent.TranscriptionReceived, handleTranscription);
//     };
//   }, [room, handleTranscription]);
// }
