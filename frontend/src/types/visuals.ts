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

/**
 * Split-board panel assignment. Stamped by the backend based on instruction
 * type; the LLM never sets this. Consumed by the SplitBoard renderer.
 */
export type Panel = "slide" | "notebook" | "reference";

/**
 * Functional position of a diagram element in its layout. Mirrors the
 * `ElementPosition` Literal in `design_agent/backend/schema.py`.
 */
export type ElementPosition =
  | "top"
  | "bottom"
  | "left"
  | "right"
  | "top-left"
  | "top-right"
  | "bottom-left"
  | "bottom-right"
  | "center"
  | "diagonal";

/**
 * Bounding box `[x, y, width, height]` in SVG viewBox coordinates. Annotations
 * compute their position from this; the overlay layer shares the diagram's
 * viewBox so coords map directly without DOM measurement.
 */
export type ElementBounds = readonly [number, number, number, number];

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

export interface HighlightWalkStep {
  sub_element_id: string;
  trigger_words: string[];
  style?: HighlightStyle;
  color?: string;
}

// ── Instruction types ─────────────────────────────────────────

interface BaseInstruction {
  element_id?: string;
  duration_ms?: number;
  sync_mode?: SyncMode;
  term_hints?: TermSyncHint[];
  zone?: BoardZone;
  board_id?: string;
  /** Exact X position from Board Cortex solver (overrides zone placement). */
  position_x?: number;
  /** Exact Y position from Board Cortex solver (overrides zone placement). */
  position_y?: number;
  /** Split-board panel assignment, stamped by backend based on instruction type. */
  panel?: Panel;
  /** Client-stamped tile X coordinate (set by board store, not from backend). */
  _tileX?: number;
  /** Client-stamped tile Y coordinate (set by board store, not from backend). */
  _tileY?: number;
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
  /** SVG sub-element IDs within the target card (for design diagram parts). */
  sub_element_ids?: string[];
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

export interface HighlightWalkInstruction extends BaseInstruction {
  type: "highlight_walk";
  target_id: string;
  steps: HighlightWalkStep[];
}

export interface ScrollViewInstruction extends BaseInstruction {
  type: "scroll_view";
  target_x: number;
  target_y: number;
}

export interface SceneTemplateRef {
  template_id: string;
  params?: Record<string, string | number | boolean>;
  component_ids?: string[];
}

/** A semantic element in a layout spec — describes WHAT, not WHERE. */
export interface SemanticSceneElement {
  id: string;
  kind: string;
  label?: string;
  from?: string;
  to?: string;
  direction?: string;
  angle?: number;
  magnitude?: number;
  color?: string;
  extras?: Record<string, string | number | boolean>;
}

export interface DrawSceneInstruction extends BaseInstruction {
  type: "draw_scene";
  title?: string;
  description?: string;
  template?: SceneTemplateRef;
  /** Scene type for semantic layout (e.g. "free_body") */
  scene_type?: string;
  /** Semantic elements the layout strategy will position */
  elements?: SemanticSceneElement[];
  progressive?: boolean;
}

// ── Design Diagram types (from design_agent) ─────────────────

/** Coordinate value — number or math expression string referencing parameter names. */
export type DiagramCoord = number | string;

export interface DesignDiagramGraphCurve {
  expression: string;
  color?: string;
  strokeWidth?: number;
}

export interface DesignDiagramSliderParam {
  name: string;
  min: number;
  max: number;
  default: number;
  step?: number;
  label?: string;
}

export interface DesignDiagramSvgLine {
  type: "svg_line";
  id?: string;
  x1?: DiagramCoord;
  y1?: DiagramCoord;
  x2?: DiagramCoord;
  y2?: DiagramCoord;
  stroke?: string;
  strokeWidth?: number;
  strokeDasharray?: string;
}

export interface DesignDiagramSvgRect {
  type: "svg_rect";
  id?: string;
  x?: DiagramCoord;
  y?: DiagramCoord;
  width?: DiagramCoord;
  height?: DiagramCoord;
  fill?: string;
  stroke?: string;
  strokeWidth?: number;
  rx?: DiagramCoord;
}

export interface DesignDiagramSvgCircle {
  type: "svg_circle";
  id?: string;
  cx?: DiagramCoord;
  cy?: DiagramCoord;
  r?: DiagramCoord;
  stroke?: string;
  fill?: string;
  strokeWidth?: number;
  strokeDasharray?: string;
}

export interface DesignDiagramSvgEllipse {
  type: "svg_ellipse";
  id?: string;
  cx?: DiagramCoord;
  cy?: DiagramCoord;
  rx?: DiagramCoord;
  ry?: DiagramCoord;
  stroke?: string;
  fill?: string;
  strokeWidth?: number;
}

export interface DesignDiagramSvgPath {
  type: "svg_path";
  id?: string;
  d?: string;
  stroke?: string;
  strokeWidth?: number;
  fill?: string;
  strokeDasharray?: string;
}

export interface DesignDiagramSvgText {
  type: "svg_text";
  id?: string;
  x?: DiagramCoord;
  y?: DiagramCoord;
  text?: string;
  fontSize?: number;
  fill?: string;
  textAnchor?: string;
  fontWeight?: string;
  fontFamily?: string;
  angle?: number;
  verticalAnchor?: string;
}

export interface DesignDiagramSvgArc {
  type: "svg_arc";
  id?: string;
  cx?: DiagramCoord;
  cy?: DiagramCoord;
  r?: DiagramCoord;
  startAngle?: DiagramCoord;
  endAngle?: DiagramCoord;
  stroke?: string;
  strokeWidth?: number;
  fill?: string;
  strokeDasharray?: string;
}

export interface DesignDiagramSvgGroup {
  type: "svg_group";
  id?: string;
  transform?: string;
  elements?: DesignDiagramElement[];
}

export interface DesignDiagramSvgLatex {
  type: "svg_latex";
  id?: string;
  expression?: string;
  x?: DiagramCoord;
  y?: DiagramCoord;
  fontSize?: number;
  color?: string;
}

export interface DesignDiagramSvgArrow {
  type: "svg_arrow";
  id?: string;
  x1?: DiagramCoord;
  y1?: DiagramCoord;
  x2?: DiagramCoord;
  y2?: DiagramCoord;
  stroke?: string;
  strokeWidth?: number;
  strokeDasharray?: string;
}

/**
 * Labeled panel — a rounded rectangle with an optional title at the top
 * and caption at the bottom, rendered BEFORE its spec-siblings so other
 * primitives can be drawn inside it. Enables the prototype's warm
 * comparison-frame aesthetic (e.g. "Earth's Surface" vs "Space/Moon") on
 * any design_agent diagram at runtime.
 */
export interface DesignDiagramSvgFrame {
  type: "svg_frame";
  id?: string;
  x?: DiagramCoord;
  y?: DiagramCoord;
  width?: DiagramCoord;
  height?: DiagramCoord;
  /** Rendered top-center, Crimson Pro via CSS in split-board mode. */
  title?: string;
  /** Rendered bottom-center, muted. */
  caption?: string;
  /** Panel fill — hex or palette token name (e.g. "sb-panel-earth"). */
  background?: string;
  /** Border + title color — hex or palette token. Defaults to muted ink. */
  accent?: string;
  /** Corner radius. Defaults to 14. */
  rx?: DiagramCoord;
}

export interface DesignDiagramGraph {
  type: "graph";
  id?: string;
  x?: DiagramCoord;
  y?: DiagramCoord;
  width?: DiagramCoord;
  height?: DiagramCoord;
  xDomain?: [number, number];
  yDomain?: [number, number];
  xLabel?: string;
  yLabel?: string;
  backgroundColor?: string;
  borderColor?: string;
  curves?: DesignDiagramGraphCurve[];
  showGrid?: boolean;
}

export type DesignDiagramElement =
  | DesignDiagramSvgLine
  | DesignDiagramSvgRect
  | DesignDiagramSvgCircle
  | DesignDiagramSvgEllipse
  | DesignDiagramSvgPath
  | DesignDiagramSvgText
  | DesignDiagramSvgArc
  | DesignDiagramSvgGroup
  | DesignDiagramSvgLatex
  | DesignDiagramSvgArrow
  | DesignDiagramSvgFrame
  | DesignDiagramGraph;

/**
 * Semantic metadata for a single SVG element in a `DesignDiagramSpec`.
 * Populated by the design_agent so the teaching agent can refer to elements
 * by *role* ("hypotenuse") rather than raw IDs ("side_AB"), and so the
 * annotation overlay can position itself from `bounds` without DOM lookup.
 */
export interface ElementMeta {
  role: string;
  semantic: string;
  position: ElementPosition;
  spatial_relations?: readonly string[];
  bounds?: ElementBounds;
}

/** Full diagram specification from the design agent. */
export interface DesignDiagramSpec {
  title?: string;
  description?: string;
  width?: number;
  height?: number;
  backgroundColor?: string;
  elements?: DesignDiagramElement[];
  parameters?: DesignDiagramSliderParam[];
  /**
   * Semantic dictionary keyed by element_id. Populated by the design_agent
   * at generation time. Empty/missing means a legacy spec — the annotation
   * overlay falls through to a no-op for that target.
   */
  dictionary?: Record<string, ElementMeta>;
}

export interface DrawDesignDiagramInstruction extends BaseInstruction {
  type: "draw_design_diagram";
  title?: string;
  description?: string;
  spec: DesignDiagramSpec;
}

/**
 * Generation in progress — split-board shows DraftingLoader while a slow
 * slide tool (cache-miss draw_design_diagram) completes. Cleared on arrival
 * of any slide-typed instruction for the same board, or on switch_board.
 */
export interface SlidePendingInstruction extends BaseInstruction {
  type: "slide_pending";
  title?: string;
}

// ── Notebook write-tools (split-board Phase 5) ────────────────

export type NotebookTextStyle = "default" | "key_point";

export interface WriteEquationInstruction extends BaseInstruction {
  type: "write_equation";
  latex: string;
  label?: string;
  align_group?: string | null;
  indent?: number;
}

export interface WriteStepInstruction extends BaseInstruction {
  type: "write_step";
  text: string;
  number?: number | null;
  indent?: number;
}

export interface WriteTextInstruction extends BaseInstruction {
  type: "write_text";
  text: string;
  style?: NotebookTextStyle;
  indent?: number;
}

export interface WriteSectionInstruction extends BaseInstruction {
  type: "write_section";
  title: string;
}

export interface WriteAnswerInstruction extends BaseInstruction {
  type: "write_answer";
  latex?: string | null;
  text?: string | null;
}

export interface StrikethroughInstruction extends BaseInstruction {
  type: "strikethrough";
  target_id: string;
}

export interface NewPageInstruction extends BaseInstruction {
  type: "new_page";
  carry_forward_ids?: readonly string[];
}

// ── Slide annotation overlays (diagram awareness) ─────────────

export type PinLabelPosition = "above" | "below" | "left" | "right";

export type CalloutDirection =
  | "up"
  | "down"
  | "up-left"
  | "up-right"
  | "down-left"
  | "down-right";

export type BracketSide = "above" | "below" | "left" | "right";

/**
 * Multi-kind annotation target (Phase 1 diagram-awareness re-architecture).
 *
 * The legacy `target_element_id` string only resolves against pre-baked
 * diagram-dictionary ids/roles. Real teaching needs wider vocabulary:
 * "the red line", "next to '60°'", arbitrary data-attr queries. This
 * structured form lets the frontend pick a resolver against the live DOM.
 *
 * Kinds:
 *  - `id`        — exact `data-design-element="value"` match.
 *  - `role`      — dictionary role lookup → element id → DOM.
 *  - `color`     — `[stroke="value"]` or `[fill="value"]` match.
 *  - `near_text` — `<text>` whose content contains `value` (substring).
 *  - `data_attr` — arbitrary `[data-{attr}="value"]` (escape hatch).
 */
export type AnnotationTargetKind =
  | "id"
  | "role"
  | "color"
  | "near_text"
  | "data_attr";

export interface AnnotationTarget {
  kind: AnnotationTargetKind;
  value: string;
  /** Attribute name for `data_attr` kind only; ignored otherwise. */
  attr?: string | null;
}

export interface PinLabelInstruction extends BaseInstruction {
  type: "pin_label";
  target_element_id: string;
  /** Phase 1: richer multi-kind target. When present, prefer over the
   * legacy `target_element_id` string. */
  target?: AnnotationTarget | null;
  text: string;
  position?: PinLabelPosition;
}

export interface DrawCalloutInstruction extends BaseInstruction {
  type: "draw_callout";
  target_element_id: string;
  target?: AnnotationTarget | null;
  text: string;
  direction?: CalloutDirection;
}

export interface BracketInstruction extends BaseInstruction {
  type: "bracket";
  element_a_id: string;
  element_b_id: string;
  target_a?: AnnotationTarget | null;
  target_b?: AnnotationTarget | null;
  label: string;
  side?: BracketSide;
}

export interface HighlightPulseInstruction extends BaseInstruction {
  type: "highlight_pulse";
  target_element_id: string;
  target?: AnnotationTarget | null;
  /** Pulse duration in ms; backend default 1200, range 400–3000. */
  duration_ms?: number;
  /** CSS variable token for the glow color, e.g. `--sb-neon`. */
  color_token?: string;
}

export type AnnotationInstruction =
  | PinLabelInstruction
  | DrawCalloutInstruction
  | BracketInstruction
  | HighlightPulseInstruction;

// ── Discriminated union ───────────────────────────────────────

export type VisualInstruction =
  | ClearInstruction
  | ShowTextInstruction
  | ShowEquationInstruction
  | StepEquationInstruction
  | DrawDiagramInstruction
  | DrawDesignDiagramInstruction
  | ShowGraphInstruction
  | HighlightInstruction
  | AnnotateInstruction
  | SwitchBoardInstruction
  | DrawSceneInstruction
  | HighlightWalkInstruction
  | ScrollViewInstruction
  | SlidePendingInstruction
  | WriteEquationInstruction
  | WriteStepInstruction
  | WriteTextInstruction
  | WriteSectionInstruction
  | WriteAnswerInstruction
  | StrikethroughInstruction
  | NewPageInstruction
  | PinLabelInstruction
  | DrawCalloutInstruction
  | BracketInstruction
  | HighlightPulseInstruction;

export type VisualType = VisualInstruction["type"];

// ── Frame (for future batching) ───────────────────────────────

export interface VisualFrame {
  sequence: number;
  instructions: VisualInstruction[];
}
