/**
 * Tests for the chapter picker home screen.
 *
 * Covers the four fetch states (loading / error / empty / loaded) and the
 * click handler that navigates into a chapter via the `?lecture=<id>` param.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { LectureHomeScreen } from "./LectureHomeScreen";

const originalLocation = window.location;

beforeEach(() => {
  // Replace window.location with a stub we can inspect. The href setter is
  // captured by a spy so we can assert what the click handler navigated to.
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: {
      ...originalLocation,
      href: "http://localhost:5173/",
      search: "",
    },
  });
});

afterEach(() => {
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: originalLocation,
  });
  vi.restoreAllMocks();
});

describe("LectureHomeScreen", () => {
  it("shows a loading skeleton while chapters are fetching", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {}),
    );
    const { container } = render(<LectureHomeScreen />);
    expect(container.querySelector("[aria-busy='true']")).toBeTruthy();
  });

  it("surfaces a fetch error with a hint about the preview server", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error("Failed to fetch"),
    );
    const { findByText } = render(<LectureHomeScreen />);
    await findByText(/Can't reach the lecture server/i);
    await findByText(/make dev-preview-server/i);
  });

  it("shows an empty state when no chapters are ingested", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByText } = render(<LectureHomeScreen />);
    await findByText(/No lectures yet/i);
  });

  it("renders a card per chapter when chapters are returned", async () => {
    const chapters = [
      {
        id: "chapter:physics:relativity",
        title: "The Special Theory of Relativity",
        idx: 47,
        has_manifest: true,
      },
      {
        id: "chapter:physics:newton",
        title: "Newton's Laws of Motion",
        idx: 5,
        has_manifest: false,
      },
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(chapters), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findAllByTestId } = render(
      <LectureHomeScreen visibleChapterIds={null} />,
    );
    const cards = await waitFor(async () => {
      const all = await findAllByTestId("chapter-card");
      expect(all).toHaveLength(2);
      return all;
    });
    expect(cards[0].getAttribute("data-chapter-id")).toBe(
      "chapter:physics:relativity",
    );
    // Ready chapter is enabled, no-audio chapter is disabled.
    expect(cards[0]).not.toHaveProperty("disabled", true);
    expect((cards[1] as HTMLButtonElement).disabled).toBe(true);
  });

  it("navigates to ?lecture=<id> when a ready chapter is clicked", async () => {
    const chapters = [
      {
        id: "chapter:physics:relativity",
        title: "Relativity",
        idx: 47,
        has_manifest: true,
      },
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(chapters), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId } = render(
      <LectureHomeScreen visibleChapterIds={null} />,
    );
    const card = await findByTestId("chapter-card");
    fireEvent.click(card);
    expect(window.location.href).toContain(
      "lecture=chapter%3Aphysics%3Arelativity",
    );
  });

  it("curates to the allow-list: only allowed chapters, in allow-list order, hiding others + empty cards", async () => {
    const chapters = [
      {
        id: "chapter:physics:newtons_laws_of_motion",
        title: "Newton's Laws of Motion",
        idx: 5,
        has_manifest: true,
      },
      {
        id: "chapter:physics:friction",
        title: "Friction",
        idx: 6,
        has_manifest: true,
      },
      {
        id: "chapter:mathematics:arithmetic_progressions",
        title: "Arithmetic Progressions",
        idx: 1,
        has_manifest: true,
      },
      { id: null, title: null, idx: null, has_manifest: false },
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(chapters), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findAllByTestId } = render(
      <LectureHomeScreen
        visibleChapterIds={[
          "chapter:mathematics:arithmetic_progressions",
          "chapter:physics:friction",
        ]}
      />,
    );
    const cards = await waitFor(async () => {
      const all = await findAllByTestId("chapter-card");
      expect(all).toHaveLength(2);
      return all;
    });
    // Allow-list order wins over fetch order; Newton's Laws + the empty card hidden.
    expect(cards[0].getAttribute("data-chapter-id")).toBe(
      "chapter:mathematics:arithmetic_progressions",
    );
    expect(cards[1].getAttribute("data-chapter-id")).toBe(
      "chapter:physics:friction",
    );
  });

  // ── Class tabs (default, tabbed path) ────────────────────────────

  const TAB_GROUPS = [
    { label: "A", ids: ["chapter:a:one", "chapter:a:two"] },
    { label: "B", ids: ["chapter:b:one"] },
  ];
  const TAB_CHAPTERS = [
    { id: "chapter:a:one", title: "Alpha One", idx: 1, has_manifest: true },
    { id: "chapter:a:two", title: "Alpha Two", idx: 2, has_manifest: true },
    { id: "chapter:b:one", title: "Beta One", idx: 3, has_manifest: true },
  ];

  it("renders a tab per class group and shows only the active group's cards", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(TAB_CHAPTERS), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId, findAllByTestId } = render(
      <LectureHomeScreen classGroups={TAB_GROUPS} />,
    );
    // One tab button per group.
    await findByTestId("class-tab-A");
    await findByTestId("class-tab-B");
    // Active group (first) shows its 2 cards, in order; group B's card absent.
    const cards = await findAllByTestId("chapter-card");
    expect(cards).toHaveLength(2);
    expect(cards.map((c) => c.getAttribute("data-chapter-id"))).toEqual([
      "chapter:a:one",
      "chapter:a:two",
    ]);
  });

  it("switches the visible cards when another class tab is clicked", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(TAB_CHAPTERS), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { findByTestId, findAllByTestId } = render(
      <LectureHomeScreen classGroups={TAB_GROUPS} />,
    );
    // Starts on group A (2 cards).
    expect(await findAllByTestId("chapter-card")).toHaveLength(2);
    // Switch to group B → only its single card.
    fireEvent.click(await findByTestId("class-tab-B"));
    const cards = await waitFor(async () => {
      const all = await findAllByTestId("chapter-card");
      expect(all).toHaveLength(1);
      return all;
    });
    expect(cards[0].getAttribute("data-chapter-id")).toBe("chapter:b:one");
  });
});
