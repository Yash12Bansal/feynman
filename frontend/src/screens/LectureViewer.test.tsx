/**
 * Tests for the immersive LectureViewer.
 *
 * Focus: chapter-loading state machine + SplitBoard wiring. The playback
 * engine itself is tested in useExtractionPlayback.test.tsx — here we only
 * verify the viewer mounts, fetches, and renders the right child.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { LectureViewer } from "./LectureViewer";

vi.mock("../engine/whiteboard/split/SplitBoard", () => ({
  SplitBoard: ({ mode }: { mode?: string }) => (
    <div data-testid="split-board" data-mode={mode}>
      split-board
    </div>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LectureViewer", () => {
  it("shows a preparing status while the chapter is loading", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {}), // never resolves
    );
    const { getByText } = render(<LectureViewer chapterId="chapter:test" />);
    expect(getByText(/Preparing lecture/i)).toBeTruthy();
    fetchSpy.mockRestore();
  });

  it("surfaces a fetch error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("not found", { status: 404 }),
    );
    const { findByText } = render(<LectureViewer chapterId="chapter:test" />);
    await findByText(/Failed to load lecture/i);
  });

  it("renders SplitBoard in slide_full mode once the chapter loads", async () => {
    const payload = {
      chapter_id: "chapter:test",
      title: "Test",
      chapter_index: 1,
      events: [],
      diagrams: {},
      topics: {},
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId } = render(<LectureViewer chapterId="chapter:test" />);
    const board = await waitFor(() => findByTestId("split-board"));
    expect(board.getAttribute("data-mode")).toBe("slide_full");
  });
});
