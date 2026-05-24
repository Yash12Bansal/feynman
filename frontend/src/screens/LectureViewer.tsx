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
  SatisfactionPrompt,
  type SatisfactionOption,
} from "../components/SatisfactionPrompt";
import {
  useExtractionPlayback,
  type ChapterPayload,
  type DoubtBeatAnnotation,
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

interface DoubtResolutionFailedPayload {
  readonly type: "doubt_resolution_failed";
  readonly reason: string;
}

interface ResolutionReadyPayload {
  readonly type: "resolution_ready";
  readonly beats: number;
  readonly matched_diagram_ids: readonly string[];
}

interface DoubtBeatStartPayload {
  readonly type: "doubt_beat_start";
  readonly beat_index: number;
  readonly target_diagram_id: string | null;
  readonly annotation_actions: readonly DoubtBeatAnnotation[];
}

interface SatisfactionPromptPayload {
  readonly type: "satisfaction_prompt";
  readonly options: readonly SatisfactionOption[];
}

interface LectureResumePayload {
  readonly type: "lecture_resume";
}

interface DoubtCaptureReadyPayload {
  readonly type: "doubt_capture_ready";
}

type DoubtServerPayload =
  | DoubtCapturedPayload
  | DoubtCaptureFailedPayload
  | DoubtResolutionFailedPayload
  | ResolutionReadyPayload
  | DoubtBeatStartPayload
  | SatisfactionPromptPayload
  | LectureResumePayload
  | DoubtCaptureReadyPayload;

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

  const {
    slide,
    notebook,
    setAudioElement,
    cursor,
    currentTopicId,
    pause,
    play,
    applyDoubtBeat,
    clearDoubtAnnotations,
  } = useExtractionPlayback({ chapter, autoStart: true });

  const [doubtState, setDoubtState] = useState<AskFeynmanState>("idle");
  const [satisfactionOptions, setSatisfactionOptions] = useState<
    readonly SatisfactionOption[] | null
  >(null);
  const room = useRoomContext();

  const onDoubtMessage = useCallback(
    (msg: { payload: Uint8Array; topic?: string }) => {
      try {
        const text = new TextDecoder().decode(msg.payload);
        const parsed = JSON.parse(text) as DoubtServerPayload;
        switch (parsed.type) {
          case "doubt_captured":
            setDoubtState("thinking");
            return;
          case "doubt_capture_failed":
          case "doubt_resolution_failed":
            setDoubtState("idle");
            setSatisfactionOptions(null);
            return;
          case "resolution_ready":
            // Backend has the plan; voice + visuals start streaming next.
            // Stay in "thinking" until satisfaction_prompt arrives.
            return;
          case "doubt_beat_start":
            if (chapter) {
              applyDoubtBeat(
                {
                  target_diagram_id: parsed.target_diagram_id,
                  annotation_actions: parsed.annotation_actions,
                },
                chapter,
              );
            }
            return;
          case "satisfaction_prompt":
            setSatisfactionOptions(parsed.options);
            return;
          case "lecture_resume":
            setSatisfactionOptions(null);
            clearDoubtAnnotations();
            setDoubtState("idle");
            void play();
            return;
          case "doubt_capture_ready":
            setSatisfactionOptions(null);
            setDoubtState("listening");
            return;
        }
      } catch (err) {
        console.error("[LectureViewer] failed to parse doubt payload:", err);
      }
    },
    [applyDoubtBeat, chapter, clearDoubtAnnotations, play],
  );

  const onSatisfactionChoose = useCallback(
    (option: string) => {
      if (!room?.localParticipant) return;
      const payload = new TextEncoder().encode(
        JSON.stringify({ type: "satisfaction_choice", option }),
      );
      room.localParticipant
        .publishData(payload, { reliable: true, topic: DOUBT_TOPIC })
        .catch((err) => {
          console.error(
            "[LectureViewer] satisfaction publishData failed:",
            err,
          );
        });
      setSatisfactionOptions(null);
      // Hold button at "thinking" until the worker drives the next state.
      setDoubtState("thinking");
    },
    [room],
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
      {satisfactionOptions && (
        <SatisfactionPrompt
          options={satisfactionOptions}
          onChoose={onSatisfactionChoose}
        />
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
