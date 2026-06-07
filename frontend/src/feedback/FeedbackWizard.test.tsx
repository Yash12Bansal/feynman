/**
 * Tests for the one-question-at-a-time wizard: intro → required-gated text →
 * MCQ-with-comment → submit, plus Back/Close. Asserts the assembled payload
 * carries answers / ratings / source and the legacy mirror fields.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { submitMock } = vi.hoisted(() => ({ submitMock: vi.fn() }));
vi.mock("./feedbackService", () => ({ submitFeedback: submitMock }));
vi.mock("../auth/authContext", () => ({
  useAuth: () => ({
    user: { uid: "u1", email: "a@b.com", displayName: "Aanya" },
    profile: { name: "Aanya" },
  }),
}));

import { FeedbackWizard } from "./FeedbackWizard";
import type { FeedbackStep } from "./steps";

const STEPS: readonly FeedbackStep[] = [
  { id: "intro", kind: "intro", title: "Hi there", bullets: ["one", "two"], cta: "Start" },
  { id: "like_most", kind: "text", required: true, prompt: "Most?" },
  { id: "feel", kind: "mcq", prompt: "Feel?", options: ["Bad", "Good"], commentPlaceholder: "why" },
];

describe("FeedbackWizard", () => {
  it("walks one step at a time, gates required steps, and submits a structured payload", async () => {
    const onSubmitted = vi.fn();
    render(
      <FeedbackWizard
        steps={STEPS}
        source="manual"
        onClose={vi.fn()}
        onSubmitted={onSubmitted}
      />,
    );

    // Intro slide → advance via the CTA.
    expect(screen.getByText("Hi there")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    // Required text slide — Next stays disabled until something is typed.
    expect(screen.getByText("Most?")).toBeTruthy();
    expect((screen.getByRole("button", { name: /next/i }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "the diagrams" } });
    expect((screen.getByRole("button", { name: /next/i }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /next/i }));

    // MCQ slide — pick an option + add a comment, then send.
    expect(screen.getByText("Feel?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    fireEvent.change(screen.getByPlaceholderText("why"), { target: { value: "loved it" } });
    fireEvent.click(screen.getByRole("button", { name: /send feedback/i }));

    await waitFor(() => expect(submitMock).toHaveBeenCalledTimes(1));
    const [payload, ctx] = submitMock.mock.calls[0];
    expect(payload.source).toBe("manual");
    expect(payload.variant).toBe("manual");
    expect(payload.answers.like_most).toBe("the diagrams");
    expect(payload.answers.feel__comment).toBe("loved it");
    expect(payload.ratings.feel).toBe(1);
    expect(payload.ratingLabels.feel).toBe("Good");
    // Legacy mirror: LEGACY_MIRROR_IDS.liked === "like_most".
    expect(payload.liked).toBe("the diagrams");
    expect(payload.disliked).toBe("");
    expect(ctx.uid).toBe("u1");
    expect(ctx.name).toBe("Aanya");

    // onSubmitted fires on a 1100ms delay after the thank-you shows.
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled(), { timeout: 2000 });
  });

  it("supports Back and an explicit Close", () => {
    const onClose = vi.fn();
    render(
      <FeedbackWizard steps={STEPS} source="exit" onClose={onClose} onSubmitted={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    // Anchor on the arrow — /back/i alone also matches "Close feedBACK".
    fireEvent.click(screen.getByRole("button", { name: /← back/i }));
    expect(screen.getByText("Hi there")).toBeTruthy(); // back on the intro
    fireEvent.click(screen.getByRole("button", { name: /close feedback/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
