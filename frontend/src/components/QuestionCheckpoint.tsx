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

import { useEffect, useRef, useState } from "react";
import {
  checkpointTtsUrl,
  explanationNarration,
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
  const revealed = outcome !== null;

  // Solve-gate countdown (prompt phase only).
  useEffect(() => {
    if (revealed) return;
    const id = window.setInterval(() => {
      setSecondsLeft((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => window.clearInterval(id);
  }, [revealed]);

  // Narrate in the lecture's own voice (Kokoro, via the preview server):
  // the prompt + question while solving, then the explanation on reveal.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const playTts = (text: string) => {
    audioRef.current?.pause();
    const audio = new Audio(checkpointTtsUrl(text));
    audioRef.current = audio;
    void audio.play().catch(() => {});
  };

  // Prompt phase — "Let's test your understanding, genius. <question>".
  useEffect(() => {
    if (revealed) return;
    playTts(promptNarration(question.q_text));
    return () => audioRef.current?.pause();
  }, [revealed, question.q_text]);

  // Reveal phase — "Let me help you understand. <explanation>". Re-fires if the
  // explanation arrives just after reveal (it's prefetched, usually ready).
  useEffect(() => {
    if (!revealed) return;
    const explanation = solution?.explanation ?? "";
    if (!explanation) return;
    playTts(explanationNarration(explanation));
    return () => audioRef.current?.pause();
  }, [revealed, solution?.explanation]);

  const canSubmit = !revealed && selected !== null && secondsLeft === 0;

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
            {/* Field 2 — answer-neutral reasoning for the question (shared). */}
            <div style={REASONING_LABEL}>Reasoning</div>
            {solution?.explanation ? (
              <p style={ANSWER}>{solution.explanation}</p>
            ) : (
              <p style={SUBTLE_NOTE}>Working through the reasoning…</p>
            )}
            <button style={PRIMARY} onClick={onDismiss}>
              Continue the lecture
            </button>
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
const ANSWER: React.CSSProperties = { fontSize: "0.98rem", lineHeight: 1.55, marginBottom: 20 };
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
