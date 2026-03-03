/**
 * Layout engine types — semantic elements + strategy interface.
 *
 * ForceDirection is a layout domain concept (mapping semantic direction
 * strings to angles). SemanticSceneElement is re-exported from the wire
 * format types for convenience.
 */

import type { SemanticSceneElement } from "../../../../types/visuals";
import type { SceneGeometry } from "../scene-types";
import type { LayoutContext } from "../components/types";

export type { SemanticSceneElement, SceneGeometry, LayoutContext };

export type ForceDirection =
  | "up"
  | "down"
  | "left"
  | "right"
  | "up-left"
  | "up-right"
  | "down-left"
  | "down-right";

/**
 * Direction string → angle (degrees, 0 = right, clockwise).
 * Used by layout strategies to convert semantic directions to vector angles.
 */
export const DIRECTION_ANGLES: Record<ForceDirection, number> = {
  right: 0,
  "down-right": 45,
  down: 90,
  "down-left": 135,
  left: 180,
  "up-left": 225,
  up: 270,
  "up-right": 315,
};

/**
 * A layout strategy takes semantic elements and a context,
 * and produces SceneGeometry the renderer can draw.
 */
export type LayoutStrategy = (
  elements: SemanticSceneElement[],
  context: LayoutContext,
) => SceneGeometry;
