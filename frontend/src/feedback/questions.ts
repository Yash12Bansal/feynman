/**
 * Feedback questions. MCQ options are ordered low → high; we store the chosen
 * index (0..n-1) plus the human label, so analysis stays readable in Firestore.
 */

export interface McqQuestion {
  readonly id: string;
  readonly prompt: string;
  /** Ordered low → high. */
  readonly options: readonly string[];
}

/** The 5 aspects asked on exit — recommendation, clarity, visuals, voice, value. */
export const EXIT_MCQS: readonly McqQuestion[] = [
  {
    id: "recommend",
    prompt: "How likely are you to recommend Feynman to a friend?",
    options: ["Definitely not", "Probably not", "Maybe", "Probably", "Definitely"],
  },
  {
    id: "clarity",
    prompt: "How clear were Feynman's explanations?",
    options: ["Very confusing", "A bit confusing", "Okay", "Clear", "Crystal clear"],
  },
  {
    id: "visuals",
    prompt: "How helpful were the diagrams and the board?",
    options: ["Not helpful", "Slightly", "Okay", "Helpful", "Very helpful"],
  },
  {
    id: "voice",
    prompt: "How natural did talking with Feynman feel?",
    options: ["Very robotic", "A bit off", "Okay", "Natural", "Very natural"],
  },
  {
    id: "understanding",
    prompt: "Did it help you understand better than your usual way of studying?",
    options: ["Much worse", "A bit worse", "About the same", "Better", "Much better"],
  },
];

/** Single quick pulse for the always-available manual form. */
export const MANUAL_QUICK: McqQuestion = {
  id: "session_feel",
  prompt: "How's it going so far?",
  options: ["Bad", "Meh", "Okay", "Good", "Love it"],
};
