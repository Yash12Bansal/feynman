/**
 * The in-lecture checkpoint overlay (Apple 3, Phase 2).
 *
 * Two phases:
 *   PROMPT  — show the question + options; submit is gated for 30s so the
 *             student actually attempts it (and the solution diagram finishes
 *             generating in that window).
 *   REVEAL  — after submit: correct/incorrect + the worked solution (diagram
 *             on the board, answer text, narrated audio) + Continue.
 *
 * Pure presentation; the parent (useCheckpoints) owns the state + the player
 * pause/resume.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  checkpointTtsUrl,
  promptNarration,
  type AttemptOutcome,
  type CheckpointQuestion,
  type Solution,
} from "../lib/api";
import type { DrawDesignDiagramInstruction, DesignDiagramSpec } from "../types/visuals";
import { DesignDiagramContent } from "../engine/whiteboard/content/DesignDiagramContent";

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

  return (
    <div style={OVERLAY}>
      <div style={CARD}>
        <div style={KICKER}>{revealed ? "Solution" : "Your turn — try this"}</div>
        <h2 style={QTEXT}>{question.q_text}</h2>

        {!revealed && (
          <>
            {question.diagram_needed && question.diagram_spec && (
              <div style={DIAGRAM_WRAP}>
                <DesignDiagramContent
                  instruction={_asInstruction(
                    `${question.question_id}-q`,
                    question.diagram_spec,
                  )}
                />
              </div>
            )}
            <div style={OPTIONS}>
              {question.options.map((opt) => {
                const letter = opt.trim().charAt(0).toUpperCase();
                const isSel = selected === letter;
                return (
                  <button
                    key={letter}
                    style={{ ...OPTION, ...(isSel ? OPTION_SEL : {}) }}
                    onClick={() => setSelected(letter)}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>
            <button
              style={{ ...PRIMARY, ...(canSubmit ? {} : DISABLED) }}
              disabled={!canSubmit}
              onClick={() => selected && onSubmit(selected)}
            >
              {secondsLeft > 0
                ? `Take your time — submit in ${secondsLeft}s`
                : "Submit"}
            </button>
          </>
        )}

        {revealed && (
          <>
            {/* Field 1 — the student's result for THIS attempt (green/red). */}
            <div style={outcome!.correct ? BADGE_CORRECT : BADGE_INCORRECT}>
              {outcome!.correct ? "✓ Correct" : "✗ Incorrect"}
            </div>
            <p style={CORRECT_LINE}>
              <span style={CORRECT_LABEL}>Correct answer</span>
              {_correctOptionText(question.options, outcome!.answer)}
            </p>
            {solution?.diagram_needed && solution.diagram_spec && (
              <div style={DIAGRAM_WRAP}>
                <DesignDiagramContent
                  instruction={_asInstruction(question.question_id, solution.diagram_spec)}
                />
              </div>
            )}
            {/* Field 2 — worked solution as steps. CORRECT shows all; WRONG
                reveals one at a time so the student works through it. */}
            <div style={REASONING_LABEL}>
              {outcome!.correct ? "Worked solution" : "Let's walk through it"}
            </div>
            {stepCount === 0 ? (
              <p style={SUBTLE_NOTE}>Working through the solution…</p>
            ) : (
              <ol style={STEP_LIST}>
                {steps.slice(0, revealedCount).map((s, i) => (
                  <li key={i} style={STEP_ITEM}>
                    {s}
                  </li>
                ))}
              </ol>
            )}
            {moreSteps ? (
              <>
                <p style={NUDGE}>
                  Take a moment — what do you think the next step is? Tap when
                  you're ready.
                </p>
                <button style={SECONDARY} onClick={showNextStep}>
                  Show next step
                </button>
              </>
            ) : (
              <button style={PRIMARY} onClick={onDismiss}>
                Continue the lecture
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Resolve the correct option's FULL text from the answer letter (e.g. "B" →
 *  "B. Velocity is shared…"), so the reveal shows the real answer, not a bare
 *  letter. Falls back to the raw answer if no option matches. */
function _correctOptionText(options: readonly string[], answer: string): string {
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

const OVERLAY: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 120,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(8, 9, 12, 0.78)",
  backdropFilter: "blur(6px)",
};
const CARD: React.CSSProperties = {
  width: "min(94vw, 640px)",
  maxHeight: "88vh",
  overflowY: "auto",
  padding: "28px 30px",
  background: "#14151a",
  border: "1px solid rgba(232, 232, 238, 0.12)",
  borderRadius: 18,
  color: "rgba(232, 232, 238, 0.92)",
  boxShadow: "0 24px 60px rgba(0,0,0,0.5)",
};
const KICKER: React.CSSProperties = {
  fontSize: "0.72rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "#7fd4ff",
};
const QTEXT: React.CSSProperties = { margin: "8px 0 20px", fontSize: "1.25rem", lineHeight: 1.4 };
const OPTIONS: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 10, marginBottom: 18 };
const OPTION: React.CSSProperties = {
  textAlign: "left",
  padding: "12px 16px",
  background: "#1c1d24",
  border: "1px solid rgba(232, 232, 238, 0.12)",
  borderRadius: 10,
  color: "rgba(232, 232, 238, 0.92)",
  fontSize: "0.95rem",
  cursor: "pointer",
};
const OPTION_SEL: React.CSSProperties = {
  borderColor: "#7fd4ff",
  background: "rgba(127, 212, 255, 0.12)",
};
const PRIMARY: React.CSSProperties = {
  width: "100%",
  padding: "12px 0",
  background: "#7fd4ff",
  color: "#0a0a0a",
  border: "none",
  borderRadius: 10,
  fontSize: "0.95rem",
  fontWeight: 600,
  cursor: "pointer",
};
const DISABLED: React.CSSProperties = { opacity: 0.45, cursor: "not-allowed" };
const BADGE_BASE: React.CSSProperties = {
  display: "inline-block",
  padding: "5px 14px",
  borderRadius: 999,
  fontSize: "0.85rem",
  fontWeight: 700,
  letterSpacing: "0.02em",
  marginBottom: 14,
};
const BADGE_CORRECT: React.CSSProperties = {
  ...BADGE_BASE,
  color: "#0a0a0a",
  background: "#7CFFB2",
};
const BADGE_INCORRECT: React.CSSProperties = {
  ...BADGE_BASE,
  color: "#0a0a0a",
  background: "#FF8F8F",
};
const REASONING_LABEL: React.CSSProperties = {
  fontSize: "0.72rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "rgba(232, 232, 238, 0.55)",
  marginBottom: 6,
};
const DIAGRAM_WRAP: React.CSSProperties = {
  width: "100%",
  aspectRatio: "900 / 650",
  marginBottom: 16,
  background: "#0a0a0a",
  borderRadius: 12,
  overflow: "hidden",
};
const STEP_LIST: React.CSSProperties = {
  margin: "0 0 18px",
  paddingLeft: 22,
  display: "flex",
  flexDirection: "column",
  gap: 10,
};
const STEP_ITEM: React.CSSProperties = {
  fontSize: "0.98rem",
  lineHeight: 1.55,
  paddingLeft: 4,
};
const NUDGE: React.CSSProperties = {
  fontSize: "0.92rem",
  lineHeight: 1.5,
  color: "rgba(127, 212, 255, 0.85)",
  marginBottom: 12,
};
const SECONDARY: React.CSSProperties = {
  width: "100%",
  padding: "11px 0",
  background: "transparent",
  color: "#7fd4ff",
  border: "1px solid rgba(127, 212, 255, 0.45)",
  borderRadius: 10,
  fontSize: "0.95rem",
  fontWeight: 600,
  cursor: "pointer",
};
const CORRECT_LINE: React.CSSProperties = {
  fontSize: "1rem",
  lineHeight: 1.5,
  margin: "0 0 14px",
  padding: "10px 14px",
  background: "rgba(124, 255, 178, 0.08)",
  border: "1px solid rgba(124, 255, 178, 0.25)",
  borderRadius: 10,
};
const CORRECT_LABEL: React.CSSProperties = {
  display: "block",
  fontSize: "0.7rem",
  letterSpacing: "0.07em",
  textTransform: "uppercase",
  color: "#7CFFB2",
  marginBottom: 4,
};
const SUBTLE_NOTE: React.CSSProperties = {
  fontSize: "0.9rem",
  color: "rgba(232, 232, 238, 0.55)",
  marginBottom: 20,
};
