/**
 * Thin adapter kept so existing call sites keep compiling: it maps the old
 * `variant` prop to the shared question list + a canonical `source` tag and
 * renders the FeedbackWizard. All real UI now lives in FeedbackWizard — the old
 * single-scrolling-dialog form is gone.
 */

import { FeedbackWizard } from "./FeedbackWizard";
import { WIZARD_STEPS } from "./steps";
import type { FeedbackSource } from "./feedbackService";

interface FeedbackModalProps {
  readonly variant: "exit" | "manual";
  readonly onClose: () => void;
  readonly onSubmitted: () => void;
}

export function FeedbackModal({ variant, onClose, onSubmitted }: FeedbackModalProps) {
  const source: FeedbackSource = variant === "exit" ? "exit" : "manual";
  return (
    <FeedbackWizard
      steps={WIZARD_STEPS}
      source={source}
      onClose={onClose}
      onSubmitted={onSubmitted}
    />
  );
}
