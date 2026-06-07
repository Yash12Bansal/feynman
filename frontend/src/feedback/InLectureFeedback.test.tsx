/**
 * Tests for the in-lecture trigger component: at the threshold it pauses the
 * lecture and opens the wizard, closing resumes playback, and it stays inert
 * when disabled.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("../auth/authContext", () => ({
  useAuth: () => ({ user: null, profile: null }),
}));
const { submitMock } = vi.hoisted(() => ({ submitMock: vi.fn() }));
vi.mock("./feedbackService", () => ({ submitFeedback: submitMock }));

import { InLectureFeedback } from "./InLectureFeedback";
import { feedbackSession } from "./feedbackSession";

afterEach(() => {
  feedbackSession._reset();
  vi.clearAllMocks();
});

describe("InLectureFeedback", () => {
  it("pauses + opens at the threshold and resumes on close", () => {
    const pause = vi.fn();
    const play = vi.fn();
    const { rerender } = render(
      <InLectureFeedback
        currentMs={0}
        durationMs={1_000_000}
        enabled
        isPlaying
        pause={pause}
        play={play}
      />,
    );
    expect(pause).not.toHaveBeenCalled();

    rerender(
      <InLectureFeedback
        currentMs={460_000}
        durationMs={1_000_000}
        enabled
        isPlaying
        pause={pause}
        play={play}
      />,
    );
    expect(pause).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /close feedback/i }));
    expect(play).toHaveBeenCalledTimes(1);
  });

  it("does not fire while the lecture is paused (isPlaying=false)", () => {
    const pause = vi.fn();
    const { rerender } = render(
      <InLectureFeedback
        currentMs={0}
        durationMs={1_000_000}
        enabled
        isPlaying={false}
        pause={pause}
        play={vi.fn()}
      />,
    );
    rerender(
      <InLectureFeedback
        currentMs={460_000}
        durationMs={1_000_000}
        enabled
        isPlaying={false}
        pause={pause}
        play={vi.fn()}
      />,
    );
    expect(pause).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("stays inert when disabled", () => {
    const pause = vi.fn();
    const { rerender } = render(
      <InLectureFeedback
        currentMs={0}
        durationMs={1_000_000}
        enabled={false}
        isPlaying
        pause={pause}
        play={vi.fn()}
      />,
    );
    rerender(
      <InLectureFeedback
        currentMs={460_000}
        durationMs={1_000_000}
        enabled={false}
        isPlaying
        pause={pause}
        play={vi.fn()}
      />,
    );
    expect(pause).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
