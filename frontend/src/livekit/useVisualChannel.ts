import { useDataChannel, useRoomContext } from "@livekit/components-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { TranscriptionSegment, Participant } from "livekit-client";
import { RoomEvent } from "livekit-client";
import type {
  VisualInstruction,
  SwitchBoardInstruction,
  ClearInstruction,
  HighlightWalkInstruction,
  ScrollViewInstruction,
} from "../types/visuals";
import { useBoardStore } from "../engine/whiteboard/useBoardStore";
import type {
  BoardMeta,
  BoardTransition,
  CameraState,
  PendingSlide,
} from "../engine/whiteboard/useBoardStore";

/**
 * Phase 2 (voice-visual sync, Tier A): instructions with
 * `sync_mode === "after_next_sentence"` are queued instead of applied
 * immediately. They drain on the next sentence boundary detected in the
 * agent's TTS-aligned transcription. Hard timeout fallback (2s) ensures a
 * pending instruction never gets stuck — e.g., if the agent goes silent
 * after the tool call. See `docs/design/16-diagram-awareness-rearchitecture.md`.
 */
const SENTENCE_BOUNDARY = /[.!?]/;
const PENDING_FALLBACK_MS = 2000;

interface PendingEntry {
  readonly instruction: VisualInstruction;
  timer: ReturnType<typeof setTimeout> | null;
}

export interface VisualChannelResult {
  lastInstruction: VisualInstruction | null;
  /** Flat instruction array — legacy compat for non-whiteboard renderers. */
  instructions: VisualInstruction[];
  /** Active board's instructions — use for WhiteboardScene. */
  activeInstructions: VisualInstruction[];
  /** Active highlight walks — ephemeral, not stored in board. */
  activeWalks: HighlightWalkInstruction[];
  activeBoardId: string;
  activeBoardMeta: BoardMeta | null;
  pendingTransition: BoardTransition | null;
  cameraState: CameraState;
  /** Per-board pending-slide loader state. Set by `slide_pending`, cleared on slide arrival / board switch. */
  pendingSlide: Record<string, PendingSlide | undefined>;
  clearTransition: () => void;
  getBoardInstructions: (boardId: string) => VisualInstruction[];
  getBoardMeta: (boardId: string) => BoardMeta | null;
}

export function useVisualChannel(): VisualChannelResult {
  const [lastInstruction, setLastInstruction] =
    useState<VisualInstruction | null>(null);
  // Legacy flat array for non-whiteboard renderers (VisualScene card-list)
  const instructionsRef = useRef<VisualInstruction[]>([]);
  const [instructions, setInstructions] = useState<VisualInstruction[]>([]);

  // Highlight walks are ephemeral — separate channel, not stored in board.
  const [activeWalks, setActiveWalks] = useState<HighlightWalkInstruction[]>(
    [],
  );

  const store = useBoardStore();
  // Destructure stable methods (all wrapped in useCallback with [] deps)
  const { switchBoard, addInstruction, clearBoard, scrollTo } = store;

  const applyInstruction = useCallback(
    (parsed: VisualInstruction) => {
      if (parsed.type === "switch_board") {
        switchBoard(parsed as SwitchBoardInstruction);
        // Clear walks on board switch — they're tied to the current board
        setActiveWalks([]);
      } else if (parsed.type === "scroll_view") {
        // Ephemeral — update camera position, don't store in board
        const scroll = parsed as ScrollViewInstruction;
        scrollTo(scroll.target_x, scroll.target_y);
      } else if (parsed.type === "clear") {
        const clear = parsed as ClearInstruction;
        // boardId defaults to active board inside clearBoard when undefined
        clearBoard(clear.board_id, clear.target_id);

        // Legacy flat array
        if (clear.target_id) {
          instructionsRef.current = instructionsRef.current.filter(
            (i) => i.element_id !== clear.target_id,
          );
        } else {
          instructionsRef.current = [];
        }

        // Clear walks if board is cleared
        if (!clear.target_id) {
          setActiveWalks([]);
        }
      } else if (parsed.type === "highlight_walk") {
        // Ephemeral — don't store in board (avoids re-render of diagram cards).
        // Replace any existing walk on the same target to prevent accumulation.
        const walk = parsed as HighlightWalkInstruction;
        setActiveWalks((prev) => [
          ...prev.filter((w) => w.target_id !== walk.target_id),
          walk,
        ]);

        // Auto-expire: remove walk after its duration to prevent stale registrations.
        const walkDuration =
          walk.duration_ms ?? (walk.steps?.length ?? 1) * 5000;
        setTimeout(() => {
          setActiveWalks((prev) => prev.filter((w) => w !== walk));
        }, walkDuration + 1000);
      } else {
        addInstruction(parsed);

        // Legacy flat array
        instructionsRef.current = [...instructionsRef.current, parsed];
      }

      setInstructions(instructionsRef.current);
      setLastInstruction(parsed);
    },
    [switchBoard, addInstruction, clearBoard, scrollTo],
  );

  // Sentence-boundary queue for sync_mode === "after_next_sentence".
  const pendingRef = useRef<PendingEntry[]>([]);

  const drainPending = useCallback(() => {
    const entries = pendingRef.current;
    if (entries.length === 0) return;
    pendingRef.current = [];
    for (const entry of entries) {
      if (entry.timer !== null) clearTimeout(entry.timer);
      applyInstruction(entry.instruction);
    }
  }, [applyInstruction]);

  const enqueueDeferred = useCallback(
    (parsed: VisualInstruction) => {
      const entry: PendingEntry = { instruction: parsed, timer: null };
      entry.timer = setTimeout(() => {
        const idx = pendingRef.current.indexOf(entry);
        if (idx === -1) return; // already drained
        pendingRef.current.splice(idx, 1);
        entry.timer = null;
        applyInstruction(parsed);
      }, PENDING_FALLBACK_MS);
      pendingRef.current.push(entry);
    },
    [applyInstruction],
  );

  // Track per-segment text length so we only react to NEW `.!?` chars as they
  // appear in the TTS-aligned transcript stream. The agent emits cumulative
  // segment text on each update (LiveKit `_publish_transcription` pattern),
  // so substring-after-previous-length gives us the just-spoken delta.
  const segmentLengthRef = useRef<Map<string, number>>(new Map());

  const room = useRoomContext();

  const handleTranscription = useCallback(
    (segments: TranscriptionSegment[], participant?: Participant) => {
      // Skip the local participant — that's the student's STT, not agent speech.
      if (participant?.isLocal) return;
      let boundaryHit = false;
      for (const seg of segments) {
        const prev = segmentLengthRef.current.get(seg.id) ?? 0;
        const delta = seg.text.slice(prev);
        segmentLengthRef.current.set(seg.id, seg.text.length);
        if (SENTENCE_BOUNDARY.test(delta)) boundaryHit = true;
      }
      if (boundaryHit) drainPending();
    },
    [drainPending],
  );

  useEffect(() => {
    if (!room) return;
    room.on(RoomEvent.TranscriptionReceived, handleTranscription);
    return () => {
      room.off(RoomEvent.TranscriptionReceived, handleTranscription);
    };
  }, [room, handleTranscription]);

  // Clean up any still-pending timers if the channel unmounts mid-session.
  useEffect(() => {
    return () => {
      for (const entry of pendingRef.current) {
        if (entry.timer !== null) clearTimeout(entry.timer);
      }
      pendingRef.current = [];
    };
  }, []);

  const onMessage = useCallback(
    (msg: { payload: Uint8Array; topic?: string; from?: unknown }) => {
      try {
        const text = new TextDecoder().decode(msg.payload);
        const parsed = JSON.parse(text) as VisualInstruction;

        // Phase 2: annotation overlays (pin_label / highlight_pulse / etc.)
        // arrive ahead of the spoken word. Hold them until the next sentence
        // boundary so they land in sync with the agent's voice.
        if (parsed.sync_mode === "after_next_sentence") {
          enqueueDeferred(parsed);
          return;
        }

        applyInstruction(parsed);
      } catch (err) {
        console.error("[VisualChannel] Failed to parse:", err);
      }
    },
    [applyInstruction, enqueueDeferred],
  );

  useDataChannel("visuals", onMessage);

  return {
    lastInstruction,
    instructions,
    activeInstructions: store.activeInstructions,
    activeWalks,
    activeBoardId: store.activeBoardId,
    activeBoardMeta: store.activeBoardMeta,
    pendingTransition: store.pendingTransition,
    cameraState: store.cameraState,
    pendingSlide: store.pendingSlide,
    clearTransition: store.clearTransition,
    getBoardInstructions: store.getBoardInstructions,
    getBoardMeta: store.getBoardMeta,
  };
}
