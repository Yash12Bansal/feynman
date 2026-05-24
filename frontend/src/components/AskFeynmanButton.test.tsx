/**
 * Tests for the AskFeynmanButton presentational component.
 *
 * Verifies labels per state, accessibility name, disabled-when-not-idle
 * behaviour, and that onActivate fires only on idle taps.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import { AskFeynmanButton, type AskFeynmanState } from "./AskFeynmanButton";

describe("AskFeynmanButton", () => {
  it.each<[AskFeynmanState, string]>([
    ["idle", "Ask Feynman"],
    ["listening", "I'm listening…"],
    ["thinking", "Feynman is thinking…"],
  ])("renders the right label in %s state", (state, label) => {
    const { getByText, getByTestId } = render(
      <AskFeynmanButton state={state} onActivate={() => {}} />,
    );
    expect(getByText(label)).toBeTruthy();
    expect(getByTestId("ask-feynman-button").getAttribute("data-state")).toBe(
      state,
    );
  });

  it("fires onActivate on tap in idle state", () => {
    const onActivate = vi.fn();
    const { getByTestId } = render(
      <AskFeynmanButton state="idle" onActivate={onActivate} />,
    );
    fireEvent.click(getByTestId("ask-feynman-button"));
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it("does not fire onActivate when listening", () => {
    const onActivate = vi.fn();
    const { getByTestId } = render(
      <AskFeynmanButton state="listening" onActivate={onActivate} />,
    );
    fireEvent.click(getByTestId("ask-feynman-button"));
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("does not fire onActivate when thinking", () => {
    const onActivate = vi.fn();
    const { getByTestId } = render(
      <AskFeynmanButton state="thinking" onActivate={onActivate} />,
    );
    fireEvent.click(getByTestId("ask-feynman-button"));
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("exposes an accessible name", () => {
    const { getByRole } = render(
      <AskFeynmanButton state="idle" onActivate={() => {}} />,
    );
    expect(getByRole("button", { name: /ask feynman/i })).toBeTruthy();
  });

  // ── Hotfix: error state + retry ─────────────────────────────────

  it("error state renders the message and a retry control", () => {
    const onRetry = vi.fn();
    const { getByTestId, getByText } = render(
      <AskFeynmanButton
        state="error"
        onActivate={() => {}}
        onRetry={onRetry}
        errorMessage="I didn't hear anything."
      />,
    );
    expect(getByTestId("ask-feynman-button").getAttribute("data-state")).toBe(
      "error",
    );
    expect(getByText("I didn't hear anything.")).toBeTruthy();
    fireEvent.click(getByTestId("ask-feynman-retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("error state falls back to a default message", () => {
    const { getByText } = render(
      <AskFeynmanButton
        state="error"
        onActivate={() => {}}
        onRetry={() => {}}
      />,
    );
    expect(getByText(/something went wrong/i)).toBeTruthy();
  });
});
