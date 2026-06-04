import type {
  AnnotationInstruction,
  ShowGraphInstruction,
  VisualInstruction,
} from "../../../types/visuals";

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
  /**
   * LEGACY — Phase 2 annotation overlays, no longer read. Kept on the type
   * for back-compat so old code paths compile.
   */
  readonly annotations?: readonly AnnotationInstruction[];

  // ── Doc 19 §12 live-annotation primitives ─────────────────────────────
  //
  // Each list accumulates as new events arrive. show_diagram + clear_annotations
  // wipe them to empty. nextAnnotationKey is a monotonic counter that
  // hands React-keys to the appended items so re-emit of the same element
  // retriggers its animation cleanly.
  readonly traces?: readonly TraceState[];
  readonly markPoints?: readonly MarkPointState[];
  readonly marginNotes?: readonly MarginNoteState[];
  readonly pointers?: readonly PointerState[];
  readonly nextAnnotationKey?: number;

  // ── FOCUS (glow+lift) ─────────────────────────────────────────────────
  //
  // The element currently spotlighted while the agent talks about it. Applied
  // IN PLACE to the real diagram element (DesignDiagramContent), not via an
  // overlay — so no bounds math, and it glows the actual shape in its own
  // colour. Either id (preferred) or role (resolved against the dictionary).
  // Cleared on unfocus / clear_annotations / show_diagram.
  readonly focusedElementId?: string | null;
  readonly focusedRole?: string | null;
  // Co-highlight: the full set of elements spotlighted simultaneously (a
  // relationship between parts discussed together). Single-focus leaves this
  // empty/undefined and uses focusedElementId; DesignDiagramContent glows the
  // union of both. Cleared alongside focusedElementId.
  readonly focusedElementIds?: ReadonlySet<string> | null;
  // Optional inline label shown next to a focused element (from a focus event's
  // `text`). null/undefined → no label.
  readonly inlineLabelText?: string | null;
  // Presentation mode of the active diagram: "build_up" enables staged reveal
  // (see revealedElementIds); "overview"/undefined renders everything at once.
  readonly presentationMode?: "build_up" | "overview";
  // ── Staged element reveal (Workstream B) ──────────────────────────────
  //
  // Only meaningful when presentationMode === "build_up" AND the diagram opted
  // into staging. `null`/undefined means "show everything" — static parity
  // (INV-7): a spec with no staging renders byte-identically to before.
  //
  //  - revealedElementIds: the element_ids currently drawn. A non-null EMPTY
  //    set means staging is active but nothing is revealed yet (all hidden).
  //  - revealOrder: ordered groups of ids (from deriveRevealPlan / animations)
  //    that `reveal_step` walks through.
  //  - revealCursor: index into revealOrder of the last-revealed group; -1
  //    before the first reveal.
  readonly revealedElementIds?: ReadonlySet<string> | null;
  readonly revealOrder?: readonly (readonly string[])[] | null;
  readonly revealCursor?: number;

  // ── Narration-driven parameters (Workstream A5) ───────────────────────
  //
  // Overrides for the active diagram's interactive parameters, set by
  // `set_parameter` events so narration can drive a slider value without the
  // student touching it. Merged over the spec defaults at render time;
  // show_diagram resets it to {}. Empty/undefined → diagram uses its own
  // defaults (INV-7).
  readonly paramOverrides?: Readonly<Record<string, number>>;
}

/** Doc 19 §12: stroke-draw animation along an element's geometry. */
export interface TraceState {
  readonly key: number;
  readonly elementId: string;
  readonly durationMs: number;
}

/** Doc 19 §12: dot/cross/star marker at a viewBox-space coordinate. */
export interface MarkPointState {
  readonly key: number;
  readonly x: number;
  readonly y: number;
  readonly kind: "dot" | "cross" | "star";
  readonly label: string;
}

/** Doc 19 §12: hand-written-style note anchored to an element's side. */
export interface MarginNoteState {
  readonly key: number;
  readonly anchorElementId: string;
  readonly side: "top" | "bottom" | "left" | "right";
  readonly text: string;
}

/** Doc 19 §12: an arrow pointing at an element from one side ("look here"). */
export interface PointerState {
  readonly key: number;
  readonly elementId: string;
  readonly fromSide: "top" | "bottom" | "left" | "right";
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
