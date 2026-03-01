/**
 * Handwritten text renderer using Hershey single-stroke fonts.
 *
 * Each character is an SVG <path> animated via stroke-dashoffset
 * for the "teacher writing on the board" effect. Title uses the
 * cursive Scripts font, body uses the print Futural font.
 */

import { useEffect, useRef } from "react";
import gsap from "gsap";
import type { ShowTextInstruction, TextStyle } from "../../../types/visuals";
import { COLORS } from "../../theme";
import { FUTURAL, SCRIPTS } from "../fonts/hershey-font-data";
import { layoutText, FONT_MIN_Y, LINE_HEIGHT } from "../fonts/hershey";
import type { TextLayout } from "../fonts/hershey";
import { ALIVE_FILTER_ID } from "../AliveFilter";

// ── Style → accent color mapping ────────────────────────────

const STYLE_ACCENTS: Record<TextStyle, string> = {
  default: COLORS.accentBlue,
  definition: COLORS.accentBlue,
  key_point: COLORS.accentAmber,
  example: COLORS.accentGreen,
};

// ── Layout constants ────────────────────────────────────────

/** Max width in font units for layout. Tuned so scaled SVG fills card width well. */
const TITLE_MAX_WIDTH = 300;
const BODY_MAX_WIDTH = 400;

/** Scale from font units to display pixels (approx) */
const TITLE_SCALE = 2.5;
const BODY_SCALE = 1.8;

/** Max total animation duration in seconds */
const MAX_DURATION = 3.5;

/** Small gap between characters for natural feel */
const CHAR_GAP = 0.02;

/** Gap between title and body animation */
const SECTION_GAP = 0.2;

// ── SVG section renderer ────────────────────────────────────

function HandwrittenSection({
  layout,
  scale,
  color,
  label,
  dataPrefix,
}: {
  layout: TextLayout;
  scale: number;
  color: string;
  label: string;
  dataPrefix: string;
}) {
  if (layout.glyphs.length === 0) return null;

  const svgWidth = layout.width * scale;
  const svgHeight = layout.height * scale;
  // Shift all glyphs down so the topmost ascender (FONT_MIN_Y) sits at y=0
  const yOffset = -FONT_MIN_Y;

  return (
    <svg
      viewBox={`0 0 ${layout.width} ${layout.height + yOffset}`}
      width={svgWidth}
      height={svgHeight + yOffset * scale}
      style={{ display: "block", maxWidth: "100%", overflow: "visible" }}
      role="img"
      aria-label={label}
    >
      <g style={{ filter: `url(#${ALIVE_FILTER_ID})` }}>
        {layout.glyphs.map((glyph, i) => (
          <path
            key={`${dataPrefix}-${i}`}
            d={glyph.d}
            transform={`translate(${glyph.x},${glyph.y + yOffset})`}
            stroke={color}
            strokeWidth={1.5}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            data-hw-char={glyph.char}
            data-hw-section={dataPrefix}
          />
        ))}
      </g>
    </svg>
  );
}

// ── Main component ──────────────────────────────────────────

export function HandwrittenTextContent({
  instruction,
}: {
  instruction: ShowTextInstruction;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  const style = instruction.style ?? "default";
  const accent = STYLE_ACCENTS[style];

  const titleLayout = instruction.title
    ? layoutText(instruction.title, SCRIPTS, TITLE_MAX_WIDTH, LINE_HEIGHT)
    : null;

  const bodyLayout = layoutText(
    instruction.text,
    FUTURAL,
    BODY_MAX_WIDTH,
    LINE_HEIGHT,
  );

  // Animate stroke-dashoffset on mount
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    timelineRef.current?.kill();

    const titlePaths = container.querySelectorAll<SVGPathElement>(
      '[data-hw-section="title"]',
    );
    const bodyPaths = container.querySelectorAll<SVGPathElement>(
      '[data-hw-section="body"]',
    );

    const allPaths = [...Array.from(titlePaths), ...Array.from(bodyPaths)];
    if (allPaths.length === 0) return;

    // Measure total path length for speed calculation
    let totalLength = 0;
    const lengths: number[] = [];
    for (const path of allPaths) {
      const len = path.getTotalLength();
      lengths.push(len);
      totalLength += len;
    }

    // Compute pen speed: constant speed, capped at MAX_DURATION
    const totalCharTime = allPaths.length * CHAR_GAP;
    const penSpeed =
      totalLength / Math.max(0.5, MAX_DURATION - SECTION_GAP - totalCharTime);

    const tl = gsap.timeline();
    timelineRef.current = tl;

    // Set initial state: fully hidden via dashoffset
    for (let i = 0; i < allPaths.length; i++) {
      const len = lengths[i];
      gsap.set(allPaths[i], {
        strokeDasharray: len,
        strokeDashoffset: len,
      });
    }

    // Animate title paths
    let pos = 0;
    for (let i = 0; i < titlePaths.length; i++) {
      const idx = i; // Same index in allPaths since title comes first
      const duration = Math.max(0.01, lengths[idx] / penSpeed);
      tl.to(
        allPaths[idx],
        { strokeDashoffset: 0, duration, ease: "none" },
        pos,
      );
      pos += duration + CHAR_GAP;
    }

    // Gap between sections
    if (titlePaths.length > 0 && bodyPaths.length > 0) {
      pos += SECTION_GAP;
    }

    // Animate body paths
    for (let i = 0; i < bodyPaths.length; i++) {
      const idx = titlePaths.length + i;
      const duration = Math.max(0.01, lengths[idx] / penSpeed);
      tl.to(
        allPaths[idx],
        { strokeDashoffset: 0, duration, ease: "none" },
        pos,
      );
      pos += duration + CHAR_GAP;
    }

    return () => {
      tl.kill();
    };
  }, [instruction.title, instruction.text]);

  return (
    <div ref={containerRef}>
      {titleLayout && titleLayout.glyphs.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <HandwrittenSection
            layout={titleLayout}
            scale={TITLE_SCALE}
            color={accent}
            label={instruction.title!}
            dataPrefix="title"
          />
        </div>
      )}
      {bodyLayout.glyphs.length > 0 && (
        <HandwrittenSection
          layout={bodyLayout}
          scale={BODY_SCALE}
          color={COLORS.textPrimary}
          label={instruction.text}
          dataPrefix="body"
        />
      )}
    </div>
  );
}
