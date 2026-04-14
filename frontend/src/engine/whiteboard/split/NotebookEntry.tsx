/**
 * Single notebook entry — equation, step, text, section, key_point, answer.
 *
 * Equations use KaTeX. When two equations share an alignGroup, the parent
 * Notebook measures `=` offsets and nudges them into vertical alignment.
 */

import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import type { NotebookEntry } from "./types";

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

export function NotebookEntryView({
  entry,
  alignOffsetPx,
  onEqualsOffset,
}: NotebookEntryViewProps) {
  const indent = indentClass(entry.indent);
  const struck = struckClass(entry.struck);

  switch (entry.kind) {
    case "section_header":
      return (
        <div
          className={`sb-entry sb-entry--section${indent}`}
          data-entry-id={entry.id}
        >
          <span>{entry.title}</span>
        </div>
      );

    case "text":
      return (
        <div
          className={`sb-entry sb-entry--text${indent}${struck}`}
          data-entry-id={entry.id}
        >
          {entry.text}
        </div>
      );

    case "key_point":
      return (
        <div
          className={`sb-entry sb-entry--key-point${indent}${struck}`}
          data-entry-id={entry.id}
        >
          {entry.text}
        </div>
      );

    case "step":
      return (
        <div
          className={`sb-entry sb-entry--step${indent}${struck}`}
          data-entry-id={entry.id}
        >
          {entry.number !== undefined && (
            <span className="sb-step-num">({entry.number})</span>
          )}
          <span>{entry.text}</span>
        </div>
      );

    case "equation":
      return (
        <EquationView
          id={entry.id}
          latex={entry.latex}
          indent={indent}
          struck={struck}
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
        />
      );
  }
}

// ── Equation with KaTeX + optional `=` alignment ──────────────

function EquationView({
  id,
  latex,
  indent,
  struck,
  alignGroup,
  alignOffsetPx,
  onEqualsOffset,
}: {
  readonly id: string;
  readonly latex: string;
  readonly indent: string;
  readonly struck: string;
  readonly alignGroup?: string;
  readonly alignOffsetPx?: number;
  readonly onEqualsOffset?: (id: string, offsetPx: number) => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
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
      className={`sb-entry sb-entry--equation${indent}${struck}`}
      data-entry-id={id}
      data-align-group={alignGroup ?? undefined}
      style={style}
    >
      <div ref={hostRef} />
    </div>
  );
}

// ── Answer (boxed, can be equation or text) ───────────────────

function AnswerView({
  id,
  latex,
  text,
  indent,
}: {
  readonly id: string;
  readonly latex?: string;
  readonly text?: string;
  readonly indent: string;
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
      className={`sb-entry sb-entry--answer${indent}`}
      data-entry-id={id}
    >
      {latex ? <div ref={hostRef} /> : <span>{text}</span>}
    </div>
  );
}
