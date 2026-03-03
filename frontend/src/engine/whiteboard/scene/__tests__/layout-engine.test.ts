import { describe, it, expect } from "vitest";
import { resolveLayout } from "../layout/engine";
import type { SemanticSceneElement } from "../../../../types/visuals";

// Ensure components are registered
import "../components/box";
import "../components/force-arrow";
import "../components/surface";
import "../components/spring";

describe("resolveLayout", () => {
  it("returns null for unknown scene_type", () => {
    const elements: SemanticSceneElement[] = [
      { id: "block", kind: "box", label: "m" },
    ];

    expect(resolveLayout("nonexistent", elements)).toBeNull();
  });

  it("returns SceneGeometry for free_body with valid elements", () => {
    const elements: SemanticSceneElement[] = [
      { id: "block", kind: "box", label: "m" },
      {
        id: "weight",
        kind: "force_arrow",
        from: "block",
        direction: "down",
        label: "W",
      },
    ];

    const result = resolveLayout("free_body", elements);

    expect(result).not.toBeNull();
    expect(result!.paths.length).toBeGreaterThan(0);
    expect(result!.labels.length).toBeGreaterThan(0);
    expect(result!.bounds.width).toBeGreaterThan(0);
  });

  it("uses default context (500x400) when none provided", () => {
    const elements: SemanticSceneElement[] = [
      { id: "block", kind: "box", label: "m" },
    ];

    const result = resolveLayout("free_body", elements);

    // Block should be centered at (250, 200) — default 500x400 / 2
    expect(result).not.toBeNull();
    expect(result!.anchors?.blockCenter).toEqual({ x: 250, y: 200 });
  });

  it("uses custom context when provided", () => {
    const elements: SemanticSceneElement[] = [
      { id: "block", kind: "box", label: "m" },
    ];

    const result = resolveLayout("free_body", elements, {
      sceneWidth: 800,
      sceneHeight: 600,
      colors: {} as never,
    });

    // Block should be centered at (400, 300) — 800x600 / 2
    expect(result).not.toBeNull();
    expect(result!.anchors?.blockCenter).toEqual({ x: 400, y: 300 });
  });
});
