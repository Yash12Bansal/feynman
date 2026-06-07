/**
 * The feedback questionnaire, as data. One entry per wizard slide; the wizard
 * (FeedbackWizard) renders them one at a time. Three kinds:
 *   - `intro`: a bulleted splash that sets the tone (no answer collected)
 *   - `mcq`:   pick-one options, plus an optional free-text "why?" comment
 *   - `text`:  a single open-ended answer
 *
 * The `id` of every mcq/text step is a STABLE CONTRACT — it becomes the key in
 * the Firestore `answers`/`ratings` maps (see feedbackService.ts). MCQ comments
 * are stored under `${id}__comment`. Add or reorder steps freely; never rename
 * an id, or you fragment historical analysis.
 */

export type FeedbackStepId = string;

interface BaseStep {
  readonly id: FeedbackStepId;
  /** When true, the wizard blocks "Next" until this step is answered. */
  readonly required?: boolean;
}

export interface IntroStep extends BaseStep {
  readonly kind: "intro";
  readonly title: string;
  readonly bullets: readonly string[];
  /** "Next" button label for the intro (e.g. "Let's do it →"). */
  readonly cta?: string;
}

export interface McqStep extends BaseStep {
  readonly kind: "mcq";
  readonly prompt: string;
  /** Ordered low → high. */
  readonly options: readonly string[];
  /** Show a free-text "why?" box under the options. Default true. */
  readonly withComment?: boolean;
  readonly commentPlaceholder?: string;
}

export interface TextStep extends BaseStep {
  readonly kind: "text";
  readonly prompt: string;
  readonly placeholder?: string;
  /** Encouraging sub-line under the prompt (the "say anything" framing). */
  readonly helper?: string;
}

export type FeedbackStep = IntroStep | McqStep | TextStep;

/** Suffix appended to a step id to key its optional MCQ comment in `answers`. */
export const COMMENT_SUFFIX = "__comment";

export const FEEDBACK_INTRO: IntroStep = {
  id: "intro",
  kind: "intro",
  title: "Help us build this for you",
  bullets: [
    "Feynman is in its earliest days — you're seeing the first rough sketch of something far bigger.",
    "The aim: a tutor that can teach you anything, the way the greatest teacher who ever lived would — visual, patient, out loud.",
    "The sky's the limit — we can build almost any feature. The hard part is knowing which ones matter to you.",
    "So this is 60 seconds about you: what you love, what makes you want to throw your laptop, and the one problem you wish would vanish.",
    "Say anything. The blunter the better — we'd rather hear the painful truth now than guess wrong for months.",
  ],
  cta: "Let's do it →",
};

/**
 * The full survey, shown one slide at a time by every trigger (FAB, exit-intent,
 * in-lecture). Required text steps are the highest-signal product questions.
 */
export const WIZARD_STEPS: readonly FeedbackStep[] = [
  FEEDBACK_INTRO,
  {
    id: "disappointment",
    kind: "mcq",
    prompt: "How would you feel if you could no longer use Feynman?",
    options: ["Not disappointed", "A bit disappointed", "Very disappointed"],
    commentPlaceholder: "What makes you say that?",
  },
  {
    id: "like_most",
    kind: "text",
    required: true,
    prompt: "What do you like most about Feynman so far?",
    placeholder: "The thing that made you smile, or kept you watching…",
  },
  {
    id: "like_least",
    kind: "text",
    required: true,
    prompt: "What do you like least — what made you cringe or frustrated you?",
    helper: "Be brutal. This is the most useful thing you can tell us.",
    placeholder: "Don't hold back…",
  },
  {
    id: "burning_problem",
    kind: "text",
    required: true,
    prompt:
      "What's the one problem in how you study or learn that you wish something could just solve — the thing that, if we nailed it, you'd happily pay for?",
    helper:
      "Sky's the limit — any feature is possible. Describe the pain, not the solution. Say anything.",
    placeholder: "The thing that keeps tripping you up…",
  },
  {
    id: "willingness",
    kind: "mcq",
    prompt: "If we built exactly that, what would you pay per month?",
    options: ["Wouldn't pay", "Under ₹500", "₹500–1500", "₹1500–4000", "₹4000+"],
    commentPlaceholder: "What feels fair — and why? (No wrong answer, we won't hold you to it.)",
  },
  {
    id: "understanding",
    kind: "mcq",
    prompt: "Did it help you understand better than your usual way of studying?",
    options: ["Much worse", "A bit worse", "About the same", "Better", "Much better"],
  },
  {
    id: "recommend",
    kind: "mcq",
    prompt: "How likely are you to recommend Feynman to a friend?",
    options: ["Definitely not", "Probably not", "Maybe", "Probably", "Definitely"],
  },
  {
    id: "alternative",
    kind: "text",
    prompt: "If Feynman vanished tomorrow, what would you use instead — and why isn't it enough?",
    placeholder: "A tutor, YouTube, ChatGPT, a friend…",
  },
  {
    id: "anything_else",
    kind: "text",
    prompt: "Anything else on your mind? Dreams, rants, wild ideas — all welcome.",
    placeholder: "Optional",
  },
];

/**
 * Step ids whose text answers mirror into the legacy payload fields
 * (liked/disliked/future/note). Keeps older Firestore reads working.
 */
export const LEGACY_MIRROR_IDS: Readonly<
  Record<"liked" | "disliked" | "future" | "note", FeedbackStepId>
> = {
  liked: "like_most",
  disliked: "like_least",
  future: "burning_problem",
  note: "anything_else",
};
