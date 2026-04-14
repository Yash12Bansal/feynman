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
}

export type NotebookEntryKind =
  | "section_header"
  | "equation"
  | "step"
  | "text"
  | "key_point"
  | "answer";

export interface NotebookEntryBase {
  readonly id: string;
  readonly kind: NotebookEntryKind;
  readonly indent?: 0 | 1 | 2 | 3;
  readonly struck?: boolean;
  readonly boxed?: boolean;
  readonly alignGroup?: string;
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

export type NotebookEntry =
  | EquationEntry
  | StepEntry
  | TextEntry
  | KeyPointEntry
  | SectionEntry
  | AnswerEntry;

export interface NotebookPage {
  readonly pageNum: number;
  readonly entries: readonly NotebookEntry[];
}

export interface NotebookState {
  readonly page: NotebookPage;
  readonly turning?: boolean;
}
