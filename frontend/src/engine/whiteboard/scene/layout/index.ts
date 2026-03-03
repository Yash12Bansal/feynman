/**
 * Layout engine — public API.
 *
 * Re-exports the resolver + types for consumers.
 */

export { resolveLayout } from "./engine";
export type {
  LayoutStrategy,
  ForceDirection,
  SemanticSceneElement,
} from "./types";
export { DIRECTION_ANGLES } from "./types";
