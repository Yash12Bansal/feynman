/**
 * Render-time colour remap so precomputed (dark-authored) diagrams read on a
 * LIGHT board, without re-generating any lecture.
 *
 * Diagrams are authored against a mandated dark-board palette
 * (data_pre_compute_v2/.../enrichment/diagrams.py + backend canvas_dsl.py):
 * light ink #e8e8ee, cyan #7fd4ff, green #9effc9, pink #ff7a8a (+ a rare gold).
 * The long tail is author-chosen colours, many of them mid-light (#90caf9,
 * #bbdefb, pale tints) that wash out on warm paper.
 *
 * Light mode therefore does two things to keep every stroke/label GREATLY
 * visible:
 *   1. maps the canonical accents to deep, on-brand equivalents, and
 *   2. enforces a minimum WCAG contrast floor against the paper for every other
 *      stroke/text colour — darkening (hue-preserving) until it clears.
 * Fills are left alone (a light fill is an intentional background, not "ink").
 *
 * Dark mode is the identity (the board's native habitat) — zero change.
 */

import type { Theme } from "../../theme/themeContext";

type Role = "stroke" | "fill" | "text";

const INK = "#1b1916";
const PAPER = "#f6f4ee"; // the light board surface (SplitBoard.css)

// Canonical dark-board accents → deep light-board equivalents (all ≥4.5:1 on paper).
const ACCENT_MAP: Record<string, string> = {
  "#7fd4ff": "#1f37c4", // cyan → deep fountain-pen blue
  "#9effc9": "#0f7a37", // green → deep emerald
  "#ff7a8a": "#b5271a", // pink → deep coral-red
  "#e8c97a": "#8a5a00", // gold → deep amber
};

// Near-white inks that vanish on paper → ink (stroke/text only).
const INK_LIKE = new Set([
  "#e8e8ee",
  "#ffffff",
  "#fafafa",
  "#f8f9fa",
  "#f5f5f5",
  "#eeeeee",
]);

// Per-role contrast targets against the paper. Text is held to AA (4.5:1);
// strokes/graphics a touch lower (4.0) so strong hues keep some colour.
const TARGET: Record<Role, number> = { text: 4.5, stroke: 4.0, fill: 1 };

function normalizeHex(value: string): string | null {
  let h = value.trim().toLowerCase();
  if (!h.startsWith("#")) return null;
  h = h.slice(1);
  if (h.length === 3) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  }
  if (h.length !== 6 || /[^0-9a-f]/.test(h)) return null;
  return `#${h}`;
}

function srgbToLinear(c: number): number {
  const x = c / 255;
  return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
}

function luminanceRGB(r: number, g: number, b: number): number {
  return (
    0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
  );
}

function luminanceHex(hex: string): number {
  return luminanceRGB(
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  );
}

const PAPER_L = luminanceHex(PAPER);

function contrastOnPaper(l: number): number {
  const hi = Math.max(PAPER_L, l);
  const lo = Math.min(PAPER_L, l);
  return (hi + 0.05) / (lo + 0.05);
}

function toHex(r: number, g: number, b: number): string {
  const h = (n: number) =>
    Math.max(0, Math.min(255, Math.round(n)))
      .toString(16)
      .padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}

/** Darken a colour toward black (hue-preserving channel scale) until it clears
 *  the contrast target against the paper. */
function darkenToContrast(hex: string, target: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  for (let k = 1; k >= 0; k -= 0.04) {
    const l = luminanceRGB(r * k, g * k, b * k);
    if (contrastOnPaper(l) >= target) return toHex(r * k, g * k, b * k);
  }
  return INK;
}

const cache = new Map<string, string>();

/**
 * Map a single colour for the active theme. Returns `undefined` only when the
 * input is nullish, so callers keep their own `?? var(--sb-ink)` fallback
 * (unspecified colours then follow the theme-aware ink variable).
 */
export function mapColor(
  color: string | undefined | null,
  theme: Theme,
  role: Role = "stroke",
): string | undefined {
  if (color == null) return undefined;
  if (theme === "dark") return color;

  const c = color.trim().toLowerCase();
  if (c === "none" || c === "transparent" || c === "currentcolor") return color;
  if (c === "white") return role === "fill" ? color : INK;

  const hex = normalizeHex(c);
  if (!hex) return color; // named colours (steelblue, etc.) — leave as-is

  const key = `${role}:${hex}`;
  const cached = cache.get(key);
  if (cached) return cached;

  let out: string;
  if (ACCENT_MAP[hex]) {
    out = ACCENT_MAP[hex];
  } else if (role === "fill") {
    out = color; // intentional background fill — keep
  } else if (INK_LIKE.has(hex)) {
    out = INK;
  } else {
    const target = TARGET[role];
    out =
      contrastOnPaper(luminanceHex(hex)) >= target
        ? color
        : darkenToContrast(hex, target);
  }
  cache.set(key, out);
  return out;
}
