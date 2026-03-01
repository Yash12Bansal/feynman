/**
 * Visual instruction types — mirrors backend protocol.
 *
 * Keep in sync with:
 * - backend: feynman.visuals.schemas
 * - contract: contracts/visuals.schema.json
 *
 * Wire format is flattened — type tag + fields at the same level,
 * no nested `payload` object.
 */

// ── Shared enums ──────────────────────────────────────────────

export type TextStyle = "default" | "definition" | "key_point" | "example";

export type EquationAnimation =
  | "none"
  | "fade_in"
  | "term_by_term"
  | "write_on";

export type DiagramType =
  | "flowchart"
  | "concept_map"
  | "force_diagram"
  | "tree"
  | "cycle"
  | "comparison"
  | "free_form";

export type NodeShape =
  | "rectangle"
  | "rounded"
  | "circle"
  | "diamond"
  | "ellipse";

export type EdgeStyle = "solid" | "dashed" | "dotted";

export type GraphType = "line" | "bar" | "scatter" | "function";

export type HighlightStyle = "glow" | "underline" | "box" | "pulse";

export type AnnotationAction = "circle" | "underline" | "arrow";

export type SyncMode = "immediate" | "on_playout" | "term_sync";

export type BoardIntent = "new" | "revisit" | "reference";

export type BoardZone =
  | "top-left"
  | "top-center"
  | "top-right"
  | "center-left"
  | "center-center"
  | "center-right"
  | "bottom-left"
  | "bottom-center"
  | "bottom-right";

// ── Sub-models ────────────────────────────────────────────────

export interface TermSyncHint {
  term_id: string;
  trigger_words: string[];
}

export interface DiagramNode {
  id: string;
  label: string;
  shape?: NodeShape;
  color?: string;
}

export interface DiagramEdge {
  from_id: string;
  to_id: string;
  label?: string;
  style?: EdgeStyle;
  directed?: boolean;
}

export interface DataPoint {
  x: number;
  y: number;
  label?: string;
}

export interface DataSeries {
  label?: string;
  points: DataPoint[];
  color?: string;
}

export interface FunctionDef {
  expression: string;
  label?: string;
  color?: string;
  domain_min?: number;
  domain_max?: number;
}

export interface AxisConfig {
  label?: string;
  min?: number;
  max?: number;
}

export interface EquationStep {
  latex: string;
  annotation?: string;
  highlight_terms?: string[];
}

// ── Instruction types ─────────────────────────────────────────

interface BaseInstruction {
  element_id?: string;
  duration_ms?: number;
  sync_mode?: SyncMode;
  term_hints?: TermSyncHint[];
  zone?: BoardZone;
  board_id?: string;
}

export interface ClearInstruction extends BaseInstruction {
  type: "clear";
  target_id?: string;
}

export interface ShowTextInstruction extends BaseInstruction {
  type: "show_text";
  text: string;
  title?: string;
  style?: TextStyle;
}

export interface ShowEquationInstruction extends BaseInstruction {
  type: "show_equation";
  latex: string;
  label?: string;
  animation?: EquationAnimation;
}

export interface DrawDiagramInstruction extends BaseInstruction {
  type: "draw_diagram";
  diagram_type?: DiagramType;
  title?: string;
  description?: string;
  nodes?: DiagramNode[];
  edges?: DiagramEdge[];
  progressive?: boolean;
}

export interface ShowGraphInstruction extends BaseInstruction {
  type: "show_graph";
  graph_type: GraphType;
  title?: string;
  x_axis?: AxisConfig;
  y_axis?: AxisConfig;
  series?: DataSeries[];
  functions?: FunctionDef[];
  animated?: boolean;
}

export interface StepEquationInstruction extends BaseInstruction {
  type: "step_equation";
  title?: string;
  steps: EquationStep[];
}

export interface HighlightInstruction extends BaseInstruction {
  type: "highlight";
  target_id: string;
  style?: HighlightStyle;
  color?: string;
}

export interface AnnotateInstruction extends BaseInstruction {
  type: "annotate";
  action: AnnotationAction;
  target_id?: string;
  from_id?: string;
  to_id?: string;
  color?: string;
}

export interface SwitchBoardInstruction extends BaseInstruction {
  type: "switch_board";
  label?: string;
  intent?: BoardIntent;
}

// ── Discriminated union ───────────────────────────────────────

export type VisualInstruction =
  | ClearInstruction
  | ShowTextInstruction
  | ShowEquationInstruction
  | StepEquationInstruction
  | DrawDiagramInstruction
  | ShowGraphInstruction
  | HighlightInstruction
  | AnnotateInstruction
  | SwitchBoardInstruction;

export type VisualType = VisualInstruction["type"];

// ── Frame (for future batching) ───────────────────────────────

export interface VisualFrame {
  sequence: number;
  instructions: VisualInstruction[];
}
