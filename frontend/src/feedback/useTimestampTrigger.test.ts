/**
 * Tests for the in-lecture timestamp trigger: respects the elapsed floor + the
 * percentage threshold, fires once, doesn't re-fire on a backward seek, retries
 * when the fire is refused, and stays inert when disabled.
 */
import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useTimestampTrigger } from "./useTimestampTrigger";

function setup(onFire: () => boolean | void, durationMs = 1_000_000) {
  return renderHook(
    ({ currentMs }: { currentMs: number }) =>
      useTimestampTrigger({ currentMs, durationMs, enabled: true, onFire }),
    { initialProps: { currentMs: 0 } },
  );
}

describe("useTimestampTrigger", () => {
  it("does not fire before the 90s elapsed floor (even past the %)", () => {
    const onFire = vi.fn();
    // 50% of 100s = 50s, which is past 45% but below the 90s floor.
    const { rerender } = renderHook(
      ({ currentMs }: { currentMs: number }) =>
        useTimestampTrigger({ currentMs, durationMs: 100_000, enabled: true, onFire }),
      { initialProps: { currentMs: 0 } },
    );
    rerender({ currentMs: 50_000 });
    expect(onFire).not.toHaveBeenCalled();
  });

  it("fires once when both the floor and the 45% threshold are crossed", () => {
    const onFire = vi.fn();
    const { rerender } = setup(onFire);
    rerender({ currentMs: 460_000 }); // 46%, well past 90s
    expect(onFire).toHaveBeenCalledTimes(1);
    rerender({ currentMs: 500_000 });
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  it("does not re-fire after seeking backward across the threshold", () => {
    const onFire = vi.fn();
    const { rerender } = setup(onFire);
    rerender({ currentMs: 460_000 });
    rerender({ currentMs: 200_000 });
    rerender({ currentMs: 470_000 });
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  it("retries the threshold when onFire returns false", () => {
    let allow = false;
    const onFire = vi.fn(() => allow);
    const { rerender } = setup(onFire);
    rerender({ currentMs: 460_000 }); // refused
    expect(onFire).toHaveBeenCalledTimes(1);
    allow = true;
    rerender({ currentMs: 461_000 }); // accepted
    expect(onFire).toHaveBeenCalledTimes(2);
    rerender({ currentMs: 462_000 }); // consumed — no more
    expect(onFire).toHaveBeenCalledTimes(2);
  });

  it("is inert when disabled", () => {
    const onFire = vi.fn();
    const { rerender } = renderHook(
      ({ currentMs }: { currentMs: number }) =>
        useTimestampTrigger({ currentMs, durationMs: 1_000_000, enabled: false, onFire }),
      { initialProps: { currentMs: 0 } },
    );
    rerender({ currentMs: 460_000 });
    expect(onFire).not.toHaveBeenCalled();
  });
});
