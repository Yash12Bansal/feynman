import type { ShowGraphInstruction, VisualInstruction } from "../../../types/visuals";

export type PanelMode = "split" | "slide_full" | "notebook_full";

export type SlideStatus = "empty" | "loading" | "ready";

export interface SlideSketch {
  readonly viewBox: string;
  readonly paths: readonly {
    readonly d: string;
    readonly stroke?: string;
    readonly strokeWidth?: number;
    readonly fill?: string;
    readonly label?: string;
    readonly labelX?: number;
    readonly labelY?: number;
  }[];
}

export interface SlideSpec {
  readonly id: string;
  readonly title: string;
  readonly subtitle?: string;
  readonly sketch: SlideSketch;
}

export interface SlideState {
  readonly status: SlideStatus;
  readonly active?: SlideSpec;
  readonly pendingTitle?: string;
  /**
   * Live mode: a real backend visual instruction routed to the slide. When
   * present (and status === "ready"), SlidePanel renders this via the shared
   * InstructionSwitch instead of `active.sketch`. Used in production; the
   * prototype path keeps using `active`.
   */
  readonly liveInstruction?: VisualInstruction;
}

export type NotebookEntryKind =
  | "section_header"
  | "equation"
  | "step"
  | "text"
  | "key_point"
  | "answer"
  | "graph";

export interface NotebookEntryBase {
  readonly id: string;
  readonly kind: NotebookEntryKind;
  readonly indent?: 0 | 1 | 2 | 3;
  readonly struck?: boolean;
  readonly boxed?: boolean;
  readonly alignGroup?: string;
  /**
   * True when this entry is a muted reminder copy carried onto a new page
   * via `new_page(carry_forward_ids=[...])`. Carried copies are inert:
   * strikethrough won't target them directly (their id is suffixed
   * `__carried__pN`) but their visual state mirrors the original's.
   */
  readonly carriedForward?: boolean;
}

export interface EquationEntry extends NotebookEntryBase {
  readonly kind: "equation";
  readonly latex: string;
}

export interface StepEntry extends NotebookEntryBase {
  readonly kind: "step";
  readonly text: string;
  readonly number?: number;
}

export interface TextEntry extends NotebookEntryBase {
  readonly kind: "text";
  readonly text: string;
}

export interface KeyPointEntry extends NotebookEntryBase {
  readonly kind: "key_point";
  readonly text: string;
}

export interface SectionEntry extends NotebookEntryBase {
  readonly kind: "section_header";
  readonly title: string;
}

export interface AnswerEntry extends NotebookEntryBase {
  readonly kind: "answer";
  readonly latex?: string;
  readonly text?: string;
}

/**
 * A graph rendered inside a notebook entry. Wraps the original
 * ShowGraphInstruction so the existing RoughGraphContent renderer can be
 * reused without re-implementation. May be revisited after Phase 3 dogfood
 * — graphs in a narrow notebook column may need to move back to the slide.
 */
export interface GraphEntry extends NotebookEntryBase {
  readonly kind: "graph";
  readonly instr: ShowGraphInstruction;
}

export type NotebookEntry =
  | EquationEntry
  | StepEntry
  | TextEntry
  | KeyPointEntry
  | SectionEntry
  | AnswerEntry
  | GraphEntry;

export interface NotebookPage {
  readonly pageNum: number;
  readonly entries: readonly NotebookEntry[];
}

export interface NotebookState {
  readonly page: NotebookPage;
  readonly turning?: boolean;
}
