import { describe, it, expect, vi } from "vitest";
import { SyncManager } from "../SyncManager";
import type { TermSyncHint } from "../../types/visuals";

describe("SyncManager", () => {
  const makeHints = (): TermSyncHint[] => [
    { term_id: "term-F", trigger_words: ["force", "F"] },
    { term_id: "term-m", trigger_words: ["mass", "m"] },
    { term_id: "term-a", trigger_words: ["acceleration", "a"] },
  ];

  it("calls the correct callback when a trigger word is spoken", () => {
    const sm = new SyncManager();
    const hints = makeHints();
    const cbF = vi.fn();
    const cbM = vi.fn();
    const cbA = vi.fn();
    const callbacks = new Map([
      ["term-F", cbF],
      ["term-m", cbM],
      ["term-a", cbA],
    ]);

    sm.register("eq-1", hints, callbacks);

    sm.onWord("force");
    expect(cbF).toHaveBeenCalledTimes(1);
    expect(cbM).not.toHaveBeenCalled();
    expect(cbA).not.toHaveBeenCalled();
  });

  it("matches case-insensitively", () => {
    const sm = new SyncManager();
    const cb = vi.fn();
    sm.register(
      "eq-1",
      [{ term_id: "term-F", trigger_words: ["Force"] }],
      new Map([["term-F", cb]]),
    );

    sm.onWord("FORCE");
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("strips punctuation before matching", () => {
    const sm = new SyncManager();
    const cb = vi.fn();
    sm.register(
      "eq-1",
      [{ term_id: "term-F", trigger_words: ["force"] }],
      new Map([["term-F", cb]]),
    );

    sm.onWord("force,");
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("does not double-reveal the same term", () => {
    const sm = new SyncManager();
    const cb = vi.fn();
    sm.register(
      "eq-1",
      [{ term_id: "term-F", trigger_words: ["force", "F"] }],
      new Map([["term-F", cb]]),
    );

    sm.onWord("force");
    sm.onWord("F");
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("revealAll reveals unrevealed terms", () => {
    const sm = new SyncManager();
    const hints = makeHints();
    const cbF = vi.fn();
    const cbM = vi.fn();
    const cbA = vi.fn();
    const callbacks = new Map([
      ["term-F", cbF],
      ["term-m", cbM],
      ["term-a", cbA],
    ]);

    sm.register("eq-1", hints, callbacks);

    // Only reveal F through word match
    sm.onWord("force");
    expect(cbF).toHaveBeenCalledTimes(1);

    // Force reveal remaining
    sm.revealAll("eq-1");
    expect(cbM).toHaveBeenCalledTimes(1);
    expect(cbA).toHaveBeenCalledTimes(1);
    // F should NOT be called again
    expect(cbF).toHaveBeenCalledTimes(1);
  });

  it("revealAll is a no-op for unknown id", () => {
    const sm = new SyncManager();
    // Should not throw
    sm.revealAll("nonexistent");
  });

  it("unregister removes sync entry", () => {
    const sm = new SyncManager();
    const cb = vi.fn();
    const unregister = sm.register(
      "eq-1",
      [{ term_id: "term-F", trigger_words: ["force"] }],
      new Map([["term-F", cb]]),
    );

    unregister();
    sm.onWord("force");
    expect(cb).not.toHaveBeenCalled();
  });

  it("clear removes all entries", () => {
    const sm = new SyncManager();
    const cb = vi.fn();
    sm.register(
      "eq-1",
      [{ term_id: "term-F", trigger_words: ["force"] }],
      new Map([["term-F", cb]]),
    );

    sm.clear();
    sm.onWord("force");
    expect(cb).not.toHaveBeenCalled();
  });

  it("handles multiple concurrent syncs", () => {
    const sm = new SyncManager();
    const cb1 = vi.fn();
    const cb2 = vi.fn();

    sm.register(
      "eq-1",
      [{ term_id: "term-F", trigger_words: ["force"] }],
      new Map([["term-F", cb1]]),
    );
    sm.register(
      "eq-2",
      [{ term_id: "term-F", trigger_words: ["force"] }],
      new Map([["term-F", cb2]]),
    );

    sm.onWord("force");
    expect(cb1).toHaveBeenCalledTimes(1);
    expect(cb2).toHaveBeenCalledTimes(1);
  });

  it("ignores empty/whitespace words", () => {
    const sm = new SyncManager();
    const cb = vi.fn();
    sm.register(
      "eq-1",
      [{ term_id: "term-F", trigger_words: ["force"] }],
      new Map([["term-F", cb]]),
    );

    sm.onWord("");
    sm.onWord("   ");
    sm.onWord("...");
    expect(cb).not.toHaveBeenCalled();
  });
});
