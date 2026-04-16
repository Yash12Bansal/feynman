/**
 * Single notebook entry — equation, step, text, section, key_point, answer.
 *
 * Equations use KaTeX. When two equations share an alignGroup, the parent
 * Notebook measures `=` offsets in a layout effect (before paint) and nudges
 * them into vertical alignment — no flash of unaligned content. Strikethrough
 * and the answer box draw themselves in via SVG path overlays animated with
 * `stroke-dashoffset` so they read as hand-drawn strokes rather than snap-in.
 */

import { useEffect, useLayoutEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import type { NotebookEntry } from "./types";
import { RoughGraphContent } from "../content/RoughGraphContent";

interface NotebookEntryViewProps {
  readonly entry: NotebookEntry;
  readonly alignOffsetPx?: number;
  readonly onEqualsOffset?: (id: string, offsetPx: number) => void;
}

function indentClass(indent: 0 | 1 | 2 | 3 | undefined): string {
  if (!indent) return "";
  return ` sb-entry--indent-${indent}`;
}

function struckClass(struck: boolean | undefined): string {
  return struck ? " sb-entry--struck" : "";
}

function carriedClass(carried: boolean | undefined): string {
  return carried ? " sb-entry--carried" : "";
}

function StrikeOverlay() {
  // A slightly curved quadratic path reads as a felt-tip swipe rather than a
  // ruler-straight line. `pathLength={1}` normalizes dasharray math across
  // any entry width so the keyframe works the same for a 20-char line and a
  // 200-char line.
  return (
    <svg
      className="sb-strike-svg"
      aria-hidden="true"
      viewBox="0 0 100 20"
      preserveAspectRatio="none"
    >
      <path d="M 2 10 Q 50 7 98 10" pathLength={1} />
    </svg>
  );
}

export function NotebookEntryView({
  entry,
  alignOffsetPx,
  onEqualsOffset,
}: NotebookEntryViewProps) {
  const indent = indentClass(entry.indent);
  const struck = struckClass(entry.struck);
  const carried = carriedClass(entry.carriedForward);
  const showStrike = entry.struck === true;

  switch (entry.kind) {
    case "section_header":
      return (
        <div
          className={`sb-entry sb-entry--section${indent}${carried}`}
          data-entry-id={entry.id}
        >
          <span>{entry.title}</span>
        </div>
      );

    case "text":
      return (
        <div
          className={`sb-entry sb-entry--text${indent}${struck}${carried}`}
          data-entry-id={entry.id}
        >
          {entry.text}
          {showStrike && <StrikeOverlay />}
        </div>
      );

    case "key_point":
      return (
        <div
          className={`sb-entry sb-entry--key-point${indent}${struck}${carried}`}
          data-entry-id={entry.id}
        >
          {entry.text}
          {showStrike && <StrikeOverlay />}
        </div>
      );

    case "step":
      return (
        <div
          className={`sb-entry sb-entry--step${indent}${struck}${carried}`}
          data-entry-id={entry.id}
        >
          {entry.number !== undefined && (
            <span className="sb-step-num">({entry.number})</span>
          )}
          <span>{entry.text}</span>
          {showStrike && <StrikeOverlay />}
        </div>
      );

    case "equation":
      return (
        <EquationView
          id={entry.id}
          latex={entry.latex}
          indent={indent}
          struck={struck}
          carried={carried}
          showStrike={showStrike}
          alignGroup={entry.alignGroup}
          alignOffsetPx={alignOffsetPx}
          onEqualsOffset={onEqualsOffset}
        />
      );

    case "answer":
      return (
        <AnswerView
          id={entry.id}
          latex={entry.latex}
          text={entry.text}
          indent={indent}
          carried={carried}
        />
      );

    case "graph":
      return (
        <div
          className={`sb-entry sb-entry--graph${indent}${carried}`}
          data-entry-id={entry.id}
        >
          <RoughGraphContent instruction={entry.instr} />
        </div>
      );
  }
}

// ── Equation with KaTeX + optional `=` alignment ──────────────

function EquationView({
  id,
  latex,
  indent,
  struck,
  carried,
  showStrike,
  alignGroup,
  alignOffsetPx,
  onEqualsOffset,
}: {
  readonly id: string;
  readonly latex: string;
  readonly indent: string;
  readonly struck: string;
  readonly carried: string;
  readonly showStrike: boolean;
  readonly alignGroup?: string;
  readonly alignOffsetPx?: number;
  readonly onEqualsOffset?: (id: string, offsetPx: number) => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  // useLayoutEffect — render KaTeX and report the `=` offset synchronously
  // after DOM mutation but before the browser paints. The parent Notebook
  // hears the offset, re-renders with the nudge applied, and commits all of
  // it in the same paint. Running under useEffect let the unaligned frame
  // slip through first, producing a flash-of-unaligned-content.
  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    try {
      katex.render(latex, host, {
        throwOnError: false,
        displayMode: false,
        output: "html",
      });
    } catch {
      host.textContent = latex;
    }

    if (!alignGroup || !onEqualsOffset) return;

    // Measure the horizontal position of the first `=` sign inside the rendered
    // KaTeX output. We walk the .mrel elements; the first whose text is `=`
    // (or starts with `=`) is our alignment anchor.
    const hostRect = host.getBoundingClientRect();
    const relEls = host.querySelectorAll<HTMLElement>(".mrel");
    for (const el of relEls) {
      const txt = el.textContent?.trim() ?? "";
      if (txt === "=" || txt.startsWith("=")) {
        const rect = el.getBoundingClientRect();
        const offset = rect.left - hostRect.left;
        onEqualsOffset(id, offset);
        break;
      }
    }
  }, [latex, id, alignGroup, onEqualsOffset]);

  const style = alignOffsetPx
    ? ({ "--sb-align-offset": alignOffsetPx } as React.CSSProperties)
    : undefined;

  return (
    <div
      className={`sb-entry sb-entry--equation${indent}${struck}${carried}`}
      data-entry-id={id}
      data-align-group={alignGroup ?? undefined}
      style={style}
    >
      <div ref={hostRef} />
      {showStrike && <StrikeOverlay />}
    </div>
  );
}

// ── Answer (boxed, can be equation or text) ───────────────────

function AnswerView({
  id,
  latex,
  text,
  indent,
  carried,
}: {
  readonly id: string;
  readonly latex?: string;
  readonly text?: string;
  readonly indent: string;
  readonly carried: string;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !latex) return;
    try {
      katex.render(latex, host, {
        throwOnError: false,
        displayMode: false,
        output: "html",
      });
    } catch {
      host.textContent = latex;
    }
  }, [latex]);

  return (
    <div
      className={`sb-entry sb-entry--answer${indent}${carried}`}
      data-entry-id={id}
    >
      {latex ? <div ref={hostRef} /> : <span>{text}</span>}
      <svg
        className="sb-answer-rect"
        aria-hidden="true"
        preserveAspectRatio="none"
      >
        <rect x="0" y="0" width="100%" height="100%" rx={6} pathLength={1} />
      </svg>
    </div>
  );
}
