import type { HersheyFont, HersheyGlyph } from "./hershey-font-data";

// --- Font metrics (derived from scanning all glyphs) ---

/** Advance width for space character (no path) */
export const SPACE_WIDTH = 8;

/** Vertical spacing between baselines */
export const LINE_HEIGHT = 32;

/** Topmost Y across all glyphs (ascender + accents) */
export const FONT_MIN_Y = -3;

/** Bottommost Y across all glyphs (descenders) */
export const FONT_MAX_Y = 29;

// --- Glyph lookup ---

export function getGlyph(font: HersheyFont, char: string): HersheyGlyph | null {
  const code = char.charCodeAt(0);
  if (code < 33 || code > 126) return null;
  return font.chars[code - 33] ?? null;
}

// --- Path bounds ---

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/** Extract min/max x,y from Hershey path data (M/L commands only). */
export function computePathBounds(d: string): Bounds {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  // Match all coordinate pairs: "x,y"
  const pairs = d.match(/-?\d+,-?\d+/g);
  if (!pairs) return { minX: 0, maxX: 0, minY: 0, maxY: 0 };

  for (const pair of pairs) {
    const [xs, ys] = pair.split(",");
    const x = Number(xs);
    const y = Number(ys);
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }

  return { minX, maxX, minY, maxY };
}

// --- Text layout ---

export interface PositionedGlyph {
  char: string;
  d: string;
  x: number;
  y: number;
  width: number;
}

export interface TextLayout {
  glyphs: PositionedGlyph[];
  width: number;
  height: number;
  lineCount: number;
}

/**
 * Lay out text with word-wrapping. Returns positioned glyphs.
 * Pure function — no React, no DOM.
 */
export function layoutText(
  text: string,
  font: HersheyFont,
  maxWidth: number,
  lineHeight: number = LINE_HEIGHT,
): TextLayout {
  if (!text) {
    return { glyphs: [], width: 0, height: 0, lineCount: 0 };
  }

  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return { glyphs: [], width: 0, height: 0, lineCount: 0 };
  }

  const glyphs: PositionedGlyph[] = [];
  let cursorX = 0;
  let cursorY = 0;
  let lineCount = 1;
  let maxLineWidth = 0;

  function measureWord(word: string): number {
    let w = 0;
    for (const ch of word) {
      const g = getGlyph(font, ch);
      w += g ? g.o : 0;
    }
    return w;
  }

  function emitWord(word: string) {
    for (const ch of word) {
      const g = getGlyph(font, ch);
      if (!g) continue;
      glyphs.push({ char: ch, d: g.d, x: cursorX, y: cursorY, width: g.o });
      cursorX += g.o;
    }
  }

  for (let i = 0; i < words.length; i++) {
    const word = words[i];
    const wordWidth = measureWord(word);

    // Wrap if this word would exceed maxWidth (unless we're at the start of a line)
    if (cursorX > 0 && cursorX + SPACE_WIDTH + wordWidth > maxWidth) {
      if (cursorX > maxLineWidth) maxLineWidth = cursorX;
      cursorX = 0;
      cursorY += lineHeight;
      lineCount++;
    } else if (cursorX > 0) {
      // Add space between words
      cursorX += SPACE_WIDTH;
    }

    emitWord(word);
  }

  // Final line width
  if (cursorX > maxLineWidth) maxLineWidth = cursorX;

  return {
    glyphs,
    width: maxLineWidth,
    height: cursorY + lineHeight,
    lineCount,
  };
}
