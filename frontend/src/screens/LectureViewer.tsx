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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  type BoardSnapshot,
  type ChapterPayload,
  type DoubtBeatAnnotation,
  type TopicJumpEntry,
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
  // feat/unify_boardstate consumer: authoritative "what is on the board"
  // at the moment the doubt was raised. The backend uses this to scope the
  // resolution prompt instead of guessing from the chapter context alone.
  // Null for chapters ingested before snapshots existed.
  readonly board_snapshot: BoardSnapshot | null;
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
    status,
    slide,
    notebook,
    setAudioElement,
    cursor,
    currentTopicId,
    currentSnapshot,
    currentNarrationText,
    totalAudioMs,
    currentAudioOffsetMs,
    topicJumps,
    pause,
    play,
    seekToEvent,
    seekToTimeMs,
    applyDoubtBeat,
    clearDoubtAnnotations,
  } = useExtractionPlayback({ chapter, autoStart: true });

  const [doubtState, setDoubtState] = useState<AskFeynmanState>("idle");
  const [doubtErrorMessage, setDoubtErrorMessage] = useState<string>("");
  const [satisfactionOptions, setSatisfactionOptions] = useState<
    readonly SatisfactionOption[] | null
  >(null);
  const room = useRoomContext();

  // Hotfix: bound the listening / thinking states with explicit timeouts
  // so a silent backend (worker down, mic permission denied, network
  // hiccup) surfaces as a clear error instead of an infinite spinner.
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearStuckTimeout = useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);
  const armStuckTimeout = useCallback(
    (ms: number, message: string) => {
      clearStuckTimeout();
      timeoutRef.current = setTimeout(() => {
        setDoubtErrorMessage(message);
        setDoubtState("error");
        timeoutRef.current = null;
      }, ms);
    },
    [clearStuckTimeout],
  );

  useEffect(() => clearStuckTimeout, [clearStuckTimeout]);

  const onDoubtMessage = useCallback(
    (msg: { payload: Uint8Array; topic?: string }) => {
      try {
        const text = new TextDecoder().decode(msg.payload);
        const parsed = JSON.parse(text) as DoubtServerPayload;
        // Any worker message means the backend is alive — clear the
        // stuck-state timeout, then arm a new one for the next leg.
        clearStuckTimeout();
        switch (parsed.type) {
          case "doubt_captured":
            setDoubtState("thinking");
            armStuckTimeout(
              75_000,
              "Feynman's taking too long to respond. Check the worker logs.",
            );
            return;
          case "doubt_capture_failed":
          case "doubt_resolution_failed":
            setDoubtState("idle");
            setSatisfactionOptions(null);
            return;
          case "resolution_ready":
            // Backend has the plan; voice + visuals start streaming next.
            // Re-arm the thinking timeout — we're not done until the
            // satisfaction prompt arrives.
            armStuckTimeout(
              75_000,
              "Feynman's taking too long to respond. Check the worker logs.",
            );
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
            armStuckTimeout(
              12_000,
              "I didn't hear anything. Make sure your mic is granted and the worker is running.",
            );
            return;
        }
      } catch (err) {
        console.error("[LectureViewer] failed to parse doubt payload:", err);
      }
    },
    [
      applyDoubtBeat,
      armStuckTimeout,
      chapter,
      clearDoubtAnnotations,
      clearStuckTimeout,
      play,
    ],
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
    armStuckTimeout(
      12_000,
      "I didn't hear anything. Make sure your mic is granted and the worker is running.",
    );
    const intent: DoubtIntentPayload = {
      type: "doubt_intent",
      chapter_id: chapterId,
      cursor,
      topic_id: currentTopicId,
      board_snapshot: currentSnapshot,
    };
    const payload = new TextEncoder().encode(JSON.stringify(intent));
    room.localParticipant
      .publishData(payload, { reliable: true, topic: DOUBT_TOPIC })
      .catch((err) => {
        console.error("[LectureViewer] publishData failed:", err);
        clearStuckTimeout();
        setDoubtState("idle");
      });
  }, [
    doubtState,
    room,
    pause,
    armStuckTimeout,
    clearStuckTimeout,
    chapterId,
    cursor,
    currentTopicId,
    currentSnapshot,
  ]);

  const onErrorRetry = useCallback(() => {
    clearStuckTimeout();
    setDoubtState("idle");
    setSatisfactionOptions(null);
    setDoubtErrorMessage("");
  }, [clearStuckTimeout]);

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

  // Pause/resume — toggles the playback engine. The doubt path already uses
  // pause()/play() internally; we explicitly hide this button while a doubt
  // session is active so the two controls never fight.
  const isPaused = status === "paused";
  const wasPlayingBeforeSeekRef = useRef(false);
  const onPauseToggle = useCallback(() => {
    if (isPaused) {
      void play();
    } else {
      pause();
    }
  }, [isPaused, pause, play]);

  // Scrubber: keep playback state intact across a seek. Auto-resume if the
  // lecture was playing when the user grabbed the thumb.
  const onSeekStart = useCallback(() => {
    wasPlayingBeforeSeekRef.current = status === "playing";
    if (status === "playing") pause();
  }, [pause, status]);
  const onSeekCommit = useCallback(
    (ms: number) => {
      seekToTimeMs(ms);
      if (wasPlayingBeforeSeekRef.current) void play();
    },
    [seekToTimeMs, play],
  );

  // Topic jump: same auto-resume semantics as the scrubber.
  const onTopicJump = useCallback(
    (eventIndex: number) => {
      const wasPlaying = status === "playing";
      if (wasPlaying) pause();
      seekToEvent(eventIndex);
      if (wasPlaying) void play();
    },
    [pause, play, seekToEvent, status],
  );

  const doubtActive = doubtState !== "idle";

  return (
    <ImmersiveShell>
      {body}
      {chapter && !doubtActive && (
        <PausePlayButton paused={isPaused} onToggle={onPauseToggle} />
      )}
      {chapter && !doubtActive && topicJumps.length > 0 && (
        <TopicJumpMenu
          topics={topicJumps}
          currentTopicId={currentTopicId}
          onJump={onTopicJump}
        />
      )}
      {chapter && !doubtActive && currentNarrationText && (
        <TranscriptBand text={currentNarrationText} />
      )}
      {chapter && !doubtActive && totalAudioMs > 0 && (
        <Scrubber
          totalMs={totalAudioMs}
          currentMs={currentAudioOffsetMs}
          onSeekStart={onSeekStart}
          onSeekCommit={onSeekCommit}
        />
      )}
      {chapter && (
        <AskFeynmanButton
          state={doubtState}
          onActivate={onAskFeynman}
          onRetry={onErrorRetry}
          errorMessage={doubtErrorMessage}
        />
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

interface TranscriptBandProps {
  readonly text: string;
}

function TranscriptBand({ text }: TranscriptBandProps) {
  return (
    <div
      style={{
        position: "fixed",
        // Sit ABOVE the scrubber (bottom: 24, ~40px tall). Anchor at the
        // bottom so the band grows UPWARD for multi-line transcripts.
        bottom: 80,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 90,
        maxWidth: "min(72vw, 920px)",
        padding: "10px 22px",
        background: "rgba(12, 13, 16, 0.78)",
        border: "1px solid rgba(232, 232, 238, 0.10)",
        borderRadius: 14,
        color: "rgba(232, 232, 238, 0.88)",
        fontSize: "1rem",
        lineHeight: 1.5,
        textAlign: "center",
        backdropFilter: "blur(8px)",
        pointerEvents: "none",
        userSelect: "text",
      }}
    >
      {text}
    </div>
  );
}

interface ScrubberProps {
  readonly totalMs: number;
  readonly currentMs: number;
  readonly onSeekStart: () => void;
  readonly onSeekCommit: (ms: number) => void;
}

function Scrubber({
  totalMs,
  currentMs,
  onSeekStart,
  onSeekCommit,
}: ScrubberProps) {
  // Local drag value — overrides currentMs while the user is interacting
  // with the slider so the thumb doesn't fight the live progress updates.
  const [dragMs, setDragMs] = useState<number | null>(null);
  const displayMs = dragMs ?? currentMs;
  const pct = totalMs > 0 ? Math.min(100, (displayMs / totalMs) * 100) : 0;

  return (
    <div
      style={{
        position: "fixed",
        // Sit at the bottom — pause button (left) and Ask Feynman (right)
        // are also at bottom: 32 but at the edges, so center-anchored
        // scrubber doesn't conflict horizontally. Transcript band sits
        // ABOVE this (bottom: 80, anchored bottom so it grows upward).
        bottom: 24,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 95,
        width: "min(72vw, 920px)",
        padding: "8px 16px",
        display: "flex",
        alignItems: "center",
        gap: 14,
        background: "rgba(12, 13, 16, 0.72)",
        border: "1px solid rgba(232, 232, 238, 0.10)",
        borderRadius: 999,
        backdropFilter: "blur(8px)",
        fontSize: "0.72rem",
        color: "rgba(232, 232, 238, 0.70)",
        fontVariantNumeric: "tabular-nums",
        userSelect: "none",
      }}
    >
      <span style={{ minWidth: 44, textAlign: "right" }}>{_fmtMs(displayMs)}</span>
      <input
        type="range"
        min={0}
        max={totalMs}
        step={500}
        value={Math.round(displayMs)}
        onMouseDown={() => {
          onSeekStart();
          setDragMs(currentMs);
        }}
        onTouchStart={() => {
          onSeekStart();
          setDragMs(currentMs);
        }}
        onChange={(e) => setDragMs(Number(e.currentTarget.value))}
        onMouseUp={(e) => {
          const val = Number(e.currentTarget.value);
          setDragMs(null);
          onSeekCommit(val);
        }}
        onTouchEnd={(e) => {
          const val = Number(e.currentTarget.value);
          setDragMs(null);
          onSeekCommit(val);
        }}
        aria-label="Seek lecture"
        style={{
          flex: 1,
          // The webkit / moz pseudo-elements that style the range are CSS-only
          // so we leave them at the browser default for now; the surrounding
          // pill gives the band shape. Range itself is intentionally minimal.
          accentColor: "#7fd4ff",
          height: 4,
          cursor: "pointer",
          background: `linear-gradient(to right, rgba(127, 212, 255, 0.55) 0%, rgba(127, 212, 255, 0.55) ${pct}%, rgba(232, 232, 238, 0.15) ${pct}%, rgba(232, 232, 238, 0.15) 100%)`,
          borderRadius: 2,
          appearance: "none",
        }}
      />
      <span style={{ minWidth: 44 }}>{_fmtMs(totalMs)}</span>
    </div>
  );
}

function _fmtMs(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface TopicJumpMenuProps {
  readonly topics: readonly TopicJumpEntry[];
  readonly currentTopicId: string | null;
  readonly onJump: (eventIndex: number) => void;
}

function TopicJumpMenu({
  topics,
  currentTopicId,
  onJump,
}: TopicJumpMenuProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Jump to topic"
        title="Jump to topic"
        style={{
          position: "fixed",
          top: 32,
          right: 32,
          zIndex: 100,
          padding: "10px 18px",
          borderRadius: 999,
          background: "rgba(20, 20, 24, 0.85)",
          border: "1px solid rgba(232, 232, 238, 0.18)",
          color: "#e8e8ee",
          fontSize: "0.85rem",
          cursor: "pointer",
          backdropFilter: "blur(6px)",
          boxShadow: "0 6px 20px rgba(0, 0, 0, 0.45)",
        }}
      >
        ☰ Topics
      </button>
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 98,
            background: "rgba(0,0,0,0.30)",
            backdropFilter: "blur(2px)",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              top: 88,
              right: 32,
              zIndex: 99,
              width: 340,
              maxHeight: "70vh",
              overflowY: "auto",
              padding: "12px 0",
              background: "rgba(18, 19, 22, 0.95)",
              border: "1px solid rgba(232, 232, 238, 0.14)",
              borderRadius: 14,
              boxShadow: "0 12px 40px rgba(0, 0, 0, 0.55)",
              backdropFilter: "blur(10px)",
            }}
          >
            <div
              style={{
                padding: "4px 18px 10px",
                fontSize: "0.72rem",
                letterSpacing: "0.05em",
                textTransform: "uppercase",
                color: "rgba(232, 232, 238, 0.45)",
              }}
            >
              Jump to topic
            </div>
            {topics.map((t) => {
              const active = t.topicId === currentTopicId;
              return (
                <button
                  key={t.topicId}
                  type="button"
                  onClick={() => {
                    onJump(t.eventIndex);
                    setOpen(false);
                  }}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: "10px 18px",
                    background: active
                      ? "rgba(127, 212, 255, 0.12)"
                      : "transparent",
                    border: "none",
                    borderLeft: active
                      ? "3px solid #7fd4ff"
                      : "3px solid transparent",
                    textAlign: "left",
                    color: active ? "#e8e8ee" : "rgba(232, 232, 238, 0.78)",
                    fontSize: "0.92rem",
                    cursor: "pointer",
                  }}
                >
                  <div
                    style={{
                      fontSize: "0.7rem",
                      color: "rgba(232, 232, 238, 0.45)",
                      letterSpacing: "0.04em",
                      marginBottom: 2,
                    }}
                  >
                    {t.section}
                  </div>
                  {t.name}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

interface PausePlayButtonProps {
  readonly paused: boolean;
  readonly onToggle: () => void;
}

function PausePlayButton({ paused, onToggle }: PausePlayButtonProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={paused ? "Resume lecture" : "Pause lecture"}
      title={paused ? "Resume" : "Pause"}
      style={{
        position: "fixed",
        bottom: 32,
        left: 32,
        zIndex: 100,
        width: 52,
        height: 52,
        borderRadius: 26,
        background: "rgba(20, 20, 24, 0.85)",
        border: "1px solid rgba(232, 232, 238, 0.18)",
        color: "#e8e8ee",
        fontSize: 18,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 6px 20px rgba(0, 0, 0, 0.45)",
        backdropFilter: "blur(6px)",
        transition: "transform 0.08s, background 0.12s",
      }}
      onMouseDown={(e) => (e.currentTarget.style.transform = "scale(0.94)")}
      onMouseUp={(e) => (e.currentTarget.style.transform = "scale(1)")}
      onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
    >
      {paused ? "▶" : "❚❚"}
    </button>
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
