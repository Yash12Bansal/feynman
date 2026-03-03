import { describe, it, expect } from "vitest";
import { doubleSlit } from "../templates/double-slit";

describe("doubleSlit", () => {
  it("default params produce source + barrier + screen + rays + waves + pattern", () => {
    const result = doubleSlit();
    const ids = result.paths.map((p) => p.id);

    // Always-present elements
    expect(ids).toContain("source");
    expect(ids).toContain("barrier-top");
    expect(ids).toContain("barrier-middle");
    expect(ids).toContain("barrier-bottom");
    expect(ids).toContain("screen");

    // Rays (default on)
    expect(ids).toContain("slit-ray-1");
    expect(ids).toContain("slit-ray-2");

    // Wavefronts (default on)
    expect(ids).toContain("wavefront-s1-0");
    expect(ids).toContain("wavefront-s1-1");
    expect(ids).toContain("wavefront-s1-2");
    expect(ids).toContain("wavefront-s2-0");
    expect(ids).toContain("wavefront-s2-1");
    expect(ids).toContain("wavefront-s2-2");

    // Interference pattern (default on)
    expect(ids).toContain("bright-band-0");
    expect(ids).toContain("bright-band-6");
    expect(ids).toContain("dark-band-0");
    expect(ids).toContain("dark-band-5");
  });

  it("showRays=false removes ray paths", () => {
    const result = doubleSlit({ showRays: false });
    const ids = result.paths.map((p) => p.id);

    expect(ids).not.toContain("slit-ray-1");
    expect(ids).not.toContain("slit-ray-2");

    // Other elements still present
    expect(ids).toContain("source");
    expect(ids).toContain("barrier-top");
    expect(ids).toContain("screen");
  });

  it("showWaves=false removes wavefront arcs", () => {
    const result = doubleSlit({ showWaves: false });
    const wavefronts = result.paths.filter((p) => p.id.startsWith("wavefront"));
    expect(wavefronts).toHaveLength(0);
  });

  it("showPattern=false removes interference bands", () => {
    const result = doubleSlit({ showPattern: false });
    const bands = result.paths.filter(
      (p) => p.id.startsWith("bright-band") || p.id.startsWith("dark-band"),
    );
    expect(bands).toHaveLength(0);
  });

  it("showLabels=true produces labels", () => {
    const result = doubleSlit({ showLabels: true });
    const labelIds = result.labels.map((l) => l.id);

    expect(labelIds).toContain("source-label");
    expect(labelIds).toContain("slit-sep-label");
    expect(labelIds).toContain("screen-label");
  });

  it("showLabels=false removes all labels", () => {
    const result = doubleSlit({ showLabels: false });
    expect(result.labels).toHaveLength(0);
  });

  it("has correct number of bright and dark bands", () => {
    const result = doubleSlit();
    const bright = result.paths.filter((p) => p.id.startsWith("bright-band"));
    const dark = result.paths.filter((p) => p.id.startsWith("dark-band"));

    expect(bright).toHaveLength(7);
    expect(dark).toHaveLength(6);
  });

  it("has 6 wavefront arcs (3 per slit)", () => {
    const result = doubleSlit();
    const wavefronts = result.paths.filter((p) => p.id.startsWith("wavefront"));
    expect(wavefronts).toHaveLength(6);
  });

  it("bounds are reasonable for the 700x400 scene", () => {
    const result = doubleSlit();
    // Tight bounds should be smaller than the full 700x400 canvas
    // but encompass all content (source at x=60, screen+bands to x=605+)
    expect(result.bounds.width).toBeGreaterThan(400);
    expect(result.bounds.width).toBeLessThan(750);
    expect(result.bounds.height).toBeGreaterThan(200);
    expect(result.bounds.height).toBeLessThan(450);
  });

  it("slitSeparation='wide' changes slit positions", () => {
    const narrow = doubleSlit({ slitSeparation: "narrow" });
    const wide = doubleSlit({ slitSeparation: "wide" });

    // Wide separation should produce different barrier geometry
    const narrowMid = narrow.paths.find((p) => p.id === "barrier-middle");
    const wideMid = wide.paths.find((p) => p.id === "barrier-middle");
    expect(narrowMid!.d).not.toEqual(wideMid!.d);

    // Both should have the same anchors structure
    expect(wide.anchors?.slit1).toBeDefined();
    expect(wide.anchors?.slit2).toBeDefined();
  });

  it("has expected anchors", () => {
    const result = doubleSlit();
    expect(result.anchors?.source).toBeDefined();
    expect(result.anchors?.slit1).toBeDefined();
    expect(result.anchors?.slit2).toBeDefined();
    expect(result.anchors?.screenCenter).toBeDefined();
  });
});
