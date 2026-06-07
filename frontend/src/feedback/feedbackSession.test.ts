/**
 * Tests for the cross-surface coordination singleton: one wizard open at a time,
 * quiet after submit, per-source cooldowns, and the lecture-active flag.
 */
import { afterEach, describe, expect, it } from "vitest";
import { feedbackSession } from "./feedbackSession";

afterEach(() => feedbackSession._reset());

describe("feedbackSession", () => {
  it("allows only one wizard open at a time", () => {
    expect(feedbackSession.tryOpen("exit")).toBe(true);
    expect(feedbackSession.isOpen()).toBe(true);
    expect(feedbackSession.tryOpen("in_lecture")).toBe(false);
    feedbackSession.markClosed();
    expect(feedbackSession.isOpen()).toBe(false);
    expect(feedbackSession.tryOpen("in_lecture")).toBe(true);
  });

  it("stays quiet for the session after a submit", () => {
    expect(feedbackSession.tryOpen("manual")).toBe(true);
    feedbackSession.markSubmitted();
    expect(feedbackSession.hasSubmitted()).toBe(true);
    expect(feedbackSession.tryOpen("exit")).toBe(false);
    expect(feedbackSession.tryOpen("in_lecture")).toBe(false);
  });

  it("honors a per-source cooldown without affecting other sources", () => {
    feedbackSession.startCooldown("exit", 60_000);
    expect(feedbackSession.canOpen("exit")).toBe(false);
    expect(feedbackSession.tryOpen("exit")).toBe(false);
    expect(feedbackSession.canOpen("in_lecture")).toBe(true);
  });

  it("tracks the lecture-active flag", () => {
    expect(feedbackSession.isLectureActive()).toBe(false);
    feedbackSession.setLectureActive(true);
    expect(feedbackSession.isLectureActive()).toBe(true);
    feedbackSession.setLectureActive(false);
    expect(feedbackSession.isLectureActive()).toBe(false);
  });
});
