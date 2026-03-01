import { describe, it, expect } from "vitest";
import { FUTURAL, SCRIPTS } from "../hershey-font-data";
import {
  getGlyph,
  computePathBounds,
  layoutText,
  SPACE_WIDTH,
  LINE_HEIGHT,
} from "../hershey";

// ── getGlyph ───────────────────────────────────────────────

describe("getGlyph", () => {
  it("returns glyph data for printable ASCII characters", () => {
    const a = getGlyph(FUTURAL, "A");
    expect(a).toBeTruthy();
    expect(a!.d).toContain("M");
    expect(a!.o).toBeGreaterThan(0);
  });

  it("returns correct glyph for exclamation mark (first char)", () => {
    const bang = getGlyph(FUTURAL, "!");
    expect(bang).toBeTruthy();
    expect(bang!.d).toBeTruthy();
  });

  it("returns correct glyph for tilde (last printable char)", () => {
    const tilde = getGlyph(FUTURAL, "~");
    expect(tilde).toBeTruthy();
    expect(tilde!.d).toBeTruthy();
  });

  it("returns null for space", () => {
    expect(getGlyph(FUTURAL, " ")).toBeNull();
  });

  it("returns null for control characters", () => {
    expect(getGlyph(FUTURAL, "\n")).toBeNull();
    expect(getGlyph(FUTURAL, "\t")).toBeNull();
  });

  it("returns null for characters above ASCII 126", () => {
    expect(getGlyph(FUTURAL, "\x7F")).toBeNull();
    expect(getGlyph(FUTURAL, "\x80")).toBeNull();
  });

  it("works with Scripts font", () => {
    const a = getGlyph(SCRIPTS, "A");
    expect(a).toBeTruthy();
    expect(a!.d).toContain("M");
  });
});

// ── computePathBounds ──────────────────────────────────────

describe("computePathBounds", () => {
  it("extracts correct bounds from simple path", () => {
    const bounds = computePathBounds("M5,1 L5,15 M5,20 L4,21 5,22 6,21 5,20");
    expect(bounds.minX).toBe(4);
    expect(bounds.maxX).toBe(6);
    expect(bounds.minY).toBe(1);
    expect(bounds.maxY).toBe(22);
  });

  it("handles negative coordinates", () => {
    const bounds = computePathBounds("M-3,10 L5,-2");
    expect(bounds.minX).toBe(-3);
    expect(bounds.maxX).toBe(5);
    expect(bounds.minY).toBe(-2);
    expect(bounds.maxY).toBe(10);
  });

  it("returns zero bounds for empty path", () => {
    const bounds = computePathBounds("");
    expect(bounds.minX).toBe(0);
    expect(bounds.maxX).toBe(0);
  });

  it("handles single coordinate", () => {
    const bounds = computePathBounds("M10,20");
    expect(bounds.minX).toBe(10);
    expect(bounds.maxX).toBe(10);
    expect(bounds.minY).toBe(20);
    expect(bounds.maxY).toBe(20);
  });
});

// ── layoutText ─────────────────────────────────────────────

describe("layoutText", () => {
  it("returns empty layout for empty string", () => {
    const layout = layoutText("", FUTURAL, 500);
    expect(layout.glyphs).toHaveLength(0);
    expect(layout.width).toBe(0);
    expect(layout.height).toBe(0);
    expect(layout.lineCount).toBe(0);
  });

  it("returns empty layout for whitespace-only string", () => {
    const layout = layoutText("   ", FUTURAL, 500);
    expect(layout.glyphs).toHaveLength(0);
    expect(layout.lineCount).toBe(0);
  });

  it("lays out a single word on one line", () => {
    const layout = layoutText("Hello", FUTURAL, 500);
    expect(layout.glyphs.length).toBe(5);
    expect(layout.lineCount).toBe(1);
    expect(layout.width).toBeGreaterThan(0);
    expect(layout.height).toBe(LINE_HEIGHT);
  });

  it("lays out characters with increasing x positions", () => {
    const layout = layoutText("ABC", FUTURAL, 500);
    expect(layout.glyphs.length).toBe(3);
    for (let i = 1; i < layout.glyphs.length; i++) {
      expect(layout.glyphs[i].x).toBeGreaterThan(layout.glyphs[i - 1].x);
    }
  });

  it("wraps text at maxWidth", () => {
    // Use very small maxWidth to force wrapping
    const layout = layoutText("Hello World", FUTURAL, 30);
    expect(layout.lineCount).toBeGreaterThan(1);
    expect(layout.height).toBeGreaterThan(LINE_HEIGHT);
  });

  it("does not wrap when text fits", () => {
    const layout = layoutText("Hi", FUTURAL, 500);
    expect(layout.lineCount).toBe(1);
  });

  it("handles multiple spaces between words", () => {
    const layout = layoutText("Hello    World", FUTURAL, 500);
    // Should treat as two words with single space
    expect(layout.glyphs.length).toBe(10); // H-e-l-l-o-W-o-r-l-d
  });

  it("preserves correct glyph data for each character", () => {
    const layout = layoutText("A", FUTURAL, 500);
    expect(layout.glyphs.length).toBe(1);
    expect(layout.glyphs[0].char).toBe("A");
    expect(layout.glyphs[0].d).toBe(getGlyph(FUTURAL, "A")!.d);
    expect(layout.glyphs[0].width).toBe(getGlyph(FUTURAL, "A")!.o);
  });

  it("inserts space advance between words", () => {
    const layout = layoutText("A B", FUTURAL, 500);
    expect(layout.glyphs.length).toBe(2);
    const aWidth = getGlyph(FUTURAL, "A")!.o;
    // B should be at A's width + SPACE_WIDTH
    expect(layout.glyphs[1].x).toBe(aWidth + SPACE_WIDTH);
  });

  it("respects custom lineHeight", () => {
    const customHeight = 50;
    const layout = layoutText("Hello World", FUTURAL, 30, customHeight);
    if (layout.lineCount > 1) {
      expect(layout.height).toBeGreaterThanOrEqual(customHeight * 2);
    }
  });

  it("works with Scripts font", () => {
    const layout = layoutText("Test", SCRIPTS, 500);
    expect(layout.glyphs.length).toBe(4);
    expect(layout.lineCount).toBe(1);
  });

  it("SPACE_WIDTH is a reasonable value", () => {
    expect(SPACE_WIDTH).toBeGreaterThan(0);
    expect(SPACE_WIDTH).toBeLessThan(20);
  });
});
