/**
 * Visual instruction types — mirrors backend protocol.
 *
 * Keep in sync with:
 * - backend: feynman.visuals.instructions
 * - contract: contracts/visuals.schema.json
 */

export type VisualType =
  | "clear"
  | "draw_diagram"
  | "show_equation"
  | "show_text"
  | "show_graph"
  | "animate"
  | "highlight";

export interface VisualInstruction {
  type: VisualType;
  payload?: Record<string, unknown>;
  duration_ms?: number;
}

export interface VisualFrame {
  sequence: number;
  instructions: VisualInstruction[];
}
