/**
 * The in-lecture checkpoint overlay — the board's "your turn" moment.
 *
 * Two phases:
 *   PROMPT  — show the question + options; submit is gated for 30s so the
 *             student actually attempts it (and the solution diagram finishes
 *             generating in that window). The gate visibly "charges" the submit.
 *   REVEAL  — after submit: correct/incorrect + the worked solution (diagram
 *             on the board, answer text, narrated audio) + Continue. Correct
 *             reveals every step at once; wrong reveals one gated step at a time
 *             so the student works through it.
 *
 * Pure presentation; the parent (useCheckpoints) owns the state + the player
 * pause/resume. Skinned "Deep-Space Glass" off the viewer's `--lv-*` tokens
 * (see checkpoint.css), so it re-themes with the lecture.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  checkpointTtsUrl,
  promptNarration,
  type AttemptOutcome,
  type CheckpointQuestion,
  type Solution,
} from "../lib/api";
import type {
  DrawDesignDiagramInstruction,
  DesignDiagramSpec,
} from "../types/visuals";
import { DesignDiagramContent } from "../engine/whiteboard/content/DesignDiagramContent";
import "./checkpoint.css";

const SOLVE_GATE_SECONDS = 30;

interface QuestionCheckpointProps {
  readonly question: CheckpointQuestion;
  readonly solution: Solution | null;
  readonly outcome: AttemptOutcome | null;
  readonly onSubmit: (selectedOption: string) => void;
  readonly onDismiss: () => void;
}

export function QuestionCheckpoint({
  question,
  solution,
  outcome,
  onSubmit,
  onDismiss,
}: QuestionCheckpointProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(SOLVE_GATE_SECONDS);
  // "Show next step" taps (wrong-answer path). revealedCount is DERIVED from it
  // — no setState-in-effect. The parent remounts this per question (keyed on
  // question_id), so this resets cleanly between checkpoints.
  const [extraReveals, setExtraReveals] = useState(0);
  const revealed = outcome !== null;
  const steps = useMemo(() => solution?.steps ?? [], [solution]);
  const stepCount = steps.length;
  // CORRECT → all steps at once; WRONG → 1, then +1 per "Show next step".
  const revealedCount = !revealed
    ? 0
    : outcome.correct
      ? stepCount
      : Math.min(1 + extraReveals, stepCount);

  // Solve-gate countdown (prompt phase only).
  useEffect(() => {
    if (revealed) return;
    const id = window.setInterval(() => {
      setSecondsLeft((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => window.clearInterval(id);
  }, [revealed]);

  // Narrate in the lecture's own voice (Kokoro). `playSequence` plays a list of
  // texts back-to-back; a token cancels any in-flight sequence so a new reveal /
  // next-step never overlaps the previous audio.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const seqRef = useRef(0);
  const playSequence = useCallback((texts: string[]) => {
    audioRef.current?.pause();
    const token = ++seqRef.current;
    let i = 0;
    const playNext = () => {
      if (token !== seqRef.current || i >= texts.length) return;
      const audio = new Audio(checkpointTtsUrl(texts[i]));
      audioRef.current = audio;
      audio.onended = () => {
        i += 1;
        playNext();
      };
      void audio.play().catch(() => {});
    };
    playNext();
  }, []);

  // Prompt phase — narrate "Let's test your understanding. <question>".
  useEffect(() => {
    if (revealed) return;
    playSequence([promptNarration(question.q_text)]);
    return () => audioRef.current?.pause();
  }, [revealed, question.q_text, playSequence]);

  // Reveal phase — narrate the initially-shown steps ONCE the steps have loaded
  // (audio only; no state change). CORRECT → narrate all; WRONG → narrate step 1.
  const narratedInitRef = useRef(false);
  useEffect(() => {
    if (!revealed || narratedInitRef.current || stepCount === 0) return;
    narratedInitRef.current = true;
    const count = outcome.correct ? stepCount : 1;
    playSequence(steps.slice(0, count));
    return () => audioRef.current?.pause();
  }, [revealed, stepCount, outcome, steps, playSequence]);

  // "Show next step" (wrong-answer path) — reveal + narrate the next step only.
  const showNextStep = useCallback(() => {
    if (revealedCount >= stepCount) return;
    playSequence([steps[revealedCount]]);
    setExtraReveals((n) => n + 1);
  }, [revealedCount, stepCount, steps, playSequence]);

  const canSubmit = !revealed && selected !== null && secondsLeft === 0;
  const moreSteps =
    revealed && !outcome.correct && stepCount > 0 && revealedCount < stepCount;

  const gatePct =
    ((SOLVE_GATE_SECONDS - secondsLeft) / SOLVE_GATE_SECONDS) * 100;
  const submitLabel =
    secondsLeft > 0
      ? `Take your time · ${secondsLeft}s`
      : selected
        ? "Submit answer"
        : "Select an answer";

  return (
    <div className="cp-root">
      <div className="cp-overlay">
        <div
          className={`cp-card${revealed && outcome.correct ? " is-correct" : ""}`}
        >
          <div className="cp-kicker">
            <span className="cp-kicker__dot" aria-hidden />
            {revealed ? "Solution" : "Your turn — try this"}
          </div>
          <h2 className="cp-qtext">{question.q_text}</h2>

          {!revealed && (
            <>
              {question.diagram_needed && question.diagram_spec && (
                <div className="cp-diagram">
                  <DesignDiagramContent
                    instruction={_asInstruction(
                      `${question.question_id}-q`,
                      question.diagram_spec,
                    )}
                  />
                </div>
              )}
              <div className="cp-options">
                {question.options.map((opt) => {
                  const m = opt.match(/^\s*([A-Za-z])[.)\s-]+(.*)$/);
                  const letter = (
                    m ? m[1] : opt.trim().charAt(0)
                  ).toUpperCase();
                  const text = m ? m[2].trim() : opt;
                  const isSel = selected === letter;
                  return (
                    <button
                      key={letter}
                      type="button"
                      className={`cp-option${isSel ? " is-selected" : ""}`}
                      onClick={() => setSelected(letter)}
                    >
                      <span className="cp-option__letter">{letter}</span>
                      <span className="cp-option__text">{text}</span>
                    </button>
                  );
                })}
              </div>
              <button
                type="button"
                className={`cp-submit${canSubmit ? " is-ready" : ""}`}
                disabled={!canSubmit}
                onClick={() => selected && onSubmit(selected)}
              >
                {secondsLeft > 0 && (
                  <span
                    className="cp-submit__fill"
                    style={{ width: `${gatePct}%` }}
                    aria-hidden
                  />
                )}
                <span className="cp-submit__label">{submitLabel}</span>
              </button>
            </>
          )}

          {revealed && (
            <>
              {/* Field 1 — the student's result for THIS attempt. */}
              <div
                className={`cp-badge ${outcome.correct ? "cp-badge--correct" : "cp-badge--wrong"}`}
              >
                {outcome.correct ? "✓ Correct" : "✗ Not quite"}
              </div>
              <p className="cp-answer">
                <span className="cp-answer__label">Correct answer</span>
                {_correctOptionText(question.options, outcome.answer)}
              </p>
              {solution?.diagram_needed && solution.diagram_spec && (
                <div className="cp-diagram">
                  <DesignDiagramContent
                    instruction={_asInstruction(
                      question.question_id,
                      solution.diagram_spec,
                    )}
                  />
                </div>
              )}
              {/* Field 2 — worked solution as steps. CORRECT shows all; WRONG
                  reveals one at a time so the student works through it. */}
              <div className="cp-steps-label">
                {outcome.correct ? "Worked solution" : "Let's walk through it"}
              </div>
              {stepCount === 0 ? (
                <p className="cp-subtle">Working through the solution…</p>
              ) : (
                <ol className="cp-steps">
                  {steps.slice(0, revealedCount).map((s, i) => (
                    <li
                      key={i}
                      className="cp-step"
                      style={{ "--i": i } as React.CSSProperties}
                    >
                      {s}
                    </li>
                  ))}
                </ol>
              )}
              {moreSteps ? (
                <>
                  <p className="cp-nudge">
                    Take a moment — what do you think the next step is? Tap when
                    you're ready.
                  </p>
                  <button
                    type="button"
                    className="cp-secondary"
                    onClick={showNextStep}
                  >
                    Show next step
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="cp-primary"
                  onClick={onDismiss}
                >
                  Continue the lecture
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** Resolve the correct option's FULL text from the answer letter (e.g. "B" →
 *  "B. Velocity is shared…"), so the reveal shows the real answer, not a bare
 *  letter. Falls back to the raw answer if no option matches. */
function _correctOptionText(
  options: readonly string[],
  answer: string,
): string {
  const letter = answer.trim().charAt(0).toUpperCase();
  const match = options.find(
    (o) => o.trim().charAt(0).toUpperCase() === letter,
  );
  return match ?? answer;
}

function _asInstruction(
  id: string,
  spec: Record<string, unknown>,
): DrawDesignDiagramInstruction {
  return {
    type: "draw_design_diagram",
    element_id: id,
    title: "",
    description: "",
    spec: spec as unknown as DesignDiagramSpec,
  };
}
