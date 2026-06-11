/**
 * Tests the exit-intent handshake: the first leave gesture opens, a later
 * gesture closes (so the user can leave), and the SAME gesture can't do both
 * (the reopen guard). Non-top mouseouts are ignored.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import { useState } from "react";
import { useExitIntent } from "./useExitIntent";

/** mouseout with the cursor above the viewport + no relatedTarget = left via top. */
function leaveViaTop() {
  fireEvent.mouseOut(document, { clientY: -1, relatedTarget: null });
}

function Harness({
  onOpen,
  onClose,
}: {
  readonly onOpen: () => void;
  readonly onClose: () => void;
}) {
  const [open, setOpen] = useState(false);
  useExitIntent({
    enabled: true,
    isOpen: open,
    onOpen: () => {
      setOpen(true);
      onOpen();
    },
    onClose: () => {
      setOpen(false);
      onClose();
    },
  });
  return <div data-testid="state">{open ? "open" : "closed"}</div>;
}

afterEach(() => vi.restoreAllMocks());

describe("useExitIntent", () => {
  it("opens on the first leave gesture and closes on a later one", () => {
    let t = 1000;
    vi.spyOn(performance, "now").mockImplementation(() => t);
    const onOpen = vi.fn();
    const onClose = vi.fn();
    const { getByTestId } = render(<Harness onOpen={onOpen} onClose={onClose} />);

    leaveViaTop();
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(getByTestId("state").textContent).toBe("open");

    // Within the guard window → the SAME gesture must not also close it.
    t = 1300;
    leaveViaTop();
    expect(onClose).not.toHaveBeenCalled();
    expect(getByTestId("state").textContent).toBe("open");

    // After the guard → a deliberate second gesture closes it.
    t = 2000;
    leaveViaTop();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(getByTestId("state").textContent).toBe("closed");
  });

  it("ignores mouseouts that aren't a top exit", () => {
    const onOpen = vi.fn();
    render(<Harness onOpen={onOpen} onClose={vi.fn()} />);
    fireEvent.mouseOut(document, { clientY: 200, relatedTarget: null }); // not top
    fireEvent.mouseOut(document, { clientY: -1, relatedTarget: document.body }); // into a child
    expect(onOpen).not.toHaveBeenCalled();
  });
});
