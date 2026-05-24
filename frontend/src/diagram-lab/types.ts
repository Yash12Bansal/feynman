/**
 * Mirrors the testbed backend's response shapes. Hand-maintained for now —
 * the testbed is single-user experimentation, not worth a contracts pipeline.
 */

import type { AnnotationInstruction } from "../types/visuals";

export interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: unknown[];
  default?: unknown;
  description?: string;
  minimum?: number;
  maximum?: number;
  $defs?: Record<string, JsonSchema>;
  allOf?: JsonSchema[];
  anyOf?: JsonSchema[];
}

export interface StrategyAvailability {
  readonly available: boolean;
  readonly reason: string | null;
}

export interface StrategyDescriptor {
  readonly id: string;
  readonly display_name: string;
  readonly description: string;
  readonly category: "json" | "python" | "latex" | "other";
  readonly supports_models: readonly string[];
  readonly default_model: string;
  readonly options_schema: JsonSchema;
  readonly options_defaults: Record<string, unknown>;
  readonly availability: StrategyAvailability;
}

export interface TimingBreakdown {
  readonly total_ms: number;
  readonly first_token_ms: number | null;
  readonly first_element_ms: number | null;
  readonly llm_ms: number | null;
  readonly parse_ms: number | null;
  readonly sandbox_ms: number | null;
  readonly render_ms: number | null;
  readonly extra: Record<string, number>;
}

/**
 * DiagramSpec shape we render. Mirrors backend `DiagramSpec` + the testbed-only
 * `_tikz_svg` / `_tikz_source` escape hatches the TikZ strategy emits.
 */
export interface LabDiagramSpec {
  readonly title?: string;
  readonly description?: string;
  readonly width?: number;
  readonly height?: number;
  readonly backgroundColor?: string;
  readonly elements?: readonly unknown[];
  readonly parameters?: readonly unknown[];
  readonly animations?: readonly unknown[];
  readonly dictionary?: Record<string, unknown>;
  readonly _tikz_svg?: string;
  readonly _tikz_source?: string;
}

export interface StrategyResult {
  readonly spec: LabDiagramSpec;
  readonly raw_output: string;
  readonly prompt_used: string;
  readonly model_used: string;
  readonly timing: TimingBreakdown;
  readonly metadata: Record<string, unknown>;
  readonly warnings: readonly string[];
}

export interface RunResponse {
  readonly run_id: string;
  readonly result: StrategyResult;
}

export interface HistoryEntry {
  readonly run_id: string;
  readonly strategy_id: string;
  readonly model: string;
  readonly prompt: string;
  readonly label: string | null;
  readonly total_ms: number;
  readonly element_count: number;
  readonly success: boolean;
  readonly error: string | null;
}

export interface MathsPrompt {
  readonly id: string;
  readonly label: string;
  readonly prompt: string;
}

export interface MathsGroup {
  readonly topic: string;
  readonly prompts: readonly MathsPrompt[];
}

export interface MathsLibrary {
  readonly version: string;
  readonly description: string;
  readonly groups: readonly MathsGroup[];
}

export interface AnnotationInjectResponse {
  readonly instruction: AnnotationInstruction;
  readonly latency_ms: number;
  readonly raw_output: string;
  readonly chosen_target: { kind: string; value: string } | null;
}
