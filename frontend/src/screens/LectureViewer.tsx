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
import { InLectureFeedback } from "../feedback/InLectureFeedback";
import {
  useExtractionPlayback,
  type BoardSnapshot,
  type ChapterPayload,
  type ManifestEvent,
  type TopicJumpEntry,
} from "../hooks/useExtractionPlayback";
import type { DesignDiagramSpec } from "../types/visuals";

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
  // True when the doubt is a local clarification about a diagram already on the
  // board: the doubt board is seeded with a copy of the current page (diagram +
  // notebook) and the resolution builds on it. Absent/false → fresh blank board.
  readonly carry_over?: boolean;
  readonly matched_diagram_ids: readonly string[];
}

interface DoubtBeatStartPayload {
  readonly type: "doubt_beat_start";
  readonly beat_index: number;
  // Board events in the lecture's ManifestEvent vocabulary — replayed on the
  // doubt board through the same applySyncEvent path the lecture uses.
  readonly board_events: readonly ManifestEvent[];
}

interface DoubtDiagramReadyPayload {
  readonly type: "doubt_diagram_ready";
  readonly diagram_id: string;
  // A generated diagram ships a spec; a canonical template ships a
  // template_concept_id (spec null) and the client builds it from the registry.
  readonly spec?: DesignDiagramSpec | null;
  readonly template_concept_id?: string | null;
  readonly template_params?: Record<string, number> | null;
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

// Fired by the worker the moment the student starts speaking. Capture then
// runs until 5s of continuous silence, which can exceed the short "listening"
// stuck-timeout — this lets us extend it so we don't wrongly give up mid-doubt.
interface DoubtListeningPayload {
  readonly type: "doubt_listening";
}

type DoubtServerPayload =
  | DoubtCapturedPayload
  | DoubtCaptureFailedPayload
  | DoubtResolutionFailedPayload
  | ResolutionReadyPayload
  | DoubtBeatStartPayload
  | DoubtDiagramReadyPayload
  | SatisfactionPromptPayload
  | LectureResumePayload
  | DoubtCaptureReadyPayload
  | DoubtListeningPayload;

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
    chapterDurationMs,
    currentLectureMs,
    topicJumps,
    pause,
    play,
    seekToEvent,
    seekToTimeMs,
    waitForIdle,
    beginDoubtBoard,
    beginDoubtBoardFromCurrent,
    addDoubtDiagram,
    applyDoubtBoardEvents,
    clearDoubtAnnotations,
  } = useExtractionPlayback({ chapter, autoStart: true });

  const [doubtState, setDoubtState] = useState<AskFeynmanState>("idle");
  const [doubtErrorMessage, setDoubtErrorMessage] = useState<string>("");
  const [satisfactionOptions, setSatisfactionOptions] = useState<
    readonly SatisfactionOption[] | null
  >(null);
  // True while the in-lecture feedback wizard is up — hides player chrome so the
  // wizard gets the same clean backdrop the doubt flow / satisfaction prompt do.
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const room = useRoomContext();

  // Subtitle (closed-caption) prefs. Visibility + size persist across
  // reloads via localStorage (YouTube-style). Position is per-session only —
  // when the user drags the band somewhere, we keep it there until the next
  // page load; defaults centered above the scrubber.
  const [subtitlesHidden, setSubtitlesHidden] = useState<boolean>(
    () => _readCCPref("feynman.cc.hidden") === "1",
  );
  const [subtitleSize, setSubtitleSize] = useState<"S" | "M" | "L">(() => {
    const v = _readCCPref("feynman.cc.size");
    return v === "S" || v === "L" ? v : "M";
  });
  const [subtitlePos, setSubtitlePos] = useState<{ x: number; y: number } | null>(null);
  // Brief on-screen confirmation when a CC hotkey fires. Without this the
  // size change is easy to miss (especially Small→Medium), and toggling C
  // when subtitles are already empty looks like nothing happened.
  const [ccToast, setCCToast] = useState<string | null>(null);
  const ccToastTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flashCCToast = useCallback((msg: string) => {
    setCCToast(msg);
    if (ccToastTimeoutRef.current) clearTimeout(ccToastTimeoutRef.current);
    ccToastTimeoutRef.current = setTimeout(() => setCCToast(null), 1400);
  }, []);
  useEffect(() => {
    _writeCCPref("feynman.cc.hidden", subtitlesHidden ? "1" : "0");
  }, [subtitlesHidden]);
  useEffect(() => {
    _writeCCPref("feynman.cc.size", subtitleSize);
  }, [subtitleSize]);
  // Reset position when the chapter changes (per-session ≈ per-chapter is
  // a reasonable interpretation; a fresh chapter starts in the default spot).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- chapter-id is a prop-bound reset, same pattern as the fetch effect above.
    setSubtitlePos(null);
  }, [chapterId]);

  // Keyboard shortcuts for subtitle controls. `C` toggles visibility,
  // `+`/`=` and `-`/`_` adjust the size preset. Ignored while typing into
  // an input/textarea so they don't collide with text entry elsewhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      if (e.key === "c" || e.key === "C") {
        setSubtitlesHidden((v) => {
          flashCCToast(v ? "Subtitles: On" : "Subtitles: Off");
          return !v;
        });
      } else if (e.key === "+" || e.key === "=") {
        setSubtitleSize((s) => {
          const next: "S" | "M" | "L" = s === "S" ? "M" : "L";
          flashCCToast(`Subtitles: ${SUBTITLE_SIZE_LABEL[next]}`);
          return next;
        });
      } else if (e.key === "-" || e.key === "_") {
        setSubtitleSize((s) => {
          const next: "S" | "M" | "L" = s === "L" ? "M" : "S";
          flashCCToast(`Subtitles: ${SUBTITLE_SIZE_LABEL[next]}`);
          return next;
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flashCCToast]);

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
          case "doubt_listening":
            // Student is mid-doubt; capture runs until 5s of continuous silence
            // (up to ~90s). Stay in listening and extend the stuck-timeout so a
            // long, multi-sentence doubt isn't cut off as "didn't hear you".
            setDoubtState("listening");
            armStuckTimeout(
              95_000,
              "I didn't catch the end of that — check your mic is working.",
            );
            return;
          case "doubt_capture_failed":
          case "doubt_resolution_failed":
            setDoubtState("idle");
            setSatisfactionOptions(null);
            return;
          case "resolution_ready":
            // Set up the doubt board now that we know the doubt's shape:
            // carry_over → seed it with the current page (diagram + notebook)
            // already on screen and build on it; otherwise → a fresh blank
            // scratch board. (The lecture board was snapshotted on pause() and
            // is restored on resume regardless.)
            if (parsed.carry_over) {
              beginDoubtBoardFromCurrent();
            } else {
              beginDoubtBoard();
            }
            // Voice + visuals start streaming next. Re-arm the thinking
            // timeout — we're not done until the satisfaction prompt arrives.
            armStuckTimeout(
              75_000,
              "Feynman's taking too long to respond. Check the worker logs.",
            );
            return;
          case "doubt_diagram_ready":
            // A doubt diagram arrived — a generated spec, or a canonical
            // template ref the client builds from the registry. Register it so
            // the following beat's show_diagram can resolve its id.
            addDoubtDiagram(
              parsed.diagram_id,
              parsed.spec ?? null,
              parsed.template_concept_id,
              parsed.template_params,
            );
            return;
          case "doubt_beat_start":
            // Replay the beat's board events on the doubt board (diagram +
            // notebook + annotations), same vocabulary as the lecture.
            applyDoubtBoardEvents(parsed.board_events);
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
      addDoubtDiagram,
      applyDoubtBoardEvents,
      armStuckTimeout,
      beginDoubtBoard,
      beginDoubtBoardFromCurrent,
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
    // Snapshot taken by pause(). The doubt board is set up later, on
    // resolution_ready, once we know whether to carry over the current page
    // (local clarification → build on the diagram + notebook on screen) or
    // start a fresh blank board — so the student keeps seeing what they asked
    // about while Feynman thinks.
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
  // lecture was playing when the user grabbed the thumb. The mouseup → seek
  // gap gives the inflight loop time to unwind on its own; we still await
  // waitForIdle defensively so the contract matches the topic-jump path.
  const onSeekStart = useCallback(() => {
    wasPlayingBeforeSeekRef.current = status === "playing";
    if (status === "playing") pause();
  }, [pause, status]);
  const onSeekCommit = useCallback(
    async (ms: number) => {
      await waitForIdle();
      seekToTimeMs(ms);
      if (wasPlayingBeforeSeekRef.current) void play();
    },
    [seekToTimeMs, play, waitForIdle],
  );

  // Topic jump: same auto-resume semantics as the scrubber. Critical: we
  // MUST wait for the inflight playback loop to finish unwinding before
  // calling seekToEvent. Otherwise the loop's abort branch (which runs on
  // the next microtask) overwrites cursorRef with `oldIdx + 1`, undoing the
  // seek and stranding playback without ever calling play() again — that
  // was the "audio doesn't catch up to the new slide" bug.
  const onTopicJump = useCallback(
    async (eventIndex: number) => {
      const wasPlaying = status === "playing";
      if (wasPlaying) pause();
      await waitForIdle();
      seekToEvent(eventIndex);
      if (wasPlaying) void play();
    },
    [pause, play, seekToEvent, status, waitForIdle],
  );

  const doubtActive = doubtState !== "idle";
  // Hide player chrome during a doubt branch OR while the feedback wizard is up.
  const chromeHidden = doubtActive || feedbackOpen;

  return (
    <ImmersiveShell>
      {body}
      {chapter && !chromeHidden && (
        <PausePlayButton paused={isPaused} onToggle={onPauseToggle} />
      )}
      {chapter && !chromeHidden && topicJumps.length > 0 && (
        <TopicJumpMenu
          topics={topicJumps}
          currentTopicId={currentTopicId}
          onJump={onTopicJump}
        />
      )}
      {chapter && !chromeHidden && !subtitlesHidden && currentNarrationText && (
        <TranscriptBand
          text={currentNarrationText}
          size={subtitleSize}
          position={subtitlePos}
          onPositionChange={setSubtitlePos}
        />
      )}
      {ccToast && <CCToast text={ccToast} />}
      {chapter && !chromeHidden && chapterDurationMs > 0 && (
        <Scrubber
          totalMs={chapterDurationMs}
          currentMs={currentLectureMs}
          onSeekStart={onSeekStart}
          onSeekCommit={onSeekCommit}
        />
      )}
      {chapter && !feedbackOpen && (
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
      {chapter && (
        <InLectureFeedback
          currentMs={currentLectureMs}
          durationMs={chapterDurationMs}
          enabled={!doubtActive && satisfactionOptions === null}
          isPlaying={status === "playing"}
          pause={pause}
          play={play}
          onOpenChange={setFeedbackOpen}
        />
      )}
    </ImmersiveShell>
  );
}

interface TranscriptBandProps {
  readonly text: string;
  readonly size: "S" | "M" | "L";
  readonly position: { x: number; y: number } | null;
  readonly onPositionChange: (p: { x: number; y: number } | null) => void;
}

const SUBTITLE_FONT: Record<"S" | "M" | "L", string> = {
  S: "0.75rem",
  M: "1.05rem",
  L: "1.6rem",
};
const SUBTITLE_SIZE_LABEL: Record<"S" | "M" | "L", string> = {
  S: "Small",
  M: "Medium",
  L: "Large",
};

function TranscriptBand({
  text,
  size,
  position,
  onPositionChange,
}: TranscriptBandProps) {
  // Drag state: local dx/dy relative to the band's top-left at drag start,
  // so the cursor stays "stuck" to the same point inside the band while
  // dragging — feels native instead of snapping the band's center to cursor.
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);

  const onMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      // Left button only — right-click should still let the user select text.
      if (e.button !== 0) return;
      const rect = e.currentTarget.getBoundingClientRect();
      dragRef.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
      // Seed position from current rect so the first move is jump-free even
      // if we're starting from the default centered layout.
      onPositionChange({ x: rect.left, y: rect.top });
      e.preventDefault();
    },
    [onPositionChange],
  );

  useEffect(() => {
    if (dragRef.current === null) return;
    const onMove = (ev: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      // Clamp to viewport with a small margin so the band can't be lost
      // off-screen. Width/height read off the element each frame is fine —
      // a typed transcript is ~40px tall.
      const margin = 8;
      const w = 360; // typical band width; clamp uses a conservative estimate
      const h = 60;
      const x = Math.min(
        Math.max(margin, ev.clientX - d.dx),
        window.innerWidth - w - margin,
      );
      const y = Math.min(
        Math.max(margin, ev.clientY - d.dy),
        window.innerHeight - h - margin,
      );
      onPositionChange({ x, y });
    };
    const onUp = () => {
      dragRef.current = null;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    // We deliberately rebind on each position so the closure sees fresh
    // onPositionChange — the dragRef gate keeps the work cheap when idle.
  }, [position, onPositionChange]);

  const positioned = position
    ? { left: position.x, top: position.y, transform: "none" as const }
    : { left: "50%" as const, bottom: 80, transform: "translateX(-50%)" as const };

  return (
    <div
      onMouseDown={onMouseDown}
      style={{
        position: "fixed",
        // Default placement sits ABOVE the scrubber (bottom: 24, ~40px tall).
        // Anchor at the bottom so the band grows UPWARD for multi-line
        // transcripts. When the user drags, we switch to top/left positioning.
        ...positioned,
        zIndex: 90,
        maxWidth: "min(72vw, 920px)",
        padding: "10px 22px",
        background: "rgba(12, 13, 16, 0.78)",
        border: "1px solid rgba(232, 232, 238, 0.10)",
        borderRadius: 14,
        color: "rgba(232, 232, 238, 0.88)",
        fontSize: SUBTITLE_FONT[size],
        lineHeight: 1.5,
        textAlign: "center",
        backdropFilter: "blur(8px)",
        // The band catches mouse events so it can be dragged; cursor reflects
        // that affordance. Text inside is still selectable on mouseup.
        cursor: "move",
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
      <span style={{ minWidth: 44, textAlign: "right" }}>
        {_fmtMs(displayMs)}
      </span>
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

// Flash pill shown when a subtitle hotkey fires. Pure presentation; the
// parent owns the visibility timer.
function CCToast({ text }: { readonly text: string }) {
  return (
    <div
      style={{
        position: "fixed",
        top: 32,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 110,
        padding: "8px 16px",
        background: "rgba(12, 13, 16, 0.85)",
        border: "1px solid rgba(232, 232, 238, 0.18)",
        borderRadius: 999,
        color: "rgba(232, 232, 238, 0.92)",
        fontSize: "0.85rem",
        letterSpacing: "0.01em",
        backdropFilter: "blur(8px)",
        pointerEvents: "none",
        userSelect: "none",
      }}
    >
      {text}
    </div>
  );
}

// localStorage shims — defensive against environments without it (jsdom in
// tests, SSR if we ever do it, Safari private mode quota errors).
function _readCCPref(key: string): string | null {
  try {
    return window.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}
function _writeCCPref(key: string, value: string): void {
  try {
    window.localStorage?.setItem(key, value);
  } catch {
    /* swallow — preference loss isn't worth crashing the player. */
  }
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

function TopicJumpMenu({ topics, currentTopicId, onJump }: TopicJumpMenuProps) {
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
