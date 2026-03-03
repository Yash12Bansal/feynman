/**
 * Component system types for the scene diagram engine.
 *
 * LayoutContext provides scene dimensions + colors to components.
 * ComponentDef defines the contract every registered component must satisfy.
 */

import type { Options as RoughOptions } from "roughjs/bin/core";
import type { SceneGeometry } from "../scene-types";
import { COLORS } from "../../../theme";

/** Contextual information available to components during rendering. */
export interface LayoutContext {
  sceneWidth: number;
  sceneHeight: number;
  colors: typeof COLORS;
}

/** Create a default layout context (500x400, standard colors). */
export function defaultLayoutContext(): LayoutContext {
  return {
    sceneWidth: 500,
    sceneHeight: 400,
    colors: COLORS,
  };
}

/**
 * Definition of a registered diagram component.
 *
 * Pure function pattern: `render(params) => SceneGeometry`.
 * The `anchorNames` field is declarative — for documentation and validation,
 * not for anchor resolution. Actual anchors come from `render()` output.
 */
export interface ComponentDef<P = Record<string, unknown>> {
  /** Unique component kind identifier (e.g. "force-arrow", "box") */
  kind: string;
  /** Pure render function: params → geometry */
  render: (params: P) => SceneGeometry;
  /** Declared anchor point names this component provides (documentation/validation) */
  anchorNames: readonly string[];
  /** Default rough options style for this component type */
  defaultStyle?: Partial<RoughOptions>;
}
