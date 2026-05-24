/**
 * Immersive lecture viewer mounted by ClassroomScreen when the session is
 * bound to a precomputed chapter. Consumes the same `useExtractionPlayback`
 * hook as the dev playground, but with `autoStart: true` and zero player
 * chrome — the student watches a lecture, they don't operate a player.
 *
 * Phase 3 overlays an `AskFeynmanButton`. Tapping it pauses the playback
 * engine, signals the backend over the LiveKit data channel, and flips into
 * "listening" → "thinking" states. Resolution delivery + satisfaction
 * prompt come in Phases 5+.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useDataChannel, useRoomContext } from "@livekit/components-react";
import { SplitBoard } from "../engine/whiteboard/split/SplitBoard";
import {
  AskFeynmanButton,
  type AskFeynmanState,
} from "../components/AskFeynmanButton";
import {
  useExtractionPlayback,
  type ChapterPayload,
} from "../hooks/useExtractionPlayback";

interface LectureViewerProps {
  readonly chapterId: string;
}

const DOUBT_TOPIC = "doubt_signal";

interface DoubtIntentPayload {
  readonly type: "doubt_intent";
  readonly chapter_id: string;
  readonly cursor: number;
  readonly topic_id: string | null;
}

interface DoubtCapturedPayload {
  readonly type: "doubt_captured";
  readonly text: string;
  readonly duration_ms: number;
}

interface DoubtCaptureFailedPayload {
  readonly type: "doubt_capture_failed";
  readonly reason: string;
}

type DoubtServerPayload = DoubtCapturedPayload | DoubtCaptureFailedPayload;

export function LectureViewer({ chapterId }: LectureViewerProps) {
  const [chapter, setChapter] = useState<ChapterPayload | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-prop-change pattern.
    setChapter(null);
    setFetchError(null);
    fetch(`/lecture-api/chapter/${encodeURIComponent(chapterId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: ChapterPayload) => setChapter(data))
      .catch((e: Error) => setFetchError(e.message));
  }, [chapterId]);

  const { slide, notebook, setAudioElement, cursor, currentTopicId, pause } =
    useExtractionPlayback({ chapter, autoStart: true });

  const [doubtState, setDoubtState] = useState<AskFeynmanState>("idle");
  const room = useRoomContext();

  const onDoubtMessage = useCallback(
    (msg: { payload: Uint8Array; topic?: string }) => {
      try {
        const text = new TextDecoder().decode(msg.payload);
        const parsed = JSON.parse(text) as DoubtServerPayload;
        if (parsed.type === "doubt_captured") {
          setDoubtState("thinking");
        } else if (parsed.type === "doubt_capture_failed") {
          // Capture failed — drop back to idle so the student can retry.
          setDoubtState("idle");
        }
      } catch (err) {
        console.error("[LectureViewer] failed to parse doubt payload:", err);
      }
    },
    [],
  );

  useDataChannel(DOUBT_TOPIC, onDoubtMessage);

  const onAskFeynman = useCallback(() => {
    if (doubtState !== "idle") return;
    if (!room?.localParticipant) {
      console.warn("[LectureViewer] no LiveKit room — ignoring Ask Feynman");
      return;
    }
    pause();
    setDoubtState("listening");
    const intent: DoubtIntentPayload = {
      type: "doubt_intent",
      chapter_id: chapterId,
      cursor,
      topic_id: currentTopicId,
    };
    const payload = new TextEncoder().encode(JSON.stringify(intent));
    room.localParticipant
      .publishData(payload, { reliable: true, topic: DOUBT_TOPIC })
      .catch((err) => {
        console.error("[LectureViewer] publishData failed:", err);
        setDoubtState("idle");
      });
  }, [doubtState, room, pause, chapterId, cursor, currentTopicId]);

  const body = useMemo(() => {
    if (fetchError) {
      return (
        <div style={statusTextStyle}>Failed to load lecture: {fetchError}</div>
      );
    }
    if (!chapter) {
      return <div style={statusTextStyle}>Preparing lecture…</div>;
    }
    return (
      <>
        <SplitBoard
          slide={slide}
          notebook={notebook}
          mode="split"
          notebookTitle={chapter.title}
        />
        <audio ref={setAudioElement} preload="auto" />
      </>
    );
  }, [chapter, fetchError, notebook, setAudioElement, slide]);

  return (
    <ImmersiveShell>
      {body}
      {chapter && (
        <AskFeynmanButton state={doubtState} onActivate={onAskFeynman} />
      )}
    </ImmersiveShell>
  );
}

interface ImmersiveShellProps {
  readonly children: React.ReactNode;
}

function ImmersiveShell({ children }: ImmersiveShellProps) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#0a0a0a",
        color: "#fafafa",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
}

const statusTextStyle: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#6b7280",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontSize: "0.95rem",
  letterSpacing: "0.05em",
};
