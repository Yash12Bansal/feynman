/**
 * Phase 3+4+5 adapter — derives split-board state from the live instruction stream.
 *
 * Pure derivation over `useBoardStore`'s `activeInstructions`. Partitions on
 * `instruction.panel` (with type-based fallback for safety), maps notebook
 * instructions to typed entries, picks the latest slide instruction. Phase 4
 * added loading-state surfacing. Phase 5 added notebook-native write tools
 * (`write_*`, `strikethrough`, `new_page`).
 *
 * Reference instructions (highlight / annotate / highlight_walk) are dropped
 * in split mode with a `console.debug` so they're visible during dogfood.
 * Phase 8 adds proper rendering against split-mode targets.
 */

import { useMemo } from "react";
import type {
  AnnotationInstruction,
  Panel,
  ShowEquationInstruction,
  ShowGraphInstruction,
  ShowTextInstruction,
  StepEquationInstruction,
  StrikethroughInstruction,
  VisualInstruction,
  WriteAnswerInstruction,
  WriteEquationInstruction,
  WriteSectionInstruction,
  WriteStepInstruction,
  WriteTextInstruction,
} from "../../../types/visuals";
import type { PendingSlide } from "../useBoardStore";
import type {
  NotebookEntry,
  NotebookEntryBase,
  NotebookState,
  SlideState,
} from "./types";

const DIAGRAM_TYPES = new Set<string>([
  "draw_diagram",
  "draw_design_diagram",
  "draw_scene",
]);

const ANNOTATION_TYPES = new Set<string>([
  "pin_label",
  "draw_callout",
  "bracket",
  "highlight_pulse",
]);

const SLIDE_TYPES = new Set<string>([
  ...DIAGRAM_TYPES,
  ...ANNOTATION_TYPES,
  "slide_pending",
]);

function isAnnotation(
  instr: VisualInstruction,
): instr is AnnotationInstruction {
  return ANNOTATION_TYPES.has(instr.type);
}
const NOTEBOOK_TYPES = new Set([
  "show_text",
  "show_equation",
  "step_equation",
  "show_graph",
  "write_equation",
  "write_step",
  "write_text",
  "write_section",
  "write_answer",
  "strikethrough",
  "new_page",
]);

function inferPanel(instr: VisualInstruction): Panel {
  if (instr.panel) return instr.panel;
  if (SLIDE_TYPES.has(instr.type)) return "slide";
  if (NOTEBOOK_TYPES.has(instr.type)) return "notebook";
  return "reference";
}

function entryId(instr: VisualInstruction, suffix?: string): string {
  const base = instr.element_id ?? `${instr.type}-${suffix ?? ""}`;
  return suffix ? `${base}-${suffix}` : base;
}

function clampIndent(raw: number | undefined): 0 | 1 | 2 | 3 {
  if (raw === undefined || raw === null) return 0;
  if (raw <= 0) return 0;
  if (raw >= 3) return 3;
  return (raw === 1 ? 1 : 2) as 1 | 2;
}

function instructionToNotebookEntries(
  instr: VisualInstruction,
): NotebookEntry[] {
  switch (instr.type) {
    case "show_text": {
      const t = instr as ShowTextInstruction;
      const style = t.style ?? "default";
      if (style === "key_point") {
        return [
          {
            kind: "key_point",
            id: entryId(t),
            text: t.text,
          },
        ];
      }
      if (style === "definition") {
        const out: NotebookEntry[] = [];
        if (t.title) {
          out.push({
            kind: "section_header",
            id: entryId(t, "header"),
            title: t.title,
          });
        }
        out.push({
          kind: "text",
          id: entryId(t, "body"),
          text: t.text,
        });
        return out;
      }
      if (style === "example") {
        return [
          {
            kind: "text",
            id: entryId(t),
            text: t.text,
            indent: 1,
          },
        ];
      }
      return [
        {
          kind: "text",
          id: entryId(t),
          text: t.text,
        },
      ];
    }

    case "show_equation": {
      const e = instr as ShowEquationInstruction;
      return [
        {
          kind: "equation",
          id: entryId(e),
          latex: e.latex,
        },
      ];
    }

    case "step_equation": {
      const s = instr as StepEquationInstruction;
      const out: NotebookEntry[] = [];
      if (s.title) {
        out.push({
          kind: "section_header",
          id: entryId(s, "header"),
          title: s.title,
        });
      }
      s.steps.forEach((step, i) => {
        out.push({
          kind: "equation",
          id: entryId(s, `step-${i}`),
          latex: step.latex,
          indent: 1,
        });
      });
      return out;
    }

    case "show_graph": {
      const g = instr as ShowGraphInstruction;
      return [
        {
          kind: "graph",
          id: entryId(g),
          instr: g,
        },
      ];
    }

    case "write_equation": {
      const w = instr as WriteEquationInstruction;
      return [
        {
          kind: "equation",
          id: entryId(w),
          latex: w.latex,
          indent: clampIndent(w.indent),
          alignGroup: w.align_group ?? undefined,
        },
      ];
    }

    case "write_step": {
      const w = instr as WriteStepInstruction;
      return [
        {
          kind: "step",
          id: entryId(w),
          text: w.text,
          number: w.number ?? undefined,
          indent: clampIndent(w.indent),
        },
      ];
    }

    case "write_text": {
      const w = instr as WriteTextInstruction;
      const kind = w.style === "key_point" ? "key_point" : "text";
      return [
        {
          kind,
          id: entryId(w),
          text: w.text,
          indent: clampIndent(w.indent),
        },
      ];
    }

    case "write_section": {
      const w = instr as WriteSectionInstruction;
      return [
        {
          kind: "section_header",
          id: entryId(w),
          title: w.title,
        },
      ];
    }

    case "write_answer": {
      const w = instr as WriteAnswerInstruction;
      return [
        {
          kind: "answer",
          id: entryId(w),
          latex: w.latex ?? undefined,
          text: w.text ?? undefined,
          boxed: true,
        },
      ];
    }

    // Strikethrough and new_page are control instructions — not entries
    // themselves. Handled as passes in `buildNotebookState`.
    case "strikethrough":
    case "new_page":
      return [];

    default:
      return [];
  }
}

function buildSlideState(
  slideInstrs: VisualInstruction[],
  pending: PendingSlide | undefined,
): SlideState {
  // Locate the latest diagram. Annotations land *after* it in the stream and
  // are anchored to it; a fresh diagram resets the annotation list so stale
  // overlays never outlive their target. `slide_pending` is a loader signal —
  // it neither qualifies as a diagram nor anchors annotations.
  let latestDiagramIdx = -1;
  for (let i = slideInstrs.length - 1; i >= 0; i--) {
    if (DIAGRAM_TYPES.has(slideInstrs[i].type)) {
      latestDiagramIdx = i;
      break;
    }
  }

  if (latestDiagramIdx === -1) {
    if (pending) {
      return {
        status: "loading",
        pendingTitle: pending.title,
        annotations: [],
      };
    }
    return { status: "empty", annotations: [] };
  }

  const latestDiagram = slideInstrs[latestDiagramIdx];
  const annotations = slideInstrs
    .slice(latestDiagramIdx + 1)
    .filter(isAnnotation);

  return {
    status: "ready",
    liveInstruction: latestDiagram,
    annotations,
  };
}

interface PageBucket {
  pageNum: number;
  entries: NotebookEntry[];
  carryFromIds: readonly string[];
}

function buildNotebookState(
  notebookInstrs: VisualInstruction[],
): NotebookState {
  // Walk instructions in order, segmenting into pages. `new_page` pushes a
  // fresh bucket (optionally carrying ids forward from the previous page);
  // `strikethrough` accumulates into a global set applied across all pages
  // before carry synthesis, so carried reminders mirror the original's
  // live struck state. Only the latest page renders; previous pages are
  // retained in memory so carries can look back.
  const pages: PageBucket[] = [{ pageNum: 1, entries: [], carryFromIds: [] }];
  const struckIds = new Set<string>();

  for (const instr of notebookInstrs) {
    if (instr.type === "new_page") {
      const ids = instr.carry_forward_ids ? [...instr.carry_forward_ids] : [];
      pages.push({
        pageNum: pages.length + 1,
        entries: [],
        carryFromIds: ids,
      });
      continue;
    }
    if (instr.type === "strikethrough") {
      const s = instr as StrikethroughInstruction;
      struckIds.add(s.target_id);
      continue;
    }
    const current = pages[pages.length - 1];
    current.entries.push(...instructionToNotebookEntries(instr));
  }

  // Apply strike globally before carry synthesis — carried copies are built
  // from the previous page's resolved (post-strike) entries.
  if (struckIds.size) {
    for (const p of pages) {
      p.entries = p.entries.map((e) =>
        struckIds.has(e.id)
          ? ({ ...(e as NotebookEntryBase), struck: true } as NotebookEntry)
          : e,
      );
    }
  }

  // Synthesize carried reminder copies at the top of each page that asked
  // for them. Derived id `${original.id}__carried__p${pageNum}` guarantees
  // no collision with targets of future strikethroughs (those only match
  // the original).
  for (let i = 1; i < pages.length; i++) {
    const page = pages[i];
    if (!page.carryFromIds.length) continue;
    const prev = pages[i - 1];
    const carried: NotebookEntry[] = [];
    for (const id of page.carryFromIds) {
      const src = prev.entries.find((e) => e.id === id);
      if (!src) continue;
      carried.push({
        ...(src as NotebookEntryBase),
        id: `${src.id}__carried__p${page.pageNum}`,
        carriedForward: true,
      } as NotebookEntry);
    }
    if (carried.length) {
      page.entries = [...carried, ...page.entries];
    }
  }

  const current = pages[pages.length - 1];
  return {
    page: { pageNum: current.pageNum, entries: current.entries },
  };
}

export function useSplitBoardState(
  instructions: readonly VisualInstruction[],
  pending?: PendingSlide,
): { slide: SlideState; notebook: NotebookState } {
  return useMemo(() => {
    const slideInstrs: VisualInstruction[] = [];
    const notebookInstrs: VisualInstruction[] = [];

    for (const instr of instructions) {
      const panel = inferPanel(instr);
      if (panel === "slide") slideInstrs.push(instr);
      else if (panel === "notebook") notebookInstrs.push(instr);
      else if (import.meta.env.DEV) {
        console.debug(
          "[split-board] reference instruction not yet rendered in split mode",
          instr.type,
          instr.element_id,
        );
      }
    }

    return {
      slide: buildSlideState(slideInstrs, pending),
      notebook: buildNotebookState(notebookInstrs),
    };
  }, [instructions, pending]);
}
