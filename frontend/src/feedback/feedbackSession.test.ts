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

  it("auto-opens each source at most once per session (no re-pop after dismiss)", () => {
    expect(feedbackSession.tryOpen("in_lecture")).toBe(true);
    feedbackSession.markClosed();
    // Dismissed — must NOT auto-open again this session, even with no cooldown.
    expect(feedbackSession.canOpen("in_lecture")).toBe(false);
    expect(feedbackSession.tryOpen("in_lecture")).toBe(false);
    // A different source still gets its single auto-open.
    expect(feedbackSession.tryOpen("exit")).toBe(true);
  });

  it("notifies subscribers on every open/close, until unsubscribed", () => {
    let count = 0;
    const unsub = feedbackSession.subscribe(() => {
      count += 1;
    });
    feedbackSession.tryOpen("exit"); // open → notify
    feedbackSession.markClosed(); // close → notify
    expect(count).toBe(2);
    unsub();
    feedbackSession.markOpened(); // no longer subscribed
    expect(count).toBe(2);
  });

  it("tracks the lecture-active flag", () => {
    expect(feedbackSession.isLectureActive()).toBe(false);
    feedbackSession.setLectureActive(true);
    expect(feedbackSession.isLectureActive()).toBe(true);
    feedbackSession.setLectureActive(false);
    expect(feedbackSession.isLectureActive()).toBe(false);
  });
});
