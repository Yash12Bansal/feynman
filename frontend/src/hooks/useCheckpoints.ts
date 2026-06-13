/**
 * In-lecture question checkpoints (Apple 3, Phase 2).
 *
 * When a topic ends, ask that topic's question (if it has one). The lecture
 * pauses; the student solves; on submit we record the attempt and reveal the
 * solution — then resume. The solution (incl. its diagram) is fetched the
 * instant the question appears, so it's ready by the time the student submits.
 *
 * This hook owns the checkpoint STATE machine; the player's pause/play are
 * injected. Pure data — the UI lives in QuestionCheckpoint.
 */

import { useCallback, useRef, useState } from "react";
import {
  checkpointTtsUrl,
  explanationNarration,
  fetchCheckpoint,
  fetchSolution,
  promptNarration,
  submitAttempt,
  type AttemptOutcome,
  type CheckpointQuestion,
  type Solution,
} from "../lib/api";

interface UseCheckpointsOpts {
  readonly studentId: string | null | undefined;
  readonly sessionId: string | null | undefined;
  readonly pause: () => void;
  readonly play: () => void;
}

interface CheckpointController {
  /** The active question, or null when no checkpoint is up. */
  readonly question: CheckpointQuestion | null;
  /** The solution, fetched in the background during think-time. */
  readonly solution: Solution | null;
  /** Set after submit — correctness + revealed answer. */
  readonly outcome: AttemptOutcome | null;
  /** Call when a topic STARTS — warms the question (+ its diagram) so it's
   *  ready the instant that topic ends. */
  readonly prefetchForTopic: (topicId: string) => void;
  /** Call when a topic ENDS — opens the (pre-warmed) checkpoint if one exists. */
  readonly triggerForTopic: (topicId: string) => void;
  readonly submit: (selectedOption: string) => Promise<void>;
  readonly dismiss: () => void;
}

export function useCheckpoints({
  studentId,
  sessionId,
  pause,
  play,
}: UseCheckpointsOpts): CheckpointController {
  const [question, setQuestion] = useState<CheckpointQuestion | null>(null);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [outcome, setOutcome] = useState<AttemptOutcome | null>(null);
  // Topics already checkpointed this sitting — so a seek/replay never re-asks.
  const askedRef = useRef<Set<string>>(new Set());
  // Prefetch bookkeeping: which topics we've kicked a fetch for, and the
  // resolved result (CheckpointQuestion | null). Warming on topic-start gives
  // the backend the whole topic to build the question diagram.
  const prefetchStartedRef = useRef<Set<string>>(new Set());
  const prefetchedRef = useRef<Map<string, CheckpointQuestion | null>>(new Map());

  const prefetchForTopic = useCallback(
    (topicId: string) => {
      if (!studentId || !sessionId || !topicId) return;
      if (prefetchStartedRef.current.has(topicId)) return;
      prefetchStartedRef.current.add(topicId);
      fetchCheckpoint(topicId)
        .then((cp) => {
          prefetchedRef.current.set(topicId, cp);
          // Warm the prompt narration so it's synthesized + cached by the time
          // the checkpoint pops (fire-and-forget; the browser caches the audio).
          if (cp) void fetch(checkpointTtsUrl(promptNarration(cp.q_text)));
        })
        .catch(() => prefetchStartedRef.current.delete(topicId)); // allow retry
    },
    [studentId, sessionId],
  );

  const triggerForTopic = useCallback(
    (topicId: string) => {
      if (!studentId || !sessionId || !topicId) return;
      if (askedRef.current.has(topicId)) return;
      askedRef.current.add(topicId);
      void (async () => {
        // Use the pre-warmed result if it resolved; else fetch now.
        let cp = prefetchedRef.current.get(topicId);
        if (cp === undefined) cp = await fetchCheckpoint(topicId).catch(() => null);
        if (!cp) return; // no question for this topic → lecture flows on
        pause();
        setOutcome(null);
        setSolution(null);
        setQuestion(cp);
        // Prefetch the SOLUTION now — it generates during the student's solving
        // window, so its diagram + explanation are ready by submit. Also warm
        // the explanation NARRATION so it's synthesized + cached before reveal
        // (instant playback even for the first student to reach this question).
        fetchSolution(cp.question_id)
          .then((sol) => {
            setSolution(sol);
            if (sol.explanation)
              void fetch(checkpointTtsUrl(explanationNarration(sol.explanation)));
          })
          .catch(() => {});
      })();
    },
    [studentId, sessionId, pause],
  );

  const submit = useCallback(
    async (selectedOption: string) => {
      if (!question || !sessionId) return;
      const out = await submitAttempt(
        sessionId,
        question.question_id,
        selectedOption,
      ).catch(() => null);
      setOutcome(
        out ?? { correct: false, answer: "", answer_audio_url: null },
      );
      // Ensure a solution to reveal even if the prefetch failed.
      if (!solution) {
        fetchSolution(question.question_id)
          .then(setSolution)
          .catch(() => {});
      }
    },
    [question, sessionId, solution],
  );

  const dismiss = useCallback(() => {
    setQuestion(null);
    setSolution(null);
    setOutcome(null);
    play();
  }, [play]);

  return {
    question,
    solution,
    outcome,
    prefetchForTopic,
    triggerForTopic,
    submit,
    dismiss,
  };
}
