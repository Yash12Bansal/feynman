/**
 * Headless component that captures the board surface as a compressed PNG
 * on demand, triggered by a data channel message from the backend.
 *
 * Renders nothing visible — just listens for capture requests and responds
 * with the screenshot via the same data channel.
 */

import { useDataChannel, useRoomContext } from "@livekit/components-react";
import html2canvas from "html2canvas";
import { useCallback } from "react";

interface CaptureRequest {
  type: "capture_board";
  request_id: string;
  max_width?: number;
  max_height?: number;
}

interface Props {
  boardSurfaceRef: React.RefObject<HTMLDivElement | null>;
}

export function BoardCapture({ boardSurfaceRef }: Props) {
  const room = useRoomContext();

  const handleMessage = useCallback(
    (msg: { payload: Uint8Array }) => {
      let parsed: CaptureRequest;
      try {
        const text = new TextDecoder().decode(msg.payload);
        parsed = JSON.parse(text) as CaptureRequest;
      } catch {
        return;
      }
      if (parsed.type !== "capture_board") return;
      if (!boardSurfaceRef.current) return;

      const maxW = parsed.max_width ?? 512;
      const maxH = parsed.max_height ?? 288;
      const requestId = parsed.request_id;

      // Capture asynchronously — fire and forget from the callback.
      void (async () => {
        try {
          const canvas = await html2canvas(boardSurfaceRef.current!, {
            width: maxW,
            height: maxH,
            scale: 0.5,
            logging: false,
            useCORS: true,
          });

          const dataUrl = canvas.toDataURL("image/png", 0.7);
          const b64 = dataUrl.replace(/^data:image\/png;base64,/, "");

          const response = JSON.stringify({
            type: "capture_response",
            request_id: requestId,
            image_data: b64,
          });

          room.localParticipant.publishData(
            new TextEncoder().encode(response),
            { topic: "board_capture", reliable: true },
          );
        } catch (err) {
          console.error("[BoardCapture] Failed to capture board:", err);
        }
      })();
    },
    [boardSurfaceRef, room],
  );

  useDataChannel("board_capture", handleMessage);

  return null;
}
